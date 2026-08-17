"""评估 SAC-on-PushT checkpoint：加载策略 + pre/post processors，在 gym-pusht 跑 N 局。

与 lerobot 官方 eval 不同，这里直接驱动单个 gym 环境（无向量包装），并用
checkpoint 自带的 preprocessor/postprocessor（normalizer/unnormalizer）。

用法:
  python eval_sac_pusht.py --checkpoint outputs/train/sac_pusht_smoke/checkpoints/last \
      --n-episodes 3 --outdir outputs/eval/sac_pusht_gui \
      [--stream-dir outputs/stream/<ts>] [--seed 0] [--max-steps 300]
"""
import argparse
import json
import os
import time

import cv2
import numpy as np

from lerobot.configs import parser  # noqa: F401  (注册 config 工厂，供 from_pretrained 使用)
from lerobot.envs import make_env_config
from lerobot.policies import make_policy, make_pre_post_processors
from lerobot.processor import DataProcessorPipeline, TransitionKey, VanillaObservationProcessorStep, create_transition, identity_transition

STEP_EVERY = 3  # 每 N 步写一帧到 stream 目录


def _stream_write(stream_dir, step, frame, info):
    os.makedirs(stream_dir, exist_ok=True)
    if frame is not None:
        h, w = frame.shape[:2]
        small = cv2.resize(frame, (256, int(256 * h / w))) if w > 256 else frame
        cv2.imwrite(os.path.join(stream_dir, f"frame_{step:05d}.png"), cv2.cvtColor(small, cv2.COLOR_RGB2BGR))
    line = {"step": step, "reward": float(info.get("reward", 0.0)),
            "coverage": float(info.get("coverage", 0.0)),
            "success": bool(info.get("is_success", False))}
    with open(os.path.join(stream_dir, "info.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def load_policy(checkpoint_dir: str):
    """从 RL checkpoint 的 pretrained_model/ 目录加载 gaussian_actor 策略 + processors。"""
    pm = os.path.join(checkpoint_dir, "pretrained_model")
    if not os.path.isdir(pm):
        pm = checkpoint_dir
    from lerobot.configs.policies import PreTrainedConfig

    pc = PreTrainedConfig.from_pretrained(pm)
    pc.pretrained_path = pm
    # 用与训练一致的 pusht env 配置提供特征形状（obs 96x96，pixels_agent_pos）
    env_cfg = make_env_config(
        "pusht", task="PushT-v0", fps=10, episode_length=300, obs_type="pixels_agent_pos",
        render_mode="rgb_array", observation_height=96, observation_width=96,
        visualization_width=384, visualization_height=384,
    )
    policy = make_policy(cfg=pc, env_cfg=env_cfg)
    policy.eval()
    pre, post = make_pre_post_processors(policy_cfg=pc, dataset_stats=pc.dataset_stats)
    return policy, pre, post, env_cfg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True, help="checkpoints/<step> 或 checkpoints/last 目录")
    ap.add_argument("--n-episodes", type=int, default=3)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--max-steps", type=int, default=300)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--stream-dir", default=None)
    args = ap.parse_args()

    policy, pre, post, env_cfg = load_policy(args.checkpoint)
    print(f"policy loaded from {args.checkpoint} | input: {list(policy.config.input_features)} "
          f"| output: {list(policy.config.output_features)}")
    os.makedirs(args.outdir, exist_ok=True)

    import gymnasium as gym  # noqa: PLC0415
    import gym_pusht  # noqa: F401, PLC0415

    env = gym.make(env_cfg.gym_id, disable_env_checker=True, **env_cfg.gym_kwargs)
    env_processor = DataProcessorPipeline(
        steps=[VanillaObservationProcessorStep()],
        to_transition=identity_transition, to_output=identity_transition,
    )

    results = []
    t0 = time.time()
    for ep in range(args.n_episodes):
        obs, info = env.reset(seed=args.seed + ep)
        tr = env_processor(create_transition(observation=obs, info=info))
        frames, rewards, done, step = [], [], False, 0
        ep_reward = 0.0
        max_coverage = 0.0
        while not done and step < args.max_steps:
            obs_dict = {k: v for k, v in tr[TransitionKey.OBSERVATION].items()}
            with __import__("torch").inference_mode():
                norm_act = policy.select_action(pre(obs_dict))
            act = post(norm_act).detach().cpu().numpy().astype(np.float32)
            act = act.reshape(-1)  # (1,2) -> (2,)
            obs, rew, term, trunc, info = env.step(act)
            done = bool(term or trunc)
            ep_reward += float(rew)
            max_coverage = max(max_coverage, float(info.get("coverage", 0.0)))
            tr = env_processor(create_transition(
                observation=obs, action=act, reward=rew, done=term, truncated=trunc, info=info))
            if step % STEP_EVERY == 0 or done or step == 0:
                try:
                    frame = env.render()
                except Exception:
                    frame = obs.get("pixels", None)
                if frame is not None:
                    frames.append(frame)
                if args.stream_dir:
                    _stream_write(args.stream_dir, step, frame, info)
            step += 1
        success = bool(info.get("is_success", False))
        results.append({"episode": ep, "steps": step, "reward": round(ep_reward, 4),
                        "max_coverage": round(max_coverage, 4), "success": success})
        if frames:
            path = os.path.join(args.outdir, f"episode_{ep:02d}.mp4")
            h, w = frames[0].shape[:2]
            writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 10, (w, h))
            for f in frames:
                writer.write(cv2.cvtColor(f, cv2.COLOR_RGB2BGR))
            writer.release()
            try:
                import imageio.v2 as iio
                iio.mimsave(os.path.splitext(path)[0] + ".gif", frames, fps=10)
            except Exception as e:  # noqa: BLE001
                print("gif save skipped:", e)
        print(f"ep {ep}: steps={step} reward={ep_reward:.3f} max_coverage={max_coverage:.3f} success={success}")
        if args.stream_dir:
            _stream_write(args.stream_dir, step, None, info)

    env.close()
    metrics = {
        "checkpoint": args.checkpoint,
        "n_episodes": args.n_episodes,
        "avg_reward": round(float(np.mean([r["reward"] for r in results])), 4),
        "success_rate": round(float(np.mean([r["success"] for r in results])), 4),
        "avg_max_coverage": round(float(np.mean([r["max_coverage"] for r in results])), 4),
        "episodes": results,
    }
    with open(os.path.join(args.outdir, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    print(f"metrics -> {os.path.join(args.outdir, 'metrics.json')} | 耗时 {time.time() - t0:.1f}s")

    if args.stream_dir:
        os.makedirs(args.stream_dir, exist_ok=True)
        open(os.path.join(args.stream_dir, "DONE"), "w").close()
        print(f"stream done -> {args.stream_dir}")


if __name__ == "__main__":
    main()

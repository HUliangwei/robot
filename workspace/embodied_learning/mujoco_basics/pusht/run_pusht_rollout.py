"""Closed-loop PushT rollout with a pretrained LeRobot ACT policy.

Runs the SAME policy + pre/post processors either in:
  --env official : gym_pusht/PushT-v0 (pymunk 2D, the training-data environment)
  --env mujoco   : our MuJoCo re-implementation (mujoco_pusht_env.py)

The observation conversion mirrors lerobot.envs.utils.preprocess_observation:
  pixels (H,W,3) uint8 -> (1,3,H,W) float32 /255  -> observation.image
  agent_pos (2,)        -> (1,2) float32           -> observation.state
then policy.preprocessor (MEAN_STD) -> policy.select_action -> policy.postprocessor.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import cv2
import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# HF cache: reuse the project's hub directory (same as the pusht dataset cache)
os.environ.setdefault("HF_HOME", r"D:\Desktop\robot\datasets")
os.environ.setdefault("HF_HUB_CACHE", r"D:\Desktop\robot\datasets\hub")

from lerobot.processor import PolicyProcessorPipeline

MODEL_ID = "aadarshram/act_pusht"


def _policy_class_for(policy_path: str):
    """Pick the policy class from the checkpoint config (act / diffusion / ...)."""
    import json

    from huggingface_hub import hf_hub_download

    if os.path.isdir(policy_path):
        cfg_path = os.path.join(policy_path, "config.json")
    else:
        cfg_path = hf_hub_download(policy_path, "config.json")
    with open(cfg_path, encoding="utf-8") as f:
        ptype = json.load(f)["type"]
    if ptype == "act":
        from lerobot.policies.act.modeling_act import ACTPolicy

        return ACTPolicy
    if ptype == "diffusion":
        from lerobot.policies.diffusion.modeling_diffusion import DiffusionPolicy

        return DiffusionPolicy
    raise ValueError(f"unsupported policy type: {ptype}")


def make_policy(policy_path: str = MODEL_ID, temporal_ensemble: bool = False):
    policy_cls = _policy_class_for(policy_path)
    policy = policy_cls.from_pretrained(policy_path)
    policy.eval()
    policy.to("cuda" if torch.cuda.is_available() else "cpu")
    if temporal_ensemble and policy_cls.__name__ == "ACTPolicy":
        from lerobot.policies.act.modeling_act import ACTTemporalEnsembler

        policy.config.temporal_ensemble_coeff = 0.01
        policy.temporal_ensembler = ACTTemporalEnsembler(0.01, policy.config.chunk_size)
        print("temporal ensembling ENABLED (coeff=0.01)")
    preprocessor = PolicyProcessorPipeline.from_pretrained(
        policy_path, config_filename="policy_preprocessor.json"
    )
    postprocessor = PolicyProcessorPipeline.from_pretrained(
        policy_path, config_filename="policy_postprocessor.json"
    )
    return policy, preprocessor, postprocessor


def obs_to_batch(obs: dict) -> dict:
    """Convert an env observation dict to the LeRobot batch format."""
    pixels = obs["pixels"]  # (H, W, 3) uint8
    agent_pos = obs["agent_pos"]  # (2,)
    img = torch.from_numpy(pixels).permute(2, 0, 1).float() / 255.0  # (3,H,W) in [0,1]
    return {
        "observation.image": img.unsqueeze(0),
        "observation.state": torch.from_numpy(agent_pos).float().unsqueeze(0),
    }


def make_env(env_type: str, seed: int):
    if env_type == "official":
        import gymnasium as gym
        import gym_pusht  # noqa: F401

        env = gym.make(
            "gym_pusht/PushT-v0",
            obs_type="pixels_agent_pos",
            render_mode="rgb_array",
            visualization_width=680,
            visualization_height=680,
            max_episode_steps=300,
        )
        return env, env.reset(seed=seed)[0]
    elif env_type == "mujoco":
        from mujoco_pusht_env import MujocoPushtEnv

        env = MujocoPushtEnv()
        obs, _ = env.reset(seed=seed)
        return env, obs
    else:
        raise ValueError(env_type)


def run_episode(env, obs, policy, preprocessor, postprocessor, max_steps=300, video_fps=10):
    frames = []
    rewards = []
    coverages = []
    done = False
    step = 0
    total_reward = 0.0
    policy.reset()  # reset action queue / temporal ensembler state per episode
    while not done and step < max_steps:
        batch = obs_to_batch(obs)
        batch = preprocessor(batch)
        with torch.inference_mode():
            action_norm = policy.select_action(batch)
        action = postprocessor({"action": action_norm})["action"]
        action = action.squeeze(0).detach().cpu().numpy().astype(np.float32)
        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += float(reward)
        rewards.append(float(reward))
        coverages.append(float(info.get("coverage", 0.0)))
        done = bool(terminated or truncated)
        step += 1
        if step % 3 == 0 or done or step == 1:
            frames.append(env.render())
    success = bool(coverages and coverages[-1] > 0.95)
    return {
        "steps": step,
        "success": success,
        "sum_reward": round(total_reward, 4),
        "max_coverage": round(max(coverages, default=0.0), 4),
        "final_coverage": round(coverages[-1], 4) if coverages else 0.0,
        "frames": frames,
        "rewards": rewards,
        "coverages": coverages,
    }


def save_video(frames, path, fps=10):
    if not frames:
        return
    h, w = frames[0].shape[:2]
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for f in frames:
        writer.write(cv2.cvtColor(f, cv2.COLOR_RGB2BGR))
    writer.release()
    # also a gif (fallback if mp4 has issues)
    try:
        import imageio.v2 as iio

        gif_path = os.path.splitext(path)[0] + ".gif"
        iio.mimsave(gif_path, frames, fps=fps)
    except Exception as e:
        print("gif save skipped:", e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", choices=["official", "mujoco"], required=True)
    ap.add_argument("--n_episodes", type=int, default=5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--max_steps", type=int, default=300)
    ap.add_argument("--policy-path", default=MODEL_ID)
    ap.add_argument("--temporal-ensemble", action="store_true")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    policy, preprocessor, postprocessor = make_policy(args.policy_path, temporal_ensemble=args.temporal_ensemble)
    print(f"policy loaded: {args.policy_path}")

    results = []
    t0 = time.time()
    for ep in range(args.n_episodes):
        env, obs = make_env(args.env, seed=args.seed + ep)
        res = run_episode(env, obs, policy, preprocessor, postprocessor, max_steps=args.max_steps)
        res["episode"] = ep
        results.append({k: v for k, v in res.items() if k != "frames"})
        vid_path = os.path.join(args.outdir, f"episode_{ep:02d}.mp4")
        save_video(res["frames"], vid_path)
        print(
            f"ep {ep}: steps={res['steps']} success={res['success']} "
            f"sum_reward={res['sum_reward']} max_cov={res['max_coverage']} "
            f"-> {vid_path}"
        )
        env.close()

    summary = {
        "env": args.env,
        "model": args.policy_path,
        "n_episodes": args.n_episodes,
        "seed": args.seed,
        "success_rate": round(sum(r["success"] for r in results) / len(results), 4),
        "mean_sum_reward": round(float(np.mean([r["sum_reward"] for r in results])), 4),
        "mean_max_coverage": round(float(np.mean([r["max_coverage"] for r in results])), 4),
        "elapsed_s": round(time.time() - t0, 1),
        "episodes": results,
    }
    with open(os.path.join(args.outdir, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

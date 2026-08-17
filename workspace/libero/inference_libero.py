"""LIBERO 闭环推理脚本（学习用）：同一策略在 LIBERO-Spatial 环境上推理并保存视频/指标。

与 PushT 的 run_pusht_rollout.py 同构：obs → preprocessor → policy.select_action → postprocessor → env.step。
支持 ACT（图像+状态）与 SmolVLA（额外带语言指令）。

用法:
  python inference_libero.py --policy-path ishandotsh/act_libero_spatial_test \
      --task libero_spatial --task-id 0 --n-episodes 3 --outdir outputs/rollout_libero_act
  python inference_libero.py --policy-path HuggingFaceVLA/smolvla_libero \
      --task libero_spatial --task-id 0 --n-episodes 3 --outdir outputs/rollout_libero_smolvla
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

os.environ.setdefault("HF_HOME", r"D:\Desktop\robot\datasets")
os.environ.setdefault("HF_HUB_CACHE", r"D:\Desktop\robot\datasets\hub")
os.environ.setdefault("LIBERO_CONFIG_PATH", os.path.expanduser("~/.libero"))

from lerobot.processor import PolicyProcessorPipeline  # noqa: E402


def load_policy(policy_path: str):
    cfg = json.load(open(os.path.join(policy_path, "config.json"), encoding="utf-8")) if os.path.isdir(policy_path) else None
    if cfg is None:
        from huggingface_hub import hf_hub_download  # noqa: PLC0415

        cfg = json.load(open(hf_hub_download(policy_path, "config.json"), encoding="utf-8"))
    ptype = cfg.get("type")
    if ptype == "act":
        from lerobot.policies.act.modeling_act import ACTPolicy  # noqa: PLC0415

        cls = ACTPolicy
    elif ptype == "smolvla":
        from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy  # noqa: PLC0415

        cls = SmolVLAPolicy
    else:
        raise ValueError(f"unsupported policy type: {ptype}")
    policy = cls.from_pretrained(policy_path)
    policy.eval()
    policy.to("cuda" if torch.cuda.is_available() else "cpu")
    pre = PolicyProcessorPipeline.from_pretrained(policy_path, config_filename="policy_preprocessor.json")
    post = PolicyProcessorPipeline.from_pretrained(policy_path, config_filename="policy_postprocessor.json")
    print(f"policy loaded: {policy_path} (type={ptype}, params={sum(p.numel() for p in policy.parameters())/1e6:.1f}M)")
    return policy, pre, post, ptype


def _quat2axisangle(q):
    """(B,4) quat (x,y,z,w) -> (B,3) axis-angle，与 lerobot LiberoProcessorStep 一致。"""
    q = q.float()
    w = q[:, 3].clamp(-1.0, 1.0)
    den = torch.sqrt(torch.clamp(1.0 - w * w, min=0.0))
    result = torch.zeros((q.shape[0], 3), device=q.device, dtype=torch.float32)
    mask = den > 1e-10
    if mask.any():
        angle = 2.0 * torch.acos(w[mask])
        axis = q[mask, :3] / den[mask].unsqueeze(1)
        result[mask] = axis * angle.unsqueeze(1)
    return result


def obs_to_batch(obs, instruction: str | None, ptype: str):
    """env obs (SyncVectorEnv, n=1) -> policy batch（复刻 LiberoProcessorStep）。"""
    img = torch.from_numpy(obs["pixels"]["image"][0]).permute(2, 0, 1).float() / 255.0
    batch = {"observation.images.image": img.unsqueeze(0)}
    if "image2" in obs["pixels"]:
        img2 = torch.from_numpy(obs["pixels"]["image2"][0]).permute(2, 0, 1).float().unsqueeze(0) / 255.0
        batch["observation.images.image2"] = img2
    rs = obs.get("robot_state")
    if rs is not None:
        # LIBERO state = eef_pos(3) + 轴角(3) + gripper_qpos(2) = 8 维（lerobot LiberoProcessorStep）
        eef_pos = torch.from_numpy(rs["eef"]["pos"][0]).float()
        eef_quat = torch.from_numpy(rs["eef"]["quat"][0]).float().unsqueeze(0)
        gripper = torch.from_numpy(rs["gripper"]["qpos"][0]).float()
        state = torch.cat([eef_pos, _quat2axisangle(eef_quat)[0], gripper])
        batch["observation.state"] = state.unsqueeze(0)
    # HuggingFaceVLA 相机约定：图像翻转 180°（LiberoProcessorStep 对 H,W flip）
    for k in list(batch.keys()):
        if k.startswith("observation.images."):
            batch[k] = torch.flip(batch[k], dims=[2, 3])
    if ptype == "smolvla":
        # SmolVLA 的 tokenizer 预处理读取 batch["task"]（lerobot TokenizerProcessor.task_key="task"）
        batch["task"] = [instruction or "do the task"]
        batch["observation.language_instruction"] = [instruction or "do the task"]
    return batch


def _stream_write(stream_dir, step, frame, info):
    """实时可视化：帧 + 状态写入 stream 目录（GUI SSE 推送）。"""
    import os

    os.makedirs(stream_dir, exist_ok=True)
    if frame is not None:
        h, w = frame.shape[:2]
        small = cv2.resize(frame, (256, int(256 * h / w))) if w > 256 else frame
        cv2.imwrite(os.path.join(stream_dir, f"frame_{step:05d}.png"), cv2.cvtColor(small, cv2.COLOR_RGB2BGR))
    rew = float(info.get("reward", 0))
    if hasattr(rew, "all"):
        rew = float(rew.sum())
    line = {"step": step, "reward": rew,
            "success": bool(info.get("success", False) if not hasattr(info.get("success", False), "all") else info["success"].all())}
    with open(os.path.join(stream_dir, "info.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy-path", required=True)
    ap.add_argument("--task", default="libero_spatial")
    ap.add_argument("--task-id", type=int, default=0)
    ap.add_argument("--n-episodes", type=int, default=3)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--max-steps", type=int, default=500)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--stream-dir", default=None, help="实时可视化目录：每 3 步写一帧 PNG + info.jsonl")
    args = ap.parse_args()

    policy, pre, post, ptype = load_policy(args.policy_path)
    os.makedirs(args.outdir, exist_ok=True)

    import gymnasium as gym  # noqa: PLC0415
    from lerobot.envs.libero import create_libero_envs  # noqa: PLC0415

    envs = create_libero_envs(
        args.task, n_envs=1, env_cls=gym.vector.SyncVectorEnv,
        gym_kwargs={"task_ids": [args.task_id], "obs_type": "pixels_agent_pos"},  # SmolVLA 需要 observation.state
    )
    env = envs[args.task][args.task_id]
    # 语言指令：SyncVectorEnv 包装层不暴露 task_description，直接从套件任务对象取
    from lerobot.envs.libero import _get_suite  # noqa: PLC0415

    suite = _get_suite(args.task)
    task_obj = suite.get_task(args.task_id)
    instruction = getattr(task_obj, "language", None) or getattr(env, "task_description", None)
    print("task:", getattr(task_obj, "name", args.task), "| instruction:", instruction)

    results = []
    t0 = time.time()
    for ep in range(args.n_episodes):
        obs, info = env.reset(seed=args.seed + ep)
        frames, coverages, done, step = [], [], False, 0
        while not done and step < args.max_steps:
            batch = obs_to_batch(obs, instruction, ptype)
            batch = pre(batch)
            with torch.inference_mode():
                action_norm = policy.select_action(batch)
            action = post({"action": action_norm})["action"]
            action = action.squeeze(0).detach().cpu().numpy().astype(np.float32)
            obs, rew, term, trunc, info = env.step(action)
            done = bool(term.all() if hasattr(term, "all") else term)
            if done:
                success = bool(info["success"].all() if hasattr(info.get("success"), "all") else info.get("success", False))
            if step % 3 == 0 or done or step == 0:
                frame = obs["pixels"]["image"][0]
                frames.append(frame)
                if args.stream_dir:
                    _stream_write(args.stream_dir, step, frame, info)
            step += 1
        success = bool(info.get("success", False))
        results.append({"episode": ep, "steps": step, "success": success})
        path = os.path.join(args.outdir, f"episode_{ep:02d}.mp4")
        h, w = frames[0].shape[:2]
        writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 10, (w, h))
        for f in frames:
            writer.write(cv2.cvtColor(f, cv2.COLOR_RGB2BGR))
        writer.release()
        print(f"ep {ep}: steps={step} success={success} -> {path}")

    if args.stream_dir:
        os.makedirs(args.stream_dir, exist_ok=True)
        open(os.path.join(args.stream_dir, "DONE"), "w").close()
        print(f"stream done -> {args.stream_dir}")

    summary = {
        "policy": args.policy_path, "task": args.task, "task_id": args.task_id,
        "instruction": instruction, "n_episodes": args.n_episodes,
        "success_rate": round(sum(r["success"] for r in results) / len(results), 3),
        "elapsed_s": round(time.time() - t0, 1), "episodes": results,
    }
    with open(os.path.join(args.outdir, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

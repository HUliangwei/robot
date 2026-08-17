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


def obs_to_batch(obs, instruction: str | None, ptype: str):
    """env obs (SyncVectorEnv, n=1) -> policy batch."""
    img = obs["pixels"]["image"][0]  # (H,W,3) uint8
    t = torch.from_numpy(img).permute(2, 0, 1).float() / 255.0
    batch = {"observation.images.image": t.unsqueeze(0)}
    if "image2" in obs["pixels"]:
        img2 = obs["pixels"]["image2"][0]
        batch["observation.images.image2"] = torch.from_numpy(img2).permute(2, 0, 1).float().unsqueeze(0) / 255.0
    state = obs.get("robot_state")
    if state is not None:
        # robot_state: {"eef": {pos,quat,mat}, "gripper": {qpos,qvel}, "joints": {pos,vel}}
        joints = state["joints"]["pos"][0]
        gripper = state["gripper"]["qpos"][0]
        batch["observation.state"] = torch.cat([torch.from_numpy(joints).float(), torch.from_numpy(gripper).float()]).unsqueeze(0)
    if ptype == "smolvla":
        batch["observation.language_instruction"] = [instruction or "do the task"]
    return batch


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy-path", required=True)
    ap.add_argument("--task", default="libero_spatial")
    ap.add_argument("--task-id", type=int, default=0)
    ap.add_argument("--n-episodes", type=int, default=3)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--max-steps", type=int, default=500)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    policy, pre, post, ptype = load_policy(args.policy_path)
    os.makedirs(args.outdir, exist_ok=True)

    import gymnasium as gym  # noqa: PLC0415
    from lerobot.envs.libero import create_libero_envs  # noqa: PLC0415

    envs = create_libero_envs(
        args.task, n_envs=1, env_cls=gym.vector.SyncVectorEnv, gym_kwargs={"task_ids": [args.task_id]},
    )
    env = envs[args.task][args.task_id]
    instruction = getattr(env, "task_description", None)
    print("task:", getattr(env, "task", args.task), "| instruction:", instruction)

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
                frames.append(obs["pixels"]["image"][0])
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

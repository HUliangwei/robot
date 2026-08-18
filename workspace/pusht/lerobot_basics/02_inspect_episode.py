from __future__ import annotations

from pathlib import Path

import torch
from torchvision.transforms.functional import to_pil_image

from lerobot.datasets import LeRobotDataset


REPO_ID = "lerobot/pusht"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "pusht_episode_0"


def print_frame(dataset: LeRobotDataset, dataset_index: int) -> None:
    sample = dataset[dataset_index]

    state = sample["observation.state"]
    action = sample["action"]

    print("-" * 70)
    print(f"dataset索引    : {dataset_index}")
    print(f"全局index     : {sample['index'].item()}")
    print(f"episode_index : {sample['episode_index'].item()}")
    print(f"frame_index   : {sample['frame_index'].item()}")
    print(f"timestamp     : {sample['timestamp'].item():.1f} s")
    print(f"state         : {state.tolist()}")
    print(f"action        : {action.tolist()}")
    print(f"action-state  : {(action - state).tolist()}")
    print(f"next.reward   : {sample['next.reward'].item():.6f}")
    print(f"next.done     : {sample['next.done'].item()}")
    print(f"next.success  : {sample['next.success'].item()}")

    image_path = OUTPUT_DIR / f"frame_{dataset_index:03d}.png"
    image = sample["observation.image"].clamp(0.0, 1.0)
    to_pil_image(image).save(image_path)

    print(f"图像已保存    : {image_path}")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = LeRobotDataset(
        REPO_ID,
        episodes=[0],
    )

    print(f"episode 0共有 {len(dataset)} 帧")
    print(f"FPS: {dataset.fps}")
    print(f"理论采样周期: {1 / dataset.fps:.3f} s")

    selected_indices = [
        0,
        1,
        len(dataset) // 2,
        len(dataset) - 1,
    ]

    for index in selected_indices:
        print_frame(dataset, index)

    first = dataset[0]
    second = dataset[1]

    target = first["action"]
    state_before = first["observation.state"]
    state_after = second["observation.state"]

    distance_before = torch.linalg.vector_norm(target - state_before)
    distance_after = torch.linalg.vector_norm(target - state_after)

    print("\n" + "=" * 70)
    print("验证第一条action是否让推杆接近目标")
    print("=" * 70)
    print(f"执行前到目标的距离: {distance_before.item():.4f}")
    print(f"下一帧到目标的距离: {distance_after.item():.4f}")

    if distance_after < distance_before:
        print("结论：下一帧的推杆位置更接近action指定的目标位置。")
    else:
        print("结论：由于惯性、碰撞或控制过程，下一帧没有立即靠近目标。")


if __name__ == "__main__":
    main()
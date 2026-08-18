from __future__ import annotations

from pprint import pprint
from typing import Any

import torch

from lerobot.datasets import LeRobotDataset, LeRobotDatasetMetadata


REPO_ID = "lerobot/pusht"


def summarize_value(name: str, value: Any) -> None:
    """简要显示字段类型、形状和少量数值，避免打印整张图像。"""

    print(f"\n{name}")
    print(f"  Python 类型: {type(value).__name__}")

    if isinstance(value, torch.Tensor):
        print(f"  shape: {tuple(value.shape)}")
        print(f"  dtype: {value.dtype}")
        print(f"  device: {value.device}")

        if value.numel() > 0:
            flat = value.detach().cpu().flatten()

            print(f"  前几个值: {flat[:8].tolist()}")

            if value.is_floating_point():
                print(f"  最小值: {flat.min().item():.6f}")
                print(f"  最大值: {flat.max().item():.6f}")

        return

    print(f"  内容: {value!r}")


def main() -> None:
    print("=" * 70)
    print("1. 读取 PushT 元数据")
    print("=" * 70)

    metadata = LeRobotDatasetMetadata(REPO_ID)

    print(f"数据集 ID: {REPO_ID}")
    print(f"总 episode 数: {metadata.total_episodes}")
    print(f"总 frame 数: {metadata.total_frames}")
    print(f"采集频率 FPS: {metadata.fps}")
    print(f"机器人类型: {metadata.robot_type}")
    print(f"相机字段: {metadata.camera_keys}")

    print("\n任务列表:")
    pprint(metadata.tasks)

    print("\n字段定义:")
    pprint(metadata.features)

    print("\n" + "=" * 70)
    print("2. 只加载 episode 0")
    print("=" * 70)

    dataset = LeRobotDataset(
        REPO_ID,
        episodes=[0],
    )

    print(f"选中的 episode: {dataset.episodes}")
    print(f"当前 episode 数: {dataset.num_episodes}")
    print(f"当前 frame 数: {dataset.num_frames}")
    print(f"数据集长度 len(dataset): {len(dataset)}")
    print(f"FPS: {dataset.fps}")

    print("\n" + "=" * 70)
    print("3. 读取加载后数据集中的第一帧")
    print("=" * 70)

    sample = dataset[0]

    print("该 frame 包含的字段:")

    for key in sample:
        print(f"  - {key}")

    print("\n逐项查看:")

    for key, value in sample.items():
        summarize_value(key, value)


if __name__ == "__main__":
    main()
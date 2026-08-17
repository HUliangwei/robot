# MuJoCo PushT（LeRobot 复现）

把 LeRobot 官方 PushT 任务（2D pymunk）在 **MuJoCo** 中复现，并用训练于 `lerobot/pusht` 数据集的
ACT 策略完成闭环推理。

## 文件

| 文件 | 说明 |
|---|---|
| `pusht_mujoco.xml` | MuJoCo 模型：推块(agent) + T块 + 四面墙 + 目标区 + 俯视相机 |
| `mujoco_pusht_env.py` | gymnasium 封装，观测/动作/奖励与 `gym_pusht/PushT-v0` (pixels_agent_pos) 1:1 兼容 |
| `run_pusht_rollout.py` | 闭环推理脚本（官方 2D 环境 / MuJoCo 环境通用） |

## 快速使用

```bash
# 1. MuJoCo 环境随机走 50 步自检
python mujoco_pusht_env.py

# 2. 用预训练 ACT 在 MuJoCo 环境推理 3 局（权重来自 HF hub 或本地目录）
python run_pusht_rollout.py --env mujoco --n_episodes 3 --outdir ../../outputs/rollout_mujoco
python run_pusht_rollout.py --env official --n_episodes 3 --outdir ../../outputs/rollout_official

# 3. 用自己的训练 checkpoint
python run_pusht_rollout.py --env mujoco --n_episodes 5 \
    --policy-path ../../outputs/train/act_pusht_real/checkpoints/last/pretrained_model
```

## 观测/动作语义（与数据集一致）

- `obs.pixels`：(96,96,3) uint8 俯视渲染（pygame y-down）
- `obs.agent_pos`：(2,) ∈ [0,512]
- `action`：(2,) 推块目标位置 ∈ [0,512]（PD 控制：k_p=100, k_v=20, 10 子步/步）
- 奖励：`clip(coverage/0.95, 0, 1)`；成功：覆盖率 > 95%（T 块对齐目标区 (256,256,45°)）
- 回合：300 步

## 环境依赖

- `lerobot-win` conda 环境（Python 3.12 / torch 2.11 / lerobot 0.6.1 / mujoco 3.11.0 / gym-pusht 0.1.6 / pymunk==6.8.0 / shapely / cv2）
- 预训练权重缓存于 `D:\Desktop\robot\datasets\hub`（HF_HOME）

详细学习笔记见 `lerobot_basics/07_MuJoCo_PushT_模型搭建与ACT推理.ipynb`，踩坑记录见 `D:\Desktop\robot\note\04_MuJoCo_PushT_复现总结.md`。

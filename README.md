# 🤖 robot — LeRobot × MuJoCo 具身智能学习项目

> **把 LeRobot 官方 PushT 任务在 MuJoCo 中复现推理**：从数据集、ACT 训练到双环境（pymunk 2D 官方 / 自建 MuJoCo）闭环推理的完整工作区。

## ✨ 核心成果

- ✅ **自建 MuJoCo PushT 环境**：`workspace/embodied_learning/mujoco_basics/pusht/`
  - `pusht_mujoco.xml` — 推块 + T块 + 墙 + 目标区 + 俯视相机
  - `mujoco_pusht_env.py` — gymnasium 封装，与 `gym_pusht/PushT-v0` 观测/动作/奖励 **1:1 兼容**
  - `run_pusht_rollout.py` — 闭环推理脚本（官方 / MuJoCo 通用，支持本地 checkpoint）
- ✅ **双环境闭环推理跑通**：同一份 ACT 权重在两个物理引擎上推理，覆盖率分布一致（语义对齐验证）
- ✅ **自训 ACT**：`outputs/train/act_pusht_real/`（25k 步 checkpoint，loss 收敛至 l1=0.12）
- ✅ **完整文档 + 可视化**：见 `docs/`（工作流说明、自包含 HTML 报告、图表、对比视频）

## 🚀 快速开始

```bash
# 1. 环境自检（MuJoCo 环境随机走 50 步）
python workspace/embodied_learning/mujoco_basics/pusht/mujoco_pusht_env.py

# 2. 官方 2D 环境推理（社区权重）
python workspace/embodied_learning/mujoco_basics/pusht/run_pusht_rollout.py \
    --env official --n_episodes 3 --policy-path aadarshram/act_pusht \
    --outdir workspace/embodied_learning/outputs/rollout_official

# 3. MuJoCo 环境推理（本地自训权重）
python workspace/embodied_learning/mujoco_basics/pusht/run_pusht_rollout.py \
    --env mujoco --n_episodes 3 \
    --policy-path workspace/embodied_learning/outputs/train/act_pusht_real/checkpoints/025000/pretrained_model \
    --outdir workspace/embodied_learning/outputs/rollout_mujoco
```

## 📁 项目结构

```
robot/
├── docs/                     工作流文档 + 可视化报告（浏览器直接打开 inference_report.html）
├── note/                     学习笔记 01-04
├── workspace/embodied_learning/
│   ├── lerobot_basics/       01-07 学习 Notebook（07 = MuJoCo 模型搭建 + ACT 推理）
│   ├── mujoco_basics/pusht/  自建 MuJoCo 环境（核心代码）
│   ├── outputs/              rollout 视频/指标 + 训练 checkpoint（权重不入库）
│   └── environment/          conda/pip 环境清单
├── envs/                     本地 conda 环境（不入库）
├── datasets/                 HF 数据集/权重缓存（不入库）
└── tool/                     MuJoCo 二进制（不入库）
```

## 📊 结果速览

| 权重 | 官方 mean/max 覆盖率 | MuJoCo mean/max |
|---|---|---|
| 社区 aadarshram ACT | 0.32 / 0.88 | 0.35 / 0.70 |
| 社区 Lemon-03 ACT | 0.41 / 0.93 | — |
| 自训 ACT（25k 步） | 0.39 / 0.82 | 0.36 / 0.62 |

> 所有可用 ACT 权重均未达 95% 成功线（欠训练）；达到成功需官方配方（batch 8 + 60-80k 步）或官方 `lerobot/act_pusht`。详见 `docs/工作流_从数据到推理.md` §4/§5。

## 📖 学习路径

1. `note/01_机器人算法模型总结分类.md` — 算法地图
2. Notebook 01-03 — 数据结构 / 训练流程 / MuJoCo 概念
3. Notebook 05A / 06 — ACT 源码解析 + 训练推理全流程
4. **Notebook 07 — MuJoCo PushT 模型搭建与 ACT 推理（本项目的核心产出）**
5. `note/04_MuJoCo_PushT_复现总结.md` — 踩坑记录速查

## 🔧 环境要求

- Windows + conda 环境 `lerobot-win`（清单见 `workspace/embodied_learning/environment/`）
- 关键版本：lerobot 0.6.1 / torch 2.11+cu128 / mujoco 3.11.0 / gym-pusht 0.1.6 / **pymunk 6.8.0**
- GPU：CUDA 可用即可（本项目用 RTX 4060 Laptop）

## ⚠️ 未入库内容（见 .gitignore）

`envs/`（6.4GB conda 环境）、`datasets/`（411MB 缓存）、`tool/`（MuJoCo 二进制）、
`**/checkpoints/` 与 `*.safetensors`（权重超 GitHub 100MB 限制）。
需要时从 HF 重新下载或重新训练。

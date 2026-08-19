# 🤖 robot — LeRobot × MuJoCo 具身智能学习项目

> **把 LeRobot 官方 PushT 任务在 MuJoCo 中复现推理**：从数据集、ACT 训练到双环境（pymunk 2D 官方 / 自建 MuJoCo）闭环推理的完整工作区；并以此为跳板向 3D 机械臂操作（LIBERO）与 VLA 模型进阶。

## ✨ 小项目一览

| 小项目 | 一句话 | 状态 |
|---|---|---|
| **pusht**（PushT） | 2D 推块任务在自建 MuJoCo 中的完整复现（数据→ACT→双环境推理） | ✅ 主线完成，物理保真已修复 |
| **libero**（LIBERO 基准） | Franka + MuJoCo 桌面操作，ACT → SmolVLA 的 VLA 学习路线 | 🚧 已立项（骨架 + 环境安装中） |

## 🚀 快速开始

```bash
# 1. 本地仪表盘（网页端：进度 / 命令 / 视频 / 文件浏览）
python gui/server.py                 # 打开 http://127.0.0.1:8766（自动避让 8765）

# 2. PushT 环境自检
python workspace/pusht/mujoco_basics/pusht/mujoco_pusht_env.py

# 3. PushT 推理（官方 / MuJoCo，社区权重）
python workspace/pusht/mujoco_basics/pusht/run_pusht_rollout.py \
    --env official --n_episodes 3 --policy-path aadarshram/act_pusht \
    --outdir workspace/pusht/outputs/rollout_official

# 4. LIBERO 环境自检（首次需安装 libero 栈，见 workspace/libero/）
python workspace/libero/verify_env.py
```

## 📁 项目结构

```
robot/
├── gui/                     本地网页仪表盘（server.py + 前端，零依赖）
├── docs/                    工作流文档 + 可视化报告（inference_report.html）
├── note/                    跨项目学习笔记 01-04（算法分类 / 工具 / 闭环流程 / PushT 总结）
├── workspace/               小项目区（每个 = README 介绍 + PROGRESS 进度 + commands 命令）
│   ├── pusht/   PushT 小项目（README 展示卡片 + notebooks + MuJoCo 环境 + outputs）
│   └── libero/               LIBERO 小项目（README + 环境验证脚本）
├── envs/  datasets/  tool/  本地环境 / HF 缓存 / MuJoCo 二进制（不入库）
└── archives/                （预留）
```

## 📊 PushT 结果速览

| 权重 | 官方 mean/max 覆盖率 | MuJoCo mean/max |
|---|---|---|
| 社区 aadarshram ACT | 0.32 / **0.953 ✅成功** | 0.35 / 0.865 |
| 社区 Lemon-03 ACT | 0.41 / 0.93 | — |
| 自训 ACT（25k 步） | 0.39 / 0.82 | 0.36 / 0.62 |

> ✅ **官方环境成功已复现**：aadarshram ACT @seed1000 覆盖率 **0.9534**（134 步完成）。
> 🔧 **物理保真修复**：修复"推完不立即停下"（块关节阻尼 5 + 摩擦对齐 pymunk），rollout 奖励总和 +104%。
> ⚠️ **已知残余问题**：MuJoCo 真实 rollout 中块仍比官方转得多（累计 380° vs 56°），已记录于 `workspace/pusht/PROGRESS.md`（含已排除假设与下一步）。

## 📖 学习路径

1. `note/01_机器人算法模型总结分类.md` — 算法地图
2. `workspace/pusht/lerobot_basics/` Notebook 01-07（07 = MuJoCo PushT 模型搭建 + ACT 推理，核心产出）
3. `note/04_MuJoCo_PushT_复现总结.md` — 踩坑速查（10 条）
4. `docs/roadmap_复现项目.md` — LIBERO 调研 + VLA 学习路线（ACT → SmolVLA → OpenVLA）

## 🔧 环境要求

- Windows + conda 环境 `lerobot-win`（清单见 `workspace/pusht/environment/`）
- 关键版本：lerobot 0.6.1 / torch 2.11+cu128 / mujoco 3.11.0 / gym-pusht 0.1.6 / **pymunk 6.8.0** / libero 0.1.1
- GPU：RTX 4060 Laptop 8GB（CUDA 可用）

## ⚠️ 未入库内容（见 .gitignore）

`envs/`、`datasets/`、`tool/`、`**/checkpoints/`、`*.safetensors`、`**/outputs/train/`（权重/缓存超 GitHub 100MB 限制，需要时从 HF 重新下载或重新训练）。

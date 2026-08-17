# 🎯 embodied_learning — PushT × LeRobot × MuJoCo（小项目介绍）

> **项目一句话**：用 HuggingFace **LeRobot** 框架把 2D 推块任务 **PushT** 完整复现到自建的 **MuJoCo** 仿真环境——从数据集、ACT 策略训练到双环境（官方 pymunk / 自建 MuJoCo）闭环推理，沉淀为可复现的工作流与可视化。

## 🧩 这是什么 / 为什么做

- **学习目标**：具身智能闭环 = 数据采集 → 模型训练 → 仿真推理，并在 MuJoCo 里亲手搭一个可用的仿真环境
- **为什么 PushT**：LeRobot 官方入门任务（数据公开、ACT 官方支持、2D 简单可控），是理解"数据 ↔ 模型 ↔ 仿真"的最佳起点
- **为什么 MuJoCo**：官方 PushT 环境是 pymunk 2D；自建 MuJoCo 版本 = 真正理解仿真建模（几何/相机/光照/接触），并为 3D 任务（LIBERO）铺路

## 🏗️ 技术栈 / 管线

```
lerobot/pusht 数据集 ──► ACT 策略（模仿学习）──► 闭环推理
        ▲                                        │
        │                                        ▼
   MuJoCo 自建环境（pusht_mujoco.xml + gymnasium 封装）◄─┘
```

| 组件 | 说明 |
|---|---|
| 数据集 | `lerobot/pusht` v3.0（206 episodes，HF 缓存） |
| 策略 | **ACT**（Action Chunking with Transformers），社区权重 + 自训 25k 步 |
| 官方环境 | gym_pusht `PushT-v0`（pymunk 2D，训练数据同源） |
| **自建 MuJoCo 环境** | `mujoco_basics/pusht/`：XML 模型 + gymnasium 封装，观测/动作/奖励与官方 **1:1 兼容** |
| 推理脚本 | `run_pusht_rollout.py`：同一权重双环境推理，产出 mp4/gif/metrics.json |

## 📊 结果

| 权重 | 官方环境 mean/max | MuJoCo mean/max |
|---|---|---|
| 社区 aadarshram ACT | 0.32 / **0.953 ✅ 成功** | 0.35 / 0.865 |
| 社区 Lemon-03 ACT | 0.41 / 0.93 | — |
| 自训 ACT（25k 步） | 0.39 / 0.82 | 0.36 / 0.62 |

- ✅ **官方环境成功已复现**：aadarshram ACT @seed1000 覆盖率 **0.9534**（>0.95），134 步完成
- ✅ **双环境语义对齐验证**：同一权重在两种物理引擎上覆盖率分布一致；MuJoCo 渲染与训练图像分布几乎一致（白底 0.903 vs 0.912）
- 🔧 **物理保真修复**：发现并修复"推完不立即停下"问题（块关节阻尼 5 + 摩擦对齐 pymunk），rollout 奖励总和 +104%

## ⚠️ 已知问题（诚实记录）

- **MuJoCo 残余旋转**：真实策略 rollout 中块仍比官方转得多（累计旋转 380° vs 56°，90° 自旋事件 80 vs 12 次）——已确认不是惯量、不是摩擦、不是接触刚度单独可解，是 MuJoCo 软接触模型与 pymunk 刚性接触的整体差异；详见 `PROGRESS.md` 与 `note/04 §3.6`
- **成功率上限**：0.95 目标需要官方训练配方（batch 8 + 60-80k 步）或更长训练预算

## 🚀 快速运行

```bash
# 环境自检
python mujoco_basics/pusht/mujoco_pusht_env.py

# 官方 2D 环境推理（社区权重）
python mujoco_basics/pusht/run_pusht_rollout.py --env official --n_episodes 3 \
    --policy-path aadarshram/act_pusht --outdir outputs/rollout_official

# MuJoCo 环境推理（自训权重）
python mujoco_basics/pusht/run_pusht_rollout.py --env mujoco --n_episodes 3 \
    --policy-path outputs/train/act_pusht_real/checkpoints/025000/pretrained_model \
    --outdir outputs/rollout_mujoco
```

## 📚 学习索引

- `note/04_MuJoCo_PushT_复现总结.md` — 完整复现总结 + 踩坑速查（10 条）
- `lerobot_basics/07_MuJoCo_PushT_模型搭建与ACT推理.ipynb` — 核心产出 Notebook
- `docs/inference_report.html` — 可视化报告（图表 + 官方 vs MuJoCo 对比视频）
- `PROGRESS.md` — 项目进度记录（每次进展必更新）

## 🔗 相关

- 上一级：`../../README.md`（仓库总览）｜ 下一项目：`../libero/`（LIBERO 机械臂操作）
- 个人网站展示建议：直接用本文件作为项目卡片；视频取 `outputs/rollout_*/episode_*.mp4`

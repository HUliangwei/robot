# 🎯 embodied_learning — PushT × LeRobot × MuJoCo（小项目介绍）

> **项目一句话**：用 HuggingFace **LeRobot** 框架把 2D 推块任务 **PushT** 完整复现到自建的 **MuJoCo** 仿真环境——从数据集、ACT 策略训练到双环境（官方 pymunk / 自建 MuJoCo）闭环推理，沉淀为可复现工作流与可视化。
> **里程碑**：官方环境成功复现（覆盖率 0.9534）✅；物理保真修复（推完即停）✅

---

## 1️⃣ 数据集

| 项 | 值 |
|---|---|
| 仓库 | `lerobot/pusht` v3.0（HF，公开） |
| 规模 | 206 episodes / 25650 帧 |
| 观测 | `observation.image` 96×96×3 + `observation.state`(2)（agent 位置） |
| 动作 | `action[2] ∈ [0,512]`（推头目标位置，PD 控制） |
| 任务 | 把 T 形块推到目标区（覆盖率 >0.95 即成功） |
| 本地缓存 | `D:\Desktop\robot\datasets`（HF_HOME） |

## 2️⃣ 模型架构

**ACT**（Action Chunking with Transformers，模仿学习）：
- ResNet18 视觉编码 → Transformer 编码-解码 + VAE 潜变量 → 输出 **100 步动作块**（chunk）
- 每 100 步重规划一次；可选 temporal ensembling（本项目验证无效）

## 3️⃣ 权重路径（当前已拥有）

| 模型 | 来源 | 路径 | 实测 |
|---|---|---|---|
| ACT（社区） | `aadarshram/act_pusht`（80k 步） | `datasets/hub/models--aadarshram--act_pusht/...` | **官方环境 0.9534 ✅** / MuJoCo 0.865 |
| ACT（社区） | `Lemon-03/ACT_PushT_test` | `datasets/hub/models--Lemon-03--ACT_PushT_test/...` | 官方 0.93 |
| ACT（**自训**） | 本地训练 25k 步 | `workspace/.../outputs/train/act_pusht_real/checkpoints/025000/pretrained_model` | l1=0.12，与社区相当 |

## 4️⃣ 训练入口

```bash
# 自训 ACT（30k 步，已验证收敛 l1 0.58→0.12；成功需官方配方 batch8+60-80k 步）
python -m lerobot.scripts.lerobot_train --dataset.repo_id=lerobot/pusht \
  --policy.type=act --policy.push_to_hub=false \
  --output_dir=outputs/train/act_pusht_real --steps=30000 --batch_size=64 \
  --save_freq=5000 --save_checkpoint=true --env_eval_freq=0 --wandb.enable=false
```

## 5️⃣ 推理（闭环）

```bash
# 双环境推理（官方 pymunk / 自建 MuJoCo），出 mp4/gif/metrics.json
python mujoco_basics/pusht/run_pusht_rollout.py --env official --n_episodes 3 \
  --policy-path aadarshram/act_pusht --outdir outputs/rollout_official
python mujoco_basics/pusht/run_pusht_rollout.py --env mujoco --n_episodes 3 \
  --policy-path outputs/train/act_pusht_real/checkpoints/025000/pretrained_model \
  --outdir outputs/rollout_mujoco
```

## 6️⃣ 仿真（自建 MuJoCo 环境）

- **环境是自建的**（非官方）：`mujoco_basics/pusht/pusht_mujoco.xml` + `mujoco_pusht_env.py`
  - 场景：推头（圆柱）+ T 块（两矩形）+ 墙 + 目标区 + 俯视相机
  - 与官方 gym_pusht **1:1 语义对齐**（观测/动作/奖励/成功判据）
  - 无重力/无地面摩擦，物理与 pymunk 对齐（块关节阻尼 5 + 摩擦 2/0）
- **推理示例**：`outputs/rollout_mujoco_damp5_fric2_10seeds/`（修复后视频）、`outputs/rollout_official_success/`（官方成功局）

## 7️⃣ 分析与结论

- **双环境语义对齐验证**：同一权重在 pymunk/MuJoCo 覆盖率分布一致；渲染与训练图像分布几乎一致
- **物理保真修复**：定位"推完不立即停下"根因（MuJoCo 软接触不耗散偏心踢击能量）→ 块关节阻尼 5 + 摩擦对齐 → 推完即停、奖励总和 +104%
- **已知残余问题**：真实 rollout 中 MuJoCo 块仍比官方转得多（380° vs 56°），已排除 5 类假设（惯量/刚度/时间步/推力/摩擦锥），判定为接触模型整体差异（详见 PROGRESS.md）
- **成功率上限**：0.95 目标需官方训练配方（batch 8 + 60-80k 步）或更长训练预算

---
*进度详见 `PROGRESS.md`；可运行命令见 `commands.json`（GUI 直接执行）；学习笔记 `note/04_MuJoCo_PushT_复现总结.md`；核心 Notebook：`lerobot_basics/07_...ipynb`*

# PROGRESS — embodied_learning（PushT × LeRobot × MuJoCo）

> 本项目进度记录。**规则**：每次有实质进展后更新「当前状态」并加一条「更新日志」；AI 会话结束时也应在此记录。

## 项目一句话

用 LeRobot 框架把 PushT 任务在 **MuJoCo** 中复现：数据集 → ACT 训练 → 双环境（官方 pymunk 2D / 自建 MuJoCo）闭环推理，并沉淀为可复现工作流与可视化。

## 当前状态（2026-08-17）

| 阶段 | 状态 | 说明 |
|---|---|---|
| 环境搭建 | ✅ | conda `lerobot-win`（Python 3.12 / torch 2.11+cu128 / lerobot 0.6.1 / mujoco 3.11 / gym-pusht 0.1.6 / pymunk 6.8.0） |
| 数据集 | ✅ | `lerobot/pusht` 已缓存（206 episodes / 25650 帧 / v3.0） |
| 官方 2D 闭环推理 | ✅ | 社区 ACT 权重跑通，最高覆盖率 0.93（Lemon-03），**无成功（>0.95）** |
| MuJoCo 环境自建 | ✅ | `mujoco_basics/pusht/`：XML + gymnasium 封装，观测/动作/奖励与官方 1:1 对齐 |
| MuJoCo 闭环推理 | ✅ | 同一权重双环境分布一致，最高 0.70 |
| 自训 ACT | ✅(25k) | `outputs/train/act_pusht_real/`，l1=0.12 收敛；双环境 20 局**无成功**（欠训练） |
| 文档/可视化 | ✅ | Notebook 01-07、note 01-04、docs/（工作流 + HTML 报告） |

## 结果速览

| 权重 | 官方 mean/max | MuJoCo mean/max |
|---|---|---|
| 社区 aadarshram ACT | 0.32 / 0.88 | 0.35 / 0.70 |
| 社区 Lemon-03 ACT | 0.41 / 0.93 | — |
| 自训 ACT 25k | 0.39 / 0.82 | 0.36 / 0.62 |

## 待办 / 下一步

- [ ] **达成 >95% 成功**：官方配方重训（batch 8 + 60-80k 步 ≈ 8-10h）或获取 gated 的 `lerobot/act_pusht`
- [ ] 官方 `lerobot/diffusion_pusht` 旧格式迁移（0.6.1 迁移脚本有 bug，可尝试修复）
- [ ] 网页端策略服务化（FastAPI 骨架见 docs/工作流 §6，gui/ 仪表盘已接入）
- [ ] 升级 3D：SO-100 机械臂推块（需重适配观测）

## 常用命令

见同目录 `commands.json`（gui 仪表盘也读取它）。

## 更新日志

- 2026-08-17：完成 MuJoCo 环境自建与双环境闭环推理；自训 ACT 25k（用户要求停止）；文档/可视化/GitHub 推送完成

# AI_CONTEXT.md — 供 AI（如 coding agent）跨对话快速了解本仓库

> **用途**：新对话开始时，先读本文件 + 相关小项目的 `PROGRESS.md` + `commands.json`，即可快速接续工作。
> **规则**：任何 AI 或用户在本仓库做出实质进展后，更新本文件「状态快照」并在「更新日志」追加一行；同步更新对应小项目 PROGRESS.md。

---

## 1. 这是什么项目

**LeRobot × MuJoCo 具身智能学习工作区**：用 HuggingFace LeRobot 框架（数据 + 策略）配合物理仿真（pymunk 2D / MuJoCo），复现与学习机器人操作任务。当前主项目为 **PushT**（2D 推送任务）从数据到 MuJoCo 推理的完整闭环。

## 2. 目录地图

```
robot/  （git 仓库 → github.com/HUliangwei/robot）
├── AI_CONTEXT.md          本文档（AI 上下文）
├── README.md              项目总览 + 快速开始
├── .gitignore             排除 envs/datasets/tool/权重（见 §6）
├── docs/
│   ├── 工作流_从数据到推理.md    完整复现指南（含 Web 开发指引）
│   ├── roadmap_复现项目.md      下一项目调研（LIBERO 首选）
│   ├── inference_report.html   自包含可视化报告（浏览器打开）
│   └── viz/                  图表 + 官方vsMuJoCo 对比视频
├── gui/                   本地网页仪表盘（server.py + index.html + app.js）
│   └── .runs/              命令运行日志（临时）
├── note/                  学习笔记 01-04（04 = PushT 复现总结/踩坑速查）
├── workspace/
│   └── embodied_learning/  小项目：PushT × LeRobot × MuJoCo
│       ├── PROGRESS.md      进度记录（AI 会话结束必更新）
│       ├── commands.json    可运行命令清单（gui 也读取）
│       ├── lerobot_basics/   Notebook 01-07（07 = MuJoCo 模型搭建 + ACT 推理）
│       ├── mujoco_basics/pusht/  自建 MuJoCo 环境（核心代码）
│       ├── outputs/         rollout 视频 + metrics.json（权重不入库）
│       └── environment/     conda/pip 清单
├── envs/                  本地 conda 环境（不入库）
├── datasets/              HF 缓存（不入库）
└── tool/                  MuJoCo 二进制（不入库）
```

## 3. 环境与版本（关键）

- conda：`D:\Desktop\robot\envs\lerobot-win`（python.exe 在此）
- lerobot 0.6.1 / torch 2.11.0+cu128 / mujoco 3.11.0(python) / gymnasium 1.3.0 / gym-pusht 0.1.6 / **pymunk 6.8.0（勿升 7）** / shapely / matplotlib / diffusers（装了但未用）
- GPU：RTX 4060 Laptop 8GB（CUDA 可用）
- HF 缓存：`HF_HOME=D:\Desktop\robot\datasets`（权重/数据集都在 `datasets\hub`）

## 4. 状态快照（2026-08-17）

**PushT 主线：全部核心目标完成** ✅
- 自建 MuJoCo PushT 环境（语义与 gym_pusht 1:1 对齐）✅
- 双环境（官方 pymunk / MuJoCo）ACT 闭环推理跑通 ✅
- 自训 ACT 25k 步（l1=0.12，用户要求停止训练）✅
- 文档/可视化/GitHub 推送 ✅（remote: main @ 见 git log）

**关键结果**：所有可用 ACT 权重（社区 80k / 自训 25k）覆盖率最高 0.6-0.93，**均未达 95% 成功线**——原因是欠训练，与推理管线无关（管线与 MuJoCo 语义已验证正确）。

## 5. 常用入口命令

```bash
# GUI 仪表盘（进度/命令/视频可视化）
python gui/server.py                # 打开 http://127.0.0.1:8765

# PushT 推理（MuJoCo / 官方）
python workspace/embodied_learning/mujoco_basics/pusht/run_pusht_rollout.py \
    --env mujoco --n_episodes 3 --policy-path <权重目录> --outdir outputs/x

# 训练 ACT（完整命令见 workspace/embodied_learning/commands.json）
```

## 6. 重要约束（AI 必读）

1. **git 推送需代理**：仓库配置了 `http.proxy=http://127.0.0.1:7897`（国内访问 GitHub）。
2. **不入库**：`envs/ datasets/ tool/ archives/`、`*.safetensors`、`**/checkpoints/`、`**/outputs/train/`（权重超 GitHub 100MB 限制）。
3. **换对话接续**：新对话 → 读本文件 → 读 `workspace/embodied_learning/PROGRESS.md` → 继续。
4. **改文件前先读**；命令优先用 `envs\lerobot-win\python.exe`。

## 7. 下一步 / 待办（2026-08-17）

- [ ] 达成 >95% PushT 成功（官方配方 batch8 + 60-80k 步 / 或 gated `lerobot/act_pusht`）
- [ ] 启动 **LIBERO** 项目（见 docs/roadmap_复现项目.md，待用户确认）
- [ ] 网页端策略服务化（FastAPI 骨架见 docs/工作流 §6）
- [ ] gui 仪表盘后续增强（如在线 rollout 流式预览）

## 8. 更新日志

- 2026-08-17：创建；PushT 主线完成、GitHub 推送、gui/docs/AI_CONTEXT 建立

# LIBERO 小项目 — MuJoCo 机械臂操作基准

> **一句话**：在 LeRobot 0.6.1 内置的 LIBERO 环境（Franka 机械臂 + MuJoCo）上，从模仿学习（ACT）进阶到 VLA（SmolVLA），把 PushT 学到的闭环技能搬到 3D 桌面操作。
> 个人网站展示用：本目录 = 项目卡片（README）+ 进度（PROGRESS.md）+ 命令（commands.json）。

## 这是什么

**LIBERO 不是模型，是「任务基准 + 数据集」**（LifeLong Robot Learning Benchmark）：
- **130 个桌面机械臂操作任务**，4 个套件：Spatial / Object / Goal / LIBERO-100
- **Franka 机械臂 + MuJoCo**（与 PushT 同一物理引擎，2D → 3D 的天然跳板）
- 观测 = 3 视角图像 + 机器人状态；动作 = 7-DoF 关节 + 夹爪
- LeRobot 0.6.1 **已内置**（`lerobot.envs.libero`），框架零改动

## 目标 / 学习路线

```
1. 环境跑通：LIBERO + 官方数据集下载 + 随机/脚本策略验证   ✅
2. 模仿学习：LIBERO + ACT（社区权重推理，流程跑通）        ✅
3. VLA：LIBERO + SmolVLA（官方模型）                       ✅ 80% 成功率！
4. 进阶：OpenVLA（需 >16GB 显存，云 GPU 或量化）
```

## 关键成果（2026-08-17）

- **完整闭环在 Windows 跑通**：环境（Franka+MuJoCo）→ 数据集（1.9GB/1693 episodes）→ 训练（ACT 冒烟 4.6 step/s）→ 评估（lerobot-eval，出视频+指标）
- **官方 SmolVLA 在 LIBERO-Spatial task0 成功率 80%（4/5）**——VLA 学习核心验证；视频见 `outputs/eval_smolvla_spatial_t0/`
- 社区 ACT 权重（test 仓库）0/10、0/1（权重弱，流程本身正确）

## 目录

```
workspace/libero/
├── README.md          本文件（项目介绍）
├── PROGRESS.md        进度记录（每次进展必更新）
├── commands.json      GUI 可运行命令清单
├── verify_env.py      环境自检脚本（导入 lerobot LIBERO 环境）
└── (后续) datasets/  scripts/  outputs/
```

## 环境说明

- 复用 conda 环境 `lerobot-win`（已装 lerobot 0.6.1 + torch + mujoco）
- **LIBERO 栈已装好并验证通过**（2026-08-17）：libero 0.1.1 + robosuite 1.4.0 + robomimic 0.2.0
- Windows 安装方案：`python setup_windows_patches.py`（幂等补丁：egl_probe stub + --no-deps + robosuite 的 /tmp、mujoco.dll、MUJOCO_GL、mj_fullM 修复）
- 验证：`python verify_env.py`（exit 0 = LIBERO-Spatial 环境可构建可步进）
- 数据集从 HF 下载（`lerobot/libero_spatial` 等），缓存到 `D:\Desktop\robot\datasets`；环境 assets 已自动下载到 `~/.cache/libero/assets`

> 学习记录索引：`note/`（学习笔记）、`docs/roadmap_复现项目.md`（调研与 VLA 路线）

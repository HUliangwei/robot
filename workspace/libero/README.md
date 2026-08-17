# 🤖 libero — LIBERO 机械臂操作基准（Franka × MuJoCo）

> **一句话**：在 LeRobot 内置的 LIBERO 环境（Franka 机械臂 + MuJoCo）上完成数据→模型→推理闭环，并用社区/官方权重（ACT + **SmolVLA**）验证 VLA 学习路线。
> **里程碑**：官方 SmolVLA 在 LIBERO-Spatial task0 成功率 **80%**（4/5）✅

---

## 1️⃣ 数据集

| 项 | 值 |
|---|---|
| 仓库 | `lerobot/libero`（HF，公开非 gated，1.9GB） |
| 规模 | **1693 episodes / 273465 帧** / fps 10 |
| 任务 | **40 个**（Spatial 10 + Object 10 + Goal 10 + Long 10；LIBERO 论文全套 130 个） |
| 观测 | 双相机 `image`（agentview 俯视）+ `image2`（腕部），256×256×3 |
| 状态 | `observation.state`（8 = 7 关节 + 1 夹爪） |
| 动作 | `action[7] ∈ [-1,1]`（**相对关节增量**，控制频率 20Hz） |
| 语言 | **每个任务带 `language_instruction`**（VLA 的关键输入） |
| 本地缓存 | `D:\Desktop\robot\datasets\hub\datasets--lerobot--libero` |

## 2️⃣ 模型架构

| 模型 | 类型 | 架构 | 输入 | 输出 |
|---|---|---|---|---|
| **ACT** | 模仿学习 | CNN(ResNet18) 视觉编码 → Transformer 编码-解码 + VAE 潜变量 | 图像+状态 | 动作块（chunk=100） |
| **SmolVLA** | **VLA** | **SmolVLM2-500M**（视觉-语言骨干）+ 动作头 | **图像+状态+语言指令** | 动作块 |

> **ACT vs VLA 的本质区别**：不是"多一个输入"这么简单——ACT 是把视觉直接编码成动作的专用网络；SmolVLA 先用视觉-语言模型**理解"看到什么+指令要什么"**再生成动作。语言能力让一个模型能按指令**选择执行不同任务**（语言条件策略）。

## 3️⃣ 权重路径（当前已拥有）

| 模型 | 来源 | 路径 | 实测 |
|---|---|---|---|
| ACT（社区） | `ishandotsh/act_libero_spatial_test` | `datasets/hub/models--ishandotsh--act_libero_spatial_test/...` | 0/10（弱权重） |
| ACT（社区） | `Deepkar/libero-test-act` | `datasets/hub/models--Deepkar--libero-test-act/...` | 0/1（跨套件） |
| **SmolVLA（官方）** | `HuggingFaceVLA/smolvla_libero` | `datasets/hub/models--HuggingFaceVLA--smolvla_libero/...` | **80% ✅** |
| 基础 VLM | `HuggingFaceTB/SmolVLM2-500M-Instruct` | `datasets/hub/models--HuggingFaceTB--...`（已注入缓存） | 加载 OK |

> **lerobot 自带这两个模型类**（`ACTPolicy` / `SmolVLAPolicy`），推理只需 checkpoint 目录（含 config.json + model.safetensors + pre/post processor），无需额外安装模型代码。

## 4️⃣ 训练入口

```bash
# ACT 冒烟（已验证，50 步全管线 OK，~4.6 step/s）
python -m lerobot.scripts.lerobot_train --env.type=libero --env.task=libero_spatial \
  --dataset.repo_id=lerobot/libero --dataset.root=D:\Desktop\robot\datasets \
  --policy.type=act --policy.push_to_hub=false \
  --output_dir=outputs/train/libero_act_smoke --steps=50 --batch_size=2 \
  --eval_steps=0 --env_eval_freq=0 --wandb.enable=false

# SmolVLA 训练（官方教程路线，需较长预算）
# 见 https://github.com/huggingface/lerobot/blob/main/docs/source/smolvla.mdx
```

## 5️⃣ 推理（闭环）

```bash
# 官方评估（Windows 必须带两个参数，否则挂起）
python -m lerobot.scripts.lerobot_eval --env.type=libero --env.task=libero_spatial \
  --env.task_ids=[0] --env.max_parallel_tasks=1 --eval.use_async_envs=false \
  --eval.batch_size=1 --policy.path=<权重目录> --eval.n_episodes=10

# 自写推理脚本（ACT/SmolVLA 通用，含语言指令注入）
python inference_libero.py --policy-path <权重目录> --task libero_spatial --task-id 0 \
  --n-episodes 3 --outdir outputs/rollout_libero
```

## 6️⃣ 仿真（是什么 + 怎么实现）

- **没有"数据集的仿真模型"**——仿真环境是 **LIBERO 官方环境**（基于 robosuite），数据集与仿真解耦：
  1. **任务定义**：BDDL 文件（`libero/libero/bddl_files/`）描述每个任务的物体/布局/目标
  2. **环境工厂**：`robosuite` 按 BDDL 组装厨房场景 + Franka 机械臂 → 编译成 **MuJoCo 模型（XML）**
  3. **物理**：MuJoCo 引擎步进（20Hz 控制）
  4. **观测**：`OffScreenRenderEnv` 渲染 2 路相机 → 图像
  5. **初始状态**：用数据集的 `init_states` 复现每个 episode 的起始位形
- 本机实现细节：`lerobot/envs/libero.py` → `create_libero_envs` → robosuite `OffScreenRenderEnv`（bddl + 资产在 `~/.cache/libero/assets`，已下载）

## 7️⃣ 分析与结论

- **SmolVLA 80% vs 社区 ACT 0%**：语言条件让 VLA 在任务切换上有本质优势；社区 ACT 权重本身是 test 仓库（弱），不代表 ACT 上限
- **Windows 兼容性**：LIBERO 官方仅支持 Linux；本机经 6 处补丁跑通（见 `setup_windows_patches.py`），评估需 `max_parallel_tasks=1 + use_async_envs=false`
- **已知问题**：libero_10 套件评估挂起（环境直测正常，评估代码路径待排查）
- **后续**：扩展评估到全部 task0-9 / 其他套件；SmolVLA 训练教程

---
*进度详见 `PROGRESS.md`；可运行命令见 `commands.json`（GUI 直接执行）；学习 Notebook：`notebooks/01_LIBERO_环境与数据学习.ipynb`*

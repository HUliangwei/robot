# Roadmap：可复现的「数据集 + 仿真环境」项目调研

> 调研时间：2026-08-17 ｜ 目标：在 PushT 复现之后，挑选**本机（RTX 4060 Laptop 8GB / Windows）可跑、有数据集、与 MuJoCo/LeRobot 生态契合**的下一个项目。

## 对比表

| 项目 | 物理引擎 | 数据集 | 框架生态 | 本机可行性（8GB GPU） | 推荐度 |
|---|---|---|---|---|---|
| **LIBERO** | ✅ MuJoCo | ✅ HF 有（lerobot 集成） | ✅ **LeRobot 官方支持**（`lerobot.envs.libero`，0.6.1 已内置） | 高（ACT/pi0 均可训） | ⭐⭐⭐⭐⭐ |
| **SimplerEnv** | ✅ MuJoCo | ✅ Google Robot / WidowX+Bridge | 偏 VLA（RT-1/Octo/OpenVLA） | 中低（OpenVLA 7B 推理超显存；RT-1 可） | ⭐⭐⭐ |
| **ManiSkill** | ❌ SAPIEN（非 MuJoCo） | ✅ 大规模示范 | 独立框架（ManiSkill-Learn） | 中（GPU 并行仿真但引擎不同） | ⭐⭐ |
| **robomimic** | ✅ MuJoCo（旧版） | ✅ lift/can/tool 等 | 独立框架（PyTorch） | 中（学习价值高，但非 lerobot 生态） | ⭐⭐⭐ |

## 1. LIBERO（首选）— MuJoCo 机械臂操作基准

- 仓库：https://github.com/Lifelong-Robot-Learning/LIBERO
- 为什么适合你：
  - **MuJoCo** 物理引擎（与你的 PushT 复现同一引擎）；
  - **LeRobot 官方支持**：`lerobot/envs/libero.py` 已在你装的 0.6.1 里（前面调研已确认），可用 `--env.type=libero` 直接训练/评估；
  - 数据集在 HF（LIBERO-10/90 四个套件），无需自采；
  - 任务：桌面机械臂抓取/放置/开门等，观测 = 3 视角图像 + 状态，动作 = 7-DoF + 夹爪；
  - 规模适中：LIBERO-Spatial/Temporal 适合 8GB 显卡训练 ACT。
- 上手路径：`docs/工作流_从数据到推理.md` 的框架完全适用（换数据集/环境即可）。

## 2. SimplerEnv — VLA 在 MuJoCo 中的评估

- 仓库：https://github.com/simpler-env/SimplerEnv
- 特点：把真实机器人策略（RT-1 / RT-1-X / Octo / OpenVLA）放进 MuJoCo 仿真评估，覆盖 Google Robot、WidowX+Bridge 等设置。
- 评估：本机适合跑 **RT-1（~35M 参数）** 级别；**OpenVLA（7B）推理需要 >16GB 显存**，本机 8GB 无法直接跑（可量化/CPU 降级，不推荐）。
- 定位：等你进入 VLA 阶段（LLM/VLM 驱动的操作）再考虑；数据格式与 lerobot 不同，需适配。

## 3. ManiSkill — GPU 并行操作基准（注意引擎不同）

- 仓库：https://github.com/haosulab/ManiSkill（ManiSkill3）
- 特点：GPU 并行 SAPIEN 仿真 + 大规模专家示范；RL 与模仿学习皆可。
- 注意：**引擎是 SAPIEN 不是 MuJoCo**——与你当前 MuJoCo 学习主线不同，可作为扩展视野的选择，但优先级低于 LIBERO。

## 4. robomimic — 经典模仿学习基准（学习价值高）

- 仓库：https://github.com/ARISE-Initiative/robomimic
- 特点：MuJoCo 任务（lift/can/tool/assembly）+ 预生成数据集 + 大量基线（BC/BC-RNN/HBC 等）。
- 定位：适合系统学习模仿学习算法对比；非 lerobot 生态，代码风格较旧。

## 建议路线

```
当前：PushT（2D 平面推送）✅
  ↓ 下一个
LIBERO（MuJoCo 桌面机械臂 + LeRobot 官方支持）✅ 推荐
  ↓ 之后
SimplerEnv（VLA 评估，需先升级显存/或只跑 RT-1）
ManiSkill（若对 GPU 并行 RL 好奇）
```

## 决策点（需你确认后启动）

- [ ] 是否以 **LIBERO** 为下一个项目？（我可以按本工作流模板为其建 `workspace/libero/` 项目骨架）
- [ ] 更想先学 **VLA**（SimplerEnv/OpenVLA）还是 **模仿学习基线对比**（robomimic）？

---

## 补充：LIBERO 是什么 + VLA 学习路线（2026-08-17 追加）

### LIBERO 是什么

**LIBERO 不是模型，是「任务基准 + 数据集」**（LifeLong Robot Learning Benchmark）：

- 内容：**130 个桌面机械臂操作任务**，4 个套件——LIBERO-Spatial（空间泛化）/ LIBERO-Object（物体泛化）/ LIBERO-Goal（目标泛化）/ LIBERO-100（长期任务，100 个）；
- 环境：模拟厨房，**Franka 机械臂，MuJoCo 物理引擎**（与你的 PushT 同一引擎）；
- 数据：官方提供**专家示范数据集**（HF 可下载），观测 = 3 视角图像 + 机器人状态，动作 = 7-DoF + 夹爪；
- 用法：在数据集上训练模仿学习策略（ACT / BC-Transformer / Diffusion Policy 等），然后在仿真里评估成功率；
- 与你生态的契合：**LeRobot 0.6.1 已内置 LIBERO 环境**（`lerobot/envs/libero.py`），可直接 `--env.type=libero` 训练/评估——框架零改动。官方文档：https://github.com/huggingface/lerobot/blob/main/docs/source/libero.mdx

### VLA（Vision-Language-Action）是什么

**VLA = 把 LLM/VLM 的视觉-语言理解接到动作输出**：输入（图像 + 语言指令）→ 输出（机器人动作）。代表：

| 模型 | 参数量 | 特点 | 你的 8GB 显卡 |
|---|---|---|---|
| RT-2 | ~55B | Google 首创，闭源 | ❌ 不可能 |
| OpenVLA | 7B | 开源最流行，动作 token 化 | ⚠️ 需量化 + 极紧（~18GB 才舒服） |
| Pi-0 | 3B | 流式动作，物理灵巧 | ⚠️ 紧（可量化尝试） |
| **SmolVLA** | ~0.5-1.6B | **LeRobot 官方支持**，轻量开源 | ✅ 最现实 |

### 建议的 VLA 学习路线（由轻到重）

```
1. 现在：LIBERO + ACT（沿用 PushT 技能，动作=关节位置，理解模仿学习） ✅ 可行
2. 下一步：LIBERO + SmolVLA（第一个真正的 VLA：视觉+语言指令→动作；LeRobot 文档有教程） ✅ 本机可行
3. 进阶：OpenVLA（需 >16GB 显存：云 GPU / 量化推理 / 或换卡）
4. 前沿：Pi-0 / RT-2 论文精读（不一定要本机跑）
```

> 关键认知：**VLA 的难点在「多模态理解 + 动作生成」的联合训练与数据规模**，但推理原理仍是 `obs + 指令 → 策略 → action`——你已掌握的闭环框架直接适用。

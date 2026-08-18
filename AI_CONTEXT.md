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
│   └── pusht/  小项目：PushT × LeRobot × MuJoCo
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

**小项目 1：PushT（pusht）— 主线完成，物理保真已修复** ✅
- 自建 MuJoCo PushT 环境（语义与 gym_pusht 1:1 对齐）✅
- 双环境（官方 pymunk / MuJoCo）ACT 闭环推理跑通 ✅
- 自训 ACT 25k 步（l1=0.12，用户要求停止训练）✅
- 文档/可视化/GitHub 推送 ✅
- 小项目 README（个人网站展示用）+ PROGRESS（含残余问题记录）✅

**小项目 2：LIBERO（workspace/libero/）— 全链路打通，SmolVLA 评估 80% 成功** 🎉
- 骨架（README/PROGRESS/commands/verify_env.py/setup_windows_patches.py）✅
- **环境验证通过**（exit 0）；**数据集 `lerobot/libero` 下载完成**（1.9GB，1693 episodes/273465 帧/双相机 256²/action[7]∈[-1,1]，**HF 需走代理** `HTTP_PROXY=127.0.0.1:7897`）
- **训练冒烟通过**（50 步 4.6 step/s）；**评估冒烟通过**（1 局 33.7s）
- **官方 SmolVLA 评估：LIBERO-Spatial task0 成功率 80%（4/5）**——VLA 闭环验证成功，视频在 `outputs/eval_smolvla_spatial_t0/`
- 社区 ACT（test 仓库）0/10、0/1（弱权重）；libero_10 评估挂起待排查
- **Windows 关键坑**：① 评估必须 `--env.max_parallel_tasks=1 --eval.use_async_envs=false`（AsyncVectorEnv 会挂起）② `~/.libero/config.yaml` 需预建 ③ robosuite 补丁见 setup_windows_patches.py ④ SmolVLA 推理 ~1.4s/步（慢但正常）⑤ 大模型下载用 hf-mirror（36MB/s）+ 注入 HF 缓存（snapshot 目录）
- 学习 Notebook：`notebooks/01_LIBERO_环境与数据学习.ipynb`（8 节）；推理脚本：`inference_libero.py`

**RL：SAC on PushT 全链路打通（2026-08-18）** 🎉
- **lerobot 0.6.1 的 HILSerl RL 管线（learner gRPC + actor）成功驱动 gym-pusht**：双进程冒烟 600 交互步 → SAC 训练 ~20 步/s → checkpoint 000200/000400/000600/000800 落盘 ✅
- 冒烟 800 优化步的权重评估：ep0 覆盖率 26.6%（欠训练但证明管线有效）；评估脚本 `rl_scripts/eval_sac_pusht.py` 生成 metrics.json + 视频
- **归一化设计（关键）**：gym-pusht action 是 [0,512] 像素目标位置，tanh 高斯策略输出 (-1,1)；dataset_stats 用 action min=256/max=512（`x=t*256+256 ∈ (0,512)`）保证尺度一致；replay buffer 存归一化 action（PushtTeleopActionProcessorStep 存入 teleop_action）
- **Windows 补丁（setup_windows_patches.py §5，全部幂等）**：① train.py validate 允许 dataset=None（RL 无离线数据）② gym_manipulator 支持 pusht env（make_robot_env/make_processors + teleop_action 步骤）③ actor validate 容忍 output_dir 已存在 + 补齐 algorithm.policy_config ④ transport torch.load weights_only 回退（transition 含 numpy 标量）⑤ **ReplayBuffer 默认关 DRQ**（torch.compile+triton 在 Windows 不可用，producer 线程静默崩溃导致训练死锁——最难排查的一坑，faulthandler 定位）
- **启动方式**：`python rl_scripts/run_sac_pusht.py --config_path rl_configs/sac_pusht_smoke.json --clean`（learner→等端口→actor→等完成→冲刷→落盘→清理；子进程 stdout 直接写文件避免管道死锁）
- 配置文件：`rl_configs/sac_pusht_smoke.json`（smoke 600 步 / short 3000 / full 10 万可调）

**GUI v3 RL 工作台（2026-08-18）**：新增「🎮 强化学习」视图（预设 冒烟/短训/正式 + 高级参数 → 生成配置 → 监督运行 → 训练运行列表 + checkpoint 评估表单 + 实时推流）；「🚀 推理」表单统一化（任务预设 chips 一键填充环境/任务/输出目录，LIBERO 参数收进折叠区）；后端 /api/rl /api/rl_eval /api/rl_runs。

**项目改名 + GUI v4（2026-08-18）**：`embodied_learning` → **`pusht`**（按任务归类）；SAC RL（rl_scripts/rl_configs/冒烟产物）从 libero 并入 pusht（`workspace/pusht/rl_scripts/`、`rl_configs/`、`outputs/train/sac_pusht_smoke/`）。GUI v4：① 项目首页展示**已跑通的训练-推理工作流**（pusht=ACT/SAC，libero=ACT/SmolVLA）——每步含义讲解（workflows.json）+ 可切换最新权重（「用于推理/评估」按钮）+ 对应推理视频 + 命令；② 模型页**两级分类**（模型架构 ACT/SAC/SmolVLA/VLM → 权重实例），权重带**功能注释**（weights.json/内置 KNOWN_REPO_NOTES）+ **时间戳**；③ 强化学习页按 **SAC 流程**（采样→训练→评估）设计训练+推理一体页；④ 项目报告按**工作流分区**（介绍/PROGRESS/全部文件/产出/指标——pusht 现有 19 项评估记录）。数据文件：`pusht/workflows.json`、`pusht/weights.json`、`libero/workflows.json`、`libero/weights.json`。

**结构整理**：删除空目录（notes/datasets/examples/models/.vscode）、陈旧 rollout（rollout_mujoco/rollout_official*/lemon/smoke）、顶层 outputs/my_rollout；保留证据视频与权重。
**GUI 升级**：新增「全部文件」浏览（项目内所有文件可查看：md/ipynb/代码/媒体）+ 全局 README/笔记/文档导航；修复 AI_CONTEXT 导航链接（原路径 404）；**项目页顶部展示 README 项目介绍**；**命令输出实时流式**（PYTHONUNBUFFERED=1，修复块缓冲导致 GUI 读不到输出的问题）。
**README 结构化**：两个小项目 README 统一为 7 段式（数据集/模型架构/权重路径/训练入口/推理/仿真与推理示例/分析），GUI 项目页直接渲染，便于学习与个人网站展示。
**GUI v2 工作台（2026-08-17）**：新增「工作台」五大视图——📊数据集（扫描 HF 缓存+本地格式，可导入）、🧠模型与架构（列出全部权重+ACT/SmolVLA 架构图+config 详情）、🎓训练（表单生成 lerobot_train 命令）、🚀推理·仿真（环境/权重/局数表单，完成后自动展示视频）、📈分析（metrics 总览）；＋新建小项目（生成 README/PROGRESS/commands 骨架）；所有操作在控制台实时回显执行的命令（PYTHONUNBUFFERED）。后端新增 /api/datasets /api/models /api/models_config /api/analysis /api/train /api/infer /api/create_project /api/datasets/import。后续规划：仿真环境 RL（强化学习）模块。

**关键结果**：**官方环境成功已复现**——社区 aadarshram ACT @seed1000 ep0 覆盖率 0.9534（>0.95，134 步完成，成功率 1/5）；MuJoCo 环境最高 0.865。自训 25k 与社区权重水平相当；均未达高成功率（欠训练，与管线无关）。

**「推动后立刻停下」物理修复（2026-08-17）**：用户对比视频发现官方环境推完即停、MuJoCo 却一直滑/转。定量诊断定位到根因——T 块 COM 在推点下方，每次推都是偏心踢击；pymunk 刚性接触瞬间耗散踢击能量，MuJoCo 软接触不耗散导致块绕推头圆柱持续旋转飞走（偏心推旋转 62.7° vs 官方 10.4°）。修复：块关节 damping=5 + agent/块摩擦 2 + 墙摩擦 0（对齐 pymunk）。修复后偏心推旋转 13.1°、推完立刻静止；rollout 奖励总和 10.75→21.93（+104%，块能停住保持覆盖率），成功率仍 0/10。详见 `note/04_MuJoCo_PushT_复现总结.md` §3.6。

**残余旋转（未解决，已记录）**：真实策略 rollout 中 MuJoCo 块仍比官方转得多（累计 380° vs 56°，自旋事件 80 vs 12）。已排除：惯量 3000（更差 412°）、接触刚度 solref、时间步、推得更狠、elliptic 摩擦锥+μ3（更差 776°）。结论为 MuJoCo 软接触模型与 pymunk 刚性接触的整体差异，单点参数不敏感；完整记录在 `workspace/pusht/PROGRESS.md`。

## 5. 常用入口命令

```bash
# GUI 仪表盘（进度/命令/视频可视化）
python gui/server.py                # 打开 http://127.0.0.1:8765

# PushT 推理（MuJoCo / 官方）
python workspace/pusht/mujoco_basics/pusht/run_pusht_rollout.py \
    --env mujoco --n_episodes 3 --policy-path <权重目录> --outdir outputs/x

# 训练 ACT（完整命令见 workspace/pusht/commands.json）
```

## 6. 重要约束（AI 必读）

1. **git 推送需代理**：仓库配置了 `http.proxy=http://127.0.0.1:7897`（国内访问 GitHub）。
2. **不入库**：`envs/ datasets/ tool/ archives/`、`*.safetensors`、`**/checkpoints/`、`**/outputs/train/`（权重超 GitHub 100MB 限制）。
3. **换对话接续**：新对话 → 读本文件 → 读 `workspace/pusht/PROGRESS.md` → 继续。
4. **改文件前先读**；命令优先用 `envs\lerobot-win\python.exe`。
5. **HF 下载经验（2026-08-17，重要）**：
   - HF 下载也需代理：`$env:HTTP_PROXY="http://127.0.0.1:7897"; $env:HTTPS_PROXY=...`
   - `snapshot_download`/`hf_hub_download` 会间歇性卡死（xet/连接问题）；大文件改用 `curl -L --proxy http://127.0.0.1:7897 -C - -o <file> https://huggingface.co/<repo>/resolve/main/<file>`
   - 必要时 `HF_HUB_DISABLE_XET=1`（有的仓库禁用后反而快）
   - **下载与评估/训练不可并行**（会互相卡网络导致评估挂起）
   - 注意仓库总大小：SmolVLM2-500M-Instruct 仓库 7.9GB（含 5GB ONNX），只需 model.safetensors + 配置文件

## 7. 下一步 / 待办（2026-08-18）

- [x] RL 工作台：SAC on PushT 全链路冒烟（600 步训练 → checkpoint → 评估）
- [ ] SAC 正式训练：短训 3000 步起，观察覆盖率曲线；目标 >95% 成功率（预算 10 万步级）
- [ ] RL checkpoint 评估接入分析视图（metrics 已在 outputs/eval/sac_pusht_*）
- [ ] （物理待续）PushT MuJoCo 残余旋转：试 solimp 曲线 / 或接受差异专注策略侧
- [ ] 网页端策略服务化（FastAPI 骨架见 docs/工作流 §6）
- [ ] gui 仪表盘后续增强（如在线 rollout 流式预览）

## 8. 更新日志

- 2026-08-17：创建；PushT 主线完成、GitHub 推送、gui/docs/AI_CONTEXT 建立
- 2026-08-17：§4 追加「推动后立刻停下」物理修复（块关节阻尼 5 + 摩擦对齐 pymunk），详见 note 04 §3.6
- 2026-08-17：LIBERO 立项（骨架 + egl_probe stub 安装方案）；文件结构整理（删空目录/陈旧 rollout）；GUI 升级（文件浏览 + 全局导航）；残余旋转诊断记录（排除 5 类假设）
- 2026-08-17：LIBERO 全链路打通（数据/训练/评估冒烟）；SmolVLA 官方模型评估 80% 成功（hf-mirror 下载基础模型 + 注入缓存）
- 2026-08-17：GUI 命令输出实时流式修复（PYTHONUNBUFFERED）；项目页展示 README；两个小项目 README 结构化（数据/模型/权重/训练/推理/仿真/分析）
- 2026-08-18：**SAC on PushT RL 全链路打通**（HILSerl learner+actor 驱动 gym-pusht，600 步冒烟出 checkpoint）；新增 5 个 Windows 补丁（RL 相关）；GUI v3（RL 工作台 + 推理表单统一预设）；RL 评估脚本
- 2026-08-18：**项目归类重构 + GUI v4**——`embodied_learning` 改名 `pusht`，SAC RL 从 libero 并入 pusht；项目首页工作流卡片（ACT/SAC 流程讲解+权重切换+视频+命令）；模型页两级分类+权重注释/时间戳；RL 页按 SAC 流程重设计；项目报告按工作流分区（19 项指标）

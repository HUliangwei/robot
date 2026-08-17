# PROGRESS — libero（LIBERO 机械臂操作基准 × LeRobot）

> 项目进度记录。**规则**：每次有实质进展后更新「当前状态」并加一条「更新日志」；AI 会话结束时也应在此记录。

## 项目一句话

用 LeRobot 内置的 LIBERO 环境（Franka + MuJoCo）从模仿学习（ACT）进阶到 VLA（SmolVLA），把 PushT 的闭环技能搬到 3D 桌面操作。

## 当前状态（2026-08-17 立项）

| 阶段 | 状态 | 说明 |
|---|---|---|
| 项目骨架 | ✅ | README / PROGRESS / commands.json / verify_env.py / setup_windows_patches.py |
| 环境（libero 栈） | ✅ 已装 | libero 0.1.1 + robosuite 1.4.0 + robomimic 0.2.0（egl_probe stub + --no-deps，见下方补丁） |
| **环境验证** | ✅ **通过** | `verify_env.py` exit 0：套件列表 OK、LIBERO-Spatial task0 构建 + 随机 3 步 OK（obs=pixels） |
| **数据集** | ✅ 已下载 | `lerobot/libero`（1.9GB，457 files，公开非 gated；经代理下载） |
| **数据集结构** | ✅ 已了解 | 1693 episodes / 273465 帧 / fps 10；双相机 image+image2 [3,256,256]；action [7] ∈[-1,1] 相对关节增量；state [8]；含 language_instruction |
| 学习 Notebook | ✅ | `notebooks/01_LIBERO_环境与数据学习.ipynb`（环境+数据+闭环骨架+训练/评估命令） |
| **ACT 训练冒烟** | ✅ **通过** | 50 步全管线 OK（~4.6 step/s，checkpoint 已存） |
| **评估冒烟** | ✅ **通过** | 1 局闭环 OK（成功 0% 符合预期=未训练；Windows 需 `--env.max_parallel_tasks=1 --eval.use_async_envs=false`） |
| **预训练权重推理** | ✅ 流程跑通 | ishandotsh ACT：10 局 0/10（机器人真实运动，权重弱）；Deepkar ACT：spatial 0/1；SmolVLA：管线就绪（基础模型下载中） |
| ACT 正式训练 | ⏳ 待做（用户暂定用预训练权重，不训练） | LIBERO-Spatial：10k≈1-2h / 25k≈3-6h |
| SmolVLA（VLA 学习） | 🔄 准备中 | 基础模型 SmolVLM2-500M 下载受网络限制（curl 断点续传中） |

## 环境验证记录

- `lerobot.envs.libero` 模块：✅ 存在（lerobot 0.6.1 内置）
- **2026-08-17 验证通过**：`python verify_env.py` → 套件 `libero_10/100/90/goal/object/spatial` 全部可用；LIBERO-Spatial task 0（SyncVectorEnv ×1）reset + 3 随机步无报错，obs keys=['pixels']
- **Windows 安装方案（关键）**：`pip install libero` 原生失败（egl_probe 需编译 C 扩展无 wheel）→ 用 `setup_windows_patches.py` 幂等打补丁：
  1. egl_probe 本地 stub（robomimic 仅 EGL 渲染路径懒加载）
  2. robosuite/robomimic/libero `--no-deps` 安装（避免升级 numpy/transformers）
  3. robosuite 补丁：`/tmp/*` → tempfile（3 处）、复制 `mujoco.dll` 到 robosuite/utils、`MUJOCO_GL: egl→wgl`、`mj_fullM` 新 API + MjData 解包
  4. LIBERO 配置初始化（`workspace/libero/.libero/config.yaml`，datasets → `D:\Desktop\robot\datasets`）
- 注意：robosuite 每次启动有 macros 提示（无害）；重装/换机器后重跑 `setup_windows_patches.py` 即可

## 待办 / 下一步

- [x] ~~跑通 verify_env.py~~ ✅ 2026-08-17 通过
- [x] ~~下载 lerobot/libero 数据集~~ ✅ 2026-08-17（1.9GB，需代理）
- [x] ~~数据集结构了解~~ ✅（Notebook 01 已记录）
- [x] ~~ACT 冒烟训练（50 步）~~ ✅ 2026-08-17（4.6 step/s，checkpoint 已存）
- [x] ~~评估冒烟（1 局）~~ ✅ 2026-08-17（Windows 需 max_parallel_tasks=1 + use_async_envs=false）
- [x] ~~预训练 ACT 权重推理~~ ✅ 2026-08-17（ishandotsh 0/10 / Deepkar 0/1，均为弱权重；流程本身验证 OK）
- [ ] SmolVLA 官方模型评估（基础模型 SmolVLM2 下载中；注意：评估与下载不可并行，会互相卡网络）
- [ ] 排查 libero_10 套件评估挂起问题（spatial 正常，libero_10 挂）
- [ ] ACT 正式训练（可选，用户暂定不训练）
- [ ] 进阶 SmolVLA 教程（lerobot 文档：smolvla）

## 常用命令

见同目录 `commands.json`（GUI 仪表盘也读取它）。

## 更新日志

- 2026-08-17：立项，创建骨架（README/PROGRESS/commands/verify_env）；`pip install libero` 启动
- 2026-08-17：**环境验证通过**——egl_probe stub + --no-deps + robosuite Windows 补丁（固化到 setup_windows_patches.py）；`verify_env.py` exit 0
- 2026-08-17：**数据集下载完成**（`lerobot/libero` 1.9GB，HF 需走代理 HTTP_PROXY=127.0.0.1:7897）；结构学习（Notebook 01）
- 2026-08-17：**训练+评估冒烟全部通过**（50 步训练 4.6 step/s；1 局评估 33.7s）；完整闭环在 Windows 验证成功
- 2026-08-17：**预训练权重推理**——ACT 两枚（0/10、0/1，弱权重）；SmolVLA 依赖装好（transformers 5.5.4），基础模型下载受网络限制（curl 续传方案），libero_10 评估挂起待排查

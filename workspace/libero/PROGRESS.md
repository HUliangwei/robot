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
| 数据集下载 | ⏳ 待做 | HF `lerobot/libero_*`（assets 已自动下载到 ~/.cache/libero/assets） |
| ACT 训练 LIBERO-Spatial | ⏳ 待做 | 沿用 PushT 技能 |
| SmolVLA（VLA 学习） | ⏳ 待做 | 视觉+语言指令→动作 |
| 文档/展示 | ⏳ | README 已建，待结果更新 |

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
- [ ] 下载 LIBERO-Spatial 数据集并 `lerobot-info` 查看结构
- [ ] 官方样例：跑通 ACT 训练（对照 PushT 训练命令）
- [ ] 评估：官方 checkpoint 在 LIBERO 的成功率基线
- [ ] 进阶 SmolVLA 教程（lerobot 文档：smolvla）

## 常用命令

见同目录 `commands.json`（GUI 仪表盘也读取它）。

## 更新日志

- 2026-08-17：立项，创建骨架（README/PROGRESS/commands/verify_env）；`pip install libero` 启动
- 2026-08-17：**环境验证通过**——egl_probe stub + --no-deps + robosuite Windows 补丁（固化到 setup_windows_patches.py）；`verify_env.py` exit 0

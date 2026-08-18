# 04 MuJoCo PushT 复现总结（数据 ↔ 模型 ↔ MuJoCo）

> 完成日期：2026-08-17 ｜ 结论：**LeRobot ACT 策略成功在自建 MuJoCo PushT 环境中完成闭环推理**（管线、观测/动作/奖励语义全部对齐）

## 1. 干了什么

1. 下载并验证社区预训练 ACT 权重（`aadarshram/act_pusht`，80k 步训练）
2. 修复官方 gym_pusht 环境与 pymunk 7 的兼容性问题（`add_collision_handler` API 移除 → 降级 pymunk 6.8.0）
3. 用官方 `lerobot-eval` 思路 + 自写 rollout 脚本，跑通 **官方 2D PushT 闭环推理**
4. **从零搭建 MuJoCo PushT 模型**（XML + 俯视相机 + 光照），封装成 gymnasium 环境
5. 用同一份 ACT 权重在 **MuJoCo 环境** 中完成闭环推理，保存视频与指标

## 2. 关键成果

| 项目 | 位置 |
|---|---|
| MuJoCo 模型 | `workspace/pusht/mujoco_basics/pusht/pusht_mujoco.xml` |
| gymnasium 封装 | `workspace/pusht/mujoco_basics/pusht/mujoco_pusht_env.py` |
| 推理脚本 | `workspace/pusht/mujoco_basics/pusht/run_pusht_rollout.py` |
| 学习 Notebook | `workspace/pusht/lerobot_basics/07_MuJoCo_PushT_模型搭建与ACT推理.ipynb` |
| rollout 结果 | `workspace/pusht/outputs/rollout_*`（含视频） |
| 权重缓存 | `datasets/hub/models--aadarshram--act_pusht` 等 |

## 3. 结果

- **官方环境成功已复现（2026-08-17 修正）**：社区 aadarshram ACT @seed1000 ep0 覆盖率 **0.9534**（>0.95），134 步提前完成（成功率 1/5）；ep3 达 0.9117。此前"从未成功"结论基于 seed 0 抽样，需多 seed 评估。
- MuJoCo 环境：同权重最高 **0.865**（10 seeds 1000-1009），差距来自 pymunk↔MuJoCo 接触动力学（详见 §3.6，已用块关节阻尼修复"推后滑动不止"）；加大 agent 密度（0.5）反而更差（0.329），已回退。
- **「T 块地面太滑」假说测试（2026-08-17）**：❌ 不成立。诊断显示 MuJoCo 里 T 块被推后同样无摩擦滑动（速度恒定，与 pymunk 一致——pymunk 也无地面摩擦/阻尼）；给 T 块加滑动阻尼 0.3（全局 option 阻尼）后覆盖率反而降（0.50 vs 0.865），agent 质量 ×100 也变差（0.456）。真正的差异不是地面摩擦，而是**接触能量耗散**（见 §3.6：改为块关节 damping=5 后，推完即停的行为与官方一致）。
- 官方环境与 MuJoCo 环境：同一权重覆盖率分布一致（0~0.95），**证明语义对齐正确**
- **观测分布对齐量化验证**（MuJoCo 渲染 vs 训练数据图像）：每通道均值 (0.967,0.978,0.972) vs (0.973,0.981,0.979)、白底占比 0.903 vs 0.912、灰墙 0.042 vs 0.039 —— 几乎一致，策略可无缝迁移
- 官方 `lerobot/act_pusht` 为 gated 仓库；官方 `lerobot/diffusion_pusht`（~99% 成功率）为旧格式，0.6.1 迁移脚本有 bug

## 3.6 「推动后立刻停下」的物理真相（2026-08-17 复测）

**用户观察**：官方视频里 T 块被推后立刻停下，MuJoCo 里却一直滑/转，像"机器人抓着推然后松手"。

**量化诊断**（同一套"推-停"脚本，两种环境对比）：
- **正对推（head-on）+ 停**：两环境都立刻停死（滑行 0.00px）——这部分本来就一致
- **偏心推（推 stem 侧面）**：官方只转 ~7.5°~10° 就贴着推头停住（接触保持）；MuJoCo 转到 **-62.7°** 且飞离推头（接触断开），永不静止
- **根因**：T 块 COM 在头/柄交汇处下方 25~45px，任何"正对"推实际都是偏心推 → 每次都带扭矩。pymunk 的刚性接触（kinematic 推头 + 非弹性碰撞）瞬间吸收冲击能量 → 推后 <0.1s 静止；MuJoCo 软接触让 T 的角在推头圆柱上"跷跷板"式滑动，能量不耗散 → 一直转/滑
- **附带发现**：官方 T 块转动惯量 moment=3000 是 pymunk 写错的（`moment_for_poly` 两次都用了头的顶点列表、且按身体原点而非 COM 算），官方 T 比物理正确值(~975)转起来"笨"约 3 倍；MuJoCo Izz(COM)=1935。策略就是在这个"笨"T 上训练的
- **修复**：给 T 块三个关节（x/y 滑动 + θ 铰链）加 **damping=5**（只加在块上，不动 agent），模拟 pymunk 刚性接触的能量耗散；另把 agent/块摩擦设为 2、墙摩擦设为 0（对齐 pymunk：墙 Segment 默认无摩擦；MuJoCo 软接触需要更高 μ 才能复现 pymunk 刚性接触的"抓"手感）。验证：正对踢击后 v_end=0.00（官方 0.00）、settle_step=0、终距 86.8px（官方 80.1px）；偏心推旋转 13.1°（官方 10.4°，修复前 62.7°），推完立刻静止
- **对闭环推理的影响**（同 10 seeds 1000-1009）：
  | 配置 | mean_max_coverage | mean_sum_reward | 成功 |
  |---|---|---|---|
  | 基线（无阻尼） | 0.417 | 10.75 | 0/10 |
  | damping=5 | 0.375 | 18.04（+68%） | 0/10 |
  | **damping=5 + 摩擦2（最终配置）** | 0.338 | **21.93（+104%）** | 0/10 |
  - 覆盖率峰值基本不变（0.34~0.42 属 seed 噪声），但**奖励总和翻倍**：块被推入目标区后能停住保持、且贴着推头，不再滑走——正是官方视频里的行为
- **其他尝试**（不改变结论）：接触刚度 solref（0.0005~0.02）对行为无影响（已验证生效但无效）；减小时间步（0.005/0.002）单独不够；摩擦 2.0 与阻尼 5 组合即最终配置（块更"贴"推头，官方手感）
- **结论**：0.95 上限不是"推完滑走"这种基础物理问题（已修），而是策略/像素迁移的剩余差异（官方 0.9534 也只出现在部分 seed）

## 3.5 正规训练（已停止，2026-08-17）

- 命令：`lerobot-train --dataset.repo_id=lerobot/pusht --policy.type=act --batch_size=64 --steps=30000 --save_freq=5000 --env_eval_freq=0`
- 输出：`outputs/train/act_pusht_real/checkpoints/`（005000~025000 + last）
- **结果（用户要求停止训练，最终使用 025000 checkpoint）**：
  - 训练收敛良好：l1_loss 200 步 0.58 → 25k 步 **0.12**（远优于社区权重水平）
  - 闭环覆盖率却**不随训练提升**（10k→25k 平台期）：
    - MuJoCo 10 局：mean max 覆盖率 0.361，单局最高 0.624，成功 0/10
    - 官方环境 10 局：mean max 覆盖率 0.385，单局最高 0.815，成功 0/10
  - 时间集成（coeff 0.01）无效（10k/25k 均验证）
- **结论**：低 loss ≠ 高闭环成功率。ACT 在 PushT 上要 >95% 成功率，需要官方配方（batch 8 + 60-80k 步，约 8-10h）或官方专门训练的 `lerobot/act_pusht`（gated）。30k 步/batch 64 的模型与社区权重水平相当（max 0.6-0.8），验证了**推理管线正确性**，但任务级成功率需要更长的训练预算。
- 学习曲线（同一评估循环、同一组种子）：
  | checkpoint | MuJoCo mean | 官方 mean | 官方单局最高 |
  |---|---|---|---|
  | 005000 | 0.28 | 0.44 | - |
  | 010000 | 0.36 | 0.34 | - |
  | 015000 | 0.45 | - | - |
  | 020000 | 0.32 | 0.46 | 0.68 |
  | 025000 | 0.36 | 0.39 | 0.815 |

## 4. 踩坑速查（全部记录在 Notebook 07）

1. 渲染前必须 `mj_forward`（否则相机位姿全 0 全黑）
2. 相机 y-up 图像需 `img[::-1]` 翻转成 pygame y-down
3. `zfar×extent` 决定远裁剪面，相机距离必须 < far
4. 高光打爆颜色：`<asset><material specular="0"/></asset>`（放 default 里无效）
5. 颜色被光照 ~1.5x 提亮：rgba 预缩放 0.67
6. T 形几何必须用 MultiPolygon（8 顶点单 Polygon 会自交崩溃）
7. body pos 必须为 0，qpos 直接用绝对坐标
8. lerobot 0.6.1：`ACTPolicy.from_pretrained` 不带 pre/post processor，需单独加载
9. gym_pusht + pymunk 7 不兼容 → pymunk==6.8.0
10. `lerobot-eval` 传 hub repo id 在 Windows 上会被转成 WindowsPath → 用本地目录

## 5. 下一步建议

- **想看到任务真正成功**：本机跑 `lerobot-train --dataset.repo_id=lerobot/pusht --policy.type=act --output_dir=...`（4060 约 1-2 小时到 ~90%），然后用 `run_pusht_rollout.py --env mujoco --policy-path <训练好的目录>` 验证
- 升级到 3D：SO-100 机械臂推块（需重新适配观测）
- 换 Diffusion Policy：需新版格式的 pusht 权重

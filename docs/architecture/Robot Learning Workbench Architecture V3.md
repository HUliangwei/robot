# Robot Learning Workbench — Architecture V3

> **项目名**：Robot Learning Workbench（RLW）  
> **仓库**：当前继续使用 `HUliangwei/robot`，待 Workbench 核心稳定后再决定是否拆分独立仓库。  
> **定位**：面向机器人学习、VLA、模仿学习（IL）、强化学习（RL）与具身智能研究的 **Experiment Control Plane / Research Workbench**。  
> **核心目标**：统一管理 **实验定义 → 可复用资产 → 执行节点 → 训练 / 推理 / Rollout / 评测 → Artifact → Lineage → Compare / Iterate**，同时保留 LeRobot、StarVLA、vla-evaluation-harness 与自定义研究代码的原生能力。  
> **架构原则**：RLW 管实验、执行、资产、节点与追溯；不重新实现算法内部训练循环、仿真器内部逻辑或上游框架已经解决的问题。  
> **V3 状态**：本文件是后续实现的单一架构基线；Architecture V2 的有效内容已合并，本文件内部规则优先，不要求 Codex 再读取 V2。

---

# 0. Architecture V3 的核心变化

Architecture V3 以 Architecture V2 为基线，不改变 RLW “Experiment Control Plane” 的核心定位，但把 V2 中仍停留在概念层的部分补成可直接指导实现的 Architecture Specification。

V3 的新增硬约束：

1. **GUI 必须早于 Remote Compute / SSH Server 功能完成。**
   - GUI 用于理解项目当前进展、观察 Domain Model 是否合理、验证 Core/API 是否真正解耦。
   - GUI 本身只依赖 RLW API / Application Services，不拥有业务逻辑，因此后续增加服务器能力时不需要重写 GUI。
   - GUI 第一版重点是本地 Experiment / Run / Job / Artifact / Dataset / Provider 可视化，不等待远程执行完成。

2. **本地、服务器与 GitHub 的 Git-tracked Project 必须保持同构。**
   - `workbench/`、`gui/`、`architectures/`、`environments/`、`recipes/`、`configs/`、`scripts/`、`docs/`、`tests/`、接口定义、Schema、Provider Adapter 和 CLI/API/GUI 代码保持一致。
   - GitHub 是这一完整 Git-tracked Project 的代码与定义来源。
   - Local / Server 都 clone 同一仓库，并可 checkout 任意 exact commit。
   - 差异只允许存在于 **Git 不跟踪的机器本地状态和大型资产**：Dataset payload、Run payload、Artifact Replica、Provider env、cache、worktree、runtime state、secret、机器级 Node config 等。
   - 不允许维护“服务器版 RLW”“本地版 RLW”两套实现。

3. **正式统一研究对象语义：**
   ```text
   Experiment
       ↓
   Trial
       ↓
   Run
       ↓
   Job
       ↓
   ExecutionAttempt
   ```

4. **研究记录与运行时状态严格分离。**
   - `runs/` 保存可追溯、完成后近似不可变的 Research Record。
   - `.rlw/state/`、`.rlw/tmp/`、`.rlw/locks/` 保存机器本地、可变的 Runtime State。

5. **Filesystem Manifest 是可携带的研究事实记录；SQLite Catalog 是可重建索引。**
   - 一个 Run 不能因为 SQLite 丢失就失去解释能力。
   - Catalog 必须可通过文件系统重新构建、验证和修复。

6. **Artifact Replica、Job、ExecutionAttempt、Transfer 必须有明确生命周期与状态机。**

7. **Stage In / Stage Out 必须考虑原子性、Hash Verify、断点续传、失败恢复与幂等。**

8. **SSH 只是控制/传输通道，不能成为远程 Job 生命周期。**
   - Remote Job 必须 detached 执行并可在本地断线后继续。
   - 重新连接后可以通过 Remote RLW 查询 Job 状态与日志。

9. **Dataset 必须有 immutable revision / snapshot 语义。**

10. **引入 Storage Root、Environment Manager、CommandSpec、ResourceRequirement、NodeCapability、SecretRef、Schema Version 等基础抽象。**

11. **关键操作必须 recoverable + idempotent。**

12. **Compatibility Contract 分阶段实现，允许 `UNKNOWN`，不在 V0 过度建模。**

Architecture V3 的目标不是增加更多机器人算法，而是让 RLW 的核心控制平面在本地、GUI、远程执行、资产同步、失败恢复和版本演进方面具有明确而稳定的语义。

---

# 1. 项目不是“训练 GUI”

Robot Learning Workbench 不应该只是：

```text
Dataset
[Train]
[Inference]
[Evaluate]
```

如果最终只是一个方便点击 LeRobot 命令的网页，项目价值有限。

RLW 真正解决的是：

```text
Experiment Specification
+
Reusable Research Assets
+
Node-independent Execution
+
Provider Isolation
+
Artifact Identity / Replica
+
Experiment Lineage
+
Reproducibility
+
Local / Remote Compute
+
Evaluation / Compare
+
Research-oriented GUI
```

最终目标不是隐藏 LeRobot、StarVLA 或 vla-eval，而是给这些快速变化的生态建立一个稳定研究控制层。

---

# 2. 一句话定位

> **Robot Learning Workbench is an experiment control plane for reproducible robot-learning research. It manages experiments, execution, artifacts, provenance, nodes, and cross-provider workflows while preserving the native capabilities of LeRobot, StarVLA, vla-evaluation-harness, simulators, and custom research code.**

中文：

> **RLW 是机器人学习实验控制平面：统一描述实验、决定在哪里执行、管理输入与输出资产、记录完整实验来源，并通过薄 Adapter 编排不同机器人学习生态。**

---

# 3. RLW 的职责边界

## 3.1 RLW 负责什么

```text
WHAT to run
WHERE to run
HOW to execute
WITH WHAT assets
USING WHICH provider
WHAT artifacts were generated
HOW artifacts are related
CAN this experiment be reproduced
```

主要负责：

- Run / Experiment 定义
- Trial / Job / Attempt 追踪
- Node 管理
- Executor 管理
- Dataset / Checkpoint / Rollout / Report Artifact 注册
- Artifact Replica 管理
- Stage In / Stage Out
- 环境检查
- 兼容性验证
- Backend command / config resolution
- Exact Git Commit 执行
- Log / Job / GPU 状态
- 结果追溯
- Experiment Compare
- GUI / CLI 统一入口

---

## 3.2 RLW 不负责什么

RLW 不应该重新实现：

```text
ACT training loop
SmolVLA internals
StarVLA model construction internals
LIBERO physics
MuJoCo internals
vla-eval benchmark orchestration internals
RL replay/update loop
DAgger collection/update loop
SO-101 low-level driver internals
```

核心原则：

> **RLW 编排 coarse-grained research jobs，不进入算法内部 step。**

---

# 4. 上游生态职责

```text
LeRobot
  ↓
Dataset / standard Policy / hardware / standard training / inference

StarVLA
  ↓
VLA architecture research / controlled modular experiments

vla-evaluation-harness
  ↓
Benchmark model server / closed-loop evaluation / native result recording

Custom
  ↓
自定义算法 / 环境 / 模型 / 推理 / 评测

RLW
  ↓
Experiment / Node / Executor / Artifact / Lineage / GUI / CLI
```

Workbench 的价值不是重写这些框架，而是：

> **用稳定的 Control Plane 管理不稳定且不断演进的 Provider。**

---

# 5. 总体架构

RLW 采用五层结构：

```text
┌──────────────────────────────────────────────────────────┐
│ Experience Layer                                         │
│ CLI / FastAPI / React GUI                                │
├──────────────────────────────────────────────────────────┤
│ Control Plane / Application Layer                        │
│ Experiment / Trial / Run / Job / Attempt                 │
│ Validation / Planning / Lineage / Catalog Services       │
├──────────────────────────────────────────────────────────┤
│ Integration Layer                                        │
│ LeRobot / StarVLA / vla-eval / Custom Providers          │
├──────────────────────────────────────────────────────────┤
│ Execution Layer                                          │
│ LocalExecutor / SSHExecutor / Future SlurmExecutor        │
├──────────────────────────────────────────────────────────┤
│ Storage & Runtime Layer                                  │
│ Artifact / Replica / StorageRoot / Catalog / Env / Cache │
└──────────────────────────────────────────────────────────┘
```

逻辑调用关系：

```text
                         User
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
           RLW CLI                 React GUI
              │                       │
              │                    REST / WS
              └───────────┬───────────┘
                          ▼
              Application Services / API
                          │
                RLW Control Plane Core
                          │
       ┌──────────────────┼──────────────────┐
       ▼                  ▼                  ▼
   Providers          Executors          Storage
       │                  │                  │
       ▼                  ▼                  ▼
 LeRobot/etc.       Local / SSH       Artifact Replica
```

GUI 必须在 Remote Compute 之前实现，但 GUI 不直接依赖 LocalExecutor 或 SSHExecutor。它只看到稳定的 API / Service Contract。

因此增加 SSHExecutor 时：

```text
GUI
 ↓
same API
 ↓
same Application Services
 ↓
new SSHExecutor
```

而不是重写前端。

## 5.1 Core Dependency Rule

`workbench/core/` 不得直接依赖：

```text
FastAPI
Typer
SQLAlchemy ORM implementation
React
LeRobot
StarVLA
vla-eval
SSH implementation
```

Core 只定义稳定领域对象、Value Object、Protocol / Interface 与状态转换规则。

推荐依赖方向：

```text
CLI ─────┐
         ▼
API ─→ Application Services
               │
        ┌──────┼──────┐
        ▼      ▼      ▼
    Provider Executor Storage
        │      │      │
        └──────┼──────┘
               ▼
              Core
```

依赖方向只能向内，具体 Provider / Executor / DB / Web 框架属于外围实现。

---

# 6. 核心设计哲学：Reusable Assets vs Run-owned Artifacts

文件系统必须首先区分两个概念。

## 6.1 可复用资产

回答：

> **“我现在有什么东西可以拿来做实验？”**

包括：

```text
datasets/
architectures/
environments/
recipes/
```

特点：

- 可以被多个 Run 复用
- 不属于某一次训练
- 生命周期长于单次 Run
- 应有稳定 ID / metadata / revision

---

## 6.2 Run-owned Artifacts

回答：

> **“这一次研究活动做了什么，产生了什么？”**

统一进入：

```text
runs/
```

包括：

- Run 描述
- Resolved config
- Logs
- Checkpoint
- Rollout
- Evaluation
- Report
- Figures
- Generated metadata

核心原则：

> **产生结果的 Run 拥有该结果；其他 Run 通过 Artifact Reference 复用，而不是复制。**

---

# 7. 推荐仓库根目录

本地、服务器以及 GitHub 中 **Git-tracked Project Tree 使用同一结构**：

```text
robot/
│
├── workbench/                    # RLW Python Core / Services
│   ├── core/
│   ├── services/
│   ├── providers/
│   ├── executors/
│   ├── storage/
│   ├── cli/
│   └── api/
│
├── gui/                          # React / TypeScript / Vite
│
├── datasets/                     # Dataset metadata / manifests；payload 可外置
├── architectures/                # 可复用自定义模型架构
├── environments/                 # 可复用自定义环境
├── recipes/                      # 可复用 train / rollout / eval recipes
│
├── runs/                         # Research Records；大型 payload 默认不进 Git
│
├── configs/                      # 可提交的项目级配置模板
├── scripts/                      # bootstrap / doctor / migration / dev scripts
├── docs/
├── tests/
│
├── pyproject.toml
├── README.md
└── .gitignore
```

机器本地另外存在：

```text
robot/
└── .rlw/
    ├── envs/
    ├── worktrees/
    ├── cache/
    ├── state/
    ├── locks/
    ├── tmp/
    ├── secrets/          # 或仅存 Secret backend references
    └── machine.yaml
```

`.rlw/` 永不进入 Git。

核心原则：

> **Project structure is identical; physical asset availability is node-specific.**

即：

```text
GitHub
Local
Server A
Server B
```

拥有相同的代码、Schema、接口、GUI、CLI、Provider 定义和项目目录约定；不同节点只在大型 Artifact Replica、cache、环境安装状态、密钥和机器运行状态上不同。

`datasets/` 与 `runs/` 是逻辑项目入口，不要求大型 payload 永久物理存放在 Git 仓库所在磁盘；V3 引入 Storage Root 解决跨盘/NAS/scratch。

---

# 8. Git 跟踪什么

GitHub 管理 **完整可执行项目的代码与可复用定义**，而不是大型运行资产。

建议 Git 跟踪：

```text
workbench/
gui/
architectures/
environments/
recipes/
configs/
scripts/
docs/
tests/
pyproject.toml
README.md

datasets/**/dataset.yaml
datasets/**/metadata/          # 仅适合提交的小型 metadata

runs/**/run.yaml               # 是否提交由项目策略决定，默认运行结果不提交
```

大型 Dataset / Run payload / machine-local 状态默认不进入 Git：

```gitignore
.rlw/

datasets/**/raw/
datasets/**/cache/
datasets/**/data/
datasets/**/processed/

runs/**/logs/
runs/**/checkpoints/
runs/**/rollouts/
runs/**/evaluation/native/
runs/**/artifacts/

*.pt
*.pth
*.ckpt
*.safetensors
*.mp4
```

实际规则应允许小型 test fixture 例外。

## 8.1 GitHub / Local / Server 同构原则

GitHub 中的 commit 定义了：

```text
RLW Core
CLI
API
GUI
Provider Adapters
Executor Interfaces
Schemas
Recipes
Custom Architectures
Custom Environments
Tests
Docs
```

Local 和 Server 都通过：

```text
git fetch
git checkout <exact_commit>
```

获得相同 Project Snapshot。

禁止形成：

```text
local-only implementation
server-only implementation
different GUI code
different Provider Adapter behavior
```

如果某个 Node 缺少 Provider 环境或某个 Dataset Replica，应表现为：

```text
Capability / Environment / Replica availability difference
```

而不是代码分叉。

---

# 9. Dataset 目录

推荐：

```text
datasets/
├── pusht/
│   ├── dataset.yaml
│   ├── metadata/
│   ├── raw/
│   └── processed/
│
├── libero/
│   ├── dataset.yaml
│   └── ...
│
└── custom/
    └── robot_demo_v1/
```

Dataset 是：

> **实验输入资产，不是某个 Run 的副产品。**

所以同一个 PushT Dataset 不应在每个 Run 复制一次。

---

# 10. 自定义 Architecture

推荐：

```text
architectures/
├── policies/
├── action_heads/
├── memory/
├── encoders/
└── modules/
```

这里只保存自己维护的代码：

- Custom ACT
- Custom Action Head
- Memory Module
- Custom Transformer
- Custom VLA component

不要复制上游官方实现：

```text
LeRobot ACT
LeRobot SmolVLA
StarVLA QwenOFT
```

这些由 Provider 原生引用。

---

# 11. Environment

推荐：

```text
environments/
├── pusht_mujoco/
├── custom_robot/
├── ros2_robot/
└── ...
```

这里只存自己维护的 Environment / Adapter。

LIBERO 等官方 Environment 由对应 Provider 管理。

需要区分：

```text
Reusable Benchmark Task Definition
≠
Run Research Question
```

官方 Task Definition 不属于 `runs/`。

而：

> “比较 ACT chunk_size 在 LIBERO Spatial 上的差异”

属于 Run / Experiment。

---

# 12. Recipe

推荐：

```text
recipes/
├── train/
├── rollout/
└── eval/
```

用于保存可复用模板：

```text
ACT baseline
SmolVLA fine-tuning
LIBERO standard evaluation
RL post-training
```

Run 可以：

```yaml
recipe: act_baseline

overrides:
  learning_rate: 0.0001
  steps: 25000
```

最后解析成完整 `resolved_config.yaml`。

---

# 13. Runs 目录与 Canonical Run 语义

V3 正式统一：

```text
Experiment
  └── Trial
       └── Run
            ├── Job: train
            ├── Job: rollout
            ├── Job: evaluate
            └── Job: report
```

`runs/` 中的每一个 Run 表示：

> **某一个 fully-resolved Trial 的一次完整 realization / research record。**

建议目录：

```text
runs/
└── project/
    └── experiment/
        └── trial/
            └── run/
```

例如：

```text
runs/
└── pusht/
    └── act_chunk_size_ablation/
        ├── chunk16_seed1000/
        │   ├── 20260820_001/
        │   └── 20260820_002/
        └── chunk32_seed1000/
            └── 20260820_003/
```

为了避免过深目录，实际实现可以使用稳定 ID + display name：

```text
runs/pusht/exp_xxx/run_xxx/
```

Catalog 中保存完整 Experiment / Trial 关系。

目录结构是人类友好视图，不应成为对象身份本身。

---

# 14. 每一个 Run 的标准结构

Run 是一次完整研究 realization 的持久记录，因此目录既保存研究级 metadata，也保存 Run 内各 Job / Attempt 的执行记录与所有 Run-owned artifacts。

推荐：

```text
runs/
└── libero/
    └── spatial_smolvla/
        └── 20260820_001/
            │
            ├── run.yaml
            ├── resolved_config.yaml
            ├── manifest.json
            ├── lineage.json
            │
            ├── jobs/
            │   ├── train/
            │   │   ├── job.json
            │   │   └── attempts/
            │   │       ├── attempt_001.json
            │   │       └── attempt_002.json
            │   ├── rollout/
            │   ├── evaluate/
            │   └── report/
            │
            ├── logs/
            │   ├── stdout.log
            │   ├── stderr.log
            │   └── metrics.jsonl
            │
            ├── checkpoints/
            │   ├── step_10000/
            │   ├── step_20000/
            │   └── best/
            │
            ├── rollouts/
            │   ├── episode_000/
            │   ├── episode_001/
            │   └── ...
            │
            ├── evaluation/
            │   ├── native/
            │   ├── metrics.json
            │   ├── episodes.jsonl
            │   └── summary.json
            │
            ├── reports/
            │   ├── report.md
            │   └── figures/
            │
            └── artifacts/
```

其中：

```text
jobs/
=
Job / Attempt durable execution metadata
```

而：

```text
.rlw/state/jobs/
=
PID / heartbeat / transient runtime state
```

两者不能混淆。

Checkpoint / Rollout / Evaluation / Report 仍由产生它们的 Run 所有；Job metadata 只描述谁、何时、如何产生这些结果。

---

# 15. Completed Run Immutable，Runtime State Mutable

Architecture V3 将 V2 的 “Run 尽量 Append-only” 收紧为：

> **Completed research records are immutable; mutable runtime state lives outside the research record.**

运行期间允许追加：

```text
logs
metrics stream
checkpoints
rollouts
job records
```

完成后禁止无痕修改：

- 手工替换 checkpoint
- 覆盖 resolved config
- 修改 metrics 后仍沿用同一 Run ID
- 删除 lineage metadata
- 把另一次训练结果塞进原 Run

如果配置变化：

```text
Create New Trial / New Run
```

如果继续训练：

```text
Create Child Run
```

例如：

```text
run_001
ACT IL
  │
  └── art_checkpoint_best
            │
            ▼
run_002
RL post-training
```

机器本地动态状态：

```text
.rlw/state/jobs/
.rlw/state/transfers/
.rlw/locks/
.rlw/tmp/
```

可被更新和清理，不属于永久研究记录。

---

# 16. `run.yaml`、`resolved_config.yaml` 与 Schema Version

两者必须区分，并从 V0 起带 Schema Version。

## 16.1 `run.yaml`

表示用户研究意图：

```yaml
schema_version: rlw.run_spec/v1

experiment: pusht_act_baseline

dataset:
  ref: pusht

policy:
  provider: lerobot
  architecture: act

training:
  recipe: imitation
  steps: 25000
  batch_size: 8
  seed: 1000
```

`run.yaml` 不应被运行时自动覆盖。

## 16.2 `resolved_config.yaml`

表示执行前解析后的完整、不可歧义配置：

```yaml
schema_version: rlw.resolved_config/v1

run_id: run_a83d71c
trial_id: trial_...
experiment_id: exp_...

dataset:
  artifact_id: art_dataset_pusht
  revision: sha256:...
  digest: sha256:...

provider:
  name: lerobot
  version: ...
  adapter_version: ...

policy:
  architecture: act
  native_config: ...

runtime:
  environment_id: env_lerobot_...
  python: ...
  torch: ...
  cuda_runtime: ...

code:
  repository: HUliangwei/robot
  commit: abc123
  dirty: false

execution:
  node: local_hlw
  executor: local
  resources:
    gpu_count: 1
```

所有长期保存格式都必须带类似：

```text
rlw.run_spec/v1
rlw.run_manifest/v1
rlw.dataset_manifest/v1
rlw.artifact_manifest/v1
rlw.node_config/v1
```

未来字段变化通过显式 migration 处理，而不是静默猜测旧格式。

---

# 17. Core Domain Model

Architecture V3 第一批稳定 Core Object：

| 对象 | 核心问题 |
|---|---|
| `Experiment` | 研究问题是什么 |
| `Trial` | fully-resolved 实验变体是什么 |
| `Run` | 一个 Trial 的一次完整 realization 是什么 |
| `Job` | Run 中一个 coarse-grained 工作是什么 |
| `ExecutionAttempt` | Job 某一次实际启动 / 重试是什么 |
| `Artifact` | 逻辑产物是什么 |
| `ArtifactReplica` | Artifact 物理存在在哪里、状态如何 |
| `Node` | 在哪里执行 |
| `Executor` | 如何执行 |
| `ProviderSpec` | 使用哪个 Backend Provider |
| `CompatibilityContract` | 输入 / 输出语义是否兼容 |
| `MetricRecord` | 某个评测指标是什么 |
| `StorageRoot` | 某类物理存储从哪里解析 |
| `CommandSpec` | Provider 希望执行什么结构化命令 |
| `ResourceRequirement` | Job 需要什么资源 |
| `NodeCapability` | Node 当前提供什么资源与能力 |
| `SecretRef` | 如何引用敏感凭据而不持久化值 |

Dataset / Model / Checkpoint / Rollout / Report 初期优先作为：

```text
Artifact.kind
```

存在。

只有当某一类 Artifact 出现独立生命周期和复杂领域行为后，再升级为 Aggregate。

---

# 18. Experiment / Trial / Run / Job / ExecutionAttempt

必须严格区分，这一语义从 V3 起视为稳定协议。

## 18.1 Experiment

代表研究问题。

例如：

> ACT 的 `chunk_size` 对 PushT 成功率和推理延迟有什么影响？

Experiment 可以包含多个 Trial。

## 18.2 Trial

代表 fully-resolved experiment variant。

例如：

```text
chunk_size = 16
seed = 1000
dataset revision = X
policy/provider config = Y
```

Trial 表达算法、配置与输入变量组合，不绑定某次机器执行。

## 18.3 Run

代表某个 Trial 的一次完整 realization。

例如同一个 Trial 可以：

```text
Run A: local RTX GPU
Run B: V100 server
```

用于验证重跑一致性或因为前一次 Run 被取消而重新 realization。

Run 拥有这一完整研究过程产生的 Checkpoint / Rollout / Evaluation / Report。

## 18.4 Job

Run 内的 coarse-grained 工作：

```text
train
rollout
evaluate
report
export
custom
```

Job 可以有依赖：

```text
Train
  ↓
Rollout
  ↓
Evaluate
  ↓
Report
```

## 18.5 ExecutionAttempt

Job 的某一次实际启动。

例如：

```text
Job: train
Attempt 1 → FAILED (CUDA OOM)
Attempt 2 → SUCCEEDED
```

重试不改变 Trial 语义，也不应把基础设施失败伪装成新实验变量。

## 18.6 Canonical Relationship

```text
Experiment
   ├── Trial A
   │    ├── Run A1
   │    │    ├── Job Train
   │    │    │    ├── Attempt 1
   │    │    │    └── Attempt 2
   │    │    ├── Job Rollout
   │    │    └── Job Evaluate
   │    └── Run A2
   └── Trial B
```

---

# 19. Artifact

Artifact 是逻辑身份。

示例：

```yaml
artifact_id: art_ckpt_a83d71c
kind: checkpoint
display_name: smolvla_libero_best
producer_run: run_20260820_003
digest: sha256:...
```

Artifact 不等于某个路径。

---

# 20. Artifact Replica 与生命周期

Artifact 是逻辑身份；ArtifactReplica 是某个 Artifact 在某个 Node / StorageRoot 上的物理副本。

```yaml
schema_version: rlw.artifact_replica/v1

artifact_id: art_dataset_pusht
node: local_hlw
uri: file:///D:/RobotData/datasets/pusht/sha256-...
state: available
digest: sha256:...
size_bytes: ...
verified_at: ...
persistent: true
cache: false
pinned: true
```

一个 Artifact 可以有多个 Replica：

```text
Artifact: PushT revision X
   ├── Local archive replica
   └── V100 cache replica
```

因此继续禁止：

```text
LOCAL
SERVER
BOTH
REMOTE
```

固定 Artifact 状态。

## 20.1 Replica State Machine

至少支持：

```text
MISSING
   ↓
STAGING
   ↓
VERIFYING
   ↓
AVAILABLE
```

异常：

```text
STAGING  → FAILED
VERIFYING → CORRUPT
AVAILABLE → MISSING     # 外部删除后重新扫描发现
```

可选管理状态：

```text
AVAILABLE + pinned
AVAILABLE + persistent
AVAILABLE + evictable
```

不要把 `EVICTABLE` 与物理传输状态混为同一枚举。

## 20.2 Replica 可靠性原则

存在目录或文件 **不等于** Replica AVAILABLE。

只有：

```text
transfer completed
+
digest verified / trusted validation completed
+
atomic finalize
+
catalog registered
```

之后才是 AVAILABLE。

---

# 21. Checkpoint 管理

自己训练产生的 Checkpoint 应默认放：

```text
runs/.../<run>/checkpoints/
```

而不是全局 `weights/`。

其他 Run 引用：

```yaml
initial_weight:
  artifact: art_ckpt_a83d71c
```

不要复制。

完整推理 Model 和 Resume Checkpoint 也需要区分。

## 21.1 Model Artifact

偏向 inference / evaluation：

- weights
- model config
- processor
- tokenizer
- normalization stats
- LoRA / adapter
- action tokenizer

## 21.2 Training Checkpoint Artifact

用于 resume training：

- model state
- optimizer state
- scheduler state
- RNG state
- scaler
- global step

不要假设：

```text
checkpoint == deployable model
```

---

# 22. Rollout

Rollout 属于产生它的 Run。

```text
runs/.../<run>/rollouts/
```

不要建立全局：

```text
rollouts/
```

默认可长期保存：

```text
metadata.json
metrics.json
actions.parquet
states.parquet
preview.mp4
```

大型：

```text
RGB
Depth
Point Cloud
```

根据策略选择保存，避免存储爆炸。

---

# 23. Native Artifact 必须保留

RLW 不应强制所有 Provider 输出转换成单一 RLW 文件格式。

推荐：

```text
Artifact
├── native payload
├── manifest
└── derived views
```

例如 vla-eval：

```text
native:
evaluation sqlite / native result files

derived:
metrics.json
summary.json
preview.mp4
```

核心原则：

> **RLW 可以建立统一索引和视图，但不要破坏 Provider 原生输出。**

---

# 24. Provider Adapter 应该很薄

Adapter 的职责：

```text
capabilities()
validate()
resolve_config()
build_command()
inspect_native_config()
discover_artifacts()
inspect_artifact()
```

不要在 Adapter 中重新实现完整训练器。

正确：

```text
RLW
 ↓
LeRobot Adapter
 ↓
native LeRobot CLI / API
```

错误：

```text
RLW
 ↓
自己复制 LeRobot training logic
 ↓
变成半个 LeRobot fork
```

---

# 25. LeRobot Provider

优先复用：

- LeRobotDataset
- Dataset metadata
- Feature definitions
- ACT
- Diffusion Policy
- SmolVLA
- preprocess / postprocess
- standard training
- inference
- hardware support
- standard rollout / eval
- checkpoint / processor format

RLW 只做：

```text
Provider discovery
Config resolution
Compatibility projection
Execution
Artifact registration
Lineage
```

---

# 26. StarVLA Provider

StarVLA 负责：

- VLA backbone / framework
- Action Head
- Architecture research
- Controlled ablation
- Provider-native architecture registry

Architecture V3 不把：

```text
Backbone
Fusion
Memory
Action Head
```

硬编码成 Universal RLW Core。

RLW 只保存：

```yaml
provider: starvla
framework: qwen_oft
native_config: ...
```

GUI 可以通过 Provider capability projection 展示：

```text
Backbone
Action Head
Fusion
...
```

但它们属于 Provider 能力，而不是 RLW 永久数据库 Schema。

---

# 27. Custom Provider

保留：

```text
CustomPolicyAdapter
CustomTrainerAdapter
CustomEnvironmentAdapter
CustomEvaluatorAdapter
```

现有：

- PushT MuJoCo
- SAC
- Windows compatibility patches
- 自定义 inference scripts
- ROS2 robot

都可以通过 Custom Provider 接入。

---

# 28. vla-evaluation-harness Provider

vla-eval 已经负责：

```text
Model Server
Benchmark Environment
Closed-loop Episode
Evaluation orchestration
Native recording
Result aggregation
```

RLW 不重新实现这一层。

关系：

```text
RLW
 ↓
VLAEvalAdapter
 ↓
vla-evaluation-harness
 ↓
native result artifacts
 ↓
RLW Artifact Registry
```

---

# 29. Dataset Compatibility Contract

RLW 的价值不在复制上游所有 shape schema，而是建立跨 Provider 的 **最低必要语义 Contract**。

V3 要求分层实现，禁止 V0 一次性实现所有理论字段。

## 29.1 Compatibility Contract V0

优先覆盖真正会阻止运行的字段：

```yaml
observation:
  keys:
  shape:
  dtype:

action:
  dimension:
  representation:
  normalization:

embodiment:
  robot_type:

provider:
  required_capabilities:
```

结果必须支持：

```text
PASS
WARN
FAIL
UNKNOWN
```

`UNKNOWN` 是合法且重要的结果。

原则：

> **RLW 尽可能证明兼容，而不是假装知道所有语义。**

## 29.2 后续语义扩展

当真实 Provider 需求证明必要时，再增加：

```yaml
observation:
  semantic_type:
  modality:
  unit:
  frame:
  camera_identity:
  normalization:
  rate:
  timestamp_semantics:
  history:

action:
  semantic_type:
  frame:
  unit:
  mode:
  rate:

embodiment:
  kinematics:

language:
  representation:
```

Compatibility 可以回答：

```text
compatible
incompatible
adapter required
conversion required
unknown
```

---

# 30. Compatibility 示例

即使都是：

```text
7D delta EE action
```

也可能不兼容：

```text
[x,y,z,rx,ry,rz,gripper]
vs.
[x,y,z,qx,qy,qz,qw]
```

或者：

```text
axis-angle
vs.
Euler
```

或者：

```text
meters
vs.
normalized [-1, 1]
```

所以 Compatibility 必须能回答：

```text
compatible
incompatible
adapter required
conversion required
unknown
```

而不是只比较 tensor shape。

---

# 31. Workflow：Execution DAG 与 Research Loop 分离

原方案把：

```text
Policy
 ↓
Environment
 ↓
Rollout
 ↓
Reward
 ↓
Replay Buffer
 ↓
Policy Update
 └────→ Policy
```

称为 DAG 是不准确的，因为存在循环。

Architecture V3 区分：

## 31.1 Execution DAG

用于 coarse-grained Job dependencies：

```text
Train
  ↓
Rollout
  ↓
Evaluate
  ↓
Report
```

它可以是 DAG。

---

## 31.2 Algorithm Internal Loop

例如：

```text
RL replay/update loop
DAgger loop
HIL intervention loop
```

属于某个 Provider / Job 内部。

RLW 不展开到算法 step。

---

## 31.3 Research Lineage Graph

跨 Run 可以形成循环式研究过程：

```text
Dataset V1
   ↓
Train
   ↓
Rollout
   ↓
Hard Cases
   ↓
Dataset V2
   ↓
Train
```

这是 lineage / research iteration，不要求成为单一 Execution DAG。

---

# 32. Training Recipe

不能只区分：

```text
IL
RL
```

应允许描述：

| Route | Initial Policy | Dataset | Environment |
|---|---|---|---|
| Behavior Cloning / IL | random / pretrained | required | optional |
| VLA Fine-tuning | pretrained | required | optional |
| Offline RL | random / pretrained | required | optional |
| Online RL From Scratch | random | optional | required |
| IL → RL Post-training | pretrained | optional | required |
| DAgger / HIL | pretrained | initial demos | required |

但 Recipe 是 reusable definition，不等于 Universal Trainer Implementation。

---

# 33. Architecture Parameters 与 Training Parameters 分开

Architecture Parameters：

```text
hidden_dim
num_layers
num_heads
chunk_size
backbone
memory
action_head
```

Training Hyperparameters：

```text
learning_rate
batch_size
steps
optimizer
weight_decay
gradient_accumulation
precision
seed
checkpoint_interval
eval_interval
```

GUI 不应把两者混成一个无限增长的 Config 页面。

Provider-specific 参数允许通过 native config 展示。

---

# 34. MetricRecord，而不是 Universal Metric Columns

不要在数据库固定创建：

```text
success_rate
collision
smoothness
partial_completion
...
```

推荐：

```yaml
name: success_rate
namespace: libero
value: 0.83
unit: ratio
direction: higher_is_better
aggregation: mean
scope: task
episodes: 500
provider: vla_eval
definition_version: ...
```

MetricRecord 支持：

- provider namespace
- benchmark-specific semantics
- future metrics
- migration-free extension

---

# 35. Evaluation

评测仍分成两类。

## 35.1 Online Benchmark Evaluation

例如：

```text
vla-evaluation-harness
LeRobot eval
Custom closed-loop evaluator
```

逻辑：

```text
Policy / Model Server
        ↕
Benchmark Environment
        ↓
Closed-loop Episode
        ↓
Native Metrics
```

---

## 35.2 Offline Rollout Evaluation

输入：

```text
Rollout Artifact
```

可计算：

- Success Rate
- Episode Return
- Action Smoothness
- Trajectory Length
- Latency
- Control Hz
- GPU Memory
- Failure Type
- Intervention Rate
- Robustness

但这些不强行要求所有 Benchmark 都具备。

---

# 36. Experiment / Ablation

一个 Experiment 可以包含多个 Trial：

```text
baseline
variant_A
variant_B
variant_C
```

比较：

- Task metrics
- Latency
- VRAM
- Training Cost
- Robustness
- Data Efficiency
- Seed variance

适用于：

- Architecture Ablation
- Action Head Comparison
- Memory Ablation
- Domain Randomization
- Training Recipe Comparison
- Paper Experiment

---

# 37. Reproducibility Manifest

只记录 Git commit 和 seed 不够。

每个 Run 至少需要保存：

```yaml
schema_version: rlw.run_manifest/v1

code:
  repository:
  branch:
  commit:
  dirty:
  patch_hash:

provider:
  name:
  version:
  adapter_version:

runtime:
  os:
  python:
  torch:
  cuda_runtime:
  cudnn:
  platform:

hardware:
  node:
  gpu_model:
  gpu_ids:
  driver:

environment:
  environment_id:
  dependency_lock:
  conda_env:
  container_image:
  container_digest:

dataset:
  artifact_id:
  revision:
  digest:

config:
  run_config_digest:
  resolved_config_digest:

execution:
  start_time:
  end_time:
  exit_code:
```

如果当前阶段不用 Container，相关字段为空即可，不强制 Docker。

## 37.1 Manifest 的 Source-of-Truth 原则

Research Record 文件是长期可携带记录：

```text
run.yaml
resolved_config.yaml
manifest.json
lineage.json
artifact manifests
job records
```

SQLite Catalog 不是唯一事实来源。

即使 Catalog 丢失，只要 Research Record 和 Artifact payload 仍在，就应能：

```bash
rlw catalog rebuild
```

恢复索引。

---

# 38. Git / SSH / Artifact Sync 三分法

必须严格区分：

```text
Git
=
Code Distribution
```

```text
SSH
=
Execution Transport
```

```text
Artifact Sync
=
Data Distribution
```

不要让 Git 承担 Dataset / Checkpoint / Rollout 大文件同步。

不要让 rsync 代替代码版本控制。

不要让 GUI 自己拼接业务级 SSH 命令。

---

# 39. Local / Server / GitHub：项目同构，资产按需存在

Architecture V3 的硬约束：

> **Local、Server 与 GitHub 中的 Git-tracked Project Snapshot 应尽可能一模一样；差异只能来自大型资产与 machine-local state。**

GitHub 保存：

```text
complete project code
schemas
GUI
CLI
API
providers
executor interfaces
recipes
custom architectures
custom environments
tests
docs
```

Local 和 Server 都拥有：

```text
完整 Git Repository
完整 RLW Core
完整 CLI
完整 API
完整 GUI 源码
相同 Provider Adapter 代码
相同 Schema / Config definitions
```

但每个 Node 的实际运行条件允许不同：

```text
Provider environments installed or not
GPU / CPU / RAM
Dataset replicas
Checkpoint replicas
Run payloads
cache
machine-local config
secrets
runtime state
```

因此正确表述是：

> **Every node has the same RLW project capability model, while installed runtimes, hardware resources and artifact replicas are node-specific.**

不是要求每台机器镜像全部 Dataset / Checkpoint / Rollout。

---

# 40. Node

不再把：

```text
Local
Server
```

做成两种完全不同的架构。

统一：

```text
Node
```

例如：

```text
local_hlw
v100_server
4090_server
cloud_gpu
future_cluster
```

Node 回答：

> **在哪里执行？**

---

# 41. Executor

Executor 回答：

> **怎么执行？**

例如：

```text
Node: local_hlw
Executor: LocalExecutor
```

```text
Node: v100_server
Executor: SSHExecutor
```

未来：

```text
Node: cluster
Executor: SlurmExecutor
```

所以：

```text
Node ≠ Executor
```

这必须成为稳定边界。

---

# 42. Trial / Run 与 Execution 分离

Trial / Run 描述研究语义，ExecutionSpec 描述某个 Job 在哪里、以什么资源执行。

例如：

```yaml
# run.yaml

dataset: pusht

policy:
  provider: lerobot
  architecture: act

training:
  steps: 25000
```

Job execution：

```yaml
execution:
  node: v100_server
  executor: ssh
  resources:
    gpu:
      count: 1
      ids: [5]
```

同一个 Trial 可以产生多个 Run；同一套 Job Definition 也可以在：

```text
Local
V100 Server
4090 Server
Cloud GPU
```

上执行。

研究配置中不应硬编码 Windows / Linux 绝对路径。

---

# 43. 本地是主要 Research Control Plane，但不是特殊代码分支

本地通常拥有最完整的：

```text
historical datasets
runs archive
checkpoints
rollouts
reports
global artifact catalog
node registry
```

因此本地 GUI 是主要：

> **Global Research Control Plane**

但“本地是主要入口”仅意味着 **数据可见范围和使用方式** 不同，不意味着存在 Local-only Core 或 Local-only GUI。

服务器 clone 的仍是同一代码。

本地 Catalog 可以记录多个 Node 和远端 Replica；服务器自己的 Catalog 可以只记录本机可见状态。

未来如果需要真正共享 Catalog，再引入中心化服务，不在 V0/V1 提前复杂化。

---

# 44. 服务器是 Compute Node + Cache，不是另一套项目

服务器存储较小时，不镜像本地全部资产。

服务器主要物理保存：

```text
Same Git Repository
Same RLW source / GUI source
Provider Environments
Current Job Worktree
Current / Recent Run payload
Frequently-used Dataset Cache
Required Checkpoint Cache
Temporary Rollout
Logs
Machine-local Runtime State
```

代码结构与本地一致：

```text
robot/
├── workbench/
├── gui/
├── datasets/
├── architectures/
├── environments/
├── recipes/
├── runs/
...
```

只是部分 `datasets/` / `runs/` payload 没有对应 Replica。

任务完成并成功 Stage Out 后，可根据 retention policy 清理远端 cache。

---

# 45. GUI 架构：必须早于 Remote Compute

Architecture V3 明确：

> **GUI 在 SSHExecutor / Server Remote Compute 之前实现。**

原因：

1. GUI 能直观帮助理解 Experiment / Trial / Run / Job / Artifact 的关系。
2. GUI 能在早期暴露 Domain Model 与 Application Service 是否设计合理。
3. GUI 与执行层解耦，因此先做 GUI 不会妨碍后续增加 Server。
4. 在 Remote Compute 开发阶段，GUI 可以直接展示 Node doctor、Stage Plan、Job、Log 和 Artifact Replica，显著降低调试成本。

第一阶段本地：

```text
React GUI
    ↓
FastAPI
    ↓
Application Services
    ↓
Control Plane
    ↓
LocalExecutor
```

后续增加远程：

```text
same React GUI
    ↓
same FastAPI
    ↓
same Application Services
    ↓
SSHExecutor
    ↓
Remote RLW
```

禁止：

```text
React
 ↓
直接执行 Python training command

React
 ↓
直接拼 SSH / rsync 业务命令
```

GUI 是 Client / Experience Layer，不是 Executor，也不是业务逻辑拥有者。

---

# 46. Server GUI

服务器也可以：

```bash
rlw gui start
```

服务器运行同一套：

```text
RLW API
+
GUI
```

本地浏览器可以通过 SSH Tunnel 访问。

服务器 GUI 能看到：

- 当前 Server Artifact Replicas
- 当前 Dataset cache
- 当前 Checkpoint cache
- 当前 Runs
- GPU
- Disk
- Jobs
- Logs

但看不到只存在本地的完整历史资产。

这是正常的：

> **GUI 的可见范围取决于它连接的 RLW Catalog / Node。**

---

# 47. 同一套 GUI，不做 Local GUI / Server GUI 两套代码

始终只有：

```text
gui/
```

连接本地 API 时显示 Global / Archive 能力。

连接 Compute Node API 时显示 Node-scoped 状态。

可以由 API 返回：

```json
{
  "node_id": "v100_server",
  "capabilities": {
    "execution": true,
    "archive": false,
    "gui": true
  }
}
```

GUI 根据 capability 展示。

---

# 48. Server GUI 网络安全

当前阶段不建议：

```text
0.0.0.0:8000
```

直接暴露公网。

推荐：

```text
Server RLW
127.0.0.1:8000
      │
 SSH Tunnel
      │
Local Browser
```

未来真正需要多用户再增加：

- Authentication
- HTTPS
- Reverse Proxy
- Authorization
- Multi-user isolation

---

# 49. SSHExecutor，而不是 Server Agent

Remote Compute V2 不做常驻 Server Agent。

远程控制优先：

```text
Local RLW
   │
   ├── ssh remote "rlw ..."
   ├── rsync / scp for transfer
   ├── remote status query
   └── remote artifact discovery
```

但必须明确：

> **SSH connection is not the Job lifecycle.**

训练可能运行数小时或数天，因此远程任务必须 detached。

推荐：

```text
Local RLW
   ↓ SSH
Remote RLW internal job-launch
   ↓
Detached Process
   ↓
.rlw/state/jobs/job_xxx/
```

远程状态示例：

```text
.rlw/state/jobs/job_abc/
├── state.json
├── attempt.json
├── pid
├── heartbeat
├── stdout.log
└── stderr.log
```

可用实现：

```text
subprocess start_new_session
nohup
systemd-run --user
```

Remote Compute V2 先选择一种简单可靠方式，不需要立即实现 daemon。

本地断网或 GUI 关闭后：

```text
Remote Job continues
```

重新连接：

```bash
rlw job status job_abc --node v100_server
rlw job logs job_abc --node v100_server
```

即可恢复观察。

只有未来出现高频状态同步、多用户、复杂调度、断线事件推送等需求时，再评估 Server Agent。

---

# 50. Remote RLW

服务器不是 dumb shell。

服务器本身也安装完整：

```text
rlw
```

所以人工 SSH 后可以：

```bash
cd ~/robot
rlw doctor
rlw job list
rlw run ...
rlw artifact inspect ...
```

这对 Debug 很重要。

---

# 51. Run Materialization 与 Materialization Plan

远程运行不是：

```text
scp 整个 runs/
```

而是：

```text
Run / Job Spec
   ↓
Resolve Dependencies
   ↓
Materialization Plan
   ↓
Preflight
   ↓
Stage Missing Inputs
   ↓
Launch
```

Materialization Plan 至少解析：

- Exact Git commit
- Provider Environment
- Dataset Artifact revision
- Initial Model / Checkpoint Artifact
- Recipe
- Custom Architecture
- Custom Environment
- ResourceRequirement
- Required disk
- NodeCapability
- Missing ArtifactReplica
- Expected Stage Out outputs

推荐 `--dry-run` / GUI Preview 能显示完整计划。

Materialization 操作必须尽量幂等：重复规划或重复执行不应产生重复副本或重复 Run。

---

# 52. Stage In：原子、可验证、可恢复

示例：

```text
Required Artifact:
PushT Dataset revision X

Remote Replica:
AVAILABLE + DIGEST VERIFIED

→ SKIP
```

如果缺失：

```text
MISSING
  ↓
STAGING
  ↓
VERIFYING
  ↓
AVAILABLE
```

V3 要求 Stage In 至少遵守：

```text
1. Resolve target StorageRoot
2. Check existing verified replica
3. Check disk budget / reservation
4. Transfer to temporary / partial path
5. Support resume when transport allows
6. Verify digest or artifact-specific validator
7. Atomic finalize / rename
8. Register Replica AVAILABLE
```

示意：

```text
.rlw/tmp/art_xxx.partial
        ↓
hash verify
        ↓
atomic rename
        ↓
final artifact path
```

禁止仅通过“目标目录存在”判断 Stage In 成功。

重复执行同一个 Stage In 应尽量得到同一个 Replica，而不是复制多份。

---

# 53. Stage Out：先验证，再归档，再允许清理

任务完成后远端可能产生：

```text
SERVER
runs/.../run_001/
├── checkpoints/
├── rollouts/
├── evaluation/
└── reports/
```

Stage Out：

```text
Discover Outputs
   ↓
Register Remote Artifact identity
   ↓
Transfer to Local temporary destination
   ↓
Hash / semantic verify
   ↓
Atomic finalize
   ↓
Register Local Replica
   ↓
Mark archive-safe
```

只有成功确认：

```text
Local persistent verified replica exists
```

之后，服务器 cache Replica 才可以根据 retention policy 自动清理。

Stage Out 需要幂等：

```text
retry after SSH failure
```

不能重复生成 Artifact Identity 或错误创建多个逻辑 Artifact。

---

# 54. Remote Cleanup / Retention / Pinning

Cleanup 删除的是 **Replica**，不是 Artifact identity。

Replica 应至少支持：

```text
persistent
cache
pinned
last_accessed_at
verified
```

建议命令：

```bash
rlw node cleanup v100_server --completed-runs
rlw node cleanup v100_server --unused-cache
rlw node cleanup v100_server --all-cache
```

但 `unused` 不能只表示“当前没有运行中的 Job 引用”。

默认安全条件：

```text
Replica is evictable
AND
not pinned
AND
not required by active Job
AND
another verified persistent replica exists
```

删除最后一个已验证副本必须：

```text
explicit --force
```

并给出明显警告。

可增加：

```text
retention:
  completed_runs_days:
  cache_max_gb:
  protect_last_verified_replica: true
```

---

# 55. StorageRoot / Storage Budget

V3 不把逻辑资产目录永久绑定到 Git Repository 所在物理磁盘。

引入：

```text
StorageRoot
```

例如本地：

```yaml
storage_roots:
  archive:
    uri: file:///D:/RobotData
    role: persistent

  fast:
    uri: file:///E:/RLWCache
    role: cache
```

服务器：

```yaml
storage_roots:
  scratch:
    uri: file:///scratch/hlw/rlw
    role: cache
```

逻辑上仍然：

```text
datasets/pusht
runs/run_xxx
artifact://art_xxx
```

但 Replica URI 根据 Node-local StorageRoot 解析。

这样可以支持：

```text
SSD
HDD
NAS
scratch
future object storage
```

而不改变 Artifact identity。

## 55.1 Storage Budget

Node 配置：

```yaml
storage:
  workspace_limit_gb: 200

  cache:
    datasets: true
    checkpoints: true
```

Job 启动前检查：

```text
Required Storage: 83 GB
Available Storage: 41 GB

FAILED
Insufficient remote storage
```

不要运行到一半才出现 `No space left on device`。

---

# 56. 服务器 Git 使用方式

服务器也 clone 同一个：

```text
HUliangwei/robot
```

但远程执行不应简单：

```bash
git pull
python train.py
```

因为多个 Job 可能需要不同 commit。

正确：

```text
Base Repository
      ↓
git fetch
      ↓
Exact Commit
      ↓
Job Worktree
```

例如：

```text
.rlw/
└── worktrees/
    ├── job_a83d/
    └── job_b91f/
```

Job A：

```text
commit abc123
```

Job B：

```text
commit def456
```

互不影响。

---

# 57. Dirty Working Tree

Remote Compute V2 远程执行建议默认禁止 dirty tree：

```text
ERROR

Working tree contains uncommitted changes.

Commit changes before remote execution.
```

以后再支持：

```text
dirty patch
patch digest
temporary patch transport
```

第一阶段先保证：

> **Remote Run = Exact Git Commit**

---

# 58. 服务器环境分层与 Environment Manager

不要创建一个巨大：

```text
conda env robot
```

容纳全部 Provider。

推荐：

```text
HOST
 │
 ├── Linux / Windows
 ├── SSH
 ├── Git
 ├── rsync
 ├── NVIDIA Driver
 ├── Miniconda / environment tool
 └── Basic Build Tools

RLW CORE ENV
 │
 └── Control Plane dependencies

PROVIDER ENVS
 ├── LeRobot
 ├── StarVLA
 ├── vla-eval
 └── Custom
```

Local 也使用相同分层思想。

## 58.1 Environment Manager

引入 `EnvironmentManager`，负责：

```text
resolve
create/install
fingerprint
doctor
run command
remove
```

Provider Adapter 不负责直接拼：

```bash
conda activate xxx && ...
```

Adapter 输出结构化 `CommandSpec`：

```yaml
executable: python
args:
  - -m
  - lerobot.scripts.train
env:
  SOME_VAR: ...
cwd: ...
environment_ref: lerobot_default
```

Executor + EnvironmentManager 负责在具体 Node 上执行。

这样避免 shell quoting、Windows/Linux 差异和 `shell=True` 到处扩散。

---

# 59. `.rlw/` Machine-local 目录

本地和服务器都可以有相同约定：

```text
.rlw/
├── envs/
│   ├── core/
│   ├── lerobot/
│   ├── starvla/
│   └── vla_eval/
│
├── worktrees/
├── cache/
├── state/
│   ├── jobs/
│   └── transfers/
├── locks/
├── tmp/
├── secrets/
└── machine.yaml
```

`.rlw/` 不进入 Git。

它属于具体机器，而不是研究资产。

其中：

```text
state/
locks/
tmp/
```

保存 mutable runtime state；

```text
runs/
```

保存 persistent research record。

两者不得混用。

---

# 60. `rlw doctor`

环境检查必须成为 V0 正式能力，而不是后期脚本。

```bash
rlw doctor
```

至少检查：

```text
Operating System
Git
Python
Conda
Repository
RLW Core
NVIDIA Driver
GPU
GPU Architecture
CUDA compatibility
Disk
Shared Memory
SSH
Provider environments
Required executables
```

输出区分：

```text
READY
WARNING
MISSING
INCOMPATIBLE
```

---

# 61. `rlw bootstrap`

提供：

```bash
rlw bootstrap
```

但 bootstrap 不应偷偷修改系统。

流程：

```text
Check
  ↓
Generate Plan
  ↓
Show Changes
  ↓
Install User-space Dependencies
  ↓
Verify
```

默认不做：

```text
sudo
修改 Driver
修改 Firewall
替换系统 CUDA
修改 SSH daemon
```

如果 Host dependency 缺失：

```text
Administrator action required
```

明确提示。

---

# 62. Provider Doctor / Install / Test

例如：

```bash
rlw provider install lerobot
rlw provider doctor lerobot
rlw provider test lerobot
```

READY 不能只判断：

```text
pip list 有 lerobot
```

应该至少执行 smoke test：

```text
import
dataset metadata load
policy instantiate
CUDA availability
minimal forward
```

测试通过才：

```text
LeRobot: READY
```

---

# 63. Node Doctor

本地可以：

```bash
rlw node doctor v100_server
```

通过 SSH 检查：

- Remote RLW
- Git status
- Exact commit capability
- Provider env
- GPU
- Disk
- Shared memory
- Dataset replicas
- Required software

用于 GUI 中：

> Validate Node

---

# 64. CLI 设计收缩

V0 不需要一次实现几十个命令。

推荐核心：

```text
rlw
├── run
├── job
├── experiment
├── artifact
├── dataset
├── node
├── provider
├── doctor
├── bootstrap
└── gui
```

例如：

```bash
rlw run runspec.yaml
```

```bash
rlw run runspec.yaml --node v100_server
```

```bash
rlw job status job_xxx
rlw job logs job_xxx
rlw job stop job_xxx
```

不要在：

```text
train status
rollout status
eval status
```

分别重复实现 Job 管理。

---

# 65. `--dry-run` / `validate` / `preflight`

三个概念要区分。

## Static Validate

```bash
rlw run validate run.yaml
```

检查：

- Config schema
- Artifact references
- Provider compatibility
- Semantic compatibility

---

## Dry Run

```bash
rlw run run.yaml --dry-run
```

显示：

- Resolved config
- Execution plan
- Provider
- Backend command
- Required artifacts

不真正执行。

---

## Preflight

```bash
rlw run run.yaml --node v100_server --preflight
```

检查动态状态：

- SSH
- GPU
- Disk
- Provider env
- Dataset replica
- Checkpoint replica
- Git commit

GUI 可统一显示：

> Validate / Preview / Preflight

---

# 66. `--explain`

学习型 Workbench 可以保留：

```bash
rlw run run.yaml --explain
```

输出：

```text
Training Route:
Imitation Learning

Dataset:
PushT

Policy:
ACT

Action Representation:
Action Chunk

Provider:
LeRobot

Execution:
V100 Server
```

这是解释层，不侵入执行逻辑。

---

# 67. GUI 技术栈与实现位置

推荐：

```text
React
TypeScript
Vite
```

后端：

```text
Python
FastAPI
Pydantic
SQLAlchemy
SQLite
Typer
WebSocket
```

职责：

```text
FastAPI     → GUI / external API
Pydantic    → Config / Contract / Schema
SQLAlchemy  → Catalog persistence adapter
SQLite      → Local rebuildable Catalog
Typer       → rlw CLI
WebSocket   → Logs / Metrics / Job events
```

GUI 在 Remote Compute 之前实现。

开发顺序：

```text
Core + Application Services
        ↓
CLI
        ↓
FastAPI
        ↓
Local GUI
        ↓
SSHExecutor / Remote Compute
```

CLI 与 API 必须调用同一 Application Services。

禁止：

```text
CLI business logic
+
API business logic
```

形成两套实现。

---

# 68. GUI V3 的优先级

第一版 GUI 不从 Workflow Canvas 开始。

优先页面：

```text
Overview
Experiments
Trials / Runs
Jobs
Artifacts
Datasets
Providers
Evaluation
```

在 Remote Compute 尚未完成时，`Nodes` 页面先支持：

```text
Local Node
Local hardware
Local provider environments
Local disk / storage roots
```

Remote Compute 开始后，再扩展同一页面：

```text
V100 Server
4090 Server
future nodes
```

早期 GUI 最重要的问题：

```text
这个 Run 的研究意图是什么？
这个 checkpoint 从哪来的？
当前 Job 在做什么？
数据集是哪一版？
Provider 实际执行了什么？
Artifact lineage 如何？
```

而不是拖拽方块。

---

# 69. GUI 页面建议

第一阶段本地 GUI：

| 页面 | 主要职责 |
|---|---|
| **Overview** | 项目状态、最近 Run、当前 Job |
| **Experiments** | Experiment / Trial / Compare |
| **Runs** | Run detail、resolved config、lineage |
| **Jobs** | 状态、日志、Attempt、失败信息 |
| **Artifacts** | Dataset / Model / Checkpoint / Rollout / Report |
| **Datasets** | Revision、Schema、Preview |
| **Providers** | LeRobot / StarVLA / vla-eval / Custom 状态 |
| **Evaluation** | MetricRecord / Result / Compare |
| **Nodes** | 初期 Local，后续扩展 Remote |

后续远程能力加入后，同一套 GUI 增加：

```text
Artifact Replica
Stage Plan
Remote GPU
Remote Disk
Remote Provider env
Remote Jobs
Cleanup / Cache
```

后期才考虑：

```text
Architecture Research
Workflow Canvas
Real-time Simulator
Paper Export
```

---

# 70. GUI 中的 Node 切换

GUI 第一版只需要：

```text
Execution Target:
● Local
```

Remote Compute 加入后自然扩展：

```text
Execution Target:

○ Local
● V100 Server
○ 4090 Server
```

选择 Node 后后端重新计算：

```text
Node Reachability
Provider Environment
NodeCapability
Artifact Replicas
Required Stage In
ResourceRequirement match
Disk
Git Commit availability
```

Run/Trial 本身不因为换服务器而改变。

GUI 只展示后端返回的 Preflight / Materialization Plan。

---

# 71. GUI 中的 Validate / Preview / Run / Stage & Run

本地阶段：

```text
Run
PushT ACT Baseline

Execution Target
[Local]

Provider
LeRobot ✓

Dataset
PushT revision X ✓

Resources
GPU ✓
Disk ✓

[Validate]
[Preview]
[Run]
```

远程阶段扩展为：

```text
Execution Target
[V100 Server ▼]

Required Assets
✓ Dataset       AVAILABLE
! Base Model    MISSING → Stage In
✓ Code          abc123
✓ Provider Env  READY
✓ Disk          136 GB Available

[Validate]
[Preview]
[Preflight]
[Stage & Run]
```

GUI 不负责决定 Stage 哪些文件；Materialization Service 返回计划。

---

# 72. 实时日志、事件与可视化

本地 GUI 从第一版就支持：

- Job state
- stdout / stderr
- Loss / basic Metric stream
- GPU / VRAM
- Disk
- Generated Artifact discovery

推荐内部统一结构化事件流：

```text
JobStarted
JobStateChanged
MetricEmitted
ArtifactDiscovered
AttemptFailed
JobCompleted
```

CLI 可以文本显示，GUI 可以通过 WebSocket 显示。

远程执行后，同一事件模型通过 Remote polling / query 获取，不改变 GUI Domain Model。

仿真实时画面属于后续增强，不阻塞 Golden Path。

---

# 73. 现有 PushT / LIBERO 资产迁移

不要删除现有实验资产。

第一阶段先：

```text
读取旧目录
   ↓
识别
Dataset
Checkpoint
Rollout
Metrics
Config
   ↓
注册 Artifact
   ↓
建立 Run / Lineage
```

原则：

> **先让 RLW 理解旧实验，再让 RLW 创建新实验。**

这样可以验证 Domain Model 是否合理。

---

# 74. Golden Path

第一个 Golden Path：

```text
PushT
+
ACT
+
LeRobot
+
LocalExecutor
```

完整目标：

```text
Dataset Revision
 ↓
RunSpec
 ↓
Resolve Trial / Run
 ↓
Train Job
 ↓
Checkpoint Artifact
 ↓
Rollout Job
 ↓
Rollout Artifact
 ↓
Evaluation Job
 ↓
MetricRecord / Report
 ↓
Lineage
```

先用 CLI 跑通最小 vertical slice：

```text
Dataset
→ Train
→ Checkpoint
→ Manifest
```

随后立即通过 FastAPI + GUI 可视化同一数据和状态，再完善 Rollout / Evaluation。

原则：

> **GUI follows the same Core, but GUI development starts before Remote Compute.**

---

# 75. 开发路线：GUI 先于 Server

Architecture V3 的实现路线正式调整如下。

## V0 — Core Control Plane Proof

仅实现：

```text
Canonical Experiment / Trial / Run / Job / Attempt
Artifact
Dataset revision
ProviderSpec
LocalExecutor
LeRobot Adapter
CommandSpec
rlw CLI
doctor
Schema version
Filesystem manifest
SQLite catalog
```

最小 Golden Path：

```text
PushT + ACT + Local
```

成功标准：

> Dataset → Train → Checkpoint → Manifest / Lineage 可追溯。

---

## V0.5 — Local Closed Loop

加入：

```text
Rollout
Evaluation
MetricRecord
Report
Artifact discovery
Catalog rebuild / verify
Job state machine
basic failure handling
```

成功标准：

```text
PushT Dataset
  ↓
ACT Train
  ↓
Checkpoint
  ↓
Rollout
  ↓
Evaluation
  ↓
Report
```

CLI 完整成立。

---

## V1 — API + Local GUI

在 Remote Compute 之前实现：

```text
FastAPI
React / TypeScript / Vite
WebSocket / event stream
Overview
Experiments
Runs
Jobs
Artifacts
Datasets
Providers
Evaluation
Local Node
```

成功标准：

> 不查看目录和终端，也能通过 GUI 理解当前实验、Run、Job、Artifact、Lineage 与 Provider 状态；CLI 与 GUI 结果完全一致。

GUI 必须只调用 API / Application Services。

---

## V1.5 — GUI-driven Model Validation + Second Provider

接入：

```text
StarVLA
```

目的：

1. 验证 Domain Model 不是 LeRobot Wrapper。
2. 验证 GUI 通过 Provider capability projection 适配不同 Provider，而不是写死 LeRobot 页面。
3. 在增加远程复杂性之前先稳定 Core/API/GUI。

---

## V2 — Remote Compute

加入：

```text
Node
NodeCapability
ResourceRequirement
SSHExecutor
Remote RLW
Detached Remote Job
ArtifactReplica
StorageRoot
Stage In / Stage Out
Transfer recovery
Exact Git Commit
Git Worktree
Remote doctor
Storage budget
Cleanup / retention / pinning
```

成功标准：

```text
Local GUI / CLI
 ↓
Materialization Plan
 ↓
Stage Missing Inputs
 ↓
Remote Detached Job
 ↓
Reconnect / Observe
 ↓
Train / Rollout / Eval
 ↓
Stage Out
 ↓
Local persistent archive
```

不做 Server Agent。

---

## V2.5 — Evaluation Platform

加入：

```text
vla-evaluation-harness
multi-benchmark
MetricRecord expansion
robustness evaluation
experiment compare
statistics
visualization
```

---

## V3 — Architecture Research

加入：

- StarVLA capability projection expansion
- controlled backbone / action head experiments
- architecture compare
- custom architecture registry

仍不做 Universal Lego Policy Core。

---

## V4 — Post-training

加入：

- Online RL
- IL → RL
- DAgger
- Human Intervention
- Hard-case Data Return

算法内部 loop 仍归 Provider / Trainer。

---

## V5 — Real Robot

加入：

- LeRobot hardware
- SO-101
- ROS2 robot
- real rollout
- sim2real compare

注意：这里的软件迭代版本号与本文档 “Architecture V3” 是不同概念。

---

# 76. Remote Compute 阶段成功标准

Remote Compute（开发路线 V2）成功不是网页能打开，而是至少稳定完成：

```text
1. Local GUI / CLI 选择既有 RunSpec / Trial
2. 选择 Remote Node
3. Remote doctor
4. Resolve ResourceRequirement / NodeCapability
5. Resolve exact Git Commit
6. Create remote worktree
7. Resolve Provider Environment
8. Resolve required Dataset / Model revisions
9. Build Materialization Plan
10. 检查 ArtifactReplica
11. 只 Stage 缺失资产
12. 使用 temporary path + resume + verify + atomic finalize
13. 检查远端 Storage / GPU
14. Launch detached Remote Job
15. 本地断线后任务继续
16. Reconnect 后能读取 Job / Attempt 状态
17. 实时或轮询读取 Logs / Metrics
18. 生成 Checkpoint Artifact
19. Rollout
20. Evaluation
21. Stage Out
22. Verify Hash / semantic validator
23. 注册 Local persistent Replica
24. 完整 Lineage
25. Cleanup 只删除安全、可驱逐 Replica
26. 关键操作重复执行不造成重复 Artifact / 重复 Job
```

---

# 77. 当前非目标

第一阶段不做：

- 全部 VLA 模型
- 任意模块自由拖拽
- Universal Policy Lego Builder
- Universal Metric 固定数据库列
- 完整 Isaac Lab 平台
- 大规模分布式训练
- Server Agent
- Kubernetes
- Slurm 调度实现
- 多租户权限系统
- 重写 LeRobot
- 重写 StarVLA
- 重写 vla-eval
- 重写 simulator
- world-model 大规模预训练
- fleet-scale robot learning

---

# 78. 项目核心竞争力

如果最终只是：

> 一个方便点击 Train 的 GUI

项目价值有限。

真正值得展示的是：

```text
Experiment Control Plane
+
Stable RLW CLI
+
Provider Isolation
+
Node-independent Execution
+
Artifact Identity / Replica
+
On-demand Remote Materialization
+
Exact Git Commit Execution
+
Reproducible Run Manifest
+
Experiment Lineage
+
Cross-provider Compatibility
+
Research-oriented GUI
```

---

# 79. 最终 Local / Server / GitHub 架构

```text
                         GitHub
                 Same Git-tracked Project
                           │
                     exact commit
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
       LOCAL            SERVER A         SERVER B
     same project       same project      same project
        RLW                RLW              RLW
        API                API              API
        GUI src            GUI src          GUI src
         │                  │                │
 Full Archive/Replicas    Cache            Cache
         │                  │                │
 LocalExecutor             GPU              GPU
         │                  │                │
         └──── SSH / Artifact Transfer ──────┘
```

Local：

```text
Same Git project
+
Primary Global GUI
+
Research Archive
+
Global-oriented Catalog
+
Optional Local Compute
```

Server：

```text
Same Git project
+
Remote RLW Runtime
+
GPU Compute
+
On-demand Artifact Cache
+
Node-scoped runtime state
```

GitHub：

```text
Same Git-tracked project source
+
Schemas / definitions / tests / docs
-
No machine-local runtime state
-
No required large payload mirror
```

三者不是三个产品。

---

# 80. 五个核心执行抽象

Architecture V3 冻结后，真正与一次 Job 执行直接相关的五个概念是：

## Job

```text
What operation to execute
```

例如：

```text
Train
Rollout
Evaluate
Report
```

Run 是完整研究 realization 的容器，不再承担“具体执行单元”的含义。

## Node

```text
Where to execute
```

## Executor

```text
How to launch / control execution
```

## ArtifactReplica

```text
Where required / produced data physically exists
```

## Provider Environment

```text
With which runtime environment the Provider command executes
```

它们彼此独立：

```text
Job
 + Node
 + Executor
 + Provider Environment
 + Required Artifact Replicas
        ↓
ExecutionAttempt
```

上层关系仍然是：

```text
Experiment
  ↓
Trial
  ↓
Run
  ↓
Job
  ↓
ExecutionAttempt
```

---

# 81. Architecture V3 最终架构原则

## Principle 1

> **RLW is a Control Plane, not another robot-learning framework.**

## Principle 2

> **Reusable assets and Run-owned artifacts must be separated.**

```text
datasets/
architectures/
environments/
recipes/

vs.

runs/
```

## Principle 3

> **Git-tracked project content is structurally identical across GitHub, Local and Server.**

差异只允许存在于大型 Artifact Replica、installed runtime、hardware、secret、cache 与 machine-local state。

## Principle 4

> **Every execution node runs the same RLW codebase and capability model.**

Node 缺 Provider env / Artifact 是 availability 问题，不是软件分支。

## Principle 5

> **Experiment → Trial → Run → Job → ExecutionAttempt has one canonical meaning.**

禁止各层重复使用 `run` 一词表达不同对象。

## Principle 6

> **Run describes a research realization; Node describes location; Executor describes execution mechanism.**

三者不能绑定。

## Principle 7

> **Git distributes code, SSH transports control, Artifact Transfer distributes data.**

三者职责严格分离。

## Principle 8

> **Artifacts have identities; replicas have locations and lifecycles.**

Artifact 不绑定路径。

## Principle 9

> **Server storage is an execution cache unless explicitly marked persistent.**

任务需要时 Stage In，完成后 Stage Out。

## Principle 10

> **Remote runs execute exact Git commits.**

保证代码版本可复现。

## Principle 11

> **GUI is a client of RLW and is implemented before Remote Compute.**

GUI 不拥有 Executor / SSH / Provider 业务逻辑。

## Principle 12

> **Filesystem research records are portable; SQLite Catalog is rebuildable.**

数据库不能成为唯一研究事实来源。

## Principle 13

> **Completed research records are immutable; mutable runtime state belongs in `.rlw/`.**

## Principle 14

> **Critical operations must be recoverable and idempotent.**

Stage、Launch、Stage Out、Catalog registration、cleanup 都必须考虑失败重试。

## Principle 15

> **Never delete the last verified artifact replica by default.**

Cleanup 面向 Replica，并受 retention / pinning 约束。

## Principle 16

> **Dataset references resolve to immutable revisions.**

`pusht` 是逻辑 Dataset；Run 最终必须记录 `pusht@revision`.

## Principle 17

> **Provider environments are isolated and resolved by an Environment Manager.**

不要制造单一巨大环境。

## Principle 18

> **Secrets are referenced, never embedded in research records.**

Resolved Config、Manifest、Logs 必须脱敏。

## Principle 19

> **All persistent schemas are versioned from day one.**

未来通过 migration 演进。

## Principle 20

> **Compatibility may be UNKNOWN.**

RLW 不应为了“统一”伪造不存在的跨 Provider 语义。

---

# 82. 正式实现顺序

真正开始开发时严格按：

```text
① 目录结构 + Schema Version
        ↓
② Canonical Experiment / Trial / Run / Job / Attempt
        ↓
③ Artifact + ArtifactReplica basic model
        ↓
④ Dataset immutable revision
        ↓
⑤ Filesystem Manifest + SQLite Catalog
        ↓
⑥ ProviderSpec + thin Adapter + CommandSpec
        ↓
⑦ LocalExecutor + EnvironmentManager
        ↓
⑧ rlw doctor
        ↓
⑨ LeRobot Adapter
        ↓
⑩ PushT + ACT minimal Local Golden Path
        ↓
⑪ Job state machine + failure records
        ↓
⑫ Rollout + Evaluation + MetricRecord + Lineage
        ↓
⑬ Catalog rebuild / verify
        ↓
⑭ FastAPI
        ↓
⑮ React GUI — Local
        ↓
⑯ GUI Observability / Logs / Artifacts / Experiments
        ↓
⑰ StarVLA second provider
        ↓
⑱ Node + NodeCapability + ResourceRequirement
        ↓
⑲ SSHExecutor + Remote RLW detached jobs
        ↓
⑳ StorageRoot + Artifact Replica lifecycle
        ↓
㉑ Stage In / Stage Out + atomic verify + retry
        ↓
㉒ Exact Git Commit / Worktree
        ↓
㉓ Remote doctor / Preflight / Storage Budget
        ↓
㉔ Remote PushT + ACT through the same GUI
        ↓
㉕ Cleanup / Retention / Pinning
        ↓
㉖ vla-evaluation-harness
```

不要先做 Workflow Canvas，也不要为了 Remote Compute 推迟 GUI。

---

# 83. 项目名与仓库策略

项目名继续：

# **Robot Learning Workbench**

当前阶段继续使用：

```text
HUliangwei/robot
```

推荐新分支：

```bash
git checkout -b feat/workbench-v0
```

现有：

```text
PushT
LIBERO
ACT
SmolVLA
SAC
MuJoCo PushT
Rollout
Metrics
Checkpoint
Windows compatibility patches
legacy GUI
```

全部视为第一批真实迁移资产。

暂时不为了“仓库更漂亮”拆出：

```text
robot-learning-workbench
```

等 V1 / V1.5 核心稳定后再决定。

---

# 84. 最终一句话总架构

> **Robot Learning Workbench is a node-independent experiment control plane for reproducible robot-learning research. GitHub, local machines, and remote compute nodes share the same Git-tracked RLW project, while large artifacts and machine-local runtime state remain node-specific. Research is modeled canonically as Experiment → Trial → Run → Job → ExecutionAttempt; reusable assets are separated from immutable run-owned research records; providers are integrated through thin adapters; GUI and CLI consume the same application services; code executes at exact Git revisions; remote jobs survive SSH disconnects; artifacts are transferred as verified replicas through recoverable, idempotent Stage In / Stage Out operations; and every result remains traceable to dataset revision, configuration, provider, code, environment, hardware, node, attempts, and parent artifacts.**

中文：

> **Robot Learning Workbench 是一个与具体计算节点解耦、面向可复现机器人学习研究的实验控制平面。GitHub、本地与远程服务器共享完全一致的 Git-tracked RLW 项目，只有大型资产、副本、环境安装状态、密钥、缓存与机器运行时状态因节点而异；研究对象统一建模为 Experiment → Trial → Run → Job → ExecutionAttempt；可复用资产与完成后不可变的 Run 研究记录严格分离；不同生态通过薄 Provider Adapter 接入；GUI 与 CLI 共用同一 Application Services；代码按 exact Git revision 执行；远程 Job 不依赖 SSH 连接存活；Artifact 通过可验证、可恢复、幂等的 Stage In / Stage Out 形成 Replica；任何最终结果都能追溯到 Dataset revision、配置、Provider、代码版本、运行环境、硬件、Node、Attempt 与上游 Artifact。**

---

# 85. Filesystem Research Record vs SQLite Catalog

Architecture V3 明确 Source of Truth：

```text
Filesystem Research Record
=
Portable persistent research facts

SQLite Catalog
=
Rebuildable query/index projection
```

## 85.1 Filesystem 必须能独立解释 Run

一个已归档 Run 在没有原 SQLite 数据库时，仍应通过：

```text
run.yaml
resolved_config.yaml
manifest.json
lineage.json
jobs/*.json
artifact manifests
metrics / evaluation summaries
```

回答：

- 研究问题和配置是什么
- Dataset revision 是什么
- 使用哪个 Provider / Adapter
- 执行哪个 Git commit
- 在什么 Runtime / Hardware 上执行
- 哪些 Job / Attempt 成功或失败
- 产生哪些 Artifact
- Artifact 的 lineage 是什么

## 85.2 SQLite Catalog 的职责

Catalog 用于：

```text
fast search
filters
GUI list pages
experiment compare
artifact lookup
replica lookup
node registry
job index
metric query
```

Catalog 不是大型 payload storage，也不是唯一 provenance。

## 85.3 Catalog Maintenance

至少规划：

```bash
rlw catalog verify
rlw catalog rebuild
rlw catalog repair
```

`rebuild` 从 Research Record / Artifact Manifest 重建可持久索引。

如果 DB 与文件冲突，不能静默覆盖；需要报告 reconciliation issue。

---

# 86. Job / ExecutionAttempt 状态机

业务状态必须集中定义，禁止通过“有没有 PID / checkpoint 文件”到处猜测。

## 86.1 Job State

建议 V0/V1 最小状态：

```text
CREATED
  ↓
VALIDATING
  ↓
READY
  ↓
RUNNING
  ├──→ SUCCEEDED
  ├──→ FAILED
  └──→ CANCELED
```

远程 / Materialization 加入后可扩展：

```text
CREATED
  ↓
VALIDATING
  ↓
MATERIALIZING
  ↓
READY
  ↓
RUNNING
  ↓
FINALIZING / STAGING_OUT
  ↓
SUCCEEDED
```

取消路径：

```text
RUNNING → CANCELING → CANCELED
```

## 86.2 ExecutionAttempt State

```text
CREATED
STARTING
RUNNING
SUCCEEDED
FAILED
CANCELED
LOST
```

`LOST` 表示 RLW 暂时无法确认远程进程状态，不应自动等价于 FAILED。

重新连接后可以 reconcile：

```text
LOST → RUNNING
LOST → FAILED
LOST → SUCCEEDED
```

## 86.3 状态转换规则

状态转换只能通过 Core / Application Service 完成，并记录：

```text
timestamp
previous_state
new_state
reason
attempt_id
```

GUI、CLI、Executor 不可自行发明状态语义。

---

# 87. Recoverability / Idempotency / Atomicity

这是 Control Plane 与普通脚本之间的核心区别。

> **RLW operations must be recoverable and idempotent wherever practical.**

重点操作：

```text
create Run
launch Job
retry Attempt
register Artifact
Stage In
Stage Out
register Replica
catalog rebuild
cleanup
```

必须考虑重复执行。

## 87.1 Launch Idempotency

如果：

```text
ssh launch
↓
connection lost before response
```

Local RLW 不能直接假设 launch 失败并启动第二个训练。

应使用稳定：

```text
job_id
attempt_id
idempotency key
```

Remote RLW 能回答：

```text
attempt already running
attempt completed
attempt not created
```

## 87.2 Transfer Atomicity

传输写入：

```text
temporary / partial
```

验证成功才 atomic finalize。

## 87.3 Registration Idempotency

同一 digest + producer relationship 的 Artifact 注册重试不应产生多个逻辑对象，除非用户明确要求不同 identity。

## 87.4 Failure Record

失败本身必须形成可追踪记录：

```text
failure_type
message
exit_code
attempt
node
last_heartbeat
stderr tail / reference
```

不要只在终端打印后丢失。

---

# 88. Dataset Identity / Immutable Revision / Snapshot

Dataset 是可复用 Asset，但 Run 永远不能只引用一个可变目录名。

逻辑：

```text
Dataset Identity:
pusht

Dataset Revision:
sha256:abc...
```

或人类可读：

```text
pusht@20260820-abc123
```

## 88.1 Dataset Manifest

示意：

```yaml
schema_version: rlw.dataset_manifest/v1

dataset_id: pusht
revision: sha256:...
created_at: ...

source:
  provider: lerobot
  upstream_revision: ...

content:
  digest: sha256:...
  size_bytes: ...

contract:
  ...
```

## 88.2 Mutable Working Dataset vs Snapshot

数据采集过程中可以存在：

```text
working dataset
```

但一旦用于正式 Trial：

```text
snapshot / freeze
↓
immutable revision
```

Trial 和 Run 记录具体 revision。

重新 preprocess 或增加 demo：

```text
new revision
```

而不是覆盖旧 revision 后仍使用相同 provenance。

---

# 89. Secret / Credential Management

机器人学习 Provider 可能需要：

```text
Hugging Face token
W&B API key
GitHub credential
SSH key
S3 / object storage credential
ModelScope token
private registry token
```

这些值禁止进入：

```text
Git
run.yaml
resolved_config.yaml
manifest.json
lineage.json
logs
reports
```

## 89.1 SecretRef

配置只保存引用：

```yaml
tracking:
  wandb_token:
    secret_ref: wandb_default

model_hub:
  token:
    secret_ref: hf_default
```

真实 Secret 可以来自：

```text
environment variable
OS keyring
machine-local .rlw secret backend
future external secret manager
```

## 89.2 Redaction

Resolved Config / logging / exception serialization 必须对：

```text
token
password
secret
authorization header
private key
```

进行 redaction。

Remote Stage 只传递任务实际需要的 Secret，且不写入 Research Record。

---

# 90. ResourceRequirement 与 NodeCapability

Node 不只是一个 hostname。

## 90.1 ResourceRequirement

Job 可以声明：

```yaml
resources:
  gpu:
    count: 1
    min_vram_gb: 16

  cpu:
    min_cores: 8

  memory_gb: 32
  disk_gb: 80
  shared_memory_gb: 8
```

未来可扩展：

```text
compute capability
display / EGL
camera
robot hardware
ROS2
special device
network requirement
```

## 90.2 NodeCapability

Doctor / runtime discovery 产生：

```yaml
node:
  id: v100_server

capabilities:
  gpu:
    - id: 5
      model: Tesla V100
      vram_gb: ...
  cpu:
  memory_gb:
  storage:
  shared_memory_gb:
  providers:
    lerobot: ready
```

## 90.3 Matching

Preflight 回答：

```text
SATISFIED
WARNING
UNSATISFIED
UNKNOWN
```

RLW 只做研究工作台所需的轻量资源匹配，不发展成 Kubernetes 调度器。

---

# 91. Storage 与 Artifact URI 规则

Persistent Domain Object 不应把本地绝对路径当成 identity。

正确：

```text
Artifact ID
  ↓
ArtifactReplica
  ↓
Node-local URI
```

例如同一个 Artifact：

```text
Local:
file:///D:/RobotData/datasets/pusht/...

Server:
file:///scratch/hlw/rlw/datasets/pusht/...
```

Research Config 引用：

```text
artifact_id / dataset_id + revision
```

而不是：

```text
D:\Desktop\...
/home/hlw/...
```

## 91.1 URI Adapter

V0 支持：

```text
file://
```

未来如果真实需求出现，再扩展：

```text
s3://
hf://
ssh://
```

不要在 V0 预实现所有 Storage Backend。

---

# 92. Windows / Linux Portability

本地 Windows 与远程 Linux 必须从 V0 就视为正常组合。

禁止长期持久化：

```text
Windows-only command quoting
hard-coded drive letters
hard-coded /home paths
shell activation strings
```

跨平台边界：

```text
logical config
   ↓
Artifact / Environment / Command references
   ↓
Node-local resolution
```

使用：

```text
pathlib / URI abstraction
CommandSpec executable + args
EnvironmentManager
ArtifactReplica URI
```

避免在 Adapter 里：

```python
"cd ... && conda activate ... && python ..."
```

形成不可移植字符串。

---

# 93. Provider Contract 与 Contract Tests

Provider Adapter 是 RLW 最容易被上游变化破坏的位置，因此必须有明确 contract。

基本接口：

```text
capabilities()
validate()
resolve_config()
build_command()
inspect_native_config()
discover_artifacts()
inspect_artifact()
```

每个 Adapter 至少应有 Contract Test：

```text
can discover provider
can report version
can validate minimal config
can build deterministic CommandSpec
can execute smoke test
can discover expected output artifact
```

Golden Provider：

```text
LeRobot
```

Second Provider：

```text
StarVLA
```

只有第二个 Provider 也能不修改 Core Domain Model 接入时，才能证明抽象基本成立。

---

# 94. Doctor / Bootstrap / Provider Install 的边界

`doctor`：

```text
read-only inspection by default
```

`bootstrap`：

```text
plan
show changes
perform allowed user-space setup
verify
```

`provider install`：

```text
create / update isolated provider environment
```

三者不要混成一个会偷偷修改系统的命令。

需要管理员权限的 Host 改动：

```text
NVIDIA driver
system package
firewall
SSH daemon
```

仅生成明确提示 / plan，不默认 sudo。

---

# 95. Structured Events 与 Observability

为了 CLI、GUI、Local、Remote 共用一套状态语义，Application Layer 应产生结构化事件。

最小事件：

```text
RunCreated
JobCreated
JobStateChanged
AttemptStarted
MetricEmitted
ArtifactDiscovered
ReplicaStateChanged
TransferProgress
AttemptFailed
JobCompleted
RunCompleted
```

事件可以用于：

```text
GUI WebSocket
CLI live output
logs
future notification
```

但 V0 不要求构建复杂 Event Sourcing 系统。

原则是：

> **状态事实由 Control Plane 产生，展示层只消费。**

---

# 96. Error Taxonomy

错误至少区分：

```text
ValidationError
CompatibilityError
ProviderError
EnvironmentError
ResourceError
StorageError
TransferError
ExecutionError
RemoteConnectionError
ArtifactIntegrityError
CatalogError
UserCancellation
```

原因：

```text
Dataset incompatible
```

与：

```text
SSH disconnected
```

绝不能都表现成：

```text
Run FAILED
```

而不告诉用户是哪一层失败。

GUI 应根据 Error Category 提供：

```text
reason
retriable?
recommended action
related Job / Attempt / Artifact / Node
```

---

# 97. Testing Strategy

Architecture V3 的测试目标不是只验证函数，而是验证控制平面语义。

至少分：

```text
Unit Tests
Domain State Transition Tests
Schema Compatibility Tests
Provider Contract Tests
Executor Tests
Artifact Integrity Tests
Catalog Rebuild Tests
Golden Path Integration Tests
GUI API Contract Tests
Remote Failure Simulation Tests
```

关键 Golden Path：

```text
PushT + ACT + LeRobot + LocalExecutor
```

在加入 Remote 后增加：

```text
same Run through SSHExecutor
```

应尽可能复用同一 Core test fixture。

---

# 98. Migration Strategy

必须允许旧实验逐步进入 V3，而不是一次性搬家。

流程：

```text
scan legacy asset
 ↓
identify dataset / checkpoint / rollout / metrics / config
 ↓
generate candidate manifest
 ↓
user / rule verify
 ↓
register Artifact
 ↓
create imported Run / lineage
```

Imported Record 必须标注：

```text
provenance_quality:
  complete
  partial
  inferred
```

不能把未知 Git commit / Dataset revision 凭空补出来。

---

# 99. Local GUI 阶段验收标准

在任何 SSHExecutor 开发之前，至少完成：

```text
1. PushT Dataset revision 可注册与查看
2. 创建 Experiment / Trial / Run
3. Local Job 可启动
4. Job State / Attempt 可查看
5. stdout / stderr 可查看
6. basic metrics 可实时查看
7. Checkpoint Artifact 自动发现
8. Artifact lineage 可查看
9. resolved config / manifest 可查看
10. Dataset / Provider / Environment 状态可查看
11. Catalog 可以 rebuild
12. GUI 与 CLI 查询结果一致
13. GUI 不包含 Provider / LocalExecutor 业务逻辑
14. GUI 后续添加 Remote Node 不需要重写现有页面的数据模型
```

达到以上条件以后，再开始 Remote Compute。

---

# 100. Remote Failure Scenarios 必须设计验证

Remote Compute 完成前至少人为验证：

```text
SSH 在 launch 后断开
SSH 在 Stage In 中断
Stage In 重试
Stage Out 中断
Stage Out 重试
Local GUI 关闭再打开
Local RLW 重启
Remote Job 仍在运行
Remote Job 已完成但 Local 未收到结果
远端磁盘不足
远端 Artifact 已存在且 digest 正确
远端 Artifact 存在但 digest 错误
远端进程异常退出
远端 cache 被人工删除
Catalog 丢失后 rebuild
```

这些测试通过，才说明 SSHExecutor 是 Control Plane，而不仅仅是 SSH command wrapper。

---

# 101. Codex 实现约束

后续 Codex 只以 Architecture V3 为架构基线时，必须遵守：

1. 不新增与本文冲突的第二套 Domain 名称。
2. 不把 GUI 业务逻辑直接写入 React。
3. 不为了 Server 创建独立 Core / GUI / Provider 分支。
4. 不把 Artifact identity 等同于路径。
5. 不把 SQLite 当唯一 Source of Truth。
6. 不把 SSH Session 当远程 Job 生命周期。
7. 不直接覆盖完成后的 Research Record。
8. 不默认删除最后一个 verified Replica。
9. 不在 Config / Log 中持久化 Secret value。
10. 不用单一巨大 Conda env 容纳所有 Provider。
11. 不在 V0 过度实现 Universal Compatibility Schema。
12. 不提前实现 Server Agent、Slurm、Kubernetes、Workflow Canvas。
13. 新持久化 Schema 必须有 `schema_version`。
14. 新关键写操作必须说明幂等/失败恢复策略。
15. 新 Provider 必须通过 Provider Contract，而不是侵入 Core。
16. Local / Server / GitHub 的 Git-tracked project structure 和实现保持一致。
17. GUI 在 Remote Compute 之前完成并用于观察项目进展。
18. 若实际实现发现 Architecture V3 某条假设不成立，应先记录 Architecture Decision / Issue，再修改架构，而不是静默绕过。

---

# 102. Architecture V3 Definition of Done

Architecture V3 对“RLW 核心架构成立”的最终判断不是功能数量，而是以下链路成立：

```text
Same Git Project
      │
      ├────────────── Local ──────────────┐
      │                                   │
      │                             Local GUI / CLI
      │                                   │
      │                             Application Services
      │                                   │
      │                                Run / Job
      │                                   │
      │                              LocalExecutor
      │                                   │
      │                             Artifact / Lineage
      │                                   │
      └──────── Future Remote ─────────────┤
                                          │
                                   Materialization Plan
                                          │
                                     SSHExecutor
                                          │
                                     Remote RLW
                                          │
                                   Detached Attempt
                                          │
                                  Artifact Replica
                                          │
                                    Verified Stage Out
                                          │
                                     Local Archive
```

任何节点的执行结果最终都可以回答：

```text
What research question?
Which Trial?
Which Run?
Which Job / Attempt?
Which Dataset revision?
Which model / checkpoint parent?
Which Provider and Adapter version?
Which exact Git commit?
Which environment?
Which hardware / Node?
Which config?
Which metrics?
Which output artifacts?
Where are verified replicas?
Can the Catalog be rebuilt?
Can the operation recover after interruption?
```

如果这些问题可以稳定回答，RLW 才真正成为：

> **Robot Learning Experiment Control Plane / Research Workbench**

而不是训练脚本集合或训练 GUI。

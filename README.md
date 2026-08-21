# Robot Learning Workbench (RLW)

> `HUliangwei/robot` is evolving from a collection of robot-learning reproductions into an **experiment control plane for reproducible robot-learning research**.

RLW manages **Experiment → Trial → Run → Job → ExecutionAttempt**, reusable research assets, artifacts/replicas, provenance, local/remote execution, and provider integration while preserving native LeRobot, StarVLA, vla-evaluation-harness, simulator, and custom-code capabilities.

## Current migration state

Existing work is **not deleted**:

- `workspace/pusht/` — PushT, ACT, MuJoCo, SAC, rollouts and metrics
- `workspace/libero/` — LIBERO, ACT/SmolVLA evaluation and environment work
- `legacy/gui_dashboard_v4/` — previous local dashboard after running the V3 updater

These are first-class migration inputs. New RLW-managed research will progressively move to V3 manifests/catalog semantics without rewriting upstream training loops.

## Architecture V3 target tree

```text
robot/
├── workbench/       # stable Python Core + Services + Providers + Executors + API + CLI
├── gui/             # React / TypeScript / Vite; API client only
├── datasets/        # dataset manifests/metadata; large payload may be external
├── architectures/   # custom architecture code only
├── environments/    # custom environment/adapters only
├── recipes/         # reusable train/rollout/eval recipes
├── runs/            # research records; heavy payload ignored by Git policy
├── configs/
├── scripts/
├── docs/
├── tests/
├── workspace/       # legacy projects retained during migration
└── .rlw/            # machine-local state, never committed
```

## Install once

```powershell
cd D:\Desktop\robot
conda activate rlw
python -m pip install -e ".[dev]"
rlw system init
rlw gui install
```

Python 3.10+ and a current Node.js/npm installation are required. The
`python -m pip install` line is the one-time bootstrap that installs the `rlw`
command; normal operation uses `rlw ...` commands. On this workstation, the
prepared `rlw` Conda environment uses Python 3.11; the global `python` command
is older and should not be used for RLW installation.

Run ordinary `rlw ...` commands only from `D:\Desktop\robot`. Once RLW starts,
it selects each child process boundary itself:

- Core/API commands use the Python interpreter that launched `rlw`.
- GUI commands run npm inside `D:\Desktop\robot\gui`.
- Provider commands use the environment stored in the Run specification, such
  as `conda run -n lerobot-win ...`.

Do not manually enter `gui/` or activate a Provider environment before running
an RLW command. The hidden `--root` override is reserved for tests and update
automation.

## Open the local GUI

Start the API and React GUI together from one terminal:

```powershell
cd D:\Desktop\robot
rlw gui start
```

RLW waits until both services are ready and opens
[http://127.0.0.1:5173](http://127.0.0.1:5173) in your browser. Press `Ctrl+C`
once to stop both process trees.

The API health endpoint is
[http://127.0.0.1:8000/api/v1/health](http://127.0.0.1:8000/api/v1/health),
and interactive API documentation is available at
[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

Useful launch options:

```powershell
rlw gui start --no-open
rlw gui start --api-port 8100 --gui-port 5200
rlw gui start --help
```

If dependencies are missing, run `rlw gui install`. If a port is occupied,
RLW reports which port must be changed or released.

`rlw system doctor` reports the resolved project root, RLW Python executable,
the Python environment separately from the parent shell's Conda environment,
Node/npm paths, and GUI installation state.

Useful control-plane checks:

```powershell
rlw system doctor
rlw catalog rebuild
rlw system overview
rlw run preflight RUN_ID
rlw run execute RUN_ID
rlw run reconcile RUN_ID
rlw run inspect RUN_ID
rlw evaluation compare RUN_A RUN_B
```

## Configure and install local Providers

RLW currently registers LeRobot and StarVLA behind the same thin Provider
boundary. List their stable capabilities from the repository root:

```powershell
rlw provider list
rlw provider doctor lerobot
rlw provider doctor starvla
```

If StarVLA is checked out elsewhere on this machine, include its root so RLW
also validates the expected upstream entrypoint and Accelerate configuration:

```powershell
rlw provider configure starvla --environment starvla --provider-root D:\path\to\starVLA
rlw provider doctor starvla
```

Preview the command that the adapter would construct without starting training:

```powershell
rlw provider command starvla --recipe recipes/train/starvla_qwenoft.yaml
```

The preview is deliberately non-executing (`executed: false`). Runtime selection
is stored under the ignored `.rlw/providers/` directory. Explicit runtime flags
override the stored selection for one command. The GUI's **提供器 Providers**
page uses the same API for configuration, install planning, confirmation, and
Doctor checks.

If StarVLA is not installed, inspect the side-effect-free plan first, then
repeat it with exact confirmation:

```powershell
rlw provider install starvla
rlw provider install starvla --confirm starvla
rlw provider doctor starvla
```

The managed plan uses an isolated Python 3.10 Conda environment and registers
the runtime only after every required step succeeds. FlashAttention remains an
explicit compatibility item because its build must match CUDA and PyTorch; RLW
does not silently mutate host drivers or CUDA.

## Prepare and run StarVLA

After Provider Doctor reports `READY`, use the canonical workflow:

```powershell
rlw run prepare starvla-qwenoft --dataset-revision REVISION
rlw run preflight RUN_ID
rlw run execute RUN_ID
rlw run inspect RUN_ID
rlw run reconcile RUN_ID
```

`prepare` resolves the saved runtime, native config, portable lineage, and exact
command without starting training. Reconcile discovers StarVLA checkpoints and
registers provider-attributed Artifact records. The GUI overview exposes both
`pusht-act` and `starvla-qwenoft` through the same API.

The local Run flow is **Preflight → Execute → Inspect → Reconcile**. `execute`
repeats the required preflight checks before starting the Provider process;
`reconcile` safely re-discovers generated Artifact and Metric records and may
be repeated. The Runs page exposes the same actions. GUI execution stays locked
until its Preflight result passes, then requires confirmation of the exact Run
ID. CLI execution asks for the same explicit Run target in the command.

`rlw run inspect RUN_ID` and the GUI's **查看详情 Inspect** action use the
same observability service. They show Run lifecycle events, durable Jobs and
ExecutionAttempts, bounded stdout/stderr tails, failure category and guidance,
portable manifest/run specification/resolved configuration/lineage documents,
Artifact Replica facts, Artifacts, and Metrics. While a local Run is active,
the GUI refreshes this shared detail without overlapping requests. Add `--json`
when another tool needs the stable
`rlw.run_observability/v1` response.

## Development order

The single architecture baseline is [`docs/architecture/Robot Learning Workbench Architecture V3.md`](docs/architecture/Robot%20Learning%20Workbench%20Architecture%20V3.md). The implementation follows the V3 order: core domain/schema → artifact/dataset/catalog → provider/command contracts → local execution/doctor → LeRobot golden path → job/eval/lineage → FastAPI → local React GUI → observability → StarVLA → remote nodes/SSH.

Remote compute intentionally comes **after** the local GUI and second-Provider
boundaries are stable.

## Safety invariants

- Git distributes code/definitions; it does not distribute large datasets/checkpoints.
- Filesystem manifests are portable research facts; SQLite is a rebuildable index.
- GUI owns no provider/executor/SSH business logic.
- `workspace/` migration is read-only until provenance and Run boundaries are reviewed.
- Local/server/GitHub share one Git-tracked project; machine-specific state lives under `.rlw/` or external storage roots.

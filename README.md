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

Useful control-plane checks:

```powershell
rlw system doctor
rlw catalog rebuild
rlw system overview
rlw evaluation compare RUN_A RUN_B
```

## Development order

The single architecture baseline is [`docs/architecture/Robot Learning Workbench Architecture V3.md`](docs/architecture/Robot%20Learning%20Workbench%20Architecture%20V3.md). The implementation follows the V3 order: core domain/schema → artifact/dataset/catalog → provider/command contracts → local execution/doctor → LeRobot golden path → job/eval/lineage → FastAPI → local React GUI → observability → StarVLA → remote nodes/SSH.

Remote compute intentionally comes **after** the local GUI boundary is stable.

## Safety invariants

- Git distributes code/definitions; it does not distribute large datasets/checkpoints.
- Filesystem manifests are portable research facts; SQLite is a rebuildable index.
- GUI owns no provider/executor/SSH business logic.
- `workspace/` migration is read-only until provenance and Run boundaries are reviewed.
- Local/server/GitHub share one Git-tracked project; machine-specific state lives under `.rlw/` or external storage roots.

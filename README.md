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

## First local-control-plane commands

```bash
python -m pip install -e ".[dev]"
rlw init
rlw doctor
rlw legacy scan --write
rlw catalog rebuild
rlw overview
rlw api
```

Then start the React client:

```bash
cd gui
npm install
npm run dev
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

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
python -m pip install -e ".[dev]"
python -m workbench.cli.main --root . system init
cd gui
npm install
cd ..
```

Python 3.10+ and a current Node.js/npm installation are required.

## Open the local GUI

The GUI and API are two local processes. Keep both terminals open.

Terminal 1 — start the RLW API:

```powershell
cd D:\Desktop\robot
python -m workbench.cli.main --root . system api
```

Terminal 2 — start the React GUI:

```powershell
cd D:\Desktop\robot
npm --prefix gui run dev
```

Then open [http://127.0.0.1:5173](http://127.0.0.1:5173) in your browser.
The API health endpoint is
[http://127.0.0.1:8000/api/v1/health](http://127.0.0.1:8000/api/v1/health),
and interactive API documentation is available at
[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

Press `Ctrl+C` in each terminal to stop the GUI and API. If the GUI reports
`API unavailable`, confirm Terminal 1 is still running and that the health
endpoint returns `{"status":"ok"}`.

For a non-default API address, set `VITE_RLW_API` before starting the GUI:

```powershell
$env:VITE_RLW_API = "http://127.0.0.1:8000/api/v1"
npm --prefix gui run dev
```

Useful control-plane checks:

```powershell
python -m workbench.cli.main --root . system doctor
python -m workbench.cli.main --root . catalog rebuild
python -m workbench.cli.main --root . system overview
python -m workbench.cli.main --root . evaluation compare RUN_A RUN_B
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

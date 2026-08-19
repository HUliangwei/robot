# RLW V3 compatibility migration

## What this migration changes

- Adds the V3 Python control-plane skeleton (`workbench/`) and tests.
- Replaces the root `gui/` boundary with a React/FastAPI client split.
- Archives the previous dependency-free GUI to `legacy/gui_dashboard_v4/` on first apply.
- Keeps `workspace/pusht/` and `workspace/libero/` untouched.
- Changes `.gitignore` so dataset **metadata can be tracked** while payload/cache stays ignored.
- Adds dataset/architecture/environment/recipe/run/config/script roots required by V3.
- Copies Architecture V3 as the sole implementation baseline.

## What this migration intentionally does not do

- It does not auto-import historical Runs. `rlw legacy scan --write` only creates candidates.
- It does not invent missing Git commit, dataset revision, provider version, or Run boundaries.
- It does not move checkpoints/videos into new Runs automatically.
- It does not add SSHExecutor, a server agent, Slurm, Kubernetes, or Workflow Canvas.
- It does not reimplement ACT/SAC/SmolVLA/LeRobot training loops.

## First acceptance checkpoint

```bash
rlw doctor
rlw legacy scan --write
rlw catalog rebuild
rlw overview
rlw api
```

Then `cd gui && npm install && npm run dev`.

The next implementation slice should make **PushT + ACT + LeRobot + LocalExecutor** the canonical Golden Path, producing a new Run directory with resolved config, manifest, Job/Attempt records and checkpoint discovery.

# RLW GUI V1 skeleton

This directory replaces the legacy dependency-free dashboard with the Architecture V3 client boundary:

```text
React / TypeScript / Vite
        ↓ HTTP
FastAPI (`workbench.api`)
        ↓
Application/Core services
```

The previous `gui/` is archived by the migration script to `legacy/gui_dashboard_v4/`; it remains available for reference while its useful views are migrated.

## Run

From the repository root, bootstrap the CLI once and then use only RLW's
user-facing commands:

```powershell
conda activate rlw
python -m pip install -e ".[dev]"
rlw system init
rlw catalog rebuild
rlw gui install
rlw gui start
```

All commands above run from the repository root. RLW changes the GUI child
process working directory to `gui/` internally; users should not run npm from
this directory themselves.

`rlw gui start` starts both FastAPI and Vite, waits for readiness, opens
`http://127.0.0.1:5173`, and stops both when you press `Ctrl+C`. Use
`rlw gui start --no-open` for headless use or `rlw gui start --help` for port
options.

On the **运行 Runs** page, choose **查看详情 Inspect** to load the shared
Run observability view: lifecycle events, Job/Attempt state, bounded
stdout/stderr tails, failure guidance, Artifacts, and Metrics. The equivalent
root-scoped CLI command is `rlw run inspect RUN_ID`.

The GUI must never spawn LeRobot, SSH, rsync, or local training processes directly. Add business behavior in Application Services and expose it through the API.

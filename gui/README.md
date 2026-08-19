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

```bash
# terminal 1, repository root
python -m pip install -e ".[dev]"
rlw init
rlw catalog rebuild
rlw api

# terminal 2
a cd gui
npm install
npm run dev
```

Open `http://127.0.0.1:5173`.

The GUI must never spawn LeRobot, SSH, rsync, or local training processes directly. Add business behavior in Application Services and expose it through the API.

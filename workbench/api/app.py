from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from workbench.providers.lerobot import LeRobotAdapter
from workbench.services.doctor import run_doctor
from workbench.services.legacy import scan_legacy_workspace
from workbench.services.overview import build_overview
from workbench.storage.catalog import Catalog
from workbench.storage.paths import ensure_runtime_dirs, find_project_root


def create_app(root: str | Path | None = None) -> FastAPI:
    project_root = Path(root).resolve() if root is not None else find_project_root()
    ensure_runtime_dirs(project_root)
    catalog = Catalog(project_root / ".rlw" / "catalog.sqlite3")

    app = FastAPI(title="Robot Learning Workbench API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "schema_version": "rlw.api_health/v1"}

    @app.get("/api/v1/overview")
    def overview():
        return build_overview(project_root)

    @app.get("/api/v1/runs")
    def runs():
        return {"items": catalog.list_records("run")}

    @app.get("/api/v1/datasets")
    def datasets():
        return {"items": catalog.list_records("dataset")}

    @app.get("/api/v1/jobs")
    def jobs():
        state_root = project_root / ".rlw" / "state" / "jobs"
        items = []
        if state_root.exists():
            for path in sorted(state_root.rglob("attempt.json"), reverse=True)[:200]:
                try:
                    import json
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    payload["_source_path"] = path.relative_to(project_root).as_posix()
                    items.append(payload)
                except Exception:
                    continue
        return {"items": items}

    @app.get("/api/v1/artifacts")
    def artifacts():
        return {"items": catalog.list_records("artifact")}

    @app.get("/api/v1/providers")
    def providers():
        adapter = LeRobotAdapter()
        return {"items": [{"spec": adapter.spec().__dict__, "capabilities": adapter.capabilities()}]}

    @app.get("/api/v1/doctor")
    def doctor():
        return run_doctor(project_root)

    @app.get("/api/v1/legacy")
    def legacy():
        return scan_legacy_workspace(project_root)

    return app


app = create_app()

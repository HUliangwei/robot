from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from workbench.providers.lerobot import LeRobotAdapter
from workbench.services.doctor import run_doctor
from workbench.services.golden_path import GoldenPathService
from workbench.services.legacy import scan_legacy_workspace
from workbench.services.overview import build_overview
from workbench.services.provider_doctor import run_provider_doctor
from workbench.storage.catalog import Catalog
from workbench.storage.paths import ensure_runtime_dirs, find_project_root


class GoldenPrepareRequest(BaseModel):
    dataset_revision: str
    recipe: str = "recipes/train/pusht_act.yaml"
    provider_env: str = "lerobot-win"


def create_app(root: str | Path | None = None) -> FastAPI:
    project_root = Path(root).resolve() if root is not None else find_project_root()
    ensure_runtime_dirs(project_root)
    catalog = Catalog(project_root / ".rlw" / "catalog.sqlite3")
    app = FastAPI(title="Robot Learning Workbench API", version="0.4.0")
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

    @app.get("/api/v1/artifacts")
    def artifacts():
        return {"items": catalog.list_records("artifact")}

    @app.get("/api/v1/metrics")
    def metrics():
        return {"items": catalog.list_records("metric")}

    @app.get("/api/v1/jobs")
    def jobs():
        import json
        items = []
        state_root = project_root / ".rlw" / "state" / "jobs"
        if state_root.exists():
            for path in sorted(state_root.rglob("attempt.json"), reverse=True)[:200]:
                try:
                    item = json.loads(path.read_text(encoding="utf-8"))
                    item["_source_path"] = path.relative_to(project_root).as_posix()
                    items.append(item)
                except Exception:
                    pass
        return {"items": items}

    @app.get("/api/v1/providers")
    def providers():
        adapter = LeRobotAdapter()
        return {"items": [{"spec": adapter.spec().__dict__, "capabilities": adapter.capabilities()}]}

    @app.get("/api/v1/providers/{environment}/doctor")
    def provider_doctor(environment: str):
        return run_provider_doctor(environment)

    @app.get("/api/v1/doctor")
    def doctor():
        return run_doctor(project_root)

    @app.get("/api/v1/legacy")
    def legacy():
        return scan_legacy_workspace(project_root)

    @app.post("/api/v1/golden/prepare")
    def golden_prepare(req: GoldenPrepareRequest):
        try:
            return GoldenPathService(project_root).prepare(
                req.recipe,
                dataset_revision=req.dataset_revision,
                provider_env=req.provider_env,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/v1/runs/{run_id}/preflight")
    def preflight(run_id: str):
        try:
            return GoldenPathService(project_root).preflight(run_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/runs/{run_id}/discover")
    def discover(run_id: str):
        return GoldenPathService(project_root).discover(run_id)

    return app


app = create_app()

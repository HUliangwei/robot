from __future__ import annotations

import os
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from workbench.services.doctor import run_doctor
from workbench.services.evaluation import compare_catalog_metrics
from workbench.services.golden_path import GoldenPathService
from workbench.services.legacy import scan_legacy_workspace
from workbench.services.overview import build_overview
from workbench.services.observability import RunObservabilityService
from workbench.services.provider_doctor import (
    list_providers,
    preview_provider_command,
    run_provider_doctor,
)
from workbench.services.run_actions import LocalRunActionService, RunStateError
from workbench.storage.catalog import Catalog
from workbench.services.provider_install import (
    build_provider_install_plan,
    execute_provider_install,
)
from workbench.services.provider_runtime import (
    configure_provider_runtime,
    read_provider_runtime,
    resolve_provider_runtime,
)
from workbench.storage.paths import ensure_runtime_dirs, find_project_root


class GoldenPrepareRequest(BaseModel):
    dataset_revision: str
    workflow: str = "pusht-act"
    recipe: str | None = None
    provider_env: str | None = None
    python_executable: str | None = None
    provider_root: str | None = None


class RunExecuteRequest(BaseModel):
    confirmation: str


class ProviderCommandRequest(BaseModel):
    recipe: str
    conda_prefix: str | None = None
    provider_env: str | None = None
    python_executable: str | None = None
    provider_root: str | None = None


class ProviderConfigureRequest(BaseModel):
    environment: str | None = None
    conda_prefix: str | None = None
    python_executable: str | None = None
    provider_root: str | None = None


class ProviderInstallRequest(BaseModel):
    environment: str | None = None
    conda_prefix: str | None = None
    provider_root: str | None = None
    repository: str | None = None
    revision: str | None = None
    confirmation: str | None = None


_WORKFLOW_RECIPES = {
    "pusht-act": "recipes/train/pusht_act.yaml",
    "pusht-act-smoke": "recipes/train/pusht_act_smoke.yaml",
    "starvla-libero-smoke": "recipes/train/starvla_libero_smoke.yaml",
    "starvla-qwenoft": "recipes/train/starvla_qwenoft.yaml",
}


def create_app(root: str | Path | None = None) -> FastAPI:
    project_root = Path(root).resolve() if root is not None else find_project_root()
    ensure_runtime_dirs(project_root)
    catalog = Catalog(project_root / ".rlw" / "catalog.sqlite3")
    app = FastAPI(title="Robot Learning Workbench API", version="0.5.0")
    gui_origins = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]
    configured_origin = os.environ.get("RLW_GUI_ORIGIN")
    if configured_origin and configured_origin not in gui_origins:
        gui_origins.append(configured_origin)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=gui_origins,
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

    @app.get("/api/v1/runs/{run_id}/observability")
    def run_observability(
        run_id: str,
        log_tail_lines: int = Query(default=80, ge=1, le=1000),
    ):
        try:
            return RunObservabilityService(project_root).inspect(
                run_id, log_tail_lines=log_tail_lines
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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
        return {"items": catalog.list_records("job")}

    @app.get("/api/v1/attempts")
    def attempts():
        return {"items": catalog.list_records("attempt")}

    @app.get("/api/v1/evaluation/compare")
    def evaluation_compare(run_ids: list[str] = Query(alias="run_id")):
        try:
            return compare_catalog_metrics(catalog, run_ids)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/v1/providers")
    def providers():
        return list_providers()

    @app.get("/api/v1/providers/{target}/doctor")
    def provider_doctor(
        target: str,
        environment: str | None = None,
        conda_prefix: str | None = None,
        python_executable: str | None = None,
        provider_root: str | None = None,
    ):
        try:
            runtime = resolve_provider_runtime(
                project_root, target,
                environment=environment,
                conda_prefix=conda_prefix,
                python_executable=python_executable,
                provider_root=provider_root,
            )
            doctor_args = {
                "environment": runtime["conda_env"],
                "provider_root": runtime["provider_root"],
            }
            if runtime.get("conda_prefix"):
                doctor_args["conda_prefix"] = runtime["conda_prefix"]
            if runtime.get("python_executable") and not runtime.get("conda_prefix"):
                doctor_args["python_executable"] = runtime["python_executable"]
            return run_provider_doctor(target, **doctor_args)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/providers/{provider}/command")
    def provider_command(provider: str, req: ProviderCommandRequest):
        try:
            selected = resolve_provider_runtime(
                project_root,
                provider,
                environment=req.provider_env,
                conda_prefix=req.conda_prefix,
                python_executable=req.python_executable,
                provider_root=req.provider_root,
            )
            return preview_provider_command(
                project_root,
                provider,
                req.recipe,
                provider_env=selected["conda_env"] if not selected.get("python_executable") else None,
                python_executable=selected.get("python_executable"),
                provider_root=selected["provider_root"],
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/v1/doctor")
    def doctor():
        return run_doctor(project_root)

    @app.get("/api/v1/legacy")
    def legacy():
        return scan_legacy_workspace(project_root)

    @app.post("/api/v1/golden/prepare")
    def golden_prepare(req: GoldenPrepareRequest):
        try:
            if req.workflow not in _WORKFLOW_RECIPES:
                raise ValueError(f"unknown workflow: {req.workflow}")
            recipe = req.recipe or _WORKFLOW_RECIPES[req.workflow]
            return GoldenPathService(project_root).prepare(
                recipe,
                dataset_revision=req.dataset_revision,
                provider_env=req.provider_env,
                python_executable=req.python_executable,
                provider_root=req.provider_root,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/v1/runs/{run_id}/preflight")
    def preflight(run_id: str):
        try:
            return GoldenPathService(project_root).preflight(run_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/providers/{provider}/runtime")
    def provider_runtime(provider: str):
        try:
            record = read_provider_runtime(project_root, provider)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if record is None:
            raise HTTPException(status_code=404, detail="Provider runtime is not configured")
        return record

    @app.post("/api/v1/providers/{provider}/configure")
    def provider_configure(provider: str, req: ProviderConfigureRequest):
        try:
            return configure_provider_runtime(
                project_root, provider,
                environment=req.environment,
                conda_prefix=req.conda_prefix,
                python_executable=req.python_executable,
                provider_root=req.provider_root,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/v1/providers/{provider}/install")
    def provider_install(provider: str, req: ProviderInstallRequest):
        try:
            plan = build_provider_install_plan(
                project_root, provider,
                environment=req.environment,
                conda_prefix=req.conda_prefix,
                provider_root=req.provider_root,
                repository=req.repository,
                revision=req.revision,
            )
            if req.confirmation is None:
                return plan
            result = execute_provider_install(
                project_root, plan, confirmation=req.confirmation
            )
            if result.get("status") == "FAILED":
                raise HTTPException(status_code=409, detail=result)
            return result
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post(
        "/api/v1/runs/{run_id}/execute",
        status_code=status.HTTP_202_ACCEPTED,
    )
    def execute(run_id: str, req: RunExecuteRequest, background_tasks: BackgroundTasks):
        actions = LocalRunActionService(project_root)
        try:
            accepted = actions.validate_execute(run_id, req.confirmation)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RunStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        background_tasks.add_task(actions.execute, run_id)
        return accepted

    @app.post(
        "/api/v1/runs/{run_id}/evaluate",
        status_code=status.HTTP_202_ACCEPTED,
    )
    def evaluate(run_id: str, req: RunExecuteRequest, background_tasks: BackgroundTasks):
        if req.confirmation != run_id:
            raise HTTPException(
                status_code=400, detail="confirmation must exactly match the Run ID"
            )
        try:
            GoldenPathService(project_root).discover(run_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        background_tasks.add_task(GoldenPathService(project_root).evaluate, run_id)
        return {
            "schema_version": "rlw.run_evaluation_request/v1",
            "run_id": run_id,
            "status": "ACCEPTED",
        }

    @app.post("/api/v1/runs/{run_id}/reconcile")
    def reconcile(run_id: str):
        try:
            return LocalRunActionService(project_root).reconcile(run_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/v1/runs/{run_id}/discover")
    def discover(run_id: str):
        return GoldenPathService(project_root).discover(run_id)

    return app


app = create_app()

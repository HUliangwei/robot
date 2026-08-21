from fastapi.testclient import TestClient

from workbench.api.app import create_app
from workbench.services.observability import RunObservabilityService
from workbench.storage.catalog import Catalog
from workbench.storage.manifests import atomic_write_json


def _write_durable_execution_records(root):
    job_root = root / "runs" / "run_api" / "jobs" / "train"
    atomic_write_json(
        job_root / "job.json",
        {
            "schema_version": "rlw.job/v1",
            "job_id": "job_durable",
            "run_id": "run_api",
            "kind": "train",
            "state": "SUCCEEDED",
        },
    )
    atomic_write_json(
        job_root / "attempts" / "attempt_durable.json",
        {
            "schema_version": "rlw.execution_attempt/v1",
            "attempt_id": "attempt_durable",
            "job_id": "job_durable",
            "state": "SUCCEEDED",
            "exit_code": 0,
        },
    )
    atomic_write_json(
        root / ".rlw" / "state" / "jobs" / "runtime" / "attempt.json",
        {
            "schema_version": "rlw.execution_attempt/v1",
            "attempt_id": "attempt_runtime_only",
            "job_id": "job_runtime_only",
            "state": "RUNNING",
        },
    )
    Catalog(root / ".rlw" / "catalog.sqlite3").rebuild(root)


def test_health_and_overview_are_available(tmp_path):
    app = create_app(tmp_path)
    client = TestClient(app)

    health = client.get("/api/v1/health")
    overview = client.get("/api/v1/overview")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert overview.status_code == 200
    assert overview.json()["node"]["id"]


def test_jobs_api_reads_durable_catalog_records(tmp_path):
    _write_durable_execution_records(tmp_path)
    client = TestClient(create_app(tmp_path))

    response = client.get("/api/v1/jobs")

    assert response.status_code == 200
    assert [item["job_id"] for item in response.json()["items"]] == ["job_durable"]


def test_attempts_api_reads_durable_catalog_records(tmp_path):
    _write_durable_execution_records(tmp_path)
    client = TestClient(create_app(tmp_path))

    response = client.get("/api/v1/attempts")

    assert response.status_code == 200
    assert [item["attempt_id"] for item in response.json()["items"]] == ["attempt_durable"]


def test_overview_counts_durable_jobs_and_attempts(tmp_path):
    _write_durable_execution_records(tmp_path)
    client = TestClient(create_app(tmp_path))

    catalog = client.get("/api/v1/overview").json()["catalog"]

    assert catalog.get("jobs") == 1
    assert catalog.get("attempts") == 1


def test_evaluation_compare_api_uses_shared_metric_contract(tmp_path):
    for run_id, value in (("run_a", 0.75), ("run_b", 0.9)):
        atomic_write_json(
            tmp_path
            / "runs"
            / run_id
            / "records"
            / "metrics"
            / f"metric_{run_id}"
            / "metric.json",
            {
                "schema_version": "rlw.metric_record/v1",
                "metric_id": f"metric_{run_id}",
                "run_id": run_id,
                "name": "success_rate",
                "namespace": "pusht",
                "scope": "task",
                "unit": "ratio",
                "direction": "higher_is_better",
                "aggregation": "mean",
                "definition_version": "pusht/v1",
                "value": value,
            },
        )
    Catalog(tmp_path / ".rlw" / "catalog.sqlite3").rebuild(tmp_path)
    client = TestClient(create_app(tmp_path))

    response = client.get(
        "/api/v1/evaluation/compare",
        params=[("run_id", "run_a"), ("run_id", "run_b")],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "rlw.metric_comparison/v1"
    assert payload["run_ids"] == ["run_a", "run_b"]
    assert payload["rows"][0]["values"] == {"run_a": 0.75, "run_b": 0.9}
    assert payload["rows"][0]["best_run_ids"] == ["run_b"]


def test_api_allows_the_gui_origin_selected_by_rlw_gui_start(tmp_path, monkeypatch):
    origin = "http://127.0.0.1:5200"
    monkeypatch.setenv("RLW_GUI_ORIGIN", origin)
    client = TestClient(create_app(tmp_path))

    response = client.get("/api/v1/health", headers={"Origin": origin})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_run_observability_api_returns_the_shared_detail_contract(tmp_path):
    atomic_write_json(
        tmp_path / "runs" / "run_detail" / "manifest.json",
        {
            "schema_version": "rlw.run_manifest/v1",
            "run_id": "run_detail",
            "status": "READY",
        },
    )
    client = TestClient(create_app(tmp_path))

    response = client.get("/api/v1/runs/run_detail/observability")

    assert response.status_code == 200
    assert response.json()["schema_version"] == "rlw.run_observability/v1"
    assert response.json()["run"]["run_id"] == "run_detail"
    assert response.json()["summary"]["jobs"] == 0


def test_run_observability_api_returns_404_for_a_missing_run(tmp_path):
    response = TestClient(create_app(tmp_path)).get(
        "/api/v1/runs/run_missing/observability"
    )

    assert response.status_code == 404
    assert "does not exist" in response.json()["detail"]


def test_run_observability_api_equals_the_shared_service(tmp_path):
    atomic_write_json(tmp_path / "runs" / "run_equal" / "manifest.json", {"schema_version": "rlw.run_manifest/v1", "run_id": "run_equal", "status": "READY"})

    response = TestClient(create_app(tmp_path)).get("/api/v1/runs/run_equal/observability")

    assert response.status_code == 200
    assert response.json() == RunObservabilityService(tmp_path).inspect("run_equal")


def test_execute_api_requires_confirmation_and_accepts_a_ready_run(tmp_path, monkeypatch):
    atomic_write_json(tmp_path / "runs" / "run_execute" / "manifest.json", {"schema_version": "rlw.run_manifest/v1", "run_id": "run_execute", "status": "READY"})
    monkeypatch.setattr(
        "workbench.services.run_actions.GoldenPathService.execute",
        lambda self, run_id: {"run_id": run_id, "state": "SUCCEEDED"},
    )
    client = TestClient(create_app(tmp_path))

    mismatch = client.post("/api/v1/runs/run_execute/execute", json={"confirmation": "wrong"})
    accepted = client.post("/api/v1/runs/run_execute/execute", json={"confirmation": "run_execute"})

    assert mismatch.status_code == 400
    assert accepted.status_code == 202
    assert accepted.json() == {"schema_version": "rlw.run_execution_request/v1", "run_id": "run_execute", "status": "ACCEPTED"}


def test_execute_api_maps_missing_and_invalid_state(tmp_path):
    client = TestClient(create_app(tmp_path))
    missing = client.post("/api/v1/runs/run_missing/execute", json={"confirmation": "run_missing"})
    atomic_write_json(tmp_path / "runs" / "run_busy" / "manifest.json", {"schema_version": "rlw.run_manifest/v1", "run_id": "run_busy", "status": "RUNNING"})
    busy = client.post("/api/v1/runs/run_busy/execute", json={"confirmation": "run_busy"})

    assert missing.status_code == 404
    assert busy.status_code == 409


def test_reconcile_api_uses_the_local_action_service(tmp_path, monkeypatch):
    atomic_write_json(tmp_path / "runs" / "run_reconcile" / "manifest.json", {"schema_version": "rlw.run_manifest/v1", "run_id": "run_reconcile", "status": "SUCCEEDED"})
    monkeypatch.setattr(
        "workbench.services.run_actions.GoldenPathService.discover",
        lambda self, run_id: {"schema_version": "rlw.golden_discover/v1", "run_id": run_id, "artifacts": 0, "metrics": 0},
    )

    response = TestClient(create_app(tmp_path)).post("/api/v1/runs/run_reconcile/reconcile", json={})

    assert response.status_code == 200
    assert response.json()["schema_version"] == "rlw.golden_discover/v1"


def test_provider_api_projects_registry_and_shared_command_preview(tmp_path):
    recipe = tmp_path / "recipes" / "train" / "starvla.yaml"
    recipe.parent.mkdir(parents=True)
    recipe.write_text(
        "schema_version: rlw.recipe/v1\nprovider: starvla\nkind: train\n"
        "framework: qwen_oft\nnative_config: configs/train.yaml\n",
        encoding="utf-8",
    )
    client = TestClient(create_app(tmp_path))

    providers = client.get("/api/v1/providers")
    preview = client.post(
        "/api/v1/providers/starvla/command",
        json={"recipe": "recipes/train/starvla.yaml", "provider_env": "starvla"},
    )

    assert providers.status_code == 200
    assert [item["name"] for item in providers.json()["items"]] == ["lerobot", "starvla"]
    assert preview.status_code == 200
    assert preview.json()["provider"] == "starvla"
    assert preview.json()["executed"] is False


def test_provider_doctor_api_passes_provider_runtime_selection(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "workbench.api.app.run_provider_doctor",
        lambda target, **kwargs: {"target": target, **kwargs},
    )

    response = TestClient(create_app(tmp_path)).get(
        "/api/v1/providers/starvla/doctor",
        params={"environment": "vla-dev", "provider_root": "D:/starVLA"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "target": "starvla",
        "environment": "vla-dev",
        "provider_root": "D:/starVLA",
    }


def test_provider_runtime_api_configures_and_reads_machine_local_selection(tmp_path):
    checkout = tmp_path / "provider-fixture" / "starvla"
    for relative in (
        "starVLA/training/train_starvla.py",
        "starVLA/config/deepseeds/deepspeed_zero2.yaml",
    ):
        path = checkout / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# fixture\n", encoding="utf-8")
    client = TestClient(create_app(tmp_path))
    configured = client.post(
        "/api/v1/providers/starvla/configure",
        json={"environment": "vla-dev", "provider_root": str(checkout)},
    )
    runtime = client.get("/api/v1/providers/starvla/runtime")
    assert configured.status_code == 200
    assert configured.json()["schema_version"] == "rlw.provider_runtime/v1"
    assert runtime.status_code == 200
    assert runtime.json()["environment"] == "vla-dev"
    assert runtime.json()["checkout_root"] == str(checkout.resolve())


def test_provider_install_api_is_plan_only_without_exact_confirmation(tmp_path):
    response = TestClient(create_app(tmp_path)).post(
        "/api/v1/providers/starvla/install", json={}
    )
    assert response.status_code == 200
    assert response.json()["schema_version"] == "rlw.provider_install_plan/v1"
    assert response.json()["executed"] is False
    assert response.json()["confirmation"] == "starvla"


def test_golden_prepare_api_maps_starvla_workflow_and_runtime_override(tmp_path, monkeypatch):
    captured = {}

    def fake_prepare(self, recipe, **kwargs):
        captured["recipe"] = recipe
        captured.update(kwargs)
        return {"run_id": "run_starvla"}

    monkeypatch.setattr("workbench.api.app.GoldenPathService.prepare", fake_prepare)
    response = TestClient(create_app(tmp_path)).post(
        "/api/v1/golden/prepare",
        json={
            "workflow": "starvla-qwenoft",
            "dataset_revision": "a" * 40,
            "provider_root": "D:/starVLA",
            "provider_env": "vla-dev",
        },
    )
    assert response.status_code == 200
    assert response.json()["run_id"] == "run_starvla"
    assert captured == {
        "recipe": "recipes/train/starvla_qwenoft.yaml",
        "dataset_revision": "a" * 40,
        "provider_env": "vla-dev",
        "python_executable": None,
        "provider_root": "D:/starVLA",
    }

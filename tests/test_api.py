from fastapi.testclient import TestClient

from workbench.api.app import create_app
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

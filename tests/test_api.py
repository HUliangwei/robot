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

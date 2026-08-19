from fastapi.testclient import TestClient

from workbench.api.app import create_app


def test_health_and_overview_are_available(tmp_path):
    app = create_app(tmp_path)
    client = TestClient(app)

    health = client.get("/api/v1/health")
    overview = client.get("/api/v1/overview")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert overview.status_code == 200
    assert overview.json()["node"]["id"]

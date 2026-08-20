import json
from pathlib import Path

from fastapi.testclient import TestClient

from workbench.api.app import create_app
from workbench.cli.main import main
from workbench.services.observability import RunObservabilityService
from workbench.storage.manifests import atomic_write_json


def test_run_inspect_cli_uses_the_shared_observability_contract(
    tmp_path: Path, monkeypatch, capsys
):
    (tmp_path / "workspace").mkdir()
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='test-rlw'\n", encoding="utf-8"
    )
    atomic_write_json(
        tmp_path / "runs" / "run_cli" / "manifest.json",
        {
            "schema_version": "rlw.run_manifest/v1",
            "run_id": "run_cli",
            "status": "READY",
        },
    )
    monkeypatch.chdir(tmp_path)

    exit_code = main(["run", "inspect", "run_cli", "--json"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == RunObservabilityService(
        tmp_path
    ).inspect("run_cli")


def test_cli_api_and_service_equal_the_canonical_observability_fixture(
    tmp_path: Path, monkeypatch, capsys
):
    expected = json.loads(
        (Path(__file__).parent / "fixtures" / "run_observability_v1.json").read_text(
            encoding="utf-8"
        )
    )
    (tmp_path / "workspace").mkdir()
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test-rlw'\n", encoding="utf-8")
    atomic_write_json(tmp_path / "runs" / "run_contract" / "manifest.json", expected["run"])
    monkeypatch.chdir(tmp_path)

    exit_code = main(["run", "inspect", "run_contract", "--json"])
    cli_payload = json.loads(capsys.readouterr().out)
    api_response = TestClient(create_app(tmp_path)).get("/api/v1/runs/run_contract/observability")

    assert exit_code == 0
    assert api_response.status_code == 200
    assert RunObservabilityService(tmp_path).inspect("run_contract") == expected
    assert cli_payload == expected
    assert api_response.json() == expected


def test_run_inspect_cli_reports_a_missing_run_without_a_traceback(
    tmp_path: Path, monkeypatch, capsys
):
    (tmp_path / "workspace").mkdir()
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='test-rlw'\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    exit_code = main(["run", "inspect", "run_missing"])

    assert exit_code == 2
    output = capsys.readouterr().out
    assert "Run Inspect" in output
    assert "run 'run_missing' does not exist" in output

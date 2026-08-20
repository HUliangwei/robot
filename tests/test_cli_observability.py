import json
from pathlib import Path

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

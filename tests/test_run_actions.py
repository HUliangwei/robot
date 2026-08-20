from pathlib import Path

import pytest

from workbench.services.run_actions import LocalRunActionService, RunStateError
from workbench.storage.manifests import atomic_write_json


def _manifest(root: Path, status: str = "READY") -> None:
    atomic_write_json(
        root / "runs" / "run_action" / "manifest.json",
        {"schema_version": "rlw.run_manifest/v1", "run_id": "run_action", "status": status},
    )


def test_execute_validation_requires_the_exact_run_id(tmp_path: Path):
    _manifest(tmp_path)
    service = LocalRunActionService(tmp_path)

    with pytest.raises(ValueError, match="confirmation must exactly match"):
        service.validate_execute("run_action", "another_run")

    assert service.validate_execute("run_action", "run_action") == {
        "schema_version": "rlw.run_execution_request/v1",
        "run_id": "run_action",
        "status": "ACCEPTED",
    }
    with pytest.raises(RunStateError, match="execution request is already active"):
        service.validate_execute("run_action", "run_action")


def test_execute_validation_rejects_missing_and_active_runs(tmp_path: Path):
    service = LocalRunActionService(tmp_path)
    with pytest.raises(FileNotFoundError, match="does not exist"):
        service.validate_execute("run_missing", "run_missing")

    _manifest(tmp_path, status="RUNNING")
    with pytest.raises(RunStateError, match="cannot execute from state 'RUNNING'"):
        service.validate_execute("run_action", "run_action")


def test_local_actions_delegate_to_the_existing_golden_path(tmp_path: Path, monkeypatch):
    _manifest(tmp_path)
    monkeypatch.setattr(
        "workbench.services.run_actions.GoldenPathService.execute",
        lambda self, run_id: {"schema_version": "rlw.golden_execute/v1", "run_id": run_id},
    )
    monkeypatch.setattr(
        "workbench.services.run_actions.GoldenPathService.discover",
        lambda self, run_id: {"schema_version": "rlw.golden_discover/v1", "run_id": run_id},
    )
    service = LocalRunActionService(tmp_path)

    assert service.execute("run_action")["schema_version"] == "rlw.golden_execute/v1"
    assert service.reconcile("run_action")["schema_version"] == "rlw.golden_discover/v1"

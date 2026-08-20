import sys
from pathlib import Path

import pytest

from workbench.core.domain import CommandSpec
from workbench.executors.local import LocalExecutor


def test_local_executor_records_attempt_and_logs(tmp_path: Path):
    executor = LocalExecutor(tmp_path)
    result = executor.run(
        job_id="job_test",
        command=CommandSpec(argv=(sys.executable, "-c", "print('rlw-ok')")),
    )

    assert result.exit_code == 0
    assert result.state == "SUCCEEDED"
    assert "rlw-ok" in Path(result.stdout_path).read_text(encoding="utf-8")
    assert Path(result.attempt_path).exists()


def test_local_executor_persists_a_control_plane_attempt_id(tmp_path: Path):
    result = LocalExecutor(tmp_path).run(
        job_id="job_owned",
        command=CommandSpec(argv=(sys.executable, "-c", "print('owned')")),
        attempt_id="attempt_control_plane",
    )

    assert result.attempt_id == "attempt_control_plane"
    assert Path(result.attempt_path).parent.name == "attempt_control_plane"


def test_local_executor_rejects_an_unsafe_control_plane_attempt_id(tmp_path: Path):
    for attempt_id in ("../outside", ".."):
        with pytest.raises(ValueError, match="invalid Attempt ID"):
            LocalExecutor(tmp_path).run(
                job_id="job_owned",
                command=CommandSpec(argv=(sys.executable, "-c", "print('no')")),
                attempt_id=attempt_id,
            )

    assert not (tmp_path / ".rlw" / "state" / "jobs" / "outside").exists()

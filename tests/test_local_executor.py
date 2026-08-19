import sys
from pathlib import Path

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

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from workbench.core.domain import CommandSpec
from workbench.core.ids import new_id
from workbench.executors.base import ExecutionResult
from workbench.storage.manifests import atomic_write_json


class LocalExecutor:
    """Synchronous V0 LocalExecutor with durable attempt metadata.

    Remote/detached semantics are intentionally not implemented here; V3 puts
    them after the local GUI milestone.
    """

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root).resolve()

    def run(self, job_id: str, command: CommandSpec) -> ExecutionResult:
        attempt_id = new_id("attempt")
        state_dir = self.project_root / ".rlw" / "state" / "jobs" / job_id / attempt_id
        state_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = state_dir / "stdout.log"
        stderr_path = state_dir / "stderr.log"
        attempt_path = state_dir / "attempt.json"
        started = datetime.now(timezone.utc).isoformat()

        env = os.environ.copy()
        env.update({str(k): str(v) for k, v in command.env.items()})
        cwd = Path(command.cwd).resolve() if command.cwd else self.project_root
        argv = command.normalized_argv()

        atomic_write_json(
            attempt_path,
            {
                "schema_version": "rlw.execution_attempt/v1",
                "attempt_id": attempt_id,
                "job_id": job_id,
                "state": "RUNNING",
                "argv": list(argv),
                "cwd": str(cwd),
                "started_at": started,
            },
        )
        with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
            completed = subprocess.run(argv, cwd=cwd, env=env, stdout=stdout, stderr=stderr, check=False, text=True)
        state = "SUCCEEDED" if completed.returncode == 0 else "FAILED"
        atomic_write_json(
            attempt_path,
            {
                "schema_version": "rlw.execution_attempt/v1",
                "attempt_id": attempt_id,
                "job_id": job_id,
                "state": state,
                "argv": list(argv),
                "cwd": str(cwd),
                "started_at": started,
                "ended_at": datetime.now(timezone.utc).isoformat(),
                "exit_code": completed.returncode,
            },
        )
        return ExecutionResult(
            job_id=job_id,
            attempt_id=attempt_id,
            state=state,
            exit_code=completed.returncode,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            attempt_path=str(attempt_path),
        )

from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class ExecutionResult:
    job_id: str
    attempt_id: str
    state: str
    exit_code: int
    stdout_path: str
    stderr_path: str
    attempt_path: str

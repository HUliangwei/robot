from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def run_pytest(
    root: str | Path,
    *,
    quiet: bool = False,
    show_output: bool = False,
    extra_args: list[str] | None = None,
) -> dict[str, Any]:
    """Stream pytest to the terminal while persisting the complete transcript."""
    project_root = Path(root).resolve()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_dir = project_root / ".rlw" / "logs" / "tests"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"pytest_{stamp}.log"

    argv = [sys.executable, "-m", "pytest", "-q" if quiet else "-v"]
    if show_output:
        argv.append("-s")
    if extra_args:
        argv.extend(extra_args)

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    print("RLW · Dev Test")
    print("────────────────────────────────────────────────────────")
    print("# Run pytest, stream the live output, and preserve the complete transcript.")
    print()
    print("COMMAND")
    print("  > " + " ".join(argv))
    print()
    print("OUTPUT · STREAM")
    print("────────────────────────────────────────────────────────")

    with log_path.open("w", encoding="utf-8", newline="") as log:
        log.write("COMMAND\n> " + " ".join(argv) + "\n\nOUTPUT\n")
        process = subprocess.Popen(
            argv,
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
        )
        assert process.stdout is not None
        while True:
            raw = process.stdout.readline()
            if not raw:
                break
            text = raw.decode("utf-8", errors="replace")
            print(text, end="")
            log.write(text)
        exit_code = process.wait()

    print()
    print("RESULT")
    print(f"  exit_code  {exit_code}")
    print(f"  full_log   {log_path}")
    if exit_code != 0:
        print("  status     FAILED")
    else:
        print("  status     PASSED")

    return {
        "schema_version": "rlw.dev_test/v1",
        "exit_code": exit_code,
        "status": "PASSED" if exit_code == 0 else "FAILED",
        "log_path": str(log_path),
        "command": argv,
    }

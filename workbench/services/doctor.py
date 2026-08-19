from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def _command_version(command: list[str]) -> str | None:
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    text = (completed.stdout or completed.stderr).strip().splitlines()
    return text[0] if text else None


def run_doctor(root: str | Path) -> dict[str, Any]:
    project_root = Path(root).resolve()
    checks = {
        "python": {"ok": True, "value": sys.version.split()[0]},
        "git": {"ok": shutil.which("git") is not None, "value": _command_version(["git", "--version"])},
        "project_root": {"ok": project_root.exists(), "value": str(project_root)},
        "workspace": {"ok": (project_root / "workspace").exists(), "value": str(project_root / "workspace")},
        "torch": {"ok": importlib.util.find_spec("torch") is not None},
        "lerobot": {"ok": importlib.util.find_spec("lerobot") is not None},
        "nvidia_smi": {"ok": shutil.which("nvidia-smi") is not None},
        "node": {"ok": shutil.which("node") is not None, "value": _command_version(["node", "--version"])},
        "npm": {"ok": shutil.which("npm") is not None, "value": _command_version(["npm", "--version"])},
    }
    return {
        "schema_version": "rlw.doctor/v1",
        "platform": platform.platform(),
        "cwd": os.getcwd(),
        "checks": checks,
        "healthy_required": all(checks[name]["ok"] for name in ("python", "git", "project_root")),
    }

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def _resolve_command(name: str) -> str | None:
    if os.name == "nt" and name == "npm":
        return shutil.which("npm.cmd") or shutil.which("npm")
    return shutil.which(name)


def _command_version(command: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = (completed.stdout or completed.stderr or "").strip().splitlines()
    return text[0] if text else None


def _check(ok: bool, value: Any = None, *, required: bool) -> dict[str, Any]:
    return {"ok": bool(ok), "value": value, "required": required}


def run_doctor(root: str | Path) -> dict[str, Any]:
    """Inspect the RLW control plane only.

    Provider packages such as torch and lerobot intentionally live in isolated
    provider environments and are checked by provider doctor instead.
    """
    project_root = Path(root).resolve()
    git = _resolve_command("git")
    node = _resolve_command("node")
    npm = _resolve_command("npm")
    nvidia = _resolve_command("nvidia-smi")

    checks = {
        "python": _check(True, sys.version.split()[0], required=True),
        "git": _check(git is not None, _command_version([git, "--version"]) if git else None, required=True),
        "project_root": _check(project_root.exists(), str(project_root), required=True),
        "workspace": _check((project_root / "workspace").exists(), str(project_root / "workspace"), required=True),
        "node": _check(node is not None, _command_version([node, "--version"]) if node else None, required=False),
        "npm": _check(npm is not None, _command_version([npm, "--version"]) if npm else None, required=False),
        "nvidia_smi": _check(nvidia is not None, nvidia, required=False),
    }
    required = [item for item in checks.values() if item["required"]]
    return {
        "schema_version": "rlw.doctor/v2",
        "scope": "control_plane",
        "platform": platform.platform(),
        "cwd": os.getcwd(),
        "checks": checks,
        "healthy_required": all(item["ok"] for item in required),
        "note": "torch/lerobot are provider checks; use `rlw provider doctor <environment>`.",
    }

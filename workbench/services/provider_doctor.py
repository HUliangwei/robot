from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from workbench.providers.lerobot import LeRobotAdapter


def _resolve_conda() -> str | None:
    configured = os.environ.get("CONDA_EXE")
    if configured and Path(configured).exists():
        return str(Path(configured))
    candidates = ("conda.exe", "conda.bat", "conda") if os.name == "nt" else ("conda",)
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def _run(argv: list[str], timeout: int = 60) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "exit_code": None, "stdout": "", "stderr": str(exc)}
    return {
        "ok": completed.returncode == 0,
        "exit_code": completed.returncode,
        "stdout": completed.stdout or "",
        "stderr": completed.stderr or "",
    }


def list_providers() -> dict[str, Any]:
    adapter = LeRobotAdapter()
    return {
        "schema_version": "rlw.provider_list/v1",
        "items": [
            {
                "name": "lerobot",
                "spec": adapter.spec().__dict__,
                "capabilities": adapter.capabilities(),
                "default_environment": "lerobot-win",
            }
        ],
    }


def run_provider_doctor(environment: str = "lerobot-win") -> dict[str, Any]:
    conda = _resolve_conda()
    checks: dict[str, dict[str, Any]] = {
        "conda": {"ok": conda is not None, "value": conda, "required": True},
    }
    if conda is None:
        return {
            "schema_version": "rlw.provider_doctor/v1",
            "provider": "lerobot",
            "environment": environment,
            "checks": checks,
            "ready": False,
        }

    probe_code = r"""
import importlib.util, json, sys
payload = {"python": sys.version.split()[0]}
for name in ("torch", "lerobot"):
    found = importlib.util.find_spec(name) is not None
    payload[name + "_installed"] = found
    if found:
        module = __import__(name)
        payload[name + "_version"] = getattr(module, "__version__", None)
if payload.get("torch_installed"):
    import torch
    payload["cuda_available"] = bool(torch.cuda.is_available())
else:
    payload["cuda_available"] = False
print(json.dumps(payload))
""".strip()

    probe = _run([conda, "run", "-n", environment, "python", "-c", probe_code], timeout=90)
    payload: dict[str, Any] = {}
    if probe["ok"]:
        for line in reversed(probe["stdout"].splitlines()):
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                payload = json.loads(line)
                break
            except json.JSONDecodeError:
                continue

    checks["environment"] = {
        "ok": probe["ok"],
        "value": environment,
        "required": True,
    }
    checks["python"] = {
        "ok": bool(payload.get("python")),
        "value": payload.get("python"),
        "required": True,
    }
    checks["torch"] = {
        "ok": bool(payload.get("torch_installed")),
        "value": payload.get("torch_version"),
        "required": True,
    }
    checks["lerobot"] = {
        "ok": bool(payload.get("lerobot_installed")),
        "value": payload.get("lerobot_version"),
        "required": True,
    }
    checks["cuda"] = {
        "ok": bool(payload.get("cuda_available")),
        "value": payload.get("cuda_available"),
        "required": False,
    }
    ready = all(item["ok"] for item in checks.values() if item["required"])
    return {
        "schema_version": "rlw.provider_doctor/v1",
        "provider": "lerobot",
        "environment": environment,
        "checks": checks,
        "ready": ready,
        "stderr": probe["stderr"][-1600:] if not probe["ok"] else "",
    }

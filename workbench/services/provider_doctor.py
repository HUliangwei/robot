from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from workbench.providers.registry import (
    get_provider,
    get_registration,
    provider_descriptors,
    provider_names,
)


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
    return {"schema_version": "rlw.provider_list/v1", "items": provider_descriptors()}


def _resolve_target(target: str, environment: str | None) -> tuple[str, str]:
    normalized = target.lower()
    if normalized in provider_names():
        registration = get_registration(normalized)
        return normalized, environment or registration.default_environment
    if environment is not None:
        raise ValueError(f"unknown provider {target!r}")
    return "lerobot", target


def _probe_code(packages: tuple[str, ...]) -> str:
    return (
        "import importlib.util,json,sys\n"
        "payload={'python':sys.version.split()[0]}\n"
        f"packages={list(packages)!r}\n"
        "for name in packages:\n"
        " found=importlib.util.find_spec(name) is not None\n"
        " payload[name+'_installed']=found\n"
        " if found:\n"
        "  module=__import__(name)\n"
        "  payload[name+'_version']=getattr(module,'__version__',None)\n"
        "if payload.get('torch_installed'):\n"
        " import torch\n"
        " payload['cuda_available']=bool(torch.cuda.is_available())\n"
        "else: payload['cuda_available']=False\n"
        "print(json.dumps(payload))"
    )


def run_provider_doctor(
    target: str = "lerobot",
    *,
    environment: str | None = None,
    conda_prefix: str | Path | None = None,
    python_executable: str | Path | None = None,
    provider_root: str | Path | None = None,
) -> dict[str, Any]:
    provider, selected_environment = _resolve_target(target, environment)
    registration = get_registration(provider)
    if sum(bool(item) for item in (environment, conda_prefix, python_executable)) > 1:
        raise ValueError("choose environment, conda_prefix, or python_executable, not more than one")
    conda = _resolve_conda()
    exact_python: Path | None = None
    if conda_prefix:
        prefix = Path(conda_prefix).expanduser().resolve()
        exact_python = prefix / ("python.exe" if os.name == "nt" else "bin/python")
    elif python_executable:
        exact_python = Path(python_executable).expanduser().resolve()
    uses_conda_name = exact_python is None
    checks: dict[str, dict[str, Any]] = {
        "conda": {"ok": conda is not None, "value": conda, "required": uses_conda_name},
    }
    if exact_python is not None:
        checks["python_executable"] = {
            "ok": exact_python.is_file(), "value": str(exact_python), "required": True
        }
    if provider_root is not None:
        checkout = Path(provider_root).expanduser().resolve()
        checks["provider_root"] = {
            "ok": checkout.is_dir(), "value": str(checkout), "required": True
        }
        for check_name, relative in registration.checkout_files:
            path = checkout / Path(relative)
            checks[check_name] = {
                "ok": path.is_file(), "value": str(path), "required": True
            }

    probe = {"ok": False, "stdout": "", "stderr": "conda executable was not found"}
    payload: dict[str, Any] = {}
    if exact_python is not None and exact_python.is_file():
        probe = _run([str(exact_python), "-c", _probe_code(registration.probe_packages)], timeout=90)
    elif conda is not None:
        probe = _run(
            [conda, "run", "-n", selected_environment, "python", "-c", _probe_code(registration.probe_packages)],
            timeout=90,
        )
    if probe["ok"]:
        for line in reversed(probe["stdout"].splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    payload = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue

    checks["environment"] = {
        "ok": bool(probe["ok"]),
        "value": str(exact_python) if exact_python else selected_environment,
        "required": True,
    }
    checks["python"] = {
        "ok": bool(payload.get("python")), "value": payload.get("python"), "required": True
    }
    for package in registration.probe_packages:
        checks[package] = {
            "ok": bool(payload.get(package + "_installed")),
            "value": payload.get(package + "_version"),
            "required": True,
        }
    checks["cuda"] = {
        "ok": bool(payload.get("cuda_available")),
        "value": payload.get("cuda_available"),
        "required": False,
    }
    return {
        "schema_version": "rlw.provider_doctor/v1",
        "provider": provider,
        "environment": selected_environment,
        "conda_prefix": str(Path(conda_prefix).expanduser().resolve()) if conda_prefix else None,
        "python_executable": str(exact_python) if exact_python else None,
        "provider_root": str(Path(provider_root).expanduser().resolve()) if provider_root else None,
        "checks": checks,
        "ready": all(item["ok"] for item in checks.values() if item["required"]),
        "stderr": str(probe.get("stderr") or "")[-1600:] if not probe["ok"] else "",
    }


def _project_file(project_root: Path, relative: str) -> Path:
    root = project_root.resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("recipe must be inside the project root") from exc
    if not candidate.is_file():
        raise FileNotFoundError(f"recipe does not exist: {relative}")
    return candidate


def preview_provider_command(
    project_root: str | Path,
    provider: str,
    recipe: str,
    *,
    provider_env: str | None = None,
    python_executable: str | None = None,
    provider_root: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    recipe_path = _project_file(root, recipe)
    payload = yaml.safe_load(recipe_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("recipe must contain a YAML object")
    declared = str(payload.get("provider") or "")
    if declared != provider:
        raise ValueError(
            f"recipe provider {declared!r} does not match requested provider {provider!r}"
        )
    adapter = get_provider(provider)
    resolved = adapter.resolve_config(payload)
    command = adapter.build_command(
        str(payload.get("kind") or "train"),
        resolved,
        provider_env=provider_env,
        python_executable=python_executable,
        cwd=str(provider_root) if provider_root else None,
    )
    command_payload = asdict(command)
    command_payload["argv"] = list(command.normalized_argv())
    return {
        "schema_version": "rlw.provider_command_preview/v1",
        "provider": provider,
        "recipe": recipe_path.relative_to(root).as_posix(),
        "resolved_config": resolved,
        "command": command_payload,
        "executed": False,
    }

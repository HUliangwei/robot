from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from workbench.providers.registry import get_registration
from workbench.services.provider_runtime import configure_provider_runtime


Runner = Callable[..., dict[str, Any]]


def _conda_executable() -> str:
    return shutil.which("conda.exe" if __import__("os").name == "nt" else "conda") or "conda"


def _run(argv: list[str], *, cwd: str | None = None, env: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            env={**os.environ, **(env or {})},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        return {"ok": False, "exit_code": None, "stdout": "", "stderr": str(exc)}
    return {
        "ok": completed.returncode == 0,
        "exit_code": completed.returncode,
        "stdout": completed.stdout or "",
        "stderr": completed.stderr or "",
    }


def build_provider_install_plan(
    root: str | Path,
    provider: str,
    *,
    environment: str | None = None,
    conda_prefix: str | Path | None = None,
    provider_root: str | Path | None = None,
    repository: str | None = None,
    revision: str | None = None,
) -> dict[str, Any]:
    name = provider.lower()
    registration = get_registration(name)
    if not registration.install_repository:
        raise ValueError(f"automatic install is not available for provider {name!r}")
    checkout = (
        Path(provider_root).expanduser().resolve()
        if provider_root
        else Path(root).resolve() / ".rlw" / "providers" / name / "source"
    )
    selected_environment = environment or registration.default_environment
    selected_prefix = (
        Path(conda_prefix).expanduser().resolve()
        if conda_prefix
        else (Path(root).resolve() / "envs" / name if environment is None else None)
    )
    selector = ["--prefix", str(selected_prefix)] if selected_prefix else ["-n", selected_environment]
    selected_repository = repository or registration.install_repository
    selected_revision = revision or registration.install_revision or "main"
    python_version = registration.install_python or "3.10"
    conda = _conda_executable()
    if checkout.exists():
        checkout_step = {
            "id": "update_checkout",
            "argv": ["git", "-C", str(checkout), "pull", "--ff-only", "origin", selected_revision],
            "cwd": str(checkout),
            "required": True,
        }
    else:
        checkout_step = {
            "id": "clone",
            "argv": [
                "git", "clone", "--branch", selected_revision, "--single-branch",
                selected_repository, str(checkout),
            ],
            "cwd": str(checkout.parent),
            "required": True,
        }
    prefix_python = selected_prefix / "python.exe" if selected_prefix else None
    environment_ready = bool(
        prefix_python
        and prefix_python.is_file()
        and (selected_prefix / "conda-meta" / "history").is_file()
    )
    create_step = (
        {
            "id": "verify_environment",
            "argv": [str(prefix_python), "-c", "import sys; assert sys.version_info[:2] == (3, 10)"],
            "cwd": str(Path(root).resolve()),
            "required": True,
        }
        if environment_ready
        else {
            "id": "create_environment",
            "argv": [conda, "create", f"python={python_version}", *selector, "-y"],
            "cwd": str(Path(root).resolve()),
            "required": True,
        }
    )
    site_packages = selected_prefix / "Lib" / "site-packages" if selected_prefix else None
    pytorch_ready = bool(
        site_packages
        and prefix_python
        and prefix_python.is_file()
        and any(site_packages.glob("torch-2.6.0+cu124.dist-info"))
        and any(site_packages.glob("torchvision-0.21.0+cu124.dist-info"))
    )
    pytorch_step = (
        {
            "id": "verify_pytorch",
            "argv": [
                str(prefix_python), "-c",
                "import torch,torchvision; assert torch.cuda.is_available()",
            ],
            "cwd": str(checkout),
            "required": True,
        }
        if pytorch_ready
        else {
            "id": "install_pytorch",
            "argv": [
                conda, "run", *selector, "python", "-m", "pip", "install",
                "torch==2.6.0", "torchvision==0.21.0",
                "--index-url", "https://download.pytorch.org/whl/cu124",
            ],
            "cwd": str(checkout),
            "required": True,
        }
    )
    compatibility_steps: list[dict[str, Any]] = []
    if os.name == "nt":
        cython_ready = bool(
            site_packages
            and any(site_packages.glob("Cython-*.dist-info"))
            and any(site_packages.glob("accumulation_tree-0.6.4.dist-info"))
        )
        if cython_ready:
            compatibility_steps.append({
                "id": "verify_windows_build_prerequisites",
                "argv": [
                    str(prefix_python), "-c", "import Cython, accumulation_tree",
                ],
                "cwd": str(checkout),
                "required": True,
            })
        else:
            compatibility_steps.extend([
                {
                    "id": "install_cython",
                    "argv": [
                        conda, "run", *selector, "python", "-m", "pip",
                        "install", "Cython<3",
                    ],
                    "cwd": str(checkout),
                    "required": True,
                },
                {
                    "id": "install_accumulation_tree",
                    "argv": [
                        conda, "run", *selector, "python", "-m", "pip",
                        "install", "accumulation-tree==0.6.4",
                        "--no-build-isolation", "--no-cache-dir",
                    ],
                    "cwd": str(checkout),
                    "required": True,
                },
            ])
        deepspeed_ready = bool(
            site_packages and any(site_packages.glob("deepspeed-0.16.9*.dist-info"))
        )
        compatibility_steps.append({
            "id": "verify_deepspeed" if deepspeed_ready else "install_deepspeed",
            "argv": (
                [
                    str(prefix_python), "-c",
                    "from importlib.metadata import version; "
                    "assert version('deepspeed').startswith('0.16.9')",
                ]
                if deepspeed_ready
                else [
                    conda, "run", *selector, "python", "-m", "pip", "install",
                    "deepspeed @ git+https://github.com/deepspeedai/DeepSpeed.git@v0.16.9",
                    "--no-build-isolation", "--no-deps",
                ]
            ),
            "env": {"DS_BUILD_OPS": "0", "DS_SKIP_CUDA_CHECK": "1"},
            "cwd": str(checkout),
            "required": True,
        })
    steps = [
        checkout_step,
        create_step,
        pytorch_step,
        *compatibility_steps,
        {
            "id": "install_requirements",
            "argv": [
                conda, "run", *selector, "python", "-m", "pip",
                "install", "--no-build-isolation", "-r", str(checkout / "requirements.txt"),
            ],
            "env": {"DS_BUILD_OPS": "0", "DS_SKIP_CUDA_CHECK": "1"},
            "cwd": str(checkout),
            "required": True,
        },
        {
            "id": "install_editable",
            "argv": [
                conda, "run", *selector, "python", "-m", "pip",
                "install", "-e", str(checkout),
            ],
            "cwd": str(checkout),
            "required": True,
        },
    ]
    return {
        "schema_version": "rlw.provider_install_plan/v1",
        "provider": name,
        "environment": selected_environment,
        "conda_prefix": str(selected_prefix) if selected_prefix else None,
        "checkout_root": str(checkout),
        "repository": selected_repository,
        "revision": selected_revision,
        "python_version": python_version,
        "confirmation": name,
        "steps": steps,
        "manual_requirements": [
            {
                "name": "flash-attn",
                "required_for": "Provider configurations that enable FlashAttention",
                "reason": "The build/wheel must match the selected CUDA and PyTorch runtime.",
                "automatic": False,
            }
        ],
        "executed": False,
    }


def execute_provider_install(
    root: str | Path,
    plan: dict[str, Any],
    *,
    confirmation: str,
    runner: Runner | None = None,
) -> dict[str, Any]:
    if plan.get("schema_version") != "rlw.provider_install_plan/v1":
        raise ValueError("invalid Provider install plan schema")
    provider = str(plan.get("provider") or "")
    if confirmation != plan.get("confirmation"):
        raise ValueError(f"confirmation must exactly match {provider!r}")
    execute = runner or _run
    checkout = Path(str(plan["checkout_root"]))
    checkout.parent.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for step in plan.get("steps") or []:
        if runner is None:
            raw = execute(
                list(step["argv"]), cwd=step.get("cwd"), env=step.get("env") or {}
            )
        else:
            raw = execute(list(step["argv"]), cwd=step.get("cwd"))
        result = {
            "id": step["id"],
            "ok": bool(raw.get("ok")),
            "exit_code": raw.get("exit_code"),
            "stdout": str(raw.get("stdout") or "")[-2000:],
            "stderr": str(raw.get("stderr") or "")[-2000:],
        }
        results.append(result)
        if step.get("required", True) and not result["ok"]:
            return {
                "schema_version": "rlw.provider_install_result/v1",
                "provider": provider,
                "status": "FAILED",
                "failed_step": step["id"],
                "steps_completed": sum(1 for item in results if item["ok"]),
                "steps": results,
                "runtime": None,
            }
    runtime_args: dict[str, Any] = {
        "provider_root": checkout,
        "source": {"repository": plan.get("repository"), "revision": plan.get("revision")},
    }
    if plan.get("conda_prefix"):
        runtime_args["conda_prefix"] = str(plan["conda_prefix"])
    else:
        runtime_args["environment"] = str(plan["environment"])
    runtime = configure_provider_runtime(root, provider, **runtime_args)
    return {
        "schema_version": "rlw.provider_install_result/v1",
        "provider": provider,
        "status": "SUCCEEDED",
        "failed_step": None,
        "steps_completed": len(results),
        "steps": results,
        "runtime": runtime,
    }

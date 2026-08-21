from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workbench.providers.registry import get_registration
from workbench.storage.manifests import atomic_write_json, read_json


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _runtime_path(root: str | Path, provider: str) -> Path:
    name = get_registration(provider).factory().spec().name
    return Path(root).resolve() / ".rlw" / "providers" / f"{name}.json"


def read_provider_runtime(root: str | Path, provider: str) -> dict[str, Any] | None:
    path = _runtime_path(root, provider)
    if not path.is_file():
        return None
    value = read_json(path)
    if not isinstance(value, dict) or value.get("schema_version") != "rlw.provider_runtime/v1":
        raise ValueError(f"invalid Provider runtime record: {path}")
    if value.get("provider") != provider.lower():
        raise ValueError(f"Provider runtime identity mismatch: {path}")
    return value


def configure_provider_runtime(
    root: str | Path,
    provider: str,
    *,
    environment: str | None = None,
    conda_prefix: str | Path | None = None,
    provider_root: str | Path | None = None,
    python_executable: str | Path | None = None,
    source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    name = provider.lower()
    registration = get_registration(name)
    selected_environment = str(environment).strip() if environment else None
    selected_prefix = str(Path(conda_prefix).expanduser().resolve()) if conda_prefix else None
    selected_python = str(Path(python_executable).expanduser().resolve()) if python_executable else None
    if sum(bool(item) for item in (selected_environment, selected_prefix, selected_python)) != 1:
        raise ValueError(
            "choose environment or python_executable, or conda_prefix; exactly one is required"
        )
    if selected_prefix:
        prefix = Path(selected_prefix)
        if not prefix.is_dir():
            raise ValueError(f"Conda prefix not found: {prefix}")
        candidate = prefix / ("python.exe" if __import__("os").name == "nt" else "bin/python")
        if not candidate.is_file():
            raise ValueError(f"python executable not found in Conda prefix: {candidate}")
        selected_python = str(candidate.resolve())
    if selected_python and not Path(selected_python).is_file():
        raise ValueError(f"python executable not found: {selected_python}")

    checkout: Path | None = None
    if provider_root is not None:
        checkout = Path(provider_root).expanduser().resolve()
        if not checkout.is_dir():
            raise ValueError(f"Provider checkout root not found: {checkout}")
    if registration.checkout_files:
        if checkout is None:
            raise ValueError(f"provider_root is required for {name}")
        missing = [relative for _, relative in registration.checkout_files if not (checkout / relative).is_file()]
        if missing:
            raise ValueError("missing required Provider files: " + ", ".join(missing))

    source_data = source or {}
    safe_source = {
        key: source_data[key]
        for key in ("repository", "revision")
        if source_data.get(key) not in (None, "")
    }
    record = {
        "schema_version": "rlw.provider_runtime/v1",
        "provider": name,
        "environment": selected_environment,
        "conda_prefix": selected_prefix,
        "python_executable": selected_python,
        "checkout_root": str(checkout) if checkout else None,
        "source": safe_source,
        "configured_at": _utc_now(),
    }
    atomic_write_json(_runtime_path(root, name), record)
    return record


def resolve_provider_runtime(
    root: str | Path,
    provider: str,
    *,
    environment: str | None = None,
    conda_prefix: str | Path | None = None,
    python_executable: str | Path | None = None,
    provider_root: str | Path | None = None,
) -> dict[str, Any]:
    name = provider.lower()
    registration = get_registration(name)
    configured = read_provider_runtime(root, name)
    if sum(bool(item) for item in (environment, conda_prefix, python_executable)) > 1:
        raise ValueError("choose environment, conda_prefix, or python_executable, not more than one")

    explicit_runtime = bool(environment or conda_prefix or python_executable)
    if explicit_runtime:
        conda_env = str(environment).strip() if environment else None
        selected_prefix = str(Path(conda_prefix).expanduser().resolve()) if conda_prefix else None
        if selected_prefix:
            candidate = Path(selected_prefix) / (
                "python.exe" if __import__("os").name == "nt" else "bin/python"
            )
            selected_python = str(candidate.resolve())
        else:
            selected_python = str(python_executable) if python_executable else None
        source = "explicit"
    elif configured:
        conda_env = configured.get("environment")
        selected_prefix = configured.get("conda_prefix")
        selected_python = configured.get("python_executable")
        source = "configured"
    else:
        conda_env = registration.default_environment
        selected_prefix = None
        selected_python = None
        source = "default"

    if provider_root is not None:
        selected_root = str(provider_root)
        source = "explicit"
    elif configured:
        selected_root = configured.get("checkout_root")
    else:
        selected_root = None
    result = {
        "schema_version": "rlw.provider_runtime_resolution/v1",
        "provider": name,
        "conda_env": conda_env,
        "python_executable": selected_python,
        "provider_root": selected_root,
        "source": source,
    }
    if selected_prefix:
        result["conda_prefix"] = selected_prefix
    return result

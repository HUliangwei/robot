from pathlib import Path

import pytest

from workbench.services.provider_runtime import (
    configure_provider_runtime,
    read_provider_runtime,
    resolve_provider_runtime,
)


def _starvla_checkout(root: Path) -> Path:
    checkout = root / "provider-source"
    entrypoint = checkout / "starVLA" / "training" / "train_starvla.py"
    accelerate = checkout / "starVLA" / "config" / "deepseeds" / "deepspeed_zero2.yaml"
    entrypoint.parent.mkdir(parents=True)
    accelerate.parent.mkdir(parents=True)
    entrypoint.write_text("# fixture\n", encoding="utf-8")
    accelerate.write_text("compute_environment: LOCAL_MACHINE\n", encoding="utf-8")
    return checkout


def test_configure_provider_runtime_writes_one_atomic_machine_local_record(tmp_path: Path):
    checkout = _starvla_checkout(tmp_path)

    record = configure_provider_runtime(
        tmp_path,
        "starvla",
        environment="starvla-dev",
        provider_root=checkout,
        source={"repository": "https://github.com/starVLA/starVLA", "revision": "starVLA"},
    )

    path = tmp_path / ".rlw" / "providers" / "starvla.json"
    assert path.is_file()
    assert read_provider_runtime(tmp_path, "starvla") == record
    assert record["schema_version"] == "rlw.provider_runtime/v1"
    assert record["provider"] == "starvla"
    assert record["environment"] == "starvla-dev"
    assert record["python_executable"] is None
    assert record["checkout_root"] == str(checkout.resolve())
    assert "secret" not in str(record).lower()
    assert list(path.parent.glob(".*.tmp")) == []


def test_configure_starvla_rejects_an_incomplete_checkout(tmp_path: Path):
    checkout = tmp_path / "incomplete"
    checkout.mkdir()

    with pytest.raises(ValueError, match="missing required Provider files"):
        configure_provider_runtime(
            tmp_path,
            "starvla",
            environment="starvla",
            provider_root=checkout,
        )

    assert read_provider_runtime(tmp_path, "starvla") is None


def test_provider_runtime_requires_exactly_one_python_selector(tmp_path: Path):
    checkout = _starvla_checkout(tmp_path)

    with pytest.raises(ValueError, match="choose environment or python_executable"):
        configure_provider_runtime(
            tmp_path,
            "starvla",
            environment="starvla",
            python_executable="python.exe",
            provider_root=checkout,
        )


def test_runtime_resolution_prefers_explicit_then_configured_then_registry_default(tmp_path: Path):
    checkout = _starvla_checkout(tmp_path)
    configured = configure_provider_runtime(
        tmp_path,
        "starvla",
        environment="configured-env",
        provider_root=checkout,
    )

    from_config = resolve_provider_runtime(tmp_path, "starvla")
    explicit = resolve_provider_runtime(
        tmp_path,
        "starvla",
        environment="explicit-env",
        provider_root="D:/explicit/starVLA",
    )
    default = resolve_provider_runtime(tmp_path / "empty", "lerobot")

    assert from_config == {
        "schema_version": "rlw.provider_runtime_resolution/v1",
        "provider": "starvla",
        "conda_env": "configured-env",
        "python_executable": None,
        "provider_root": configured["checkout_root"],
        "source": "configured",
    }
    assert explicit["conda_env"] == "explicit-env"
    assert explicit["provider_root"] == "D:/explicit/starVLA"
    assert explicit["source"] == "explicit"
    assert default["conda_env"] == "lerobot-win"
    assert default["provider_root"] is None
    assert default["source"] == "default"

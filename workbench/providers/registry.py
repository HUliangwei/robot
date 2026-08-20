from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable

from workbench.providers.base import ProviderAdapter
from workbench.providers.lerobot import LeRobotAdapter
from workbench.providers.starvla import StarVLAAdapter


@dataclass(frozen=True)
class ProviderRegistration:
    factory: Callable[[], ProviderAdapter]
    default_environment: str
    probe_packages: tuple[str, ...]
    checkout_files: tuple[tuple[str, str], ...] = ()


_REGISTRY: dict[str, ProviderRegistration] = {
    "lerobot": ProviderRegistration(
        factory=LeRobotAdapter,
        default_environment="lerobot-win",
        probe_packages=("torch", "lerobot"),
    ),
    "starvla": ProviderRegistration(
        factory=StarVLAAdapter,
        default_environment="starvla",
        probe_packages=("torch", "starVLA", "accelerate"),
        checkout_files=(
            ("training_entrypoint", "starVLA/training/train_starvla.py"),
            ("accelerate_config", "starVLA/config/deepseeds/deepspeed_zero2.yaml"),
        ),
    ),
}


def provider_names() -> tuple[str, ...]:
    return tuple(_REGISTRY)


def get_registration(name: str) -> ProviderRegistration:
    try:
        return _REGISTRY[name.lower()]
    except KeyError as exc:
        raise ValueError(
            f"unknown provider {name!r}; expected one of {', '.join(provider_names())}"
        ) from exc


def get_provider(name: str) -> ProviderAdapter:
    return get_registration(name).factory()


def provider_descriptors() -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for name, registration in _REGISTRY.items():
        adapter = registration.factory()
        items.append(
            {
                "name": name,
                "spec": asdict(adapter.spec()),
                "capabilities": adapter.capabilities(),
                "default_environment": registration.default_environment,
            }
        )
    return items


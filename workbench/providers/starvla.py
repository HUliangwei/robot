"""Thin StarVLA adapter: native projection and command construction only."""
from __future__ import annotations

from typing import Any

from workbench.core.domain import CommandSpec, ProviderSpec


_FRAMEWORKS = {
    "qwen_oft": {
        "id": "qwen_oft",
        "native_name": "QwenOFT",
        "backbone": "Qwen-VL",
        "action_head": "OFT",
        "fusion": "action-token hidden-state regression",
    },
    "qwen_groot": {
        "id": "qwen_groot",
        "native_name": "QwenGR00T",
        "backbone": "Qwen3-VL",
        "action_head": "GR00T flow-matching",
        "fusion": "vision-language-action co-training",
    }
}

def _stringify(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


class StarVLAAdapter:
    def spec(self) -> ProviderSpec:
        return ProviderSpec(
            name="starvla",
            adapter_version="0.1",
            capabilities=("dataset", "train", "architecture_research", "eval"),
        )

    def capabilities(self) -> dict[str, Any]:
        return {
            "provider": "starvla",
            "jobs": ["train"],
            "frameworks": list(_FRAMEWORKS.values()),
            "native_config_passthrough": True,
            "execution_modes": ["conda_env", "python_executable"],
        }

    def validate(self, config: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        framework = config.get("framework")
        if not framework:
            errors.append("framework is required")
        elif str(framework).lower() not in _FRAMEWORKS:
            errors.append(f"unsupported framework: {framework}")
        if not config.get("native_config"):
            errors.append("native_config is required")
        num_processes = config.get("num_processes", 1)
        if isinstance(num_processes, bool) or not isinstance(num_processes, int) or num_processes < 1:
            errors.append("num_processes must be a positive integer")
        return errors

    def resolve_config(self, config: dict[str, Any]) -> dict[str, Any]:
        errors = self.validate(config)
        if errors:
            raise ValueError("; ".join(errors))
        resolved = dict(config)
        framework = str(resolved["framework"]).lower()
        resolved.update(
            {
                "framework": framework,
                "native_framework": _FRAMEWORKS[framework]["native_name"],
                "entrypoint": resolved.get("entrypoint", "starVLA/training/train_starvla.py"),
                "accelerate_config": resolved.get(
                    "accelerate_config",
                    "starVLA/config/deepseeds/deepspeed_zero2.yaml",
                ),
                "num_processes": resolved.get("num_processes", 1),
                "native_overrides": dict(resolved.get("native_overrides") or {}),
            }
        )
        return resolved

    def build_command(
        self,
        job_kind: str,
        config: dict[str, Any],
        *,
        provider_env: str | None = None,
        python_executable: str | None = None,
        cwd: str | None = None,
    ) -> CommandSpec:
        if job_kind != "train":
            raise NotImplementedError(
                f"StarVLA R16 adapter only builds train commands, got {job_kind!r}"
            )
        if provider_env and python_executable:
            raise ValueError("choose provider_env or python_executable, not both")
        resolved = self.resolve_config(config)
        if python_executable:
            argv = [python_executable, "-m", "accelerate.commands.launch"]
        elif provider_env:
            argv = ["conda", "run", "-n", provider_env, "accelerate", "launch"]
        else:
            argv = ["accelerate", "launch"]
        argv += [
            "--config_file",
            str(resolved["accelerate_config"]),
            "--num_processes",
            str(resolved["num_processes"]),
            str(resolved["entrypoint"]),
            "--config_yaml",
            str(resolved["native_config"]),
            "--framework.name",
            str(resolved["native_framework"]),
        ]
        for key, value in sorted(resolved["native_overrides"].items()):
            argv.extend((f"--{key}", _stringify(value)))
        return CommandSpec(tuple(argv), cwd=cwd)


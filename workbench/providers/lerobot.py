"""Thin LeRobot adapter: config projection + command construction only."""
from __future__ import annotations

from typing import Any

from workbench.core.domain import CommandSpec, ProviderSpec


class LeRobotAdapter:
    def spec(self) -> ProviderSpec:
        return ProviderSpec(
            name="lerobot",
            adapter_version="0.1",
            capabilities=("dataset", "train", "rollout", "eval", "hardware"),
        )

    def capabilities(self) -> dict[str, Any]:
        return {
            "provider": "lerobot",
            "jobs": ["train", "rollout", "evaluate"],
            "native_config_passthrough": True,
        }

    def validate(self, config: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if not config.get("policy_type"):
            errors.append("policy_type is required")
        if not config.get("dataset_repo_id") and config.get("job_kind", "train") == "train":
            errors.append("dataset_repo_id is required for train")
        return errors

    def resolve_config(self, config: dict[str, Any]) -> dict[str, Any]:
        return dict(config)

    def build_command(self, job_kind: str, config: dict[str, Any]) -> CommandSpec:
        if job_kind != "train":
            raise NotImplementedError(f"LeRobot V0 adapter only builds train commands, got {job_kind!r}")
        errors = self.validate({**config, "job_kind": job_kind})
        if errors:
            raise ValueError("; ".join(errors))
        argv = [
            "lerobot-train",
            f"--policy.type={config['policy_type']}",
            f"--dataset.repo_id={config['dataset_repo_id']}",
        ]
        for key, value in sorted((config.get("native_overrides") or {}).items()):
            argv.append(f"--{key}={value}")
        return CommandSpec(tuple(argv))

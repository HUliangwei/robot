"""Thin LeRobot adapter: config projection + command construction only."""
from __future__ import annotations

from typing import Any

from workbench.core.domain import CommandSpec, ProviderSpec


def _stringify(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


class LeRobotAdapter:
    def spec(self) -> ProviderSpec:
        return ProviderSpec(
            name="lerobot",
            adapter_version="0.2",
            capabilities=("dataset", "train", "rollout", "eval", "hardware"),
        )

    def capabilities(self) -> dict[str, Any]:
        return {
            "provider": "lerobot",
            "jobs": ["train", "rollout", "evaluate"],
            "native_config_passthrough": True,
            "execution_modes": ["conda_env", "python_executable"],
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

    def build_command(
        self,
        job_kind: str,
        config: dict[str, Any],
        *,
        provider_env: str | None = None,
        python_executable: str | None = None,
        cwd: str | None = None,
    ) -> CommandSpec:
        if job_kind not in {"train", "evaluate"}:
            raise NotImplementedError(f"LeRobot adapter cannot build {job_kind!r} commands")
        if provider_env and python_executable:
            raise ValueError("choose provider_env or python_executable, not both")

        if python_executable:
            argv = [python_executable]
        elif provider_env:
            argv = ["conda", "run", "-n", provider_env, "python"]
        else:
            argv = ["python"]

        if job_kind == "evaluate":
            required = ("policy_path", "output_dir", "env_type")
            missing = [key for key in required if not config.get(key)]
            if missing:
                raise ValueError("missing evaluation config: " + ", ".join(missing))
            argv += [
                "-m", "lerobot.scripts.lerobot_eval",
                f"--policy.path={config['policy_path']}",
                f"--env.type={config['env_type']}",
                f"--eval.n_episodes={config.get('n_episodes', 1)}",
                f"--eval.batch_size={config.get('batch_size', 1)}",
                f"--output_dir={config['output_dir']}",
            ]
        else:
            errors = self.validate({**config, "job_kind": job_kind})
            if errors:
                raise ValueError("; ".join(errors))
            argv += [
                "-m", "lerobot.scripts.lerobot_train",
                f"--policy.type={config['policy_type']}",
                f"--dataset.repo_id={config['dataset_repo_id']}",
            ]
            if config.get("dataset_revision"):
                argv.append(f"--dataset.revision={config['dataset_revision']}")
            for key, value in sorted((config.get("native_overrides") or {}).items()):
                argv.append(f"--{key}={_stringify(value)}")
        return CommandSpec(tuple(argv), cwd=cwd)

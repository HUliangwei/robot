from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml
import pytest

from workbench.services.golden_path import GoldenPathService
from workbench.storage.catalog import Catalog


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )


def _commit_all(root: Path, message: str = "test baseline") -> None:
    _git(root, "add", ".")
    _git(root, "commit", "-m", message)


def _init_repo(root: Path) -> None:
    _git(root, "init")
    _git(root, "config", "user.email", "rlw-test@example.invalid")
    _git(root, "config", "user.name", "RLW Test")


def test_prepare_pusht_act_creates_canonical_run_and_dataset(tmp_path: Path):
    _init_repo(tmp_path)
    recipe = tmp_path / "recipes" / "train" / "pusht_act.yaml"
    recipe.parent.mkdir(parents=True)
    recipe.write_text(
        """
schema_version: rlw.recipe/v1
name: pusht_act_baseline
kind: train
provider: lerobot
policy_type: act
dataset_repo_id: lerobot/pusht
native_overrides:
  steps: 10
  batch_size: 2
""".strip() + "\n",
        encoding="utf-8",
    )
    _commit_all(tmp_path)

    service = GoldenPathService(tmp_path)
    result = service.prepare(
        recipe_path=recipe,
        dataset_revision="0123456789abcdef0123456789abcdef01234567",
        provider_env="lerobot-win",
    )

    run_manifest = Path(result["run_manifest"])
    dataset_manifest = Path(result["dataset_manifest"])
    command_manifest = Path(result["command_manifest"])

    assert run_manifest.exists()
    assert dataset_manifest.exists()
    assert command_manifest.exists()

    run = json.loads(run_manifest.read_text(encoding="utf-8"))
    command = json.loads(command_manifest.read_text(encoding="utf-8"))
    assert run["schema_version"] == "rlw.run_manifest/v1"
    assert run["status"] == "READY"
    assert run["git_state"]["source_tree_clean_at_prepare"] is True
    assert run["experiment"]["experiment_id"].startswith("experiment_")
    assert run["trial"]["trial_id"].startswith("trial_")
    assert run["job"]["job_id"].startswith("job_")
    assert run["lineage"]["dataset"]["revision"] == "0123456789abcdef0123456789abcdef01234567"
    assert command["argv"][:5] == ["conda", "run", "-n", "lerobot-win", "python"]
    assert "-m" in command["argv"]
    assert "lerobot.scripts.lerobot_train" in command["argv"]
    assert any(arg.startswith("--output_dir=") for arg in command["argv"])

    catalog = Catalog(tmp_path / ".rlw" / "catalog.sqlite3")
    summary = catalog.rebuild(tmp_path)
    assert summary["run"] == 1
    assert summary["dataset"] == 1


def test_prepare_writes_portable_run_research_record(tmp_path: Path):
    _init_repo(tmp_path)
    recipe = tmp_path / "recipes" / "train" / "pusht_act.yaml"
    recipe.parent.mkdir(parents=True)
    recipe.write_text(
        "schema_version: rlw.recipe/v1\n"
        "name: pusht_act_portable\n"
        "question: Can ACT reproduce PushT?\n"
        "kind: train\n"
        "provider: lerobot\n"
        "policy_type: act\n"
        "dataset_repo_id: lerobot/pusht\n"
        "native_overrides:\n  steps: 10\n  batch_size: 2\n",
        encoding="utf-8",
    )
    _commit_all(tmp_path)

    result = GoldenPathService(tmp_path).prepare(
        recipe,
        dataset_revision="1" * 40,
        provider_env="lerobot-win",
    )
    run_dir = Path(result["run_dir"])
    expected_records = (
        run_dir / "run.yaml",
        run_dir / "resolved_config.yaml",
        run_dir / "lineage.json",
        run_dir / "jobs" / "train" / "job.json",
    )
    assert all(path.exists() for path in expected_records), "portable Run record is incomplete"
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    run_spec = yaml.safe_load((run_dir / "run.yaml").read_text(encoding="utf-8"))
    resolved = yaml.safe_load((run_dir / "resolved_config.yaml").read_text(encoding="utf-8"))
    lineage = json.loads((run_dir / "lineage.json").read_text(encoding="utf-8"))
    job = json.loads((run_dir / "jobs" / "train" / "job.json").read_text(encoding="utf-8"))

    assert run_spec == {
        "schema_version": "rlw.run_spec/v1",
        "experiment": {
            "name": "pusht_act_portable",
            "question": "Can ACT reproduce PushT?",
        },
        "dataset": {"repo_id": "lerobot/pusht", "revision": "1" * 40},
        "policy": {"provider": "lerobot", "architecture": "act"},
        "training": {
            "recipe": "recipes/train/pusht_act.yaml",
            "native_overrides": {"steps": 10, "batch_size": 2},
        },
    }
    assert resolved["schema_version"] == "rlw.resolved_config/v1"
    assert resolved["run_id"] == result["run_id"]
    assert resolved["trial_id"] == manifest["trial"]["trial_id"]
    assert resolved["experiment_id"] == manifest["experiment"]["experiment_id"]
    assert resolved["dataset_revision"] == "1" * 40
    assert resolved.get("provider_runtime") == {
        "conda_env": "lerobot-win",
        "python_executable": None,
    }
    assert resolved.get("git_commit") == manifest["git_commit"]
    assert lineage == {
        "schema_version": "rlw.lineage/v1",
        "run_id": result["run_id"],
        "dataset": {
            "dataset_id": "lerobot_pusht",
            "revision": "1" * 40,
            "manifest": f"datasets/lerobot_pusht/{'1' * 40}/dataset.yaml",
        },
        "parents": [],
    }
    assert job["schema_version"] == "rlw.job/v1"
    assert job["job_id"] == result["job_id"]
    assert job["run_id"] == result["run_id"]
    assert job["state"] == "READY"
    assert job["command"] == f"runs/{result['run_id']}/resolved_command.json"
    assert manifest["paths"]["run_spec"] == f"runs/{result['run_id']}/run.yaml"
    assert manifest["paths"]["resolved_config"] == f"runs/{result['run_id']}/resolved_config.yaml"
    assert manifest["paths"]["lineage"] == f"runs/{result['run_id']}/lineage.json"
    assert manifest["paths"]["job_record"] == f"runs/{result['run_id']}/jobs/train/job.json"


def test_execute_archives_durable_job_and_attempt_records(tmp_path: Path):
    _init_repo(tmp_path)
    recipe = tmp_path / "recipe.yaml"
    recipe.write_text(
        "schema_version: rlw.recipe/v1\n"
        "name: portable_attempt\n"
        "kind: train\n"
        "provider: lerobot\n"
        "policy_type: act\n"
        "dataset_repo_id: lerobot/pusht\n",
        encoding="utf-8",
    )
    fake_lerobot = tmp_path / "lerobot" / "__init__.py"
    fake_lerobot.parent.mkdir()
    fake_lerobot.write_text("__version__ = 'test'\n", encoding="utf-8")
    (tmp_path / "torch.py").write_text(
        "__version__ = 'test'\n"
        "class cuda:\n"
        "    @staticmethod\n"
        "    def is_available():\n"
        "        return False\n",
        encoding="utf-8",
    )
    _commit_all(tmp_path)

    service = GoldenPathService(tmp_path)
    prepared = service.prepare(
        recipe,
        dataset_revision="2" * 40,
        python_executable=sys.executable,
    )
    run_dir = Path(prepared["run_dir"])
    command_path = Path(prepared["command_manifest"])
    command = json.loads(command_path.read_text(encoding="utf-8"))
    command["argv"] = [sys.executable, "-c", "print('portable-attempt')"]
    command_path.write_text(json.dumps(command), encoding="utf-8")

    executed = service.execute(prepared["run_id"])
    job_path = run_dir / "jobs" / "train" / "job.json"
    job = json.loads(job_path.read_text(encoding="utf-8"))
    attempt_path = run_dir / "jobs" / "train" / "attempts" / f"{executed['attempt_id']}.json"
    assert attempt_path.exists(), "ExecutionAttempt was not archived in the Run record"
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))

    assert job["state"] == "SUCCEEDED"
    assert job["last_attempt_id"] == executed["attempt_id"]
    assert job["attempt_ids"] == [executed["attempt_id"]]
    assert job["started_at"]
    assert job["ended_at"]
    assert attempt["schema_version"] == "rlw.execution_attempt/v1"
    assert attempt["attempt_id"] == executed["attempt_id"]
    assert attempt["job_id"] == prepared["job_id"]
    assert attempt["state"] == "SUCCEEDED"
    assert attempt["exit_code"] == 0
    assert attempt["stdout_path"].startswith(".rlw/state/jobs/")
    assert attempt["stderr_path"].startswith(".rlw/state/jobs/")


def test_prepare_rejects_mutable_or_missing_dataset_revision(tmp_path: Path):
    recipe = tmp_path / "recipe.yaml"
    recipe.write_text(
        "schema_version: rlw.recipe/v1\nname: x\nkind: train\nprovider: lerobot\n"
        "policy_type: act\ndataset_repo_id: lerobot/pusht\n",
        encoding="utf-8",
    )
    service = GoldenPathService(tmp_path)
    for revision in ("", "main", "master", "latest"):
        try:
            service.prepare(recipe, dataset_revision=revision, provider_env="lerobot-win")
        except ValueError as exc:
            assert "immutable dataset revision" in str(exc)
        else:
            raise AssertionError(f"revision {revision!r} should fail")


def test_prepare_rejects_recipe_outside_project_root(tmp_path: Path):
    _init_repo(tmp_path)
    (tmp_path / "tracked.txt").write_text("baseline\n", encoding="utf-8")
    _commit_all(tmp_path)
    outside_recipe = tmp_path.with_name(f"{tmp_path.name}_outside_recipe.yaml")
    outside_recipe.write_text(
        "schema_version: rlw.recipe/v1\n"
        "name: outside\n"
        "kind: train\n"
        "provider: lerobot\n"
        "policy_type: act\n"
        "dataset_repo_id: lerobot/pusht\n",
        encoding="utf-8",
    )
    try:
        with pytest.raises(ValueError, match="inside the project root"):
            GoldenPathService(tmp_path).prepare(
                outside_recipe,
                dataset_revision="3" * 40,
                provider_env="lerobot-win",
            )
    finally:
        outside_recipe.unlink(missing_ok=True)


def test_discover_registers_checkpoint_rollout_evaluation_and_metrics(tmp_path: Path):
    _init_repo(tmp_path)
    recipe = tmp_path / "recipe.yaml"
    recipe.write_text(
        "schema_version: rlw.recipe/v1\nname: x\nkind: train\nprovider: lerobot\n"
        "policy_type: act\ndataset_repo_id: lerobot/pusht\n",
        encoding="utf-8",
    )
    _commit_all(tmp_path)
    service = GoldenPathService(tmp_path)
    prepared = service.prepare(recipe, dataset_revision="a" * 40, provider_env="lerobot-win")
    run_dir = Path(prepared["run_dir"])
    output_dir = run_dir / "artifacts" / "training"
    ckpt = output_dir / "checkpoints" / "000010" / "pretrained_model"
    ckpt.mkdir(parents=True)
    (ckpt / "config.json").write_text("{}", encoding="utf-8")
    rollout = output_dir / "rollouts" / "episode_000"
    rollout.mkdir(parents=True)
    (rollout / "episode.json").write_text('{"success": true}', encoding="utf-8")
    metrics = output_dir / "evaluation" / "metrics.json"
    metrics.parent.mkdir(parents=True)
    metrics.write_text(
        '{"success_rate": {"value": 0.75, "unit": "ratio", '
        '"direction": "higher_is_better", "aggregation": "mean", '
        '"scope": "task", "episodes": 20, "definition_version": "pusht/v1"}, '
        '"reward": 12.5}',
        encoding="utf-8",
    )

    discovered = service.discover(prepared["run_id"])
    assert discovered["artifacts"] == 3
    assert discovered["metrics"] == 2

    catalog = Catalog(tmp_path / ".rlw" / "catalog.sqlite3")
    summary = catalog.rebuild(tmp_path)
    assert summary["artifact"] == 3
    assert summary["metric"] == 2
    assert {item["kind"] for item in catalog.list_records("artifact")} == {
        "checkpoint",
        "rollout",
        "evaluation",
    }
    success = next(item for item in catalog.list_records("metric") if item["name"] == "success_rate")
    assert success["unit"] == "ratio"
    assert success["direction"] == "higher_is_better"
    assert success["aggregation"] == "mean"
    assert success["scope"] == "task"
    assert success["episodes"] == 20
    assert success["definition_version"] == "pusht/v1"

    again = service.discover(prepared["run_id"])
    assert again["artifacts"] >= 1
    catalog.rebuild(tmp_path)
    assert catalog.count("metric") == 2

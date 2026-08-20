from __future__ import annotations

import json
import subprocess
from pathlib import Path

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


def test_discover_registers_checkpoint_and_metrics(tmp_path: Path):
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
    metrics = output_dir / "eval_step_000010" / "official" / "metrics.json"
    metrics.parent.mkdir(parents=True)
    metrics.write_text('{"success_rate": 0.75, "reward": 12.5}', encoding="utf-8")

    discovered = service.discover(prepared["run_id"])
    assert discovered["artifacts"] >= 1
    assert discovered["metrics"] == 2

    catalog = Catalog(tmp_path / ".rlw" / "catalog.sqlite3")
    summary = catalog.rebuild(tmp_path)
    assert summary["artifact"] >= 1
    assert summary["metric"] == 2

    again = service.discover(prepared["run_id"])
    assert again["artifacts"] >= 1
    catalog.rebuild(tmp_path)
    assert catalog.count("metric") == 2

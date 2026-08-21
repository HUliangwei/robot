from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from workbench.services.golden_path import GoldenPathService


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )


def _init_clean_repo(root: Path, recipe_text: str | None = None) -> Path:
    _git(root, "init")
    _git(root, "config", "user.email", "rlw-test@example.invalid")
    _git(root, "config", "user.name", "RLW Test")
    recipe = root / "recipes" / "train" / "pusht_act.yaml"
    recipe.parent.mkdir(parents=True, exist_ok=True)
    recipe.write_text(
        recipe_text
        or (
            "schema_version: rlw.recipe/v1\n"
            "name: pusht_act_baseline\n"
            "kind: train\n"
            "provider: lerobot\n"
            "policy_type: act\n"
            "dataset_repo_id: lerobot/pusht\n"
            "native_overrides:\n  steps: 10\n"
        ),
        encoding="utf-8",
    )
    (root / "tracked.txt").write_text("clean\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "test baseline")
    return recipe


def test_prepare_rejects_dirty_source_tree(tmp_path: Path):
    recipe = _init_clean_repo(tmp_path)
    (tmp_path / "tracked.txt").write_text("dirty\n", encoding="utf-8")

    with pytest.raises(ValueError, match="source worktree is dirty"):
        GoldenPathService(tmp_path).prepare(
            recipe,
            dataset_revision="a" * 40,
            provider_env="lerobot-win",
        )


def test_preflight_rejects_run_prepared_from_different_commit(tmp_path: Path):
    recipe = _init_clean_repo(tmp_path)
    service = GoldenPathService(tmp_path)
    prepared = service.prepare(recipe, dataset_revision="b" * 40, provider_env="lerobot-win")

    # A new source commit means the prepared run no longer names the code that would execute.
    (tmp_path / "tracked.txt").write_text("new commit\n", encoding="utf-8")
    _git(tmp_path, "add", "tracked.txt")
    _git(tmp_path, "commit", "-m", "source changed")

    report = service.preflight(prepared["run_id"], probe_provider=False)
    checks = {item["name"]: item for item in report["checks"]}
    assert report["ok"] is False
    assert checks["git_commit_match"]["ok"] is False


def test_preflight_allows_rlw_generated_records_without_marking_source_dirty(tmp_path: Path):
    recipe = _init_clean_repo(tmp_path)
    revision = "c" * 40
    snapshot = tmp_path / "datasets" / "hub" / "datasets--lerobot--pusht" / "snapshots" / revision
    snapshot.mkdir(parents=True)
    service = GoldenPathService(tmp_path)
    prepared = service.prepare(recipe, dataset_revision=revision, provider_env="lerobot-win")

    # prepare itself creates runs/ and datasets/ metadata; those must not invalidate the source snapshot.
    report = service.preflight(prepared["run_id"], probe_provider=False)
    checks = {item["name"]: item for item in report["checks"]}
    assert checks["source_tree_clean"]["ok"] is True
    assert checks["prepared_from_clean_source"]["ok"] is True
    assert checks["dataset_revision_available"]["ok"] is True


def test_preflight_does_not_ignore_tracked_dataset_mutations(tmp_path: Path):
    recipe = _init_clean_repo(tmp_path)
    definition = tmp_path / "datasets" / "custom" / "definition.yaml"
    definition.parent.mkdir(parents=True)
    definition.write_text("version: 1\n", encoding="utf-8")
    _git(tmp_path, "add", "datasets/custom/definition.yaml")
    _git(tmp_path, "commit", "-m", "track dataset definition")
    service = GoldenPathService(tmp_path)
    prepared = service.prepare(recipe, dataset_revision="9" * 40, provider_env="lerobot-win")

    definition.write_text("version: 2\n", encoding="utf-8")
    report = service.preflight(prepared["run_id"], probe_provider=False)
    checks = {item["name"]: item for item in report["checks"]}

    assert checks["source_tree_clean"]["ok"] is False
    assert "datasets/custom/definition.yaml" in checks["source_tree_clean"]["detail"]["dirty_paths"]


def test_execute_refuses_when_preflight_fails(tmp_path: Path):
    recipe = _init_clean_repo(tmp_path)
    service = GoldenPathService(tmp_path)
    prepared = service.prepare(recipe, dataset_revision="d" * 40, provider_env="lerobot-win")
    manifest_path = Path(prepared["run_manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["git_commit"] = "0" * 40
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="preflight failed"):
        service.execute(prepared["run_id"])

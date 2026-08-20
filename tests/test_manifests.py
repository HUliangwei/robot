import json
from pathlib import Path

import yaml

from workbench.storage import manifests
from workbench.storage.manifests import atomic_write_json, read_json


def test_atomic_write_json_replaces_target_without_temp_file(tmp_path: Path):
    target = tmp_path / "manifest.json"
    atomic_write_json(target, {"schema_version": "rlw.run_manifest/v1", "run_id": "run_1"})
    assert read_json(target)["run_id"] == "run_1"
    assert not list(tmp_path.glob("*.tmp"))
    assert json.loads(target.read_text(encoding="utf-8"))["schema_version"] == "rlw.run_manifest/v1"


def test_atomic_write_yaml_replaces_target_without_temp_file(tmp_path: Path):
    assert hasattr(manifests, "atomic_write_yaml"), "atomic YAML persistence is missing"
    target = tmp_path / "resolved_config.yaml"
    manifests.atomic_write_yaml(
        target,
        {"schema_version": "rlw.resolved_config/v1", "run_id": "run_1"},
    )

    assert yaml.safe_load(target.read_text(encoding="utf-8"))["run_id"] == "run_1"
    assert not list(tmp_path.glob("*.tmp"))

import json
from pathlib import Path

from workbench.storage.manifests import atomic_write_json, read_json


def test_atomic_write_json_replaces_target_without_temp_file(tmp_path: Path):
    target = tmp_path / "manifest.json"
    atomic_write_json(target, {"schema_version": "rlw.run_manifest/v1", "run_id": "run_1"})
    assert read_json(target)["run_id"] == "run_1"
    assert not list(tmp_path.glob("*.tmp"))
    assert json.loads(target.read_text(encoding="utf-8"))["schema_version"] == "rlw.run_manifest/v1"

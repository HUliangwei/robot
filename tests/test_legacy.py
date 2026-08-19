import json
from pathlib import Path

from workbench.services.legacy import scan_legacy_workspace


def test_legacy_scan_is_read_only_and_reports_known_assets(tmp_path: Path):
    project = tmp_path / "workspace" / "pusht"
    (project / "outputs" / "eval" / "demo").mkdir(parents=True)
    (project / "commands.json").write_text('{"train": "python train.py"}', encoding="utf-8")
    (project / "PROGRESS.md").write_text("# progress", encoding="utf-8")
    (project / "outputs" / "eval" / "demo" / "metrics.json").write_text(
        json.dumps({"success_rate": 0.5}), encoding="utf-8"
    )

    before = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))
    report = scan_legacy_workspace(tmp_path)
    after = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))

    assert before == after
    assert report["schema_version"] == "rlw.legacy_scan/v1"
    assert report["projects"][0]["name"] == "pusht"
    assert report["projects"][0]["metrics_files"] == ["workspace/pusht/outputs/eval/demo/metrics.json"]

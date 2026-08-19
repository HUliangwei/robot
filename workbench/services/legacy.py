"""Read-only discovery of pre-RLW workspace assets.

The scanner deliberately does not fabricate missing provenance.  It creates
candidates that can be reviewed before a later import step.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def scan_legacy_workspace(root: str | Path) -> dict[str, Any]:
    project_root = Path(root).resolve()
    workspace = project_root / "workspace"
    projects: list[dict[str, Any]] = []
    if workspace.is_dir():
        for project in sorted(p for p in workspace.iterdir() if p.is_dir() and not p.name.startswith(".")):
            metrics = sorted(_rel(project_root, p) for p in project.rglob("metrics.json"))
            eval_info = sorted(_rel(project_root, p) for p in project.rglob("eval_info.json"))
            checkpoint_dirs = []
            for p in project.rglob("pretrained_model"):
                if p.is_dir() and "checkpoints" in p.parts:
                    checkpoint_dirs.append(_rel(project_root, p))
            projects.append(
                {
                    "name": project.name,
                    "source_path": _rel(project_root, project),
                    "provenance_quality": "inferred",
                    "has_readme": (project / "README.md").exists(),
                    "has_progress": (project / "PROGRESS.md").exists(),
                    "has_commands": (project / "commands.json").exists(),
                    "has_workflows": (project / "workflows.json").exists(),
                    "has_weights_index": (project / "weights.json").exists(),
                    "metrics_files": metrics,
                    "evaluation_info_files": eval_info,
                    "checkpoint_dirs": sorted(checkpoint_dirs),
                }
            )
    return {
        "schema_version": "rlw.legacy_scan/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "workspace",
        "read_only": True,
        "projects": projects,
        "notes": [
            "This scan is candidate discovery only; it does not register artifacts or invent provenance.",
            "Review Git commit, dataset revision, provider version, and run boundaries before importing legacy research records.",
        ],
    }

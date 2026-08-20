from __future__ import annotations

import platform
import socket
from pathlib import Path
from typing import Any

from workbench.services.legacy import scan_legacy_workspace
from workbench.storage.catalog import Catalog


def build_overview(root: str | Path) -> dict[str, Any]:
    project_root = Path(root).resolve()
    catalog = Catalog(project_root / ".rlw" / "catalog.sqlite3")
    legacy = scan_legacy_workspace(project_root)
    return {
        "schema_version": "rlw.overview/v1",
        "node": {
            "id": socket.gethostname() or platform.node() or "local",
            "capabilities": {"execution": True, "archive": True, "gui": True},
        },
        "catalog": {
            "runs": catalog.count("run"),
            "datasets": catalog.count("dataset"),
            "jobs": catalog.count("job"),
            "attempts": catalog.count("attempt"),
            "total_records": catalog.count(),
        },
        "legacy": {
            "projects": len(legacy["projects"]),
            "project_names": [item["name"] for item in legacy["projects"]],
        },
    }

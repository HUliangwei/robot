from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workbench.services.doctor import run_doctor
from workbench.services.legacy import scan_legacy_workspace
from workbench.services.overview import build_overview
from workbench.storage.catalog import Catalog
from workbench.storage.manifests import atomic_write_json
from workbench.storage.paths import ensure_runtime_dirs, find_project_root


def _print(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def _root(value: str | None) -> Path:
    return Path(value).resolve() if value else find_project_root()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rlw", description="Robot Learning Workbench control plane")
    parser.add_argument("--root", help="project root; defaults to auto-detection")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="initialize machine-local .rlw state")
    sub.add_parser("doctor", help="inspect local runtime capabilities")
    sub.add_parser("overview", help="show local control-plane summary")

    cat = sub.add_parser("catalog", help="catalog operations")
    cat_sub = cat.add_subparsers(dest="catalog_command", required=True)
    cat_sub.add_parser("rebuild")
    cat_sub.add_parser("verify")

    legacy = sub.add_parser("legacy", help="legacy workspace discovery")
    legacy_sub = legacy.add_subparsers(dest="legacy_command", required=True)
    scan = legacy_sub.add_parser("scan")
    scan.add_argument("--write", action="store_true", help="write candidate report under .rlw/import_candidates")

    sub.add_parser("api", help="start FastAPI on 127.0.0.1:8000")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = _root(args.root)
    runtime = ensure_runtime_dirs(root)
    catalog = Catalog(root / ".rlw" / "catalog.sqlite3")

    if args.command == "init":
        _print({"status": "initialized", "root": str(root), "runtime": {k: str(v) for k, v in runtime.items()}})
        return 0
    if args.command == "doctor":
        _print(run_doctor(root))
        return 0
    if args.command == "overview":
        _print(build_overview(root))
        return 0
    if args.command == "catalog":
        if args.catalog_command == "rebuild":
            _print({"status": "rebuilt", "summary": catalog.rebuild(root)})
            return 0
        _print(catalog.verify_sources(root))
        return 0
    if args.command == "legacy":
        report = scan_legacy_workspace(root)
        if args.write:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            path = runtime["import_candidates"] / f"legacy_scan_{stamp}.json"
            atomic_write_json(path, report)
            report = {**report, "written_to": str(path)}
        _print(report)
        return 0
    if args.command == "api":
        import uvicorn
        uvicorn.run("workbench.api.app:app", host="127.0.0.1", port=8000, reload=False)
        return 0
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())

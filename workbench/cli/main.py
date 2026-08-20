from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workbench.services.doctor import run_doctor
from workbench.services.golden_path import GoldenPathService
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
    p = argparse.ArgumentParser(prog="rlw", description="Robot Learning Workbench control plane")
    p.add_argument("--root")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("doctor")
    sub.add_parser("overview")

    cat = sub.add_parser("catalog")
    cs = cat.add_subparsers(dest="catalog_command", required=True)
    cs.add_parser("rebuild")
    cs.add_parser("verify")

    legacy = sub.add_parser("legacy")
    ls = legacy.add_subparsers(dest="legacy_command", required=True)
    scan = ls.add_parser("scan")
    scan.add_argument("--write", action="store_true")

    golden = sub.add_parser("golden", help="PushT+ACT canonical golden path")
    gs = golden.add_subparsers(dest="golden_command", required=True)
    prep = gs.add_parser("prepare")
    prep.add_argument("--recipe", default="recipes/train/pusht_act.yaml")
    prep.add_argument("--dataset-revision", required=True)
    prep.add_argument("--provider-env", default="lerobot-win")
    prep.add_argument("--python-executable")
    preflight = gs.add_parser("preflight")
    preflight.add_argument("run_id")
    preflight.add_argument("--no-provider-probe", action="store_true")
    exe = gs.add_parser("execute")
    exe.add_argument("run_id")
    disc = gs.add_parser("discover")
    disc.add_argument("run_id")
    detect = gs.add_parser("detect-revision")
    detect.add_argument("--repo-id", default="lerobot/pusht")

    sub.add_parser("api")
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    root = _root(a.root)
    runtime = ensure_runtime_dirs(root)
    catalog = Catalog(root / ".rlw" / "catalog.sqlite3")

    if a.command == "init":
        _print({"status": "initialized", "root": str(root), "runtime": {k: str(v) for k, v in runtime.items()}})
        return 0
    if a.command == "doctor":
        _print(run_doctor(root))
        return 0
    if a.command == "overview":
        _print(build_overview(root))
        return 0
    if a.command == "catalog":
        _print({"status": "rebuilt", "summary": catalog.rebuild(root)} if a.catalog_command == "rebuild" else catalog.verify_sources(root))
        return 0
    if a.command == "legacy":
        report = scan_legacy_workspace(root)
        if a.write:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            path = runtime["import_candidates"] / f"legacy_scan_{stamp}.json"
            atomic_write_json(path, report)
            report = {**report, "written_to": str(path)}
        _print(report)
        return 0
    if a.command == "golden":
        svc = GoldenPathService(root)
        if a.golden_command == "prepare":
            provider_env = None if a.python_executable else a.provider_env
            _print(
                svc.prepare(
                    a.recipe,
                    dataset_revision=a.dataset_revision,
                    provider_env=provider_env,
                    python_executable=a.python_executable,
                )
            )
            return 0
        if a.golden_command == "preflight":
            report = svc.preflight(a.run_id, probe_provider=not a.no_provider_probe)
            _print(report)
            return 0 if report["ok"] else 1
        if a.golden_command == "execute":
            _print(svc.execute(a.run_id))
            return 0
        if a.golden_command == "detect-revision":
            _print(svc.detect_dataset_revisions(a.repo_id))
            return 0
        _print(svc.discover(a.run_id))
        return 0
    if a.command == "api":
        import uvicorn

        uvicorn.run("workbench.api.app:app", host="127.0.0.1", port=8000, reload=False)
        return 0
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())

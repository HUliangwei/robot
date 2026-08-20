from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from workbench.services.doctor import run_doctor
from workbench.services.golden_path import GoldenPathService
from workbench.services.legacy import scan_legacy_workspace
from workbench.services.overview import build_overview
from workbench.services.provider_doctor import list_providers, run_provider_doctor
from workbench.services.test_runner import run_pytest
from workbench.storage.catalog import Catalog
from workbench.storage.manifests import read_json
from workbench.storage.paths import ensure_runtime_dirs, find_project_root


def _root(value: str | None) -> Path:
    return Path(value).resolve() if value else find_project_root()


def _json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def _command_text() -> str:
    return "rlw " + " ".join(sys.argv[1:])


def _emit(
    title: str,
    comment: str,
    data: Any,
    *,
    json_mode: bool,
    inputs: dict[str, Any] | None = None,
    next_steps: list[str] | None = None,
) -> None:
    if json_mode:
        _json(data)
        return
    print(f"RLW - {title}")
    print("------------------------------------------------------------")
    print(f"# {comment}")
    print()
    print("COMMAND")
    print(f"  > {_command_text()}")
    if inputs:
        print()
        print("INPUT")
        for key, value in inputs.items():
            print(f"  {key:<18} {value}")
    print()
    print("OUTPUT")
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                print(f"  {key}")
                block = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
                for line in block.splitlines():
                    print("    " + line)
            else:
                print(f"  {key:<18} {value}")
    else:
        print(data)
    if next_steps:
        print()
        print("NEXT")
        for step in next_steps:
            print(f"  > {step}")


def _emit_doctor(data: dict[str, Any], *, json_mode: bool) -> None:
    if json_mode:
        _json(data)
        return
    print("RLW - System Doctor")
    print("------------------------------------------------------------")
    print("# Inspect the RLW control plane. Provider packages are checked separately.")
    print()
    print("COMMAND")
    print(f"  > {_command_text()}")
    print()
    print("CONTROL PLANE")
    for name, item in data["checks"].items():
        mark = "[OK]" if item["ok"] else ("[FAIL]" if item["required"] else "[INFO]")
        value = item.get("value")
        suffix = f"  {value}" if value not in (None, "") else ""
        print(f"  {mark:<6} {name:<16}{suffix}")
    print()
    print("RESULT")
    print(f"  required_health     {'READY' if data['healthy_required'] else 'FAILED'}")
    print()
    print("NEXT")
    print("  > rlw provider doctor lerobot-win")


def _emit_provider_doctor(data: dict[str, Any], *, json_mode: bool) -> None:
    if json_mode:
        _json(data)
        return
    print("RLW - Provider Doctor")
    print("------------------------------------------------------------")
    print("# Probe an isolated provider environment without installing provider packages into RLW.")
    print()
    print("COMMAND")
    print(f"  > {_command_text()}")
    print()
    print(f"PROVIDER  {data['provider']}")
    print(f"ENV       {data['environment']}")
    print()
    for name, item in data["checks"].items():
        mark = "[OK]" if item["ok"] else ("[FAIL]" if item["required"] else "[INFO]")
        value = item.get("value")
        suffix = f"  {value}" if value not in (None, "") else ""
        print(f"  {mark:<6} {name:<16}{suffix}")
    print()
    print("RESULT")
    print(f"  provider_status     {'READY' if data['ready'] else 'NOT READY'}")


def _add_output_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="emit stable JSON for automation")
    parser.add_argument("--verbose", action="store_true", help="show additional execution detail")


def _add_prepare_args(parser: argparse.ArgumentParser, *, workflow: bool) -> None:
    if workflow:
        parser.add_argument("workflow", nargs="?", default="pusht-act", choices=["pusht-act"])
    parser.add_argument("--recipe", default="recipes/train/pusht_act.yaml")
    parser.add_argument("--dataset-revision")
    parser.add_argument("--provider-env", default="lerobot-win")
    parser.add_argument("--python-executable")
    _add_output_flags(parser)


def _add_run_id(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("run_id")
    _add_output_flags(parser)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rlw",
        description="Robot Learning Workbench control plane",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Command model:
  rlw <resource> <action> [target] [options]

Core workflow:
  rlw system doctor
  rlw provider doctor lerobot-win
  rlw run prepare pusht-act
  rlw run preflight <RUN_ID>
  rlw run execute <RUN_ID>
  rlw run reconcile <RUN_ID>
  rlw dev test
""".strip(),
    )
    parser.add_argument("--root", help="project root; defaults to auto-detection")
    sub = parser.add_subparsers(dest="command", required=True)

    system = sub.add_parser("system", help="control-plane operations")
    system_sub = system.add_subparsers(dest="system_command", required=True)
    for name, help_text in (
        ("init", "initialize machine-local RLW runtime directories"),
        ("doctor", "inspect control-plane health"),
        ("overview", "show control-plane overview"),
        ("api", "start the local FastAPI service"),
    ):
        leaf = system_sub.add_parser(name, help=help_text)
        _add_output_flags(leaf)

    provider = sub.add_parser("provider", help="provider discovery and health")
    provider_sub = provider.add_subparsers(dest="provider_command", required=True)
    provider_list = provider_sub.add_parser("list", help="list registered provider adapters")
    _add_output_flags(provider_list)
    provider_doctor = provider_sub.add_parser("doctor", help="probe a provider environment")
    provider_doctor.add_argument("environment", nargs="?", default="lerobot-win")
    _add_output_flags(provider_doctor)

    catalog = sub.add_parser("catalog", help="rebuildable research catalog")
    catalog_sub = catalog.add_subparsers(dest="catalog_command", required=True)
    for name in ("rebuild", "verify"):
        leaf = catalog_sub.add_parser(name)
        _add_output_flags(leaf)

    legacy = sub.add_parser("legacy", help="read-only legacy workspace discovery")
    legacy_sub = legacy.add_subparsers(dest="legacy_command", required=True)
    legacy_scan = legacy_sub.add_parser("scan")
    legacy_scan.add_argument("--write", action="store_true")
    _add_output_flags(legacy_scan)

    run = sub.add_parser("run", help="canonical experiment lifecycle")
    run_sub = run.add_subparsers(dest="run_command", required=True)

    detect = run_sub.add_parser("detect-revision", help="detect immutable PushT revisions")
    detect.add_argument("--repo-id", default="lerobot/pusht")
    _add_output_flags(detect)

    prepare = run_sub.add_parser("prepare", help="prepare a canonical Run; does not execute it")
    _add_prepare_args(prepare, workflow=True)

    for name, help_text in (
        ("show", "show Run metadata"),
        ("status", "show Run status"),
        ("preflight", "validate Run execution preconditions"),
        ("execute", "execute the prepared train job"),
        ("reconcile", "discover and register produced artifacts/metrics"),
        ("discover", "compatibility synonym for reconcile"),
    ):
        leaf = run_sub.add_parser(name, help=help_text)
        _add_run_id(leaf)
    run_sub.choices["preflight"].add_argument("--no-provider-probe", action="store_true")

    dev = sub.add_parser("dev", help="development and verification commands")
    dev_sub = dev.add_subparsers(dest="dev_command", required=True)
    test = dev_sub.add_parser("test", help="run pytest and preserve a full transcript")
    test.add_argument("--quiet", action="store_true", help="use pytest -q")
    test.add_argument("--show-output", action="store_true", help="also pass -s to pytest")

    # Compatibility surface for pre-R6 scripts.
    golden = sub.add_parser("golden", help="legacy Golden Path compatibility commands")
    golden_sub = golden.add_subparsers(dest="golden_command", required=True)
    golden_prepare = golden_sub.add_parser("prepare")
    _add_prepare_args(golden_prepare, workflow=False)
    golden_detect = golden_sub.add_parser("detect-revision")
    golden_detect.add_argument("--repo-id", default="lerobot/pusht")
    _add_output_flags(golden_detect)
    for name in ("preflight", "execute", "discover"):
        leaf = golden_sub.add_parser(name)
        _add_run_id(leaf)
    golden_sub.choices["preflight"].add_argument("--no-provider-probe", action="store_true")

    return parser


def _run_status(root: Path, run_id: str) -> dict[str, Any]:
    path = root / "runs" / run_id / "manifest.json"
    if not path.exists():
        raise FileNotFoundError(f"run {run_id!r} does not exist")
    manifest = read_json(path)
    lineage = (manifest.get("lineage") or {}).get("dataset") or {}
    return {
        "schema_version": "rlw.run_status/v1",
        "run_id": run_id,
        "status": manifest.get("status"),
        "job": manifest.get("job"),
        "provider": (manifest.get("provider") or {}).get("name"),
        "provider_runtime": manifest.get("provider_runtime"),
        "dataset": {
            "dataset_id": lineage.get("dataset_id"),
            "revision": lineage.get("revision"),
        },
        "git_commit": manifest.get("git_commit"),
        "last_attempt": manifest.get("last_attempt"),
        "manifest": path.relative_to(root).as_posix(),
    }


def _resolve_revision(service: GoldenPathService, requested: str | None) -> str:
    if requested:
        return requested
    detection = service.detect_dataset_revisions("lerobot/pusht")
    selected = detection.get("selected")
    if selected:
        return str(selected)
    candidates = detection.get("candidates") or []
    raise ValueError(
        "dataset revision is ambiguous or unavailable; pass --dataset-revision explicitly. "
        f"Detected candidates: {candidates}"
    )


def _handle_golden_compat(args: argparse.Namespace, root: Path) -> int:
    service = GoldenPathService(root)
    command = args.golden_command
    json_mode = bool(getattr(args, "json", False))
    if command == "detect-revision":
        result = service.detect_dataset_revisions(args.repo_id)
        _emit("Dataset Revision Detection", "Detect immutable local dataset snapshots.", result, json_mode=json_mode)
        return 0
    if command == "prepare":
        revision = _resolve_revision(service, args.dataset_revision)
        provider_env = None if args.python_executable else args.provider_env
        result = service.prepare(
            args.recipe,
            dataset_revision=revision,
            provider_env=provider_env,
            python_executable=args.python_executable,
        )
        _emit("Golden Prepare (compat)", "Compatibility command; prefer `rlw run prepare pusht-act`.", result, json_mode=json_mode)
        return 0
    if command == "preflight":
        result = service.preflight(args.run_id, probe_provider=not args.no_provider_probe)
        _emit("Golden Preflight (compat)", "Compatibility command.", result, json_mode=json_mode)
        return 0 if result["ok"] else 1
    if command == "execute":
        result = service.execute(args.run_id)
        _emit("Golden Execute (compat)", "Compatibility command.", result, json_mode=json_mode)
        return 0
    result = service.discover(args.run_id)
    _emit("Golden Discover (compat)", "Compatibility command.", result, json_mode=json_mode)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = _root(args.root)
    runtime = ensure_runtime_dirs(root)
    catalog = Catalog(root / ".rlw" / "catalog.sqlite3")
    json_mode = bool(getattr(args, "json", False))

    if args.command == "system":
        if args.system_command == "init":
            result = {
                "schema_version": "rlw.system_init/v1",
                "status": "initialized",
                "root": str(root),
                "runtime": {key: str(value) for key, value in runtime.items()},
            }
            _emit("System Init", "Initialize machine-local RLW runtime directories.", result, json_mode=json_mode)
            return 0
        if args.system_command == "doctor":
            result = run_doctor(root)
            _emit_doctor(result, json_mode=json_mode)
            return 0 if result["healthy_required"] else 1
        if args.system_command == "overview":
            result = build_overview(root)
            _emit("System Overview", "Summarize the local control plane.", result, json_mode=json_mode)
            return 0
        import uvicorn
        uvicorn.run("workbench.api.app:app", host="127.0.0.1", port=8000, reload=False)
        return 0

    if args.command == "provider":
        if args.provider_command == "list":
            result = list_providers()
            _emit("Provider List", "List registered provider adapters.", result, json_mode=json_mode)
            return 0
        result = run_provider_doctor(args.environment)
        _emit_provider_doctor(result, json_mode=json_mode)
        return 0 if result["ready"] else 1

    if args.command == "catalog":
        result = (
            {"status": "rebuilt", "summary": catalog.rebuild(root)}
            if args.catalog_command == "rebuild"
            else catalog.verify_sources(root)
        )
        _emit("Catalog " + args.catalog_command.title(), "Operate the rebuildable research index.", result, json_mode=json_mode)
        return 0

    if args.command == "legacy":
        result = scan_legacy_workspace(root)
        _emit("Legacy Scan", "Read-only discovery of pre-RLW workspace assets.", result, json_mode=json_mode)
        return 0

    if args.command == "run":
        service = GoldenPathService(root)
        command = args.run_command
        if command == "detect-revision":
            result = service.detect_dataset_revisions(args.repo_id)
            _emit("Dataset Revision Detection", "Detect immutable local dataset snapshots.", result, json_mode=json_mode)
            return 0
        if command == "prepare":
            revision = _resolve_revision(service, args.dataset_revision)
            provider_env = None if args.python_executable else args.provider_env
            result = service.prepare(
                args.recipe,
                dataset_revision=revision,
                provider_env=provider_env,
                python_executable=args.python_executable,
            )
            _emit(
                "Run Prepare",
                "Create canonical metadata only; training is NOT started.",
                result,
                json_mode=json_mode,
                inputs={
                    "workflow": args.workflow,
                    "recipe": args.recipe,
                    "dataset_revision": revision,
                    "provider_env": provider_env or args.python_executable,
                },
                next_steps=[
                    f"rlw run show {result['run_id']}",
                    f"rlw run preflight {result['run_id']}",
                    f"rlw run execute {result['run_id']}",
                ],
            )
            return 0
        if command in {"show", "status"}:
            result = _run_status(root, args.run_id)
            _emit("Run Status", "Inspect canonical Run metadata without executing it.", result, json_mode=json_mode)
            return 0
        if command == "preflight":
            result = service.preflight(args.run_id, probe_provider=not args.no_provider_probe)
            _emit("Run Preflight", "Validate execution preconditions.", result, json_mode=json_mode)
            return 0 if result["ok"] else 1
        if command == "execute":
            result = service.execute(args.run_id)
            _emit(
                "Run Execute",
                "Execute the prepared Job through LocalExecutor.",
                result,
                json_mode=json_mode,
                next_steps=[f"rlw run reconcile {args.run_id}", f"rlw run show {args.run_id}"],
            )
            return 0
        result = service.discover(args.run_id)
        _emit(
            "Run Reconcile",
            "Discover and register Run-produced artifacts and metrics.",
            result,
            json_mode=json_mode,
            next_steps=[f"rlw run show {args.run_id}", "rlw catalog rebuild"],
        )
        return 0

    if args.command == "dev":
        result = run_pytest(root, quiet=args.quiet, show_output=args.show_output)
        return int(result["exit_code"])

    if args.command == "golden":
        return _handle_golden_compat(args, root)

    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())

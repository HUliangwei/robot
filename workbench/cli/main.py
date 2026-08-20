from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any

from workbench.services.doctor import run_doctor
from workbench.services.golden_path import GoldenPathService
from workbench.services.legacy import scan_legacy_workspace
from workbench.services.overview import build_overview
from workbench.storage.catalog import Catalog
from workbench.storage.paths import ensure_runtime_dirs, find_project_root

def _print(x:Any):
    print(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True))

def _root(v):
    return Path(v).resolve() if v else find_project_root()

def build_parser():
    p=argparse.ArgumentParser(
        prog="rlw",
        description="Robot Learning Workbench control plane"
    )
    p.add_argument("--root")
    sub=p.add_subparsers(dest="command",required=True)

    system=sub.add_parser("system",help="system operations")
    ss=system.add_subparsers(dest="system_command",required=True)
    ss.add_parser("init")
    ss.add_parser("doctor")
    ss.add_parser("overview")
    ss.add_parser("api")

    cat=sub.add_parser("catalog")
    cs=cat.add_subparsers(dest="catalog_command",required=True)
    cs.add_parser("rebuild")
    cs.add_parser("verify")

    legacy=sub.add_parser("legacy")
    ls=legacy.add_subparsers(dest="legacy_command",required=True)
    ls.add_parser("scan")

    run=sub.add_parser("run",help="experiment lifecycle")
    rs=run.add_subparsers(dest="run_command",required=True)

    rs.add_parser("detect-revision")

    prep=rs.add_parser("prepare")
    prep.add_argument("--recipe",default="recipes/train/pusht_act.yaml")
    prep.add_argument("--dataset-revision",required=True)
    prep.add_argument("--provider-env",default="lerobot-win")
    prep.add_argument("--python-executable")

    for n in ["preflight","execute","discover"]:
        q=rs.add_parser(n)
        q.add_argument("run_id")

    # backward compatibility
    golden=sub.add_parser("golden",help="compatibility alias")
    gs=golden.add_subparsers(dest="golden_command",required=True)
    for n in ["prepare","preflight","execute","discover","detect-revision"]:
        gs.add_parser(n)

    return p

def main(argv=None):
    a=build_parser().parse_args(argv)
    root=_root(a.root)
    ensure_runtime_dirs(root)
    catalog=Catalog(root/".rlw"/"catalog.sqlite3")

    if a.command=="system":
        if a.system_command=="doctor":
            _print(run_doctor(root)); return 0
        if a.system_command=="overview":
            _print(build_overview(root)); return 0
        if a.system_command=="init":
            _print({"status":"initialized","root":str(root)}); return 0
        if a.system_command=="api":
            import uvicorn
            uvicorn.run("workbench.api.app:app",host="127.0.0.1",port=8000)
            return 0

    if a.command=="catalog":
        _print(catalog.rebuild(root) if a.catalog_command=="rebuild"
               else catalog.verify_sources(root)); return 0

    if a.command=="legacy":
        _print(scan_legacy_workspace(root)); return 0

    if a.command=="run":
        svc=GoldenPathService(root)
        if a.run_command=="detect-revision":
            _print(svc.detect_dataset_revisions("lerobot/pusht")); return 0
        if a.run_command=="prepare":
            _print(svc.prepare(
                a.recipe,
                dataset_revision=a.dataset_revision,
                provider_env=a.provider_env,
                python_executable=a.python_executable)); return 0
        if a.run_command=="preflight":
            _print(svc.preflight(a.run_id)); return 0
        if a.run_command=="execute":
            _print(svc.execute(a.run_id)); return 0
        if a.run_command=="discover":
            _print(svc.discover(a.run_id)); return 0

    raise SystemExit("unsupported command")

if __name__=="__main__":
    raise SystemExit(main())

"""Canonical PushT + ACT golden-path orchestration for RLW V0.

This service owns research metadata and delegates provider semantics to the
LeRobot adapter and process execution to LocalExecutor. It never reimplements
LeRobot training logic.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from workbench.core.domain import CommandSpec
from workbench.core.ids import new_id
from workbench.executors.local import LocalExecutor
from workbench.providers.lerobot import LeRobotAdapter
from workbench.services.observability import LifecycleEventWriter
from workbench.storage.catalog import Catalog
from workbench.storage.manifests import atomic_write_json, atomic_write_yaml, read_json


_MUTABLE_REVISIONS = {"", "main", "master", "latest", "head"}
_ALLOWED_GENERATED_PREFIXES = (
    ".rlw/",
    ".rlw_migration_backup/",
    "runs/",
    "datasets/lerobot_pusht/",
    "gui/dist/",
    "gui/node_modules/",
)
_ALLOWED_GENERATED_FILES = {"gui/tsconfig.tsbuildinfo"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "_", value.lower()).strip("_") or "item"


def _run_text(argv: list[str], *, cwd: Path | None = None, timeout: int = 30) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "exit_code": None, "stdout": "", "stderr": str(exc)}
    return {
        "ok": completed.returncode == 0,
        "exit_code": completed.returncode,
        "stdout": completed.stdout or "",
        "stderr": completed.stderr or "",
    }


def _git_commit(root: Path) -> str | None:
    result = _run_text(["git", "-C", str(root), "rev-parse", "HEAD"], cwd=root)
    if not result["ok"]:
        return None
    value = str(result["stdout"]).strip()
    return value or None


def _normalize_status_path(line: str) -> str:
    path = line[3:] if len(line) >= 4 else line
    if " -> " in path:
        path = path.split(" -> ", 1)[1]
    return path.strip().strip('"').replace("\\", "/")


def _is_generated_record(path: str) -> bool:
    if path in _ALLOWED_GENERATED_FILES:
        return True
    return any(path.startswith(prefix) for prefix in _ALLOWED_GENERATED_PREFIXES)


def _source_tree_state(root: Path) -> dict[str, Any]:
    commit = _git_commit(root)
    status = _run_text(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "core.quotepath=false",
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ],
        cwd=root,
    )
    if commit is None or not status["ok"]:
        return {
            "clean": False,
            "commit": commit,
            "dirty_paths": [],
            "ignored_generated_paths": [],
            "error": str(status.get("stderr") or "git repository/commit unavailable").strip(),
        }
    dirty_paths: list[str] = []
    ignored: list[str] = []
    for line in str(status["stdout"]).splitlines():
        if not line.strip():
            continue
        path = _normalize_status_path(line)
        if _is_generated_record(path):
            ignored.append(path)
        else:
            dirty_paths.append(path)
    return {
        "clean": not dirty_paths,
        "commit": commit,
        "dirty_paths": dirty_paths,
        "ignored_generated_paths": ignored,
        "error": None,
    }


def _resolve_conda() -> str | None:
    from_env = os.environ.get("CONDA_EXE")
    if from_env and Path(from_env).exists():
        return str(Path(from_env))
    candidates = ("conda.exe", "conda.bat", "conda") if os.name == "nt" else ("conda",)
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def _check(name: str, ok: bool, detail: Any = None, *, required: bool = True) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "required": required, "detail": detail}


class GoldenPathService:
    def __init__(self, project_root: str | Path):
        self.root = Path(project_root).resolve()
        self.catalog = Catalog(self.root / ".rlw" / "catalog.sqlite3")

    def _recipe(self, recipe_path: str | Path) -> dict[str, Any]:
        path = Path(recipe_path)
        if not path.is_absolute():
            path = self.root / path
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        required = ("name", "kind", "provider", "policy_type", "dataset_repo_id")
        missing = [key for key in required if not data.get(key)]
        if missing:
            raise ValueError(f"recipe missing required fields: {', '.join(missing)}")
        if data["kind"] != "train":
            raise ValueError("golden path V0 accepts train recipes only")
        if data["provider"] != "lerobot":
            raise ValueError("golden path V0 accepts provider=lerobot only")
        return data

    def prepare(
        self,
        recipe_path: str | Path,
        *,
        dataset_revision: str,
        provider_env: str | None = None,
        python_executable: str | None = None,
    ) -> dict[str, Any]:
        revision = (dataset_revision or "").strip()
        if revision.lower() in _MUTABLE_REVISIONS:
            raise ValueError(
                "an immutable dataset revision is required; symbolic revisions "
                "such as main/master/latest are not accepted"
            )
        source_state = _source_tree_state(self.root)
        if not source_state["clean"]:
            dirty = ", ".join(source_state["dirty_paths"][:8]) or source_state.get("error") or "unknown"
            raise ValueError(
                "source worktree is dirty; commit/stash source changes before preparing a canonical run. "
                f"Dirty source paths: {dirty}"
            )
        recipe = self._recipe(recipe_path)
        adapter = LeRobotAdapter()

        recipe_source = Path(recipe_path)
        recipe_resolved = recipe_source.resolve() if recipe_source.is_absolute() else (self.root / recipe_source).resolve()
        try:
            recipe_ref = recipe_resolved.relative_to(self.root).as_posix()
        except ValueError as exc:
            raise ValueError("canonical Run recipes must be inside the project root") from exc

        experiment_id = new_id("experiment")
        trial_id = new_id("trial")
        run_id = new_id("run")
        job_id = new_id("job")
        dataset_id = _slug(recipe["dataset_repo_id"])

        run_rel = Path("runs") / run_id
        run_dir = self.root / run_rel
        output_rel = run_rel / "artifacts" / "training"
        output_dir = self.root / output_rel
        output_dir.mkdir(parents=True, exist_ok=True)

        requested_native = dict(recipe.get("native_overrides") or {})
        native = dict(requested_native)
        native["output_dir"] = output_rel.as_posix()
        resolved = {
            "schema_version": "rlw.resolved_config/v1",
            "run_id": run_id,
            "trial_id": trial_id,
            "experiment_id": experiment_id,
            "recipe": recipe_ref,
            "provider": "lerobot",
            "policy_type": recipe["policy_type"],
            "dataset_repo_id": recipe["dataset_repo_id"],
            "dataset_revision": revision,
            "provider_runtime": {
                "conda_env": provider_env,
                "python_executable": python_executable,
            },
            "git_commit": source_state["commit"],
            "native_overrides": native,
        }

        command = adapter.build_command(
            "train",
            resolved,
            provider_env=provider_env,
            python_executable=python_executable,
            cwd=str(self.root),
        )
        command_payload = {
            "schema_version": "rlw.command_spec/v1",
            "argv": list(command.normalized_argv()),
            "cwd": command.cwd,
            "env": dict(command.env),
        }

        dataset_rel = Path("datasets") / dataset_id / revision / "dataset.yaml"
        dataset_path = self.root / dataset_rel
        dataset_payload = {
            "schema_version": "rlw.dataset_manifest/v1",
            "dataset_id": dataset_id,
            "revision": revision,
            "source": {
                "provider": "huggingface",
                "repo_id": recipe["dataset_repo_id"],
                "revision": revision,
            },
            "immutable": True,
            "created_at": _utc_now(),
        }
        dataset_path.parent.mkdir(parents=True, exist_ok=True)
        if dataset_path.exists():
            existing = yaml.safe_load(dataset_path.read_text(encoding="utf-8")) or {}
            if existing.get("dataset_id") != dataset_id or existing.get("revision") != revision:
                raise ValueError(f"dataset manifest conflict at {dataset_path}")
        else:
            atomic_write_yaml(dataset_path, dataset_payload)

        run_spec = {
            "schema_version": "rlw.run_spec/v1",
            "experiment": {
                "name": recipe["name"],
                "question": recipe.get("question", "PushT ACT baseline"),
            },
            "dataset": {
                "repo_id": recipe["dataset_repo_id"],
                "revision": revision,
            },
            "policy": {
                "provider": "lerobot",
                "architecture": recipe["policy_type"],
            },
            "training": {
                "recipe": recipe_ref,
                "native_overrides": requested_native,
            },
        }
        lineage = {
            "schema_version": "rlw.lineage/v1",
            "run_id": run_id,
            "dataset": {
                "dataset_id": dataset_id,
                "revision": revision,
                "manifest": dataset_rel.as_posix(),
            },
            "parents": [],
        }
        job_record_rel = run_rel / "jobs" / "train" / "job.json"
        job_record = {
            "schema_version": "rlw.job/v1",
            "job_id": job_id,
            "run_id": run_id,
            "kind": "train",
            "state": "READY",
            "created_at": _utc_now(),
            "command": (run_rel / "resolved_command.json").as_posix(),
        }

        run_manifest = {
            "schema_version": "rlw.run_manifest/v1",
            "run_id": run_id,
            "status": "READY",
            "created_at": _utc_now(),
            "git_commit": source_state["commit"],
            "git_state": {
                "schema_version": "rlw.git_state/v1",
                "commit": source_state["commit"],
                "source_tree_clean_at_prepare": True,
            },
            "experiment": {
                "schema_version": "rlw.experiment/v1",
                "experiment_id": experiment_id,
                "name": recipe["name"],
                "question": recipe.get("question", "PushT ACT baseline"),
            },
            "trial": {
                "schema_version": "rlw.trial/v1",
                "trial_id": trial_id,
                "experiment_id": experiment_id,
                "resolved_variables": {
                    "policy_type": recipe["policy_type"],
                    "dataset_revision": revision,
                },
            },
            "job": job_record,
            "provider": adapter.spec().__dict__,
            "provider_runtime": {
                "conda_env": provider_env,
                "python_executable": python_executable,
            },
            "resolved_config": resolved,
            "lineage": lineage,
            "paths": {
                "run_dir": run_rel.as_posix(),
                "run_spec": (run_rel / "run.yaml").as_posix(),
                "resolved_config": (run_rel / "resolved_config.yaml").as_posix(),
                "lineage": (run_rel / "lineage.json").as_posix(),
                "job_record": job_record_rel.as_posix(),
                "training_output": output_rel.as_posix(),
                "command": (run_rel / "resolved_command.json").as_posix(),
            },
        }
        run_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_yaml(run_dir / "run.yaml", run_spec)
        atomic_write_yaml(run_dir / "resolved_config.yaml", resolved)
        atomic_write_json(run_dir / "lineage.json", lineage)
        atomic_write_json(self.root / job_record_rel, job_record)
        atomic_write_json(run_dir / "resolved_command.json", command_payload)
        atomic_write_json(run_dir / "manifest.json", run_manifest)
        atomic_write_json(
            self.root / ".rlw" / "state" / "jobs" / job_id / "job.json",
            job_record,
        )
        events = LifecycleEventWriter(self.root, run_id)
        events.emit(
            "RunCreated",
            occurred_at=run_manifest["created_at"],
            category="lifecycle",
            payload={
                "status": "READY",
                "experiment_id": experiment_id,
                "trial_id": trial_id,
            },
            dedupe_key=f"RunCreated:{run_id}",
        )
        events.emit(
            "JobCreated",
            job_id=job_id,
            occurred_at=job_record["created_at"],
            category="lifecycle",
            payload={"kind": "train", "state": "READY"},
            dedupe_key=f"JobCreated:{job_id}",
        )
        self.catalog.rebuild(self.root)
        return {
            "schema_version": "rlw.golden_prepare/v1",
            "status": "READY",
            "run_id": run_id,
            "job_id": job_id,
            "run_dir": str(run_dir),
            "run_manifest": str(run_dir / "manifest.json"),
            "run_spec": str(run_dir / "run.yaml"),
            "resolved_config": str(run_dir / "resolved_config.yaml"),
            "lineage": str(run_dir / "lineage.json"),
            "job_record": str(self.root / job_record_rel),
            "dataset_manifest": str(dataset_path),
            "command_manifest": str(run_dir / "resolved_command.json"),
        }

    def detect_dataset_revisions(self, repo_id: str = "lerobot/pusht") -> dict[str, Any]:
        cache_name = "datasets--" + repo_id.replace("/", "--")
        snapshots = self.root / "datasets" / "hub" / cache_name / "snapshots"
        candidates: list[str] = []
        if snapshots.exists():
            candidates = sorted(
                p.name
                for p in snapshots.iterdir()
                if p.is_dir() and re.fullmatch(r"[0-9a-fA-F]{7,64}", p.name)
            )
        return {
            "schema_version": "rlw.dataset_revision_detection/v1",
            "repo_id": repo_id,
            "cache_root": snapshots.relative_to(self.root).as_posix()
            if snapshots.is_relative_to(self.root)
            else str(snapshots),
            "candidates": candidates,
            "selected": candidates[0] if len(candidates) == 1 else None,
        }

    def _provider_probe(self, manifest: dict[str, Any]) -> dict[str, Any]:
        runtime = manifest.get("provider_runtime") or {}
        py = runtime.get("python_executable")
        conda_env = runtime.get("conda_env")
        if py:
            executable = Path(str(py))
            if not executable.exists():
                return {"resolved": False, "detail": f"python executable not found: {executable}"}
            argv = [str(executable)]
            runtime_detail = str(executable)
        elif conda_env:
            conda = _resolve_conda()
            if not conda:
                return {"resolved": False, "detail": "conda executable not found"}
            argv = [conda, "run", "-n", str(conda_env), "python"]
            runtime_detail = f"conda env {conda_env} via {conda}"
        else:
            argv = [sys.executable]
            runtime_detail = sys.executable

        probe_code = (
            "import json, lerobot, torch; "
            "print(json.dumps({'lerobot_version': getattr(lerobot, '__version__', None), "
            "'torch_version': getattr(torch, '__version__', None), "
            "'cuda_available': bool(torch.cuda.is_available())}))"
        )
        result = _run_text([*argv, "-c", probe_code], cwd=self.root, timeout=60)
        payload: dict[str, Any] = {}
        if result["ok"]:
            for line in reversed(str(result["stdout"]).splitlines()):
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    payload = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue
        return {
            "resolved": True,
            "runtime": runtime_detail,
            "probe_ok": bool(result["ok"]),
            "payload": payload,
            "stderr": str(result.get("stderr") or "")[-1200:],
        }

    def preflight(self, run_id: str, *, probe_provider: bool = True) -> dict[str, Any]:
        run_dir = self.root / "runs" / run_id
        manifest_path = run_dir / "manifest.json"
        command_path = run_dir / "resolved_command.json"
        if not manifest_path.exists() or not command_path.exists():
            raise FileNotFoundError(f"run {run_id!r} is not prepared")
        manifest = read_json(manifest_path)
        command = read_json(command_path)
        checks: list[dict[str, Any]] = []

        source_state = _source_tree_state(self.root)
        expected_commit = manifest.get("git_commit") or (manifest.get("git_state") or {}).get("commit")
        checks.append(
            _check(
                "git_commit_match",
                bool(expected_commit and source_state.get("commit") == expected_commit),
                {"prepared": expected_commit, "current": source_state.get("commit")},
            )
        )
        checks.append(
            _check(
                "prepared_from_clean_source",
                (manifest.get("git_state") or {}).get("source_tree_clean_at_prepare") is True,
                "run manifest must record a clean source tree at prepare time",
            )
        )
        checks.append(
            _check(
                "source_tree_clean",
                bool(source_state.get("clean")),
                {"dirty_paths": source_state.get("dirty_paths", [])},
            )
        )

        dataset_lineage = (manifest.get("lineage") or {}).get("dataset") or {}
        dataset_manifest_rel = dataset_lineage.get("manifest")
        dataset_manifest_ok = False
        dataset_detail: dict[str, Any] = {"manifest": dataset_manifest_rel}
        if dataset_manifest_rel:
            dataset_path = self.root / str(dataset_manifest_rel)
            if dataset_path.exists():
                data = yaml.safe_load(dataset_path.read_text(encoding="utf-8")) or {}
                dataset_manifest_ok = (
                    data.get("revision") == dataset_lineage.get("revision")
                    and data.get("immutable") is True
                )
                dataset_detail.update({"revision": data.get("revision"), "immutable": data.get("immutable")})
        checks.append(_check("dataset_manifest_valid", dataset_manifest_ok, dataset_detail))

        repo_id = (manifest.get("resolved_config") or {}).get("dataset_repo_id", "lerobot/pusht")
        revision = dataset_lineage.get("revision")
        snapshot = self.root / "datasets" / "hub" / ("datasets--" + str(repo_id).replace("/", "--")) / "snapshots" / str(revision)
        checks.append(
            _check(
                "dataset_revision_available",
                snapshot.is_dir(),
                snapshot.relative_to(self.root).as_posix() if snapshot.is_relative_to(self.root) else str(snapshot),
                required=False,
            )
        )

        argv = command.get("argv")
        checks.append(
            _check(
                "command_spec_valid",
                isinstance(argv, list) and bool(argv) and bool(command.get("cwd")),
                {"argv0": argv[0] if isinstance(argv, list) and argv else None, "cwd": command.get("cwd")},
            )
        )

        output_rel = (manifest.get("paths") or {}).get("training_output")
        writable = False
        output_detail = output_rel
        if output_rel:
            output_dir = self.root / str(output_rel)
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(prefix=".rlw_preflight_", dir=output_dir, delete=True):
                    pass
                writable = True
            except OSError as exc:
                output_detail = str(exc)
        checks.append(_check("output_directory_writable", writable, output_detail))

        if probe_provider:
            probe = self._provider_probe(manifest)
            checks.append(_check("provider_runtime_resolved", bool(probe.get("resolved")), probe.get("runtime") or probe.get("detail")))
            checks.append(_check("lerobot_import", bool(probe.get("probe_ok")), probe.get("stderr") or probe.get("payload")))
            checks.append(_check("torch_import", bool(probe.get("probe_ok")), (probe.get("payload") or {}).get("torch_version")))
            checks.append(
                _check(
                    "cuda_available",
                    bool((probe.get("payload") or {}).get("cuda_available")),
                    (probe.get("payload") or {}).get("cuda_available"),
                    required=False,
                )
            )
        else:
            checks.append(_check("provider_probe", True, "skipped by caller", required=False))

        ok = all(item["ok"] for item in checks if item["required"])
        return {
            "schema_version": "rlw.golden_preflight/v1",
            "run_id": run_id,
            "ok": ok,
            "checks": checks,
        }

    def execute(self, run_id: str) -> dict[str, Any]:
        run_dir = self.root / "runs" / run_id
        manifest_path = run_dir / "manifest.json"
        command_path = run_dir / "resolved_command.json"
        if not manifest_path.exists() or not command_path.exists():
            raise FileNotFoundError(f"run {run_id!r} is not prepared")

        manifest = read_json(manifest_path)
        if manifest.get("status") not in {"READY", "FAILED"}:
            raise ValueError(f"run {run_id} cannot execute from state {manifest.get('status')!r}")
        preflight = self.preflight(run_id, probe_provider=True)
        if not preflight["ok"]:
            failed = [item["name"] for item in preflight["checks"] if item["required"] and not item["ok"]]
            raise ValueError(f"preflight failed for {run_id}: {', '.join(failed)}")

        command_data = read_json(command_path)
        command = CommandSpec(
            tuple(command_data["argv"]),
            cwd=command_data.get("cwd"),
            env=command_data.get("env") or {},
        )
        job_id = manifest["job"]["job_id"]
        job_record_rel = (manifest.get("paths") or {}).get("job_record")
        if job_record_rel:
            job_record_path = self.root / str(job_record_rel)
        else:
            job_record_path = run_dir / "jobs" / str(manifest["job"].get("kind") or "train") / "job.json"
            manifest.setdefault("paths", {})["job_record"] = job_record_path.relative_to(self.root).as_posix()
        job_record = read_json(job_record_path) if job_record_path.exists() else dict(manifest["job"])
        previous_state = str(job_record.get("state") or "READY")
        attempt_id = new_id("attempt")
        events = LifecycleEventWriter(self.root, run_id)
        started_at = _utc_now()
        job_record["state"] = "RUNNING"
        job_record["started_at"] = started_at
        manifest["status"] = "RUNNING"
        manifest["job"] = job_record
        manifest["started_at"] = started_at
        manifest["preflight"] = preflight
        atomic_write_json(job_record_path, job_record)
        atomic_write_json(manifest_path, manifest)
        events.emit(
            "JobStateChanged",
            job_id=job_id,
            attempt_id=attempt_id,
            occurred_at=started_at,
            category="lifecycle",
            payload={"from": previous_state, "to": "RUNNING"},
            dedupe_key=f"JobStateChanged:{job_id}:{attempt_id}:RUNNING",
        )
        events.emit(
            "AttemptStarted",
            job_id=job_id,
            attempt_id=attempt_id,
            occurred_at=started_at,
            category="execution",
            payload={"state": "RUNNING"},
            dedupe_key=f"AttemptStarted:{attempt_id}",
        )

        result = LocalExecutor(self.root).run(job_id, command, attempt_id=attempt_id)
        manifest = read_json(manifest_path)
        ended_at = _utc_now()
        stdout_rel = Path(result.stdout_path).relative_to(self.root).as_posix()
        stderr_rel = Path(result.stderr_path).relative_to(self.root).as_posix()
        runtime_attempt_rel = Path(result.attempt_path).relative_to(self.root).as_posix()
        attempt_record = read_json(result.attempt_path)
        attempt_record.update(
            {
                "stdout_path": stdout_rel,
                "stderr_path": stderr_rel,
                "runtime_record_path": runtime_attempt_rel,
            }
        )
        failure = None
        if result.state == "FAILED":
            failure = {
                "category": "ExecutionError",
                "reason": f"Command exited with code {result.exit_code}.",
                "retriable": False,
                "recommended_action": (
                    "Inspect stdout and stderr, correct the command or provider input, then retry."
                ),
            }
            attempt_record["error"] = failure
        attempt_record_path = job_record_path.parent / "attempts" / f"{result.attempt_id}.json"
        atomic_write_json(attempt_record_path, attempt_record)

        job_record = read_json(job_record_path)
        attempt_ids = list(job_record.get("attempt_ids") or [])
        if result.attempt_id not in attempt_ids:
            attempt_ids.append(result.attempt_id)
        job_record.update(
            {
                "state": result.state,
                "ended_at": ended_at,
                "last_attempt_id": result.attempt_id,
                "attempt_ids": attempt_ids,
            }
        )
        atomic_write_json(job_record_path, job_record)

        manifest["status"] = result.state
        manifest["job"] = job_record
        manifest["ended_at"] = ended_at
        manifest["last_attempt"] = {
            "attempt_id": result.attempt_id,
            "state": result.state,
            "exit_code": result.exit_code,
            "stdout_path": stdout_rel,
            "stderr_path": stderr_rel,
            "attempt_path": attempt_record_path.relative_to(self.root).as_posix(),
            "runtime_attempt_path": runtime_attempt_rel,
        }
        atomic_write_json(manifest_path, manifest)
        if failure is not None:
            events.emit(
                "AttemptFailed",
                job_id=job_id,
                attempt_id=result.attempt_id,
                occurred_at=ended_at,
                category="execution",
                payload={"exit_code": result.exit_code, "error": failure},
                dedupe_key=f"AttemptFailed:{result.attempt_id}",
            )
        events.emit(
            "JobStateChanged",
            job_id=job_id,
            attempt_id=result.attempt_id,
            occurred_at=ended_at,
            category="lifecycle",
            payload={"from": "RUNNING", "to": result.state},
            dedupe_key=f"JobStateChanged:{job_id}:{result.attempt_id}:{result.state}",
        )
        if result.state == "SUCCEEDED":
            events.emit(
                "JobCompleted",
                job_id=job_id,
                attempt_id=result.attempt_id,
                occurred_at=ended_at,
                category="lifecycle",
                payload={"state": result.state, "exit_code": result.exit_code},
                dedupe_key=f"JobCompleted:{job_id}:{result.attempt_id}",
            )
            events.emit(
                "RunCompleted",
                job_id=job_id,
                attempt_id=result.attempt_id,
                occurred_at=ended_at,
                category="lifecycle",
                payload={"state": result.state},
                dedupe_key=f"RunCompleted:{run_id}:{result.attempt_id}",
            )
        discovered = self.discover(run_id)
        self.catalog.rebuild(self.root)
        return {
            "schema_version": "rlw.golden_execute/v1",
            "run_id": run_id,
            "state": result.state,
            "exit_code": result.exit_code,
            "attempt_id": result.attempt_id,
            "discovered": discovered,
        }

    def discover(self, run_id: str) -> dict[str, Any]:
        run_dir = self.root / "runs" / run_id
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"run {run_id!r} does not exist")
        manifest = read_json(manifest_path)
        output_rel = Path(manifest["paths"]["training_output"])
        output_dir = self.root / output_rel
        record_root = run_dir / "records"
        events = LifecycleEventWriter(self.root, run_id)
        artifacts = 0
        metrics = 0

        if output_dir.exists():
            for ckpt in sorted(output_dir.rglob("pretrained_model")):
                if not ckpt.is_dir():
                    continue
                rel = ckpt.relative_to(self.root).as_posix()
                artifact_id = "artifact_" + hashlib.sha256(f"{run_id}|{rel}".encode()).hexdigest()[:16]
                payload = {
                    "schema_version": "rlw.artifact/v1",
                    "artifact_id": artifact_id,
                    "kind": "checkpoint",
                    "display_name": ckpt.parent.name,
                    "producer_run": run_id,
                    "replicas": [
                        {
                            "schema_version": "rlw.artifact_replica/v1",
                            "node_id": "local",
                            "uri": rel,
                            "state": "AVAILABLE",
                            "persistent": True,
                            "cache": False,
                            "pinned": False,
                        }
                    ],
                }
                atomic_write_json(record_root / "artifacts" / artifact_id / "artifact.json", payload)
                events.emit(
                    "ArtifactDiscovered",
                    category="artifact",
                    payload={"artifact_id": artifact_id, "kind": "checkpoint"},
                    dedupe_key=f"ArtifactDiscovered:{artifact_id}",
                )
                artifacts += 1

            for kind, directory_name in (
                ("rollout", "rollouts"),
                ("evaluation", "evaluation"),
            ):
                for produced_dir in sorted(output_dir.rglob(directory_name)):
                    if not produced_dir.is_dir():
                        continue
                    rel = produced_dir.relative_to(self.root).as_posix()
                    artifact_id = "artifact_" + hashlib.sha256(
                        f"{run_id}|{kind}|{rel}".encode()
                    ).hexdigest()[:16]
                    payload = {
                        "schema_version": "rlw.artifact/v1",
                        "artifact_id": artifact_id,
                        "kind": kind,
                        "display_name": produced_dir.name,
                        "producer_run": run_id,
                        "replicas": [
                            {
                                "schema_version": "rlw.artifact_replica/v1",
                                "node_id": "local",
                                "uri": rel,
                                "state": "AVAILABLE",
                                "persistent": True,
                                "cache": False,
                                "pinned": False,
                            }
                        ],
                    }
                    atomic_write_json(
                        record_root / "artifacts" / artifact_id / "artifact.json",
                        payload,
                    )
                    events.emit(
                        "ArtifactDiscovered",
                        category="artifact",
                        payload={"artifact_id": artifact_id, "kind": kind},
                        dedupe_key=f"ArtifactDiscovered:{artifact_id}",
                    )
                    artifacts += 1

            for metrics_path in sorted(output_dir.rglob("metrics.json")):
                try:
                    data = json.loads(metrics_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                for name, raw_value in sorted(data.items()):
                    metadata = raw_value if isinstance(raw_value, dict) else {}
                    value = metadata.get("value") if metadata else raw_value
                    if isinstance(value, bool) or not isinstance(value, (int, float)):
                        continue
                    source_rel = metrics_path.relative_to(self.root).as_posix()
                    metric_id = "metric_" + hashlib.sha256(f"{run_id}|{source_rel}|{name}".encode()).hexdigest()[:16]
                    metric_payload = {
                        "schema_version": "rlw.metric_record/v1",
                        "metric_id": metric_id,
                        "run_id": run_id,
                        "name": str(name),
                        "value": float(value),
                        "namespace": "lerobot",
                        "scope": metadata.get("scope")
                        or metrics_path.parent.relative_to(output_dir).as_posix(),
                        "source": source_rel,
                    }
                    for key in (
                        "unit",
                        "direction",
                        "aggregation",
                        "episodes",
                        "provider",
                        "definition_version",
                    ):
                        if metadata.get(key) is not None:
                            metric_payload[key] = metadata[key]
                    atomic_write_json(record_root / "metrics" / metric_id / "metric.json", metric_payload)
                    events.emit(
                        "MetricEmitted",
                        category="metric",
                        payload={
                            "metric_id": metric_id,
                            "name": str(name),
                            "value": float(value),
                        },
                        dedupe_key=f"MetricEmitted:{metric_id}",
                    )
                    metrics += 1

        self.catalog.rebuild(self.root)
        return {
            "schema_version": "rlw.discovery/v1",
            "run_id": run_id,
            "artifacts": artifacts,
            "metrics": metrics,
        }

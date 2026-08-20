"""Shared local observability contracts for CLI, API, and GUI."""
from __future__ import annotations

import json
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from workbench.core.ids import new_id
from workbench.storage.manifests import read_json


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_directory(root: Path, run_id: str) -> Path:
    runs_root = (root / "runs").resolve()
    candidate = (runs_root / run_id).resolve()
    if not run_id or Path(run_id).name != run_id or not candidate.is_relative_to(runs_root):
        raise ValueError(f"invalid Run ID: {run_id!r}")
    return candidate


def read_lifecycle_events(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.is_file():
        return []
    events: list[dict[str, Any]] = []
    with source.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                events.append(payload)
    return events


class LifecycleEventWriter:
    def __init__(self, root: str | Path, run_id: str):
        self.root = Path(root).resolve()
        self.run_id = run_id
        self.path = _run_directory(self.root, run_id) / "events.jsonl"

    def emit(
        self,
        event_type: str,
        *,
        job_id: str | None = None,
        attempt_id: str | None = None,
        occurred_at: str | None = None,
        category: str | None = None,
        payload: dict[str, Any] | None = None,
        dedupe_key: str | None = None,
    ) -> dict[str, Any]:
        if dedupe_key:
            for event in read_lifecycle_events(self.path):
                if event.get("dedupe_key") == dedupe_key:
                    return event
        event: dict[str, Any] = {
            "schema_version": "rlw.lifecycle_event/v1",
            "event_id": new_id("event"),
            "event_type": event_type,
            "occurred_at": occurred_at or _utc_now(),
            "run_id": self.run_id,
            "payload": payload or {},
        }
        for key, value in (
            ("job_id", job_id),
            ("attempt_id", attempt_id),
            ("category", category),
            ("dedupe_key", dedupe_key),
        ):
            if value is not None:
                event[key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = (json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        with self.path.open("ab") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        return event


def _json_records(root: Path, pattern: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(root.glob(pattern)):
        try:
            payload = read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


class RunObservabilityService:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def _log_summary(self, raw_path: Any, tail_lines: int) -> dict[str, Any]:
        text_path = str(raw_path or "")
        empty = {
            "path": text_path,
            "exists": False,
            "size_bytes": 0,
            "tail": [],
            "truncated": False,
        }
        if not text_path:
            return {**empty, "error": "log path is not recorded"}
        candidate = Path(text_path)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self.root):
            return {**empty, "error": "log path is outside project root"}
        normalized = resolved.relative_to(self.root).as_posix()
        empty["path"] = normalized
        if not resolved.is_file():
            return {**empty, "error": "log file does not exist"}
        selected: deque[str] = deque(maxlen=tail_lines)
        line_count = 0
        with resolved.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line_count += 1
                selected.append(line.rstrip("\r\n"))
        return {
            "path": normalized,
            "exists": True,
            "size_bytes": resolved.stat().st_size,
            "tail": list(selected),
            "truncated": line_count > tail_lines,
        }

    def _document(
        self,
        run_dir: Path,
        kind: str,
        raw_path: Any,
        document_format: str,
        *,
        embedded: Any = None,
    ) -> dict[str, Any]:
        manifest_path = (run_dir / "manifest.json").relative_to(self.root).as_posix()
        base = {
            "schema_version": "rlw.record_document/v1",
            "kind": kind,
            "path": str(raw_path or manifest_path),
            "format": document_format,
        }
        if raw_path:
            candidate = Path(str(raw_path))
            if not candidate.is_absolute():
                candidate = self.root / candidate
            resolved = candidate.resolve()
            if not resolved.is_relative_to(run_dir):
                return {
                    **base,
                    "source": "unavailable",
                    "available": False,
                    "content": None,
                    "error": "document path is outside the Run directory",
                }
            base["path"] = resolved.relative_to(self.root).as_posix()
            if resolved.is_file():
                try:
                    if document_format == "json":
                        content = read_json(resolved)
                    else:
                        content = yaml.safe_load(resolved.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
                    return {
                        **base,
                        "source": "unavailable",
                        "available": False,
                        "content": None,
                        "error": f"document could not be read: {exc}",
                    }
                return {
                    **base,
                    "source": "file",
                    "available": True,
                    "content": content,
                }
        if embedded is not None:
            return {
                **base,
                "path": manifest_path,
                "source": "manifest_embedded",
                "available": True,
                "content": embedded,
            }
        return {
            **base,
            "source": "unavailable",
            "available": False,
            "content": None,
            "error": "document is not recorded",
        }

    def _documents(
        self, run_dir: Path, manifest: dict[str, Any]
    ) -> dict[str, dict[str, Any]]:
        manifest_rel = (run_dir / "manifest.json").relative_to(self.root).as_posix()
        paths = manifest.get("paths") if isinstance(manifest.get("paths"), dict) else {}
        return {
            "manifest": {
                "schema_version": "rlw.record_document/v1",
                "kind": "manifest",
                "path": manifest_rel,
                "format": "json",
                "source": "file",
                "available": True,
                "content": manifest,
            },
            "run_spec": self._document(run_dir, "run_spec", paths.get("run_spec"), "yaml"),
            "resolved_config": self._document(
                run_dir,
                "resolved_config",
                paths.get("resolved_config"),
                "yaml",
                embedded=manifest.get("resolved_config"),
            ),
            "lineage": self._document(
                run_dir,
                "lineage",
                paths.get("lineage"),
                "json",
                embedded=manifest.get("lineage"),
            ),
        }

    @staticmethod
    def _failure(attempt: dict[str, Any]) -> dict[str, Any] | None:
        configured = attempt.get("error")
        if isinstance(configured, dict):
            return {
                "category": str(configured.get("category") or "ExecutionError"),
                "reason": str(configured.get("reason") or "Execution failed."),
                "retriable": bool(configured.get("retriable", False)),
                "recommended_action": str(
                    configured.get("recommended_action")
                    or "Inspect stdout and stderr, correct the command or provider input, then retry."
                ),
            }
        if attempt.get("state") != "FAILED":
            return None
        exit_code = attempt.get("exit_code")
        reason = (
            f"Command exited with code {exit_code}."
            if exit_code is not None
            else "Command execution failed before an exit code was recorded."
        )
        return {
            "category": "ExecutionError",
            "reason": reason,
            "retriable": False,
            "recommended_action": (
                "Inspect stdout and stderr, correct the command or provider input, then retry."
            ),
        }

    def inspect(self, run_id: str, log_tail_lines: int = 80) -> dict[str, Any]:
        if log_tail_lines < 1 or log_tail_lines > 1000:
            raise ValueError("log_tail_lines must be between 1 and 1000")
        run_dir = _run_directory(self.root, run_id)
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(f"run {run_id!r} does not exist")
        manifest = read_json(manifest_path)
        jobs: list[dict[str, Any]] = []
        failure_count = 0
        attempt_count = 0
        for job_path in sorted(run_dir.glob("jobs/*/job.json")):
            job = read_json(job_path)
            attempts: list[dict[str, Any]] = []
            for attempt_path in sorted((job_path.parent / "attempts").glob("*.json")):
                attempt = read_json(attempt_path)
                failure = self._failure(attempt)
                if failure is not None:
                    failure_count += 1
                attempt_count += 1
                attempts.append(
                    {
                        "attempt": attempt,
                        "logs": {
                            "stdout": self._log_summary(
                                attempt.get("stdout_path"), log_tail_lines
                            ),
                            "stderr": self._log_summary(
                                attempt.get("stderr_path"), log_tail_lines
                            ),
                        },
                        "failure": failure,
                    }
                )
            jobs.append({"job": job, "attempts": attempts})
        if not jobs and isinstance(manifest.get("job"), dict):
            jobs.append({"job": manifest["job"], "attempts": []})
        events = read_lifecycle_events(run_dir / "events.jsonl")
        artifacts = _json_records(run_dir, "records/artifacts/*/artifact.json")
        metrics = _json_records(run_dir, "records/metrics/*/metric.json")
        return {
            "schema_version": "rlw.run_observability/v1",
            "run": manifest,
            "documents": self._documents(run_dir, manifest),
            "jobs": jobs,
            "events": events,
            "artifacts": artifacts,
            "metrics": metrics,
            "summary": {
                "jobs": len(jobs),
                "attempts": attempt_count,
                "artifacts": len(artifacts),
                "metrics": len(metrics),
                "events": len(events),
                "failures": failure_count,
                "latest_event_type": events[-1].get("event_type") if events else None,
            },
        }

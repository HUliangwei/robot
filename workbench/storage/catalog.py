"""Rebuildable SQLite index over filesystem research records."""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from typing import Any
import yaml

class Catalog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS records (
                    kind TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY(kind, record_id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_records_kind ON records(kind)")

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM records")

    def upsert(self, kind: str, record_id: str, source_path: str, payload: dict[str, Any]) -> None:
        schema_version = str(payload.get("schema_version") or f"rlw.{kind}/v1")
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO records(kind, record_id, schema_version, source_path, payload_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(kind, record_id) DO UPDATE SET
                  schema_version=excluded.schema_version,
                  source_path=excluded.source_path,
                  payload_json=excluded.payload_json
            """, (kind, record_id, schema_version, source_path,
                  json.dumps(payload, ensure_ascii=False, sort_keys=True)))

    def count(self, kind: str | None = None) -> int:
        with self._connect() as conn:
            if kind is None:
                return int(conn.execute("SELECT COUNT(*) FROM records").fetchone()[0])
            return int(conn.execute("SELECT COUNT(*) FROM records WHERE kind=?", (kind,)).fetchone()[0])

    def list_records(self, kind: str, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json, source_path FROM records WHERE kind=? ORDER BY record_id DESC LIMIT ?",
                (kind, limit),
            ).fetchall()
        result = []
        for row in rows:
            item = json.loads(row["payload_json"])
            item.setdefault("_source_path", row["source_path"])
            result.append(item)
        return result

    def _index_json_records(self, root: Path, pattern: str, kind: str, id_key: str) -> int:
        count = 0
        for path in sorted(root.rglob(pattern)):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            record_id = payload.get(id_key)
            if not record_id:
                continue
            self.upsert(kind, str(record_id), path.as_posix(), payload)
            count += 1
        return count

    def rebuild(self, root: str | Path) -> dict[str, int]:
        project_root = Path(root).resolve()
        self.clear()
        summary = {"run": 0, "dataset": 0, "artifact": 0, "metric": 0}

        runs_root = project_root / "runs"
        if runs_root.exists():
            for path in sorted(runs_root.rglob("manifest.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                run_id = data.get("run_id")
                if run_id:
                    self.upsert("run", str(run_id), path.relative_to(project_root).as_posix(), data)
                    summary["run"] += 1
            for path in sorted(runs_root.rglob("artifact.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                artifact_id = data.get("artifact_id")
                if artifact_id:
                    self.upsert("artifact", str(artifact_id), path.relative_to(project_root).as_posix(), data)
                    summary["artifact"] += 1
            for path in sorted(runs_root.rglob("metric.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                metric_id = data.get("metric_id")
                if metric_id:
                    self.upsert("metric", str(metric_id), path.relative_to(project_root).as_posix(), data)
                    summary["metric"] += 1

        datasets_root = project_root / "datasets"
        if datasets_root.exists():
            for path in sorted(datasets_root.rglob("dataset.yaml")):
                try:
                    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                except (OSError, yaml.YAMLError):
                    continue
                dataset_id = data.get("dataset_id")
                revision = data.get("revision")
                if not dataset_id or not revision:
                    continue
                record_id = f"{dataset_id}@{revision}"
                self.upsert("dataset", record_id, path.relative_to(project_root).as_posix(), data)
                summary["dataset"] += 1
        return summary

    def verify_sources(self, root: str | Path) -> dict[str, Any]:
        project_root = Path(root).resolve()
        missing: list[str] = []
        with self._connect() as conn:
            rows = conn.execute("SELECT source_path FROM records").fetchall()
        for row in rows:
            rel = row["source_path"]
            if not (project_root / rel).exists():
                missing.append(rel)
        return {"ok": not missing, "records": len(rows), "missing_sources": missing}

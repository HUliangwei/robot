"""Guarded local Run actions shared by API clients."""
from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any

from workbench.services.golden_path import GoldenPathService
from workbench.storage.manifests import read_json


class RunStateError(ValueError):
    """The requested Run action is invalid for the current lifecycle state."""


class LocalRunActionService:
    _execution_guard = Lock()
    _active_executions: set[tuple[Path, str]] = set()

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def _manifest(self, run_id: str) -> dict[str, Any]:
        runs_root = (self.root / "runs").resolve()
        run_dir = (runs_root / run_id).resolve()
        if not run_id or Path(run_id).name != run_id or not run_dir.is_relative_to(runs_root):
            raise ValueError(f"invalid Run ID: {run_id!r}")
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(f"run {run_id!r} does not exist")
        manifest = read_json(manifest_path)
        if not isinstance(manifest, dict):
            raise ValueError(f"run {run_id!r} manifest is invalid")
        return manifest

    def validate_execute(self, run_id: str, confirmation: str) -> dict[str, Any]:
        if confirmation != run_id:
            raise ValueError("confirmation must exactly match the Run ID")
        manifest = self._manifest(run_id)
        state = manifest.get("status")
        if state not in {"READY", "FAILED"}:
            raise RunStateError(f"run {run_id} cannot execute from state {state!r}")
        key = (self.root, run_id)
        with self._execution_guard:
            if key in self._active_executions:
                raise RunStateError(f"run {run_id} execution request is already active")
            self._active_executions.add(key)
        return {
            "schema_version": "rlw.run_execution_request/v1",
            "run_id": run_id,
            "status": "ACCEPTED",
        }

    def execute(self, run_id: str) -> dict[str, Any]:
        try:
            return GoldenPathService(self.root).execute(run_id)
        finally:
            with self._execution_guard:
                self._active_executions.discard((self.root, run_id))

    def reconcile(self, run_id: str) -> dict[str, Any]:
        self._manifest(run_id)
        return GoldenPathService(self.root).discover(run_id)

# RLW V3 Compatibility Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert `HUliangwei/robot` from the legacy workspace/dashboard layout into an Architecture V3-compatible local control-plane foundation without deleting existing PushT/LIBERO research assets.

**Architecture:** Keep `workspace/` read-only as migration input. Establish stable Core domain objects, rebuildable filesystem/SQLite storage, thin provider and executor contracts, FastAPI, and a React GUI that only consumes API services. Remote compute remains out of scope until the local GUI acceptance milestone.

**Tech Stack:** Python 3.10+, stdlib dataclasses/sqlite3/subprocess, PyYAML, FastAPI/Uvicorn, React/TypeScript/Vite, pytest.

**Spec:** `docs/architecture/Robot Learning Workbench Architecture V3.md`

## Global Constraints

- Canonical semantics: `Experiment → Trial → Run → Job → ExecutionAttempt`.
- GUI before Remote Compute; GUI owns no provider/executor business logic.
- Filesystem manifests are portable truth; SQLite is rebuildable.
- Existing `workspace/pusht` and `workspace/libero` assets are preserved and first scanned read-only.
- Dataset revisions are immutable inputs; schema version exists on persisted formats.
- Do not implement a Server Agent, Slurm/Kubernetes or Workflow Canvas in this slice.

---

### Task 1: Stable domain and lifecycle

**Files:** `workbench/core/domain.py`, `workbench/core/transitions.py`, `tests/test_transitions.py`

- [x] Define V3 domain dataclasses/enums without framework/provider dependencies.
- [x] Test invalid terminal-state reversal before implementing transition rules.
- [x] Implement explicit Job/Attempt state transitions.

### Task 2: Portable manifests and rebuildable catalog

**Files:** `workbench/storage/manifests.py`, `workbench/storage/catalog.py`, `tests/test_manifests.py`, `tests/test_catalog.py`

- [x] Test atomic JSON replacement and filesystem rebuild from Run/Dataset manifests.
- [x] Implement atomic JSON writes using same-filesystem `os.replace`.
- [x] Implement SQLite `records` index and `rebuild()` from `runs/**/manifest.json` and `datasets/**/dataset.yaml`.

### Task 3: Read-only legacy discovery

**Files:** `workbench/services/legacy.py`, `tests/test_legacy.py`

- [x] Test that scanning does not mutate `workspace/`.
- [x] Discover project metadata, metrics/evaluation files and checkpoint candidates.
- [x] Mark provenance as inferred and do not auto-register imported Runs.

### Task 4: Thin provider + local execution contracts

**Files:** `workbench/providers/base.py`, `workbench/providers/lerobot.py`, `workbench/executors/base.py`, `workbench/executors/local.py`, `tests/test_local_executor.py`

- [x] Keep LeRobot adapter to validation/config/CommandSpec construction.
- [x] Keep subprocess execution in LocalExecutor.
- [x] Persist Attempt state/logs below `.rlw/state/jobs/`.

### Task 5: Local API and GUI boundary

**Files:** `workbench/api/app.py`, `workbench/services/overview.py`, `gui/*`, `tests/test_api.py`

- [x] Expose health/overview/runs/datasets/jobs/artifacts/providers/doctor/legacy read endpoints.
- [x] Build React/TS/Vite dashboard that only calls those endpoints.
- [x] Preserve old GUI under `legacy/gui_dashboard_v4/` during migration.

### Task 6: Repository migration tooling

**Files:** bundle `apply_rlw_v3_update.py`, `verify_rlw_v3_update.py`, `rollback_rlw_v3_update.py`, `.gitignore`, docs.

- [x] Back up overwritten files before overlay.
- [x] Preserve `workspace/` and archive legacy GUI.
- [x] Install V3-managed `.gitignore` rules without exposing large dataset/cache payloads.
- [x] Provide dry-run/verify/rollback and Git synchronization instructions.

### Task 7: Next slice after migration

- [ ] Convert **PushT + ACT + LeRobot + LocalExecutor** into the first canonical new Run flow.
- [ ] Add resolved config + run manifest + lineage + durable Job/Attempt research metadata.
- [ ] Discover/register checkpoint artifacts without copying upstream training logic.
- [ ] Add Rollout/Evaluation/MetricRecord and compare the same operation via CLI and GUI.

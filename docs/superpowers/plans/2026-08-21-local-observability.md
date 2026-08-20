# Local Observability V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver structured local lifecycle events and one shared Run observability read model used by CLI, API, and GUI.

**Architecture:** Persist additive, idempotent Run-owned JSONL events while retaining manifests as state truth. Aggregate filesystem Run/Job/Attempt records and bounded machine-local log tails in one Application Service; expose it unchanged through CLI/API and render it in React.

**Tech Stack:** Python 3.10+ stdlib, FastAPI, pytest, React 19, TypeScript 5.9, Vite 7, Node test runner.

**Spec:** `docs/superpowers/specs/2026-08-21-local-observability-design.md`

## Global Constraints

- Canonical semantics remain `Experiment → Trial → Run → Job → ExecutionAttempt`.
- Filesystem manifests remain portable truth; events never replay or replace state.
- GUI owns presentation only and consumes the shared API object.
- Log reads are bounded and reject paths outside the project root.
- Existing Runs without events remain readable.
- No WebSocket, Remote Compute, SSH, Event Sourcing, or new dependency.
- R14 ships through the repository ZIP/dry-run/backup/verify/test/commit/push workflow.

---

### Task 1: Lifecycle event store and caller-owned Attempt IDs

**Files:**
- Create: `workbench/services/observability.py`
- Modify: `workbench/executors/local.py`
- Test: `tests/test_observability.py`
- Test: `tests/test_local_executor.py`

**Interfaces:**
- Produces: `LifecycleEventWriter(root, run_id).emit(event_type, *, job_id=None, attempt_id=None, occurred_at=None, category=None, payload=None, dedupe_key=None) -> dict[str, Any]`.
- Produces: `read_lifecycle_events(path) -> list[dict[str, Any]]`.
- Produces: `LocalExecutor.run(job_id, command, *, attempt_id=None) -> ExecutionResult`.

- [x] Write tests proving duplicate keys append once, malformed trailing JSON is skipped, and a caller-supplied Attempt ID is persisted.
- [x] Run the focused tests and confirm missing interfaces fail for the expected reason.
- [x] Implement one-write append/fsync, tolerant reads, deduplication, and the optional Attempt ID.
- [x] Re-run focused tests and confirm green.

### Task 2: Shared Run observability read model

**Files:**
- Modify: `workbench/services/observability.py`
- Test: `tests/test_observability.py`

**Interfaces:**
- Produces: `RunObservabilityService(root).inspect(run_id, log_tail_lines=80) -> dict[str, Any]`.
- Returns schema `rlw.run_observability/v1` with `run`, `jobs`, `events`, `artifacts`, `metrics`, and `summary`.

- [x] Write a real filesystem fixture with one failed Attempt, stdout/stderr, Artifact, Metric, event file, and hand-derived expected summaries.
- [x] Add traversal/missing-log tests and confirm the absent service fails.
- [x] Implement safe Run resolution, JSON record loading, bounded UTF-8 log tails, and normalized `ExecutionError` data.
- [x] Re-run observability tests and confirm green.

### Task 3: API and root-scoped CLI surface

**Files:**
- Modify: `workbench/api/app.py`
- Modify: `workbench/cli/main.py`
- Modify: `tests/test_api.py`
- Create: `tests/test_cli_observability.py`

**Interfaces:**
- Produces: `GET /api/v1/runs/{run_id}/observability`.
- Produces: `rlw run inspect <run_id> [--json]`.

- [x] Write API tests for identical service schema and missing Run 404.
- [x] Write a CLI JSON test and assert it equals direct service output.
- [x] Run both tests and confirm 404/unknown command failures occur.
- [x] Wire both adapters to `RunObservabilityService` without duplicating aggregation logic.
- [x] Re-run API/CLI tests and confirm green.

### Task 4: Golden Path event and failure production

**Files:**
- Modify: `workbench/services/golden_path.py`
- Modify: `tests/test_golden_path.py`

**Interfaces:**
- Consumes: `LifecycleEventWriter` and caller-owned `attempt_id`.
- Produces: ordered facts for prepare, execute, discover, success, and failure.

- [x] Extend prepare/execute/discover tests with literal event types, stable dedupe keys, and normalized nonzero-exit failure data.
- [x] Confirm tests fail because the Golden Path does not emit events.
- [x] Emit creation, state, attempt, artifact, metric, completion, and failure facts at the existing durable-write boundaries.
- [x] Re-run Golden Path and observability tests; repeat discovery and assert no duplicate artifact/metric facts.

### Task 5: GUI Run detail view

**Files:**
- Create: `gui/src/runObservability.ts`
- Create: `gui/tests/runObservability.test.ts`
- Modify: `gui/src/main.tsx`
- Modify: `gui/src/styles.css`

**Interfaces:**
- Produces: `buildRunObservabilityPath(runId) -> string`.
- Produces: TypeScript types matching `rlw.run_observability/v1`.
- Consumes: `GET /runs/{run_id}/observability` only.

- [x] Write Node tests for trimmed/encoded Run paths and stable failure/log presentation helpers.
- [x] Confirm the missing module fails.
- [x] Implement types/helpers, an Inspect action, and bilingual detail sections for events, attempts/logs, artifacts, metrics, and failures.
- [x] Run all GUI Node tests and `npm run build`.

### Task 6: Documentation, regression, and R14 delivery

**Files:**
- Modify: `README.md`
- Modify: `gui/README.md`
- Modify: `docs/superpowers/plans/2026-08-20-rlw-v3-migration-plan.md`
- Create: `docs/LOCAL_OBSERVABILITY_V1_R14.md`
- Modify: `robot_learning_workbench.egg-info/SOURCES.txt`

**Interfaces:**
- Documents: `rlw run inspect <run_id>` and GUI Inspect flow.
- Marks Architecture migration Task 10 complete and names the next local slice.

- [x] Document user commands, schemas, recovery rules, and boundaries; update packaging sources.
- [ ] Run `git diff --check`, full pytest, all GUI Node tests, and production build.
- [ ] Start GUI through `rlw gui start --no-open`, request the new endpoint, interrupt once, and confirm both ports release.
- [ ] Build the standard R14 ZIP, run protected dry-run/apply/verify/test, commit, push, and record the round log/hash.

# Local Run Control R15 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete local GUI acceptance with portable Run detail, guarded local actions, and bounded status polling.

**Architecture:** Extend the filesystem-backed observability projection without a schema bump, place action validation/delegation in an Application Service, expose it through FastAPI, and keep React limited to API calls and presentation.

**Tech Stack:** Python 3.10+, PyYAML, FastAPI BackgroundTasks, pytest, React 19, TypeScript 5.9, Node test runner, Vite 7.

**Spec:** `docs/superpowers/specs/2026-08-21-local-run-control-design.md`

## Global Constraints

- Preserve `rlw.run_observability/v1` and all pre-R15 Runs.
- Filesystem Run records remain portable truth; SQLite remains rebuildable.
- Referenced document paths must stay inside the selected Run directory.
- GUI consumes Application Service/API contracts and owns no executor logic.
- All ordinary user commands start at the repository root and use `rlw ...`.
- No Remote Compute, SSH, WebSocket, or new dependency.
- Deliver through ZIP dry-run, backup, apply, verify, test, commit, and push.

---

### Task 1: Portable Run document projection

**Files:**
- Modify: `workbench/services/observability.py`
- Modify: `tests/test_observability.py`

**Interfaces:**
- Produces: `documents.{manifest,run_spec,resolved_config,lineage}` using `rlw.record_document/v1`.
- Preserves: `RunObservabilityService.inspect(run_id, log_tail_lines=80)`.

- [ ] Add a canonical filesystem test with literal JSON/YAML content and Artifact Replica facts.
- [ ] Add old-Run fallback and unsafe referenced-path tests.
- [ ] Run focused tests and confirm failures are caused by the absent `documents` projection.
- [ ] Implement safe document loading, parsed YAML/JSON content, and embedded fallbacks.
- [ ] Re-run focused tests and keep the existing summary contract green.

### Task 2: Guarded local action service and API

**Files:**
- Create: `workbench/services/run_actions.py`
- Create: `tests/test_run_actions.py`
- Modify: `workbench/api/app.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Produces: `LocalRunActionService.validate_execute(run_id, confirmation) -> dict`.
- Produces: `LocalRunActionService.execute(run_id) -> dict` and `reconcile(run_id) -> dict`.
- Produces: `POST /api/v1/runs/{run_id}/execute` (202) and `/reconcile` (200).

- [ ] Add real manifest tests for exact confirmation, missing Run, and allowed/blocked states.
- [ ] Run focused tests and confirm the service is absent.
- [ ] Implement safe validation and Golden Path delegation.
- [ ] Add API contract tests, mocking only the long-running executor boundary.
- [ ] Confirm accepted, 400, 404, 409, and reconcile behavior.

### Task 3: GUI controls, detail, and bounded polling

**Files:**
- Modify: `gui/src/runObservability.ts`
- Modify: `gui/tests/runObservability.test.ts`
- Modify: `gui/src/main.tsx`
- Modify: `gui/src/styles.css`

**Interfaces:**
- Produces: action path helpers and `shouldPollRunObservability(detail, activeRunId)`.
- Consumes: portable documents, Artifact Replica arrays, execute/reconcile APIs.

- [ ] Add Node tests for encoded action paths, polling decisions, and document/replica facts.
- [ ] Run the Node tests and confirm missing helpers fail.
- [ ] Add typed response fields and pure presentation helpers.
- [ ] Add preflight-gated confirmation, Execute/Reconcile controls, and non-overlapping 3-second refresh scheduling.
- [ ] Render portable documents and replica facts; run Node tests and production build.

### Task 4: Equality, documentation, and R15 delivery

**Files:**
- Modify: `tests/test_api.py`
- Modify: `tests/test_cli_observability.py`
- Modify: `README.md`
- Modify: `gui/README.md`
- Modify: `docs/superpowers/plans/2026-08-20-rlw-v3-migration-plan.md`
- Create: `docs/LOCAL_RUN_CONTROL_R15.md`
- Modify: `robot_learning_workbench.egg-info/SOURCES.txt`

**Interfaces:**
- Documents: `rlw run preflight`, `rlw run execute`, `rlw run reconcile`, `rlw run inspect`, and `rlw gui start`.

- [ ] Assert CLI and API equal the direct service result for canonical Run fixtures.
- [ ] Update root-only user instructions and mark migration Task 11 complete.
- [ ] Run `git diff --check`, full Python tests, all GUI Node tests, and GUI build.
- [ ] Start via `rlw gui start --no-open`, exercise health/detail, interrupt once, and confirm both ports release.
- [ ] Build and run the standard R15 ZIP workflow; commit and push the feature branch.

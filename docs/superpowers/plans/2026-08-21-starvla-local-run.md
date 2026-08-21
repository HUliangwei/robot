# StarVLA Local Provider and Canonical Run R17 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Configure/install StarVLA as machine-local state and run it through the existing canonical local lifecycle without changing Core domain semantics.

**Architecture:** A focused Provider runtime service owns `.rlw/providers` records and auditable install plans. Golden Path resolves adapters and runtime through shared registries, while LocalExecutor remains the only process launcher and GUI remains an API client.

**Tech Stack:** Python 3.10+, stdlib subprocess/pathlib, PyYAML, FastAPI, React/TypeScript/Vite, pytest, Node test.

**Spec:** `docs/superpowers/specs/2026-08-21-starvla-local-run-design.md`

## Global Constraints

- Preserve `workspace/pusht` and `workspace/libero` read-only.
- Persist every new format with `schema_version` and atomic replacement.
- Store machine paths only below ignored `.rlw/` or runtime facts, never in portable recipes.
- Never import Provider SDKs from `workbench/core/` or GUI.
- Never execute install steps without exact `--confirm <provider>`.
- Never perform administrator, driver, CUDA, firewall, or remote-compute changes.

---

### Task 1: Provider runtime records and configuration

**Files:** Create `workbench/services/provider_runtime.py`; modify `workbench/storage/paths.py`; test `tests/test_provider_runtime_r17.py`.

**Interfaces:** `read_provider_runtime(root, provider) -> dict | None`; `configure_provider_runtime(root, provider, environment, provider_root, python_executable=None) -> dict`; `resolve_provider_runtime(root, provider, explicit_*) -> dict`.

- [x] Write failing tests proving atomic machine-local configuration, checkout validation, no-secret schema, and explicit/config/default precedence.
- [x] Run the focused test and confirm missing-module failure.
- [x] Implement the minimal runtime record service and runtime directory creation.
- [x] Re-run the focused tests and existing Provider tests.

### Task 2: Auditable Provider installation

**Files:** Create `workbench/services/provider_install.py`; modify `workbench/providers/registry.py`, `workbench/cli/main.py`; test `tests/test_provider_install_r17.py`.

**Interfaces:** `build_provider_install_plan(root, provider, ...) -> dict`; `execute_provider_install(root, plan, confirmation, runner=None) -> dict`; consumes `configure_provider_runtime(...)`.

- [x] Write failing tests for a side-effect-free stable-branch plan, mismatched confirmation, first failed required step, and atomic runtime registration after success.
- [x] Run the focused test and confirm failures are caused by absent install services/CLI.
- [x] Implement plan steps for git clone, Conda Python 3.10, requirements, and editable install; report FlashAttention separately.
- [x] Add `rlw provider configure/install` handlers with JSON and human output.
- [x] Re-run install, runtime, and CLI contract tests.

### Task 3: Provider-neutral Golden preparation and preflight

**Files:** Modify Provider adapters/registry, `workbench/services/provider_doctor.py`, `workbench/services/golden_path.py`, StarVLA recipe; test `tests/test_starvla_golden_r17.py` plus existing Golden tests.

**Interfaces:** Golden `prepare(..., provider_root=None)` resolves recipe Provider and runtime; registry exposes runtime probes and checkpoint patterns; StarVLA adapter receives portable config and execution-only output override.

- [x] Write a failing integration test for clean StarVLA prepare and generic preflight using a real temporary checkout/runtime fixture.
- [x] Confirm the current LeRobot-only recipe rejection.
- [x] Generalize recipe validation, dataset projection, Run documents, command cwd, and runtime probing through registry metadata.
- [x] Keep existing LeRobot document equality assertions green.
- [x] Re-run StarVLA, Golden Path, preflight, observability, and catalog tests.

### Task 4: StarVLA local execution and reconciliation

**Files:** Modify `workbench/services/golden_path.py`, `workbench/providers/registry.py`; test `tests/test_starvla_golden_r17.py`.

**Interfaces:** Consume existing `LocalExecutor`; Provider registration supplies checkpoint discovery patterns.

- [x] Extend the failing StarVLA fixture with a controlled local command that emits a checkpoint.
- [x] Confirm execute/reconcile fails before generic probe/discovery support exists.
- [x] Implement generic package checks and Provider-owned checkpoint discovery.
- [x] Assert durable Attempt/events and idempotent checkpoint registration.
- [x] Re-run execution, action, observability, artifact, and catalog tests.

### Task 5: API, GUI, documentation, and delivery

**Files:** Modify API, GUI Provider view/helpers, README, migration plan; create `docs/STARVLA_LOCAL_RUN_R17.md`; test API/CLI/GUI contracts.

**Interfaces:** API exposes Provider runtime/install-plan reads plus generic Golden prepare fields; GUI displays exact `rlw` commands and never executes Provider logic.

- [x] Write failing API/GUI tests for runtime state, install-plan projection, workflow selection, and root-scoped guidance.
- [x] Implement API routes and GUI runtime/plan presentation.
- [x] Update README with configure/install and StarVLA Run commands.
- [x] Run full Python tests, all GUI tests, TypeScript/Vite build, and real root `rlw` smoke.
- [x] Build and execute the R17 ZIP dry-run/backup/apply/verify/test/commit/push workflow, then pause for review.



# StarVLA Provider Boundary R16 Implementation Plan

**Goal:** Add StarVLA as the second local Provider and expose one provider-neutral
registry/diagnostic/preview boundary through CLI, API, and GUI.

**Architecture:** Provider adapters own native validation, capability projection,
and CommandSpec construction. A registry and application service provide the only
consumer entry point. Core and GUI remain provider-library-free.

**Tech stack:** Python 3.10+, FastAPI, React/TypeScript/Vite, pytest, Node test.

### Task 1: Provider contract tests and registry

- [x] Add failing tests for two registered Provider descriptors and unknown names.
- [x] Add failing StarVLA adapter validation/config/command tests.
- [x] Implement the registry and thin adapter without Core imports of Provider SDKs.

### Task 2: Unified provider application service

- [x] Add failing tests for environment probes, checkout checks, and command preview.
- [x] Generalize doctor while preserving `lerobot-win` compatibility.
- [x] Add schema-versioned provider command preview; never execute the command.

### Task 3: Root-scoped CLI and API

- [x] Add canonical parser and handler tests for provider name/environment/root.
- [x] Add provider-aware doctor and command-preview API tests.
- [x] Route all surfaces through the shared Provider service/registry.

### Task 4: GUI, docs, and delivery

- [x] Add tested GUI capability projection and provider doctor URL helpers.
- [x] Add Providers navigation/page using API data only.
- [x] Add the StarVLA recipe template and root-only README instructions.
- [ ] Execute standard R16 ZIP dry-run/backup/apply/verify/test/commit/push.

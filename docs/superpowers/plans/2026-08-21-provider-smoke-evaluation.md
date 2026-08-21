# Provider Smoke Training and PushT Evaluation R18 Implementation Plan

**Goal:** Complete real local Provider runtime selection and prove one short
LeRobot PushT train/evaluate loop while keeping StarVLA Provider-native.

**Spec:** `docs/superpowers/specs/2026-08-21-provider-smoke-evaluation-design.md`

### Task 1: Exact Provider runtimes

- [ ] Add failing tests for Conda prefix and direct-Python Doctor probes.
- [ ] Extend runtime records/resolution and CLI/API configuration.
- [ ] Make command construction use the resolved selector consistently.

### Task 2: Provider-native evaluation commands

- [ ] Add failing adapter tests for LeRobot PushT evaluation.
- [ ] Add evaluation recipe validation and CommandSpec construction.
- [ ] Preserve StarVLA-native recipe dispatch through the same registry.

### Task 3: Durable evaluation execution

- [ ] Add failing integration tests for evaluate Job/Attempt/log lifecycle.
- [ ] Implement `rlw run evaluate RUN_ID` and API action.
- [ ] Normalize native metrics and reconcile artifacts idempotently.

### Task 4: User projection

- [ ] Add GUI evaluate action and attempt/artifact visibility.
- [ ] Update README with only root-scoped `rlw ...` user commands.

### Task 5: Real Provider and PushT proof

- [ ] Configure and verify the existing LeRobot prefix runtime.
- [ ] Install/configure and Doctor the official StarVLA checkout/runtime.
- [ ] Run a short real PushT ACT training job and save its checkpoint.
- [ ] Run a real closed-loop PushT evaluation from that checkpoint.
- [ ] Reconcile and capture immutable evidence.

### Task 6: Verification and delivery

- [ ] Run focused tests, full Python tests, GUI tests, and GUI build.
- [ ] Update migration progress and README evidence.
- [ ] Review diff, commit, and push the feature branch.


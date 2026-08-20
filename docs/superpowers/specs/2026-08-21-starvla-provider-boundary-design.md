# StarVLA Provider Boundary R16 Design

## Goal

Prove that Robot Learning Workbench is a provider-neutral control plane by adding
StarVLA as the second local Provider without importing StarVLA into Core, copying
upstream training code, or claiming that the canonical Run executor already knows
StarVLA's checkpoint layout.

## Approved scope

R16 adds a stable Provider registry, a thin StarVLA adapter, provider-aware local
diagnostics and command preview, API projection, and a GUI Providers page. All
ordinary user operations remain root-scoped `rlw ...` commands. Remote Compute,
SSH, Provider installation, and StarVLA Run execution are explicitly deferred.

This is a boundary-validation slice. A command preview is declarative evidence,
not an execution request.

## Provider model

The registry owns the set of adapter descriptors and their default environments.
Consumers ask the registry for an adapter rather than importing LeRobot or
StarVLA directly. Each descriptor projects only stable workbench facts:

- Provider name and adapter version;
- supported Job kinds and execution modes;
- default environment;
- provider-owned capability data for GUI display.

StarVLA architecture choices remain provider capabilities. `framework`, backbone,
action head, and fusion are not promoted to universal Core or database fields.
The first projection advertises `qwen_oft` and maps it to the upstream native
`QwenOFT` framework name.

## StarVLA adapter

The adapter accepts a training configuration containing:

- `framework` (initially `qwen_oft`);
- `native_config` (path inside a StarVLA checkout);
- optional `accelerate_config`, `num_processes`, `native_overrides`;
- one runtime selector: `provider_env` or `python_executable`;
- optional Provider checkout root used only as CommandSpec `cwd`.

It produces a `CommandSpec` based on the current upstream `accelerate launch`
entry point. The adapter validates and normalizes data but does not execute it.
Paths are recorded as supplied; the doctor separately checks local checkout files.

## User surfaces

Canonical commands:

```text
rlw provider list
rlw provider doctor lerobot
rlw provider doctor starvla --environment starvla --provider-root <PATH>
rlw provider command starvla --recipe recipes/train/starvla_qwenoft.yaml --provider-root <PATH>
```

`rlw provider doctor lerobot-win` remains a compatibility spelling and resolves
to Provider `lerobot` plus environment `lerobot-win`.

The API exposes the same list, provider-aware doctor, and command-preview service.
The GUI consumes only these APIs and displays Provider capabilities, framework
projection, readiness checks, and the matching root-scoped CLI guidance.

## Safety and non-goals

- No network clone or Provider environment mutation.
- No Provider import in RLW Core or GUI.
- No StarVLA training process is started by `provider command`.
- No absolute Provider path is committed in recipes.
- No StarVLA-specific schema is added to SQLite or Core domain objects.
- Existing LeRobot doctor and Golden Path behavior stays compatible.

## Acceptance

- Registry and API list LeRobot and StarVLA from the same source.
- StarVLA validation and exact command construction have focused tests.
- Doctor probes the selected environment and validates optional checkout files.
- CLI legacy and canonical forms are both tested.
- GUI helper tests prove capability projection and doctor URL construction.
- Full Python tests, GUI tests/build, and root `rlw` smoke commands pass.


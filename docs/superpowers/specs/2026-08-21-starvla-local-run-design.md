# StarVLA Local Provider and Canonical Run R17 Design

## Goal

Complete Architecture V3 milestone 17 by making StarVLA a locally configurable Provider that can participate in the same canonical `Experiment → Trial → Run → Job → ExecutionAttempt` lifecycle as LeRobot.

## Scope

R17 includes machine-local Provider runtime configuration, an auditable user-space installation plan, provider-neutral Golden Path preparation and preflight, local execution, output discovery, CLI/API projection, and GUI runtime guidance. It does not add SSH, remote nodes, secrets, automatic CUDA or driver changes, or upstream StarVLA training code.

## Installation boundary

`doctor`, `configure`, and `install` remain separate operations:

- `rlw provider doctor starvla` is read-only.
- `rlw provider configure starvla ...` registers an existing environment and checkout after validating them.
- `rlw provider install starvla` only returns a schema-versioned plan.
- `rlw provider install starvla --confirm starvla` executes that exact plan.

The default StarVLA plan follows the upstream stable `starVLA` branch and uses Python 3.10. It clones the official repository, creates an isolated Conda environment, installs `requirements.txt`, and installs the checkout editable. FlashAttention is reported as a separate compatibility requirement because its wheel/build must match CUDA and PyTorch; RLW does not silently select one or modify the host toolchain.

No installation command uses administrator privileges. Every subprocess result is bounded and returned. Runtime configuration is written atomically only after all required steps succeed.

## Machine-local runtime state

Each configured Provider has one ignored record at `.rlw/providers/<provider>.json`.
Schema `rlw.provider_runtime/v1` stores Provider name, Conda environment or Python executable, checkout root, configured timestamp, and source metadata. It contains no credentials. Absolute machine paths stay out of Git and portable Run specifications.

Runtime precedence is explicit CLI/API arguments, then the machine-local record, then the Provider registry default environment.

## Provider-neutral canonical Run

Golden Path reads the recipe Provider, resolves its adapter through the registry, and delegates native validation/configuration/command construction. LeRobot's existing documents remain byte-shape compatible where practical.

StarVLA recipes record provider-owned research choices: `provider: starvla`, `framework: qwen_oft`, `native_config`, and `dataset_id: libero_provider_native`. `dataset_revision` remains mandatory and immutable. For Provider-native data, the dataset manifest uses a `provider_native` source referencing the Provider and native config, not a fabricated Hugging Face repository.

The portable `run.yaml` records Provider, framework, recipe, dataset identity, revision, and requested native overrides. Machine checkout paths appear only in runtime facts and `CommandSpec`. StarVLA receives an absolute run output path at execution time while the resolved research config retains a project-relative output reference.

## Preflight and execution

Preflight dynamically probes the selected Provider packages from registry metadata. StarVLA additionally requires its checkout root, training entrypoint, Accelerate config, and recipe native config. LeRobot retains its existing checks and names for compatibility; all Providers also expose a generic `provider_import` check.

Execution stays in `LocalExecutor`; adapters never spawn processes. R17 tests a StarVLA Run with a controlled fake runtime and command, proving the lifecycle without downloading models or starting real training.

## Discovery

Provider registrations own checkpoint patterns. LeRobot keeps `**/pretrained_model`; StarVLA recognizes checkpoint files below `**/checkpoints/` with `.pt`, `.pth`, `.bin`, or `.safetensors` suffixes. Common rollout, evaluation, and metric discovery remains shared and idempotent.

## User surfaces

Canonical root commands are:

```text
rlw provider configure starvla --environment starvla --provider-root <PATH>
rlw provider install starvla
rlw provider install starvla --confirm starvla
rlw run prepare starvla-qwenoft --dataset-revision <REVISION>
rlw run preflight <RUN_ID>
rlw run execute <RUN_ID>
rlw run reconcile <RUN_ID>
```

API and GUI read the same runtime/install-plan services. The GUI does not clone, create environments, invoke Provider processes, or own installation logic.

## Acceptance

- Installation planning is side-effect free; mismatched confirmation executes nothing.
- Successful configure/install writes one atomic machine-local runtime record.
- LeRobot tests remain green with stable document contracts.
- A fake-runtime StarVLA Run completes prepare, preflight, execute, and checkpoint reconciliation through LocalExecutor.
- CLI/API return the same Provider runtime and installation plan schemas.
- GUI displays runtime state and exact root-scoped next commands.
- Full Python tests, GUI tests/build, update ZIP workflow, and real GUI/API smoke pass before commit and push.


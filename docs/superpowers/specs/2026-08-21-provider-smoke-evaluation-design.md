# Provider Smoke Training and PushT Evaluation R18 Design

## Goal

Finish the local LeRobot and StarVLA Provider boundaries without pretending
that all Providers own the same native task. RLW selects a recipe and delegates
to the selected Provider, while every user action remains a root-scoped
`rlw ...` command.

## Scope

- Runtime selectors support a named Conda environment, an exact Conda prefix,
  or an exact Python executable. Doctor and execution probe the same runtime.
- LeRobot supports native train and evaluate CommandSpecs.
- A short real PushT ACT run performs optimizer updates and writes a checkpoint.
- Evaluation executes a real closed-loop PushT episode from that checkpoint and
  records a durable evaluate Job, ExecutionAttempt, artifacts, and metrics.
- StarVLA is installed from its official stable checkout, probed with its real
  runtime, and driven through the same prepare/preflight/execute lifecycle using
  a Provider-native smoke recipe. It is not represented as a PushT Provider.
- CLI, API, and GUI project the shared lifecycle; Provider-specific logic stays
  in adapters.

## Runtime contract

A Provider runtime record has exactly one selector:

- `environment`: a named Conda environment;
- `conda_prefix`: an absolute environment prefix; or
- `python_executable`: an absolute interpreter.

The resolved runtime supplies the same selector to Doctor, command preview,
preflight, and execution. Prefix runtimes use their interpreter directly when
possible, avoiding fragile `conda run -n` name resolution on Windows.

## Unified dispatch

`rlw run prepare <workflow>` resolves a recipe. The recipe selects `provider`,
and the registry selects the adapter. Core never maps PushT onto StarVLA or
copies native training code.

LeRobot smoke:

1. prepare immutable `lerobot/pusht` data lineage;
2. execute a small native ACT training job;
3. execute a native PushT evaluation job from the produced checkpoint;
4. reconcile checkpoint, video/evaluation output, and metrics.

StarVLA smoke:

1. install/configure a real checkout and isolated runtime;
2. Doctor validates checkout, imports, CUDA visibility, and native configs;
3. prepare and preflight the Provider-native LIBERO recipe;
4. run the smallest upstream-supported smoke command that reaches native code.

An unsupported local hardware/dependency condition is reported as a real failed
attempt with diagnostics, never converted into a fixture success.

## Evaluation records

Training and evaluation use separate durable Jobs and ExecutionAttempts below
the same Run. Evaluation output is written below
`artifacts/training/evaluation/`, and reconcile remains idempotent. Native results are
normalized into MetricRecords without discarding their original files.

## Safety

- No automatic driver, CUDA toolkit, or administrator-level mutation.
- Installation is project-local or user-space and remains confirmation gated.
- Dataset/model revisions and Provider checkout commits are recorded.
- Existing `workspace/` assets remain read-only inputs.

## Acceptance

- Both Provider Doctors use the configured exact runtime.
- LeRobot Doctor is READY.
- StarVLA uses a real official checkout/runtime and passes all required checks.
- A real PushT optimizer update and checkpoint complete successfully.
- A real closed-loop PushT evaluation completes from that checkpoint.
- The Run exposes train/evaluate Jobs, attempts, logs, checkpoint, evaluation
  artifacts, and metrics through CLI/API/GUI.
- Focused tests, full Python tests, GUI tests, and GUI build pass.


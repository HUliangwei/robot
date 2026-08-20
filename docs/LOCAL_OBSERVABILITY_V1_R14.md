# Local Observability V1 (R14)

R14 completes Architecture V3 migration Task 10 with one shared local read
model for the CLI, FastAPI, and React GUI.

## User commands

Run all commands from the repository root:

```powershell
cd D:\Desktop\robot
conda activate rlw
rlw run inspect RUN_ID
rlw run inspect RUN_ID --json
rlw gui start
```

In the GUI, open **运行 Runs** and choose **查看详情 Inspect**. The detail view
shows lifecycle events, Jobs, ExecutionAttempts, bounded stdout/stderr tails,
failure category and recommended action, Artifacts, and Metrics.

## Contracts

- `runs/<run_id>/events.jsonl` contains additive
  `rlw.lifecycle_event/v1` facts.
- `GET /api/v1/runs/{run_id}/observability` and `rlw run inspect` return
  `rlw.run_observability/v1`.
- Event `dedupe_key` values make repeated reconciliation idempotent.
- A malformed final JSONL line is skipped without hiding earlier valid facts.
- Log summaries contain at most 80 lines by default and reject paths outside
  the project root.
- Existing Runs without an event file remain readable with `events: []`.

## Produced lifecycle facts

The local Golden Path now records:

```text
RunCreated
JobCreated
JobStateChanged
AttemptStarted
AttemptFailed
JobCompleted
RunCompleted
ArtifactDiscovered
MetricEmitted
```

A failed native command is categorized as `ExecutionError` with its exit code,
retry flag, and a user-facing action to inspect logs and correct Provider input.

## Boundary

This is deliberately not Event Sourcing: manifests and portable records remain
state truth, while events describe facts for observability. There is no
WebSocket, Remote Compute, SSH, notification service, or new runtime dependency
in R14. GUI code formats the API object but does not read logs, classify errors,
discover artifacts, or execute Provider commands.

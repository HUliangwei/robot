# Local Observability V1 Design

## Purpose

R14 completes the next Architecture V3 local-GUI acceptance slice. A user can
inspect one canonical Run and answer which Job/Attempt ran, which lifecycle
facts occurred, what stdout/stderr ended with, which artifacts and metrics were
recorded, and why an attempt failed. CLI, API, and GUI consume one Application
Service contract.

## Scope

Included:

- append-only structured events for the existing local Golden Path;
- Run/Job/Attempt detail with bounded log tails;
- a stable REST response and `rlw run inspect` command;
- a bilingual GUI Run detail view;
- the first concrete `ExecutionError` presentation.

Excluded:

- Event Sourcing or rebuilding state from events;
- WebSocket/live streaming, notifications, Remote Compute, or SSH;
- a universal error taxonomy implementation;
- changes to LeRobot training internals.

## Persisted event contract

Each canonical Run owns `runs/<run_id>/events.jsonl`. Every line is one UTF-8
JSON object with schema `rlw.lifecycle_event/v1` and these fields:

```json
{
  "schema_version": "rlw.lifecycle_event/v1",
  "event_id": "event_...",
  "event_type": "AttemptStarted",
  "occurred_at": "2026-08-21T00:00:00+00:00",
  "run_id": "run_...",
  "job_id": "job_...",
  "attempt_id": "attempt_...",
  "dedupe_key": "AttemptStarted:attempt_...",
  "category": "execution",
  "payload": {}
}
```

`LifecycleEventWriter.emit()` performs one append write and fsync. A
`dedupe_key` returns the existing event instead of appending a duplicate, so
repeated reconciliation remains idempotent. Readers skip a malformed trailing
line left by interruption and preserve earlier valid events. Events describe
facts; manifests remain the state source of truth.

The V1 event types produced are `RunCreated`, `JobCreated`,
`JobStateChanged`, `AttemptStarted`, `AttemptFailed`, `JobCompleted`,
`RunCompleted`, `ArtifactDiscovered`, and `MetricEmitted`.

## Attempt identity and failure contract

The Application Service allocates the Attempt ID before execution and passes it
to `LocalExecutor.run(..., attempt_id=...)`. This lets it persist
`AttemptStarted` before the subprocess begins. Existing callers may omit the
argument and retain executor-generated IDs.

A nonzero native exit produces this portable failure shape in the archived
Attempt and observability response:

```json
{
  "category": "ExecutionError",
  "reason": "Command exited with code 7.",
  "retriable": false,
  "recommended_action": "Inspect stdout and stderr, correct the command or provider input, then retry."
}
```

## Shared read model

`RunObservabilityService.inspect(run_id, log_tail_lines=80)` returns
`rlw.run_observability/v1` with:

- `run`: the portable Run manifest;
- `jobs[].job`: durable Job records;
- `jobs[].attempts[].attempt`: durable Attempt records;
- `jobs[].attempts[].logs`: bounded stdout/stderr summaries containing
  existence, byte size, and last lines;
- `jobs[].attempts[].failure`: normalized failure or null;
- `events`, `artifacts`, `metrics` from the Run record;
- `summary` counts and latest event type.

Log paths must resolve inside the project root. Missing or rejected paths are
reported as unavailable and never raise an API 500. The service reads portable
filesystem records directly; it does not make SQLite the only truth.

## User surfaces

- CLI: `rlw run inspect <run_id>` with the normal `--json` flag.
- API: `GET /api/v1/runs/{run_id}/observability` returns the same object.
- GUI: each Run has an Inspect button and an inline detail panel for lifecycle,
  Jobs/Attempts, stdout/stderr tails, artifacts, metrics, and failure guidance.

The GUI contains formatting and presentation only. It does not classify errors,
discover artifacts, read logs, or infer state.

## Recovery and compatibility

- Event emission is additive; existing Runs without `events.jsonl` return an
  empty event list.
- A repeated `discover` call does not duplicate artifact/metric events.
- A malformed last JSONL line is ignored; earlier events remain visible.
- Existing LocalExecutor callers and API list endpoints remain compatible.
- All new persisted records declare `schema_version`.

## Verification

Tests cover event deduplication/recovery, caller-owned Attempt IDs, safe bounded
log tails, missing/unsafe paths, failure normalization, API 200/404 behavior,
CLI/API equality, Golden Path event order and discovery idempotence, GUI path
construction/detail grouping, full Python regression, GUI Node tests, and the
production Vite build.

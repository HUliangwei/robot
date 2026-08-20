# RLW Portable Run Record V1 R9

R9 advances Architecture V3 Task 7 by making the first PushT + ACT Run
self-describing without SQLite or machine-local runtime state.

## Prepared Run record

`rlw run prepare pusht-act` now writes these atomic, schema-versioned files:

```text
runs/<run_id>/
├── run.yaml
├── resolved_config.yaml
├── manifest.json
├── lineage.json
├── resolved_command.json
└── jobs/train/job.json
```

- `run.yaml` preserves user research intent and is not mutated by execution.
- `resolved_config.yaml` records the unambiguous IDs, immutable dataset revision,
  Provider configuration, and native overrides used to build the command.
- `lineage.json` records the DatasetRevision input and parent relationships.
- `jobs/train/job.json` is durable research metadata, distinct from mutable
  `.rlw/state/jobs/` runtime state.
- `manifest.json` is written last so its presence continues to mean preparation
  completed with the supporting record files in place.

## Execution record

Local execution synchronizes the durable Job state and archives each completed
runtime attempt as:

```text
runs/<run_id>/jobs/train/attempts/<attempt_id>.json
```

The archive records terminal state, exit code, command, timestamps, and relative
references to machine-local stdout/stderr runtime logs. Attempt IDs are appended
idempotently to the Job record.

## Deliberate next boundary

R9 does not yet index Job/ExecutionAttempt records in SQLite or switch the API/GUI
Jobs view from runtime state to durable research records. That is the next slice.
Remote compute, Stage In/Out, and Provider training logic remain out of scope.

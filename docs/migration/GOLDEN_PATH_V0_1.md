# RLW Golden Path V0.1

This incremental patch continues Architecture V3 Task 7 without implementing remote compute.

## Scope

- Canonical PushT + ACT preparation: immutable DatasetRevision, Experiment, Trial, Run and Job metadata.
- LeRobot command construction through the thin provider adapter.
- LocalExecutor execution remains the only process runner.
- Run-scoped training output under `runs/<run_id>/artifacts/training`.
- Checkpoint and numeric `metrics.json` discovery into Artifact and MetricRecord files.
- Rebuildable catalog now indexes Run, DatasetRevision, Artifact and MetricRecord records.
- CLI: `rlw golden detect-revision`, `prepare`, `execute`, `discover`.
- API/GUI: list Runs/Datasets/Artifacts and prepare a PushT ACT Run.
- Vite pinned to 7.3.6; run `rlw gui install` after applying to refresh `package-lock.json`.

## Deliberate boundaries

- `prepare` does not start training.
- `execute` is synchronous V0 LocalExecutor behavior and should be launched from CLI.
- GUI does not own subprocess logic.
- Immutable dataset revision is mandatory. `main`, `master`, `latest`, and empty revisions are rejected.
- Existing `workspace/` assets are not moved or rewritten.
- SSHExecutor, Stage In/Out, server agent and schedulers remain out of scope.

## Golden path

```text
PushT DatasetRevision
  -> ACT recipe
  -> LeRobot CommandSpec
  -> Experiment / Trial / Run / Job
  -> LocalExecutor / ExecutionAttempt
  -> run-scoped checkpoints
  -> Artifact records
  -> metrics.json
  -> MetricRecord
  -> Catalog / API / GUI
```

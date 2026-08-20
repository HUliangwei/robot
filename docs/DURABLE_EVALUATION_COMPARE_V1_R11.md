# Durable Evaluation Compare V1 — R11

R11 completes Architecture V3 migration Task 7 without implementing provider
evaluation loops inside RLW.

## Ownership boundary

- Providers produce native rollout and evaluation payloads.
- A Run owns its checkpoint, rollout, evaluation, report, and MetricRecord
  research results.
- RLW discovery registers produced `rollouts/` and `evaluation/` directories
  as `Artifact.kind=rollout|evaluation`; it does not copy or reinterpret their
  payload.
- SQLite remains a rebuildable index. Artifact and MetricRecord JSON below the
  Run remain the portable source of truth.

## MetricRecord contract

Flat numeric `metrics.json` values remain supported. A provider may also emit
an object with `value` plus `unit`, `direction`, `aggregation`, `scope`,
`episodes`, `provider`, and `definition_version`. Discovery preserves those
fields in `rlw.metric_record/v1`.

## Shared comparison contract

`workbench.services.evaluation` groups MetricRecords by semantic identity and
returns `rlw.metric_comparison/v1`. Values are aligned by Run ID; recognized
directions (`higher_is_better` and `lower_is_better`) determine
`best_run_ids`. Missing values remain explicit `null` values.

Both surfaces use this service:

```text
rlw evaluation compare RUN_A RUN_B
GET /api/v1/evaluation/compare?run_id=RUN_A&run_id=RUN_B
```

The GUI calls the API contract and contains no Provider, evaluator, or
comparison business logic.

## Recovery and idempotency

Discovery IDs are deterministic from Run, kind, source path, and metric name.
Repeating discovery overwrites the same generated record atomically. Catalog
rebuild can recover the complete index from filesystem records.

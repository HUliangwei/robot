# RLW Durable Execution Catalog V1 R10

R10 completes the durable Job/ExecutionAttempt query boundary introduced in R9.

## Rebuildable catalog

`rlw catalog rebuild` now indexes these filesystem research records:

```text
runs/**/jobs/*/job.json                 -> kind: job
runs/**/jobs/*/attempts/*.json          -> kind: attempt
```

The catalog stores project-relative source paths and can rebuild both record kinds
without `.rlw/state/`. Runtime state remains machine-local and is not treated as
research truth.

## API contract

```text
GET /api/v1/jobs       -> durable Job records
GET /api/v1/attempts   -> durable ExecutionAttempt records
GET /api/v1/overview   -> job and attempt counts
```

The old `/jobs` behavior that scanned `.rlw/state/jobs/**/attempt.json` has been
removed. API responses now agree with Catalog rebuild results.

## GUI contract

The local GUI adds `任务与尝试 Jobs / Attempts`. It groups attempts by `job_id`,
shows terminal state and exit code, and sorts attempts newest-first. The grouping
logic is a tested TypeScript view model; the complete React application is also
verified with the production Vite build.

## Next boundary

Architecture V3 Task 7 now has one remaining item: canonical Rollout/Evaluation,
MetricRecord semantics, and CLI/GUI comparison. Remote compute remains out of scope.

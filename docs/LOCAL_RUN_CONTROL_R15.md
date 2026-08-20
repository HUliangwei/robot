# Local Run Control R15

R15 completes Architecture V3 migration Task 11. It keeps the stable
`rlw.run_observability/v1` response and adds portable Run documents, guarded
local actions, Artifact Replica presentation, and active-Run polling.

## Root-scoped workflow

Run ordinary commands only from the repository root:

```powershell
rlw run preflight RUN_ID
rlw run execute RUN_ID
rlw run inspect RUN_ID
rlw run reconcile RUN_ID
rlw gui start
```

`rlw` selects the project directory, RLW Python runtime, GUI directory, and
Provider environment at their respective process boundaries. Users do not
change into `gui/` and do not call npm directly.

## Contracts

The observability response now includes `documents.manifest`, `run_spec`,
`resolved_config`, and `lineage`. Each `rlw.record_document/v1` object reports
its format, safe project-relative path, source, availability, parsed content,
and an error when unavailable. Old Runs use embedded manifest facts when
possible and are not changed.

`POST /api/v1/runs/{run_id}/execute` requires a JSON confirmation equal to the
Run ID and returns `202` with `rlw.run_execution_request/v1`. This means the
request was accepted; Run/Job/Attempt records report the eventual outcome.
An atomic local guard rejects duplicate accepted requests until the background
execution call returns, including its failure path.
`POST /api/v1/runs/{run_id}/reconcile` invokes the existing idempotent discovery
service. The compatibility `discover` endpoint and CLI synonym remain.

The GUI enables Execute only after a passing Preflight and asks for an exact
Run confirmation. It renders portable documents and all recorded Replica
facts. An accepted or `RUNNING` local Run is refreshed at three-second
intervals with no overlapping requests; waiting for execution to start is
bounded to 90 seconds.

## Boundaries

No remote node, SSH executor, WebSocket, new package, filesystem truth change,
or GUI-owned executor logic is included in R15.

# Local Run Control and Portable Detail Design

## Scope

R15 completes Architecture V3 migration Task 11 before any Remote Compute or
SSH work. It extends the existing local observability boundary with portable
Run documents, Artifact Replica details, guarded local actions, and bounded GUI
polling. Existing CLI commands and the `rlw.run_observability/v1` schema remain
compatible.

## Chosen approach

The shared Application Service remains the only read-model owner. Its
observability response gains a `documents` object containing `manifest`,
`run_spec`, `resolved_config`, and `lineage`. Each entry uses
`rlw.record_document/v1` and carries `kind`, project-relative `path`, `format`,
`source`, `available`, and parsed `content` (plus `error` when unavailable).
Referenced paths must resolve inside that Run's
directory. Old Runs fall back to compatible embedded manifest content and are
never rewritten.

Alternatives rejected were separate document endpoints, which would make one
screen assemble inconsistent snapshots, and GUI-side file interpretation,
which would duplicate business logic and violate the API boundary.

## Local actions

`LocalRunActionService` validates Run identity and state, validates a literal
confirmation equal to the Run ID, and delegates execution/reconciliation to
`GoldenPathService`. The API exposes:

- `POST /api/v1/runs/{run_id}/execute` with `{ "confirmation": "<run_id>" }`;
- `POST /api/v1/runs/{run_id}/reconcile` with an empty JSON body.

Execution returns `202 Accepted` with `rlw.run_execution_request/v1`; FastAPI
runs the existing synchronous local executor as a background task. Acceptance
means the request passed the local guard, not that training succeeded. The
canonical Run/Job/Attempt records remain the source of lifecycle truth.
An atomic process-local guard rejects a second request for the same Run until
the accepted background call exits; its `finally` path releases the guard.
Reconcile stays synchronous and idempotent. Missing Runs return 404, malformed
or mismatched confirmation returns 400, and invalid lifecycle state returns
409. The compatibility `/discover` endpoint remains.

## GUI behavior

The Runs page keeps Preflight and Inspect, then adds Execute and Reconcile.
Execute is enabled only after that Run has a successful preflight report and
uses a browser confirmation naming the exact Run ID. The GUI calls the API and
never invokes Python, a Provider, npm, or an executor directly.

When the selected Run is `RUNNING`, or just received an accepted execution
request, the detail loader schedules one refresh after 3 seconds. Each completed
request schedules the next one, so requests do not overlap. Terminal states and
selection changes cancel the timer. This is intentionally bounded polling, not
WebSocket infrastructure.

The detail panel renders the four portable documents as readable JSON, and
renders every Artifact Replica's node, URI, state, digest, byte size,
persistence, cache, and pin facts without inventing missing values.

## Equality, safety, and compatibility

CLI and API are asserted equal to a direct `RunObservabilityService` result for
the same canonical filesystem fixture. GUI helper tests use that same response
shape and assert document/replica projection and polling decisions.

No new dependency, schema bump, remote node, SSH behavior, mutation of completed
research records, or arbitrary filesystem read is introduced. All ordinary
user instructions remain root-scoped `rlw ...` commands.

## Acceptance

- Old and current Runs inspect without mutation.
- Unsafe document paths are reported unavailable and never read.
- Execute requires exact Run-ID confirmation and allowed state.
- Reconcile uses the existing idempotent discovery service.
- GUI shows documents/replicas and polls only active local Runs.
- Python tests, GUI Node tests, GUI production build, and real `rlw gui start`
  smoke pass before the standard R15 ZIP apply/verify/test/commit/push round.

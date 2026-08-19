# Codex instructions — Robot Learning Workbench

1. **Single architecture baseline:** read `docs/architecture/Robot Learning Workbench Architecture V3.md` before architectural work. Do not require V1/V2 documents.
2. Preserve existing `workspace/pusht` and `workspace/libero` assets during migration; never silently rewrite historical evidence.
3. Stable vocabulary is `Experiment → Trial → Run → Job → ExecutionAttempt`. Do not introduce competing domain names.
4. `workbench/core/` must not import FastAPI, React, LeRobot, StarVLA, vla-eval, SQLAlchemy implementations, or SSH implementations.
5. GUI is an API client. No subprocess, SSH, rsync, provider, or LocalExecutor business logic in React.
6. Artifact identity is not a filesystem path. SQLite is a rebuildable index, not the sole research truth.
7. Every persisted format needs `schema_version`; filesystem writes that transition state must be atomic/recoverable/idempotent.
8. Never store secret values in manifests, logs, Git, or API responses; use references.
9. Do not implement Server Agent, Slurm/Kubernetes, Workflow Canvas, or remote compute before the local GUI acceptance milestone.
10. Use tests for lifecycle transitions, manifest/catalog rebuild, provider command construction, local execution, and API behavior.

# Runs — research records

`runs/` is for RLW research records: `run.yaml`, `resolved_config.yaml`, `manifest.json`, `lineage.json`, durable Job/Attempt metadata, and Run-owned artifacts. Heavy payload is ignored by Git policy.

Completed research records must not be silently mutated; changed research intent creates a new Trial/Run and continuation creates a child Run.

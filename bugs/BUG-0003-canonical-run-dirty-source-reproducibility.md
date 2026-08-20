# BUG-0003 — Canonical Run could be prepared from a dirty source tree

- **Status:** FIXED
- **Severity:** high
- **Affected version:** RLW Golden Path V0.1 R3 and earlier
- **Environment:** any Git worktree; observed on Windows 11 / PowerShell during first PushT + ACT canonical Run preparation

## Symptom

`rlw golden prepare` recorded only `git_commit = HEAD`. It did not record whether tracked or untracked source files differed from that commit. A Run could therefore look reproducible while its actual Workbench/provider recipe code was not represented by the stored commit SHA.

The first prepared Run in this migration sequence (`run_123016e7d878`) was created while Golden Path source changes were still uncommitted. It must not be executed as the reproducible baseline.

## Reproduction

1. Modify a tracked source file without committing it.
2. Run `rlw golden prepare --dataset-revision <immutable-sha> ...` on R3.
3. Inspect `runs/<run_id>/manifest.json`.
4. The manifest stores `git_commit`, but does not prove that the working tree was clean at prepare time.

## Root cause

The R3 implementation used `git rev-parse HEAD` as the sole source snapshot identity. A commit SHA identifies committed content only; it says nothing about working-tree changes.

## Fix

R4 adds a source-state guard and a preflight contract:

- `prepare` refuses source changes that are not RLW-generated research records.
- Generated metadata under `runs/`, `datasets/lerobot_pusht/`, `.rlw/`, etc. does not make the source snapshot dirty.
- New Run manifests record `git_state.source_tree_clean_at_prepare = true`.
- `rlw golden preflight <run_id>` verifies current commit, clean source state, immutable dataset manifest, CommandSpec, output writability, and Provider runtime/imports.
- `rlw golden execute <run_id>` now refuses execution if required preflight checks fail.

## Workaround for R3 Runs

Do not execute a Run prepared before the source was committed. Preserve or archive the metadata, commit the source, and prepare a new Run from the clean commit.

## Verification

R4 regression tests cover:

- dirty source rejection during prepare;
- commit mismatch detection;
- RLW-generated Run/Dataset records not invalidating source cleanliness;
- execute refusing a failed preflight.

## Related files / commits

- `workbench/services/golden_path.py`
- `workbench/cli/main.py`
- `workbench/api/app.py`
- `tests/test_golden_preflight_r4.py`

## Lessons / prevention

A Git commit is not enough for research reproducibility unless the system also proves that the source tree used to create the Run matched that commit. Canonical Run creation must establish this invariant before any execution begins.

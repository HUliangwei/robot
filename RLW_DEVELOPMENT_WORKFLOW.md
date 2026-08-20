# RLW Development Workflow

This file defines the fixed development/update loop for Robot Learning Workbench.

## Iteration loop

```text
GitHub commit
  -> review exact current branch/commit
  -> generate incremental ZIP
  -> dry-run
  -> automatic backup
  -> apply
  -> verify
  -> pytest
  -> commit/push feature branch
  -> review next round
```

A failed test does not require discarding the feature branch. The failed state may be
committed and pushed for review when the round log clearly records the failure.

## ZIP contract

Every update ZIP must contain:

- `apply_update.py`: base validation, dry-run, backup, controlled overlay.
- `verify_update.py`: structural and targeted checks.
- `rollback_update.py`: restore overwritten files and remove files created by the update.
- `payload/`: source/docs/tests changed in the round.
- `run_update_round.ps1`: current-round transcript runner.

Updates must not silently delete `workspace/`, canonical research records, datasets,
checkpoints, legacy assets, or machine-local state.

## Round transcript policy

Terminal scrollback is not evidence. Every update round writes one complete PowerShell
transcript to:

```text
.rlw/logs/update_rounds/
```

The transcript starts before the project-changing dry-run/apply sequence and records:

```text
round / timestamp
PowerShell + Python + Conda context
git branch + HEAD + status
ZIP path + SHA256
dry-run
backup + apply
verification
pytest
git status + diff
commit + push (when requested)
final HEAD + status
```

`.rlw/` is machine-local runtime state and remains outside Git.

## Encoding policy

The round runner configures UTF-8 for native commands and Python:

```text
code page 65001
PYTHONUTF8=1
PYTHONIOENCODING=utf-8
```

RLW human-facing terminal decorations use ASCII-safe text (`[OK]`, `[FAIL]`, `-`)
instead of box-drawing/check-mark glyphs. JSON remains UTF-8.

## Test-output policy

Use:

```powershell
rlw dev test
```

It streams pytest and separately preserves the full pytest transcript under:

```text
.rlw/logs/tests/
```

The round transcript therefore records the entire update lifecycle, while the pytest
log remains a focused test artifact.

## What to send back after each round

The normal handoff to ChatGPT is only:

1. the newest round log from `.rlw/logs/update_rounds/`;
2. your suggestions / observations for the next round.

The log should already contain the commit SHA, test result, diff summary, and push result.

## Branch policy

Development stays on the feature branch until milestone validation. Do not merge to
`main` only because one incremental round passes.

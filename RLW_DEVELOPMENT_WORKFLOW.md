# RLW Development Workflow

This file defines the fixed development/update loop for Robot Learning Workbench.

## Iteration loop

```text
GitHub commit
      ↓
ChatGPT reviews the exact current branch/commit
      ↓
ChatGPT generates an incremental ZIP update
      ↓
Local dry-run
      ↓
Automatic backup
      ↓
Apply update
      ↓
Verification / pytest
      ↓
Commit to the feature branch
      ↓
Push to GitHub
      ↓
ChatGPT reviews the new commit and prepares the next ZIP
```

A test failure does **not** require discarding the branch. Commit/push the diagnostic
or fix state when useful, provide the terminal evidence, and continue review from the
new GitHub commit.

## ZIP contract

Every update ZIP must contain:

- `apply_update.py` — dry-run, base-commit validation, backup, controlled overlay.
- `verify_update.py` — structural verification and targeted checks.
- `rollback_update.py` — restore overwritten files and remove files created by the update.
- `payload/` — only the source/docs/tests changed in that round.

Updates must not silently delete `workspace/`, canonical research records, datasets,
checkpoints, legacy GUI assets, or machine-local state.

## Normal local sequence

```powershell
git status -sb
git rev-parse HEAD
```

Then use the one-command extraction + dry-run command supplied with the ZIP, followed
by the apply command.

After applying:

```powershell
rlw dev test
git status -sb
git diff --stat
git add -A
git commit -m "<round commit message>"
git push
```

## Test-output policy

Raw terminal scrollback is not a durable verification record. Use:

```powershell
rlw dev test
```

RLW streams pytest output to the terminal **and** writes the full transcript under:

```text
.rlw/logs/tests/
```

If the terminal scrollback truncates older lines, the full test transcript remains
available in the logged file.

Use:

```powershell
rlw dev test --quiet
rlw dev test --show-output
```

when needed.

## Branch policy

Development remains on a feature branch until the milestone is validated.

Current line:

```text
main
└── feat/workbench-v0
    └── feat/golden-path-v0.1
```

Do not merge to `main` merely because one incremental round passes.

# RLW Bug Registry

`bugs/` records engineering defects that are important enough to preserve for future development, debugging, Codex work, and regression prevention.

This directory is **not** a runtime log folder. Runtime failures still belong under `.rlw/` or Run/Job/Attempt records. A bug document is created when a reproducible defect, root cause, and repair decision are worth keeping with the Git-tracked project.

## Naming

```text
BUG-0001-short-description.md
BUG-0002-short-description.md
...
```

IDs are monotonic and are never reused.

## Required sections

Every bug record should contain:

- **Status** — OPEN / FIXED / WONTFIX / DUPLICATE
- **Severity** — low / medium / high / critical
- **Affected version**
- **Environment**
- **Symptom**
- **Reproduction**
- **Root cause**
- **Fix**
- **Workaround**
- **Verification**
- **Related files / commits**
- **Lessons / prevention**

## Rules

1. Record evidence, not guesses. If the root cause is unknown, say so and keep the status OPEN.
2. Do not paste secrets, tokens, private credentials, or machine-private data.
3. Prefer the smallest reproducible case.
4. A FIXED bug must include fresh verification evidence.
5. When practical, add a regression test that would fail if the defect returns.
6. Link the code path and commit once the fix is committed.
7. Do not use bug documents as a substitute for canonical Run/Job/Attempt failure records.

## Current records

- `BUG-0001-windows-python-subprocess-npm.md` — Windows `npm.cmd` executable resolution.
- `BUG-0002-windows-subprocess-output-decoding.md` — UTF-8 external command output decoded as GBK.
- `BUG-0003-canonical-run-dirty-source-reproducibility.md` — canonical Run prepared from source not represented by its Git commit.

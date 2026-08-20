# RLW Golden Path V0.1 R4

R4 hardens the first PushT + ACT canonical Run flow and makes the local GUI bilingual by showing **Chinese meaning + English technical terminology together**. It is not a two-language-page/i18n system.

## R4 scope

1. `rlw golden preflight <run_id>` before training.
2. `prepare` requires a Git-clean source snapshot, while ignoring RLW-generated research records.
3. `execute` refuses required preflight failures.
4. GUI terminology uses forms such as `运行 Runs`, `数据集版本 Dataset Revisions`, `预检 Preflight`.
5. Runs page can invoke Preflight through FastAPI.
6. BUG-0003 records the reproducibility flaw found during the first prepared Run.

## Preflight required checks

- prepared Git commit equals current Git commit;
- Run was prepared from a clean source tree;
- current source tree is clean, excluding RLW-generated records;
- Dataset manifest is immutable and matches the Run lineage revision;
- CommandSpec is structurally valid;
- Run-owned training output directory is writable;
- Provider runtime resolves;
- `lerobot` and `torch` import in the Provider environment.

CUDA availability is reported as an advisory check rather than a universal hard failure.

## Existing first prepared Run

`run_123016e7d878` was prepared before the Golden Path/R4 source was committed. It is useful evidence that led to BUG-0003, but it should not be executed as the reproducible baseline. After committing R4, archive that unexecuted Run locally and prepare a new Run from the clean commit.

## Architecture boundary

R4 does not add SSH/server execution, workflow canvas, or training logic. GUI calls FastAPI; FastAPI calls services; Provider builds CommandSpec; LocalExecutor owns process execution.

# BUG-0002 — Windows verifier crashes while decoding Vite subprocess output

- **Status:** FIXED
- **Severity:** medium
- **Affected version:** RLW Golden Path V0.1 R2 verifier
- **Environment:** Windows 10/11, Python 3.11 RLW control-plane environment, Node.js/npm/Vite 7.3.6

## Symptom

After BUG-0001 fixed Windows `npm.cmd` resolution, the verifier successfully launched `npm run build` but crashed while Python captured the process output:

```text
UnicodeDecodeError: 'gbk' codec can't decode byte 0x93 ...
```

The reader thread then left `completed.stdout` as `None`, and the verifier hit a secondary exception:

```text
TypeError: 'NoneType' object is not subscriptable
```

The same GUI build succeeded when run directly from PowerShell.

## Reproduction

On Windows:

```powershell
python verify_rlw_golden_path_v01.py D:\Desktop\robot
```

The verifier reached the Vite build, then failed in Python `subprocess` output decoding. Running the build directly was successful:

```powershell
cd D:\Desktop\robot\gui
npm audit
npm run build
```

Observed direct-build result:

```text
npm audit: found 0 vulnerabilities
vite v7.3.6 building client environment for production...
build succeeded
```

## Root cause

The verifier used:

```python
subprocess.run(..., capture_output=True, text=True)
```

without an explicit encoding. On Windows, Python selected the process locale encoding (GBK/CP936 on the affected machine) for captured text. Node/Vite emits UTF-8 console output, including non-ASCII status symbols. The locale decoder therefore failed inside Python's subprocess reader thread.

A second robustness defect amplified the failure: the verifier sliced `completed.stdout[-5000:]` and `completed.stderr[-3000:]` without guarding against `None` after a reader-thread failure.

## Fix

All verifier-controlled external command output is now decoded explicitly as UTF-8 with replacement for malformed bytes:

```python
subprocess.run(
    ...,
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
    check=False,
)
```

Returned output is also normalized defensively:

```python
stdout = (completed.stdout or "")[-5000:]
stderr = (completed.stderr or "")[-3000:]
```

This matches the UTF-8 output expected from modern Node/Vite tools while preventing an unexpected byte sequence from crashing the verifier.

## Workaround

R2 can still be validated by building the GUI separately and bypassing the verifier's GUI subprocess step:

```powershell
cd D:\Desktop\robot\gui
npm audit
npm run build

cd D:\Desktop\robot
python verify_rlw_golden_path_v01.py D:\Desktop\robot --no-gui-build
```

## Verification

Regression coverage includes a child process that writes an intentionally malformed byte followed by UTF-8 output. Before the fix, the test raises `UnicodeDecodeError`; after the fix, the verifier returns a normal structured result and replaces the malformed byte with `U+FFFD`.

The affected machine already separately established:

```text
Golden Path Python verifier (--no-gui-build): ok = true
pytest: 10 passed, 1 warning
PushT immutable revision detected: b1c3ecbae7f244acc039a3dbc255a00dad1372b9
Vite lock: 7.3.6
npm audit: 0 vulnerabilities
npm run build: succeeded
```

A full R3 verifier run on the affected Windows machine is the final acceptance check for this fix.

## Related files / commits

- Bundle verifier: `verify_rlw_golden_path_v01.py`
- Bundle regression tests: `tests/test_verify_npm_resolution.py`
- Registry: `bugs/BUG-0002-windows-subprocess-output-decoding.md`
- Git commit: add after R3 is accepted on `feat/workbench-v0`

## Lessons / prevention

- Never rely on the Windows locale to decode output from modern cross-platform developer tools.
- Control-plane subprocess boundaries should choose their text encoding explicitly.
- Captured subprocess streams should be normalized before truncation or serialization.
- A verifier must return failures as structured evidence rather than fail while formatting another tool's output.

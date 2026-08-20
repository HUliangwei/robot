# BUG-0001 — Windows Python verifier cannot launch bare `npm`

- **Status:** FIXED
- **Severity:** medium
- **Affected version:** RLW Golden Path V0.1 initial bundle
- **Environment:** Windows 10/11, Python 3.11 RLW control-plane environment, Node.js/npm installed through standard Windows shims

## Symptom

`verify_rlw_golden_path_v01.py` crashed during the GUI build step instead of returning a structured verification result:

```text
FileNotFoundError: [WinError 2] 系统找不到指定的文件。
```

The failing call was equivalent to:

```python
subprocess.run(["npm", "run", "build"], ...)
```

At the same time, PowerShell could run `npm` normally.

## Reproduction

On the affected machine:

```powershell
where.exe npm
```

returned Windows command shims including:

```text
C:\Program Files\nodejs\npm
C:\Program Files\nodejs\npm.cmd
C:\Users\<user>\AppData\Roaming\npm\npm
C:\Users\<user>\AppData\Roaming\npm\npm.cmd
```

Running the verifier without `--no-gui-build` reproduced `WinError 2`.

## Root cause

PowerShell performs command resolution that recognizes the Windows `npm.cmd` shim. Python's direct `subprocess` / Windows `CreateProcess` path is not equivalent to PowerShell command resolution when given the bare executable name `npm`.

The verifier assumed that a command accepted by PowerShell could always be passed unchanged as the first element of a Python subprocess argv list. That assumption was not portable.

## Fix

The verifier now resolves the executable before launching it:

```python
npm = shutil.which("npm.cmd") or shutil.which("npm")  # Windows preference
```

The implementation is cross-platform:

- Windows (`os.name == "nt"`): prefer `npm.cmd`, then `npm`.
- POSIX: prefer `npm`, then `npm.cmd` as a fallback.

`run()` also catches `FileNotFoundError` and returns a structured failed check with exit code `127` instead of crashing the verifier.

## Workaround

For the initial V0.1 bundle, GUI validation could be split manually:

```powershell
cd D:\Desktop\robot\gui
npm audit
npm run build

cd D:\Desktop\robot
python verify_rlw_golden_path_v01.py D:\Desktop\robot --no-gui-build
```

## Verification

Fresh verification evidence from the affected Windows machine:

```text
Python verifier with --no-gui-build: ok = true
pytest: 10 passed, 1 warning
PushT revision detection: selected b1c3ecbae7f244acc039a3dbc255a00dad1372b9
Vite lock version: 7.3.6
npm audit: found 0 vulnerabilities
npm run build: succeeded with Vite 7.3.6
```

The updated bundle also contains regression tests that verify:

1. Windows resolution prefers `npm.cmd`.
2. POSIX resolution prefers `npm`.
3. Missing executables are reported as structured verification failures instead of uncaught exceptions.

## Related files / commits

- Bundle verifier: `verify_rlw_golden_path_v01.py`
- Regression test: `tests/test_verify_npm_resolution.py` inside the update bundle
- Project registry: `bugs/README.md`
- Git commit: add after applying this fix to `feat/workbench-v0`

## Lessons / prevention

- Do not assume shell command resolution and direct process creation are identical.
- External tool discovery belongs at the control-plane boundary and should produce explicit diagnostics.
- Verification tools must report failures as data whenever possible; a missing optional external executable should not destroy the whole report.
- Cross-platform launcher behavior requires a regression test whenever Windows `.cmd`/`.bat` shims are involved.

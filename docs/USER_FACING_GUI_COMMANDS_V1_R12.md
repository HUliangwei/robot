# User-facing GUI commands V1 (R12)

R12 makes the RLW CLI the supported boundary for local GUI setup and use.
Users no longer need to coordinate FastAPI and Vite in separate terminals.

## Commands

```powershell
rlw gui install
rlw gui start
```

`rlw gui install` installs the React GUI dependencies below the project
`gui/` directory. `rlw gui start` starts FastAPI and Vite, supplies the API
origin to both processes, waits for both readiness endpoints, and opens the
browser only after the GUI is ready.

```powershell
rlw gui start --no-open
rlw gui start --api-port 8100 --gui-port 5200
```

`Ctrl+C` stops both process trees. A partial startup failure also cleans up
every process that was already started. Missing Node.js/npm, missing GUI
dependencies, invalid ports, occupied ports, and readiness failures produce a
short CLI error and a non-zero exit code.

## Boundary

The launcher owns local process supervision only. The GUI remains an API
client and contains no Provider, evaluator, executor, or SSH business logic.
The raw FastAPI/Vite commands remain implementation details for developers and
automated tests, not the ordinary user workflow.

## Verification contract

- CLI parser and dispatch tests cover install/start flags and exit codes.
- Process tests cover readiness ordering, browser opening, and reverse-order
  cleanup on normal exit and `Ctrl+C`.
- Preflight tests cover dependency and port failures.
- API tests cover the GUI origin passed by the launcher.
- A real `--no-open` smoke test verifies that one command brings up both local
  services and that one interrupt releases both ports.

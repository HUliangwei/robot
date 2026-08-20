# Root-scoped command runtime V1 (R13)

R13 makes the repository root the ordinary user boundary for every `rlw ...`
operation. Users remain in the root; RLW resolves child working directories
and execution environments from structured data.

## Runtime boundaries

| Boundary | Working directory | Runtime |
|---|---|---|
| RLW Core and FastAPI | repository root | the Python executable that launched `rlw` |
| React/Vite GUI | `gui/` | resolved Node.js/npm executables |
| Provider jobs | CommandSpec `cwd` | declared environment reference or Python executable |

The implementation does not construct shell strings such as
`cd ... && conda activate ...`. Provider environments continue to use
structured execution such as `conda run -n lerobot-win python ...`, matching
Architecture V3's Environment Manager direction.

## User contract

```powershell
cd D:\Desktop\robot
rlw system doctor
rlw gui install
rlw gui start
```

Running an operation from a subdirectory fails before RLW creates machine-local
state. The `--root` option remains accepted but is hidden from ordinary help;
it exists only for controlled tests and ZIP update automation.

`rlw gui install` validates `gui/package.json`, runs `npm install` with `gui/`
as the real process working directory, and converts platform-specific native
failures into stable CLI exit code `1`.

`rlw system doctor` schema V3 adds the RLW Python executable, its resolved
Conda environment, the parent shell's Conda environment as a separate fact,
current/root path match, Node/npm executable paths, GUI package, GUI
dependencies, and state-driven next commands.

## Verification contract

- Unit tests protect the GUI argv/cwd split and failure-code normalization.
- CLI tests protect root-only ordinary operation and the hidden automation override.
- Doctor tests protect both JSON data and human-facing next steps.
- A real root-directory smoke test installs GUI dependencies, launches API and
  Vite together, and confirms one interrupt releases both ports.

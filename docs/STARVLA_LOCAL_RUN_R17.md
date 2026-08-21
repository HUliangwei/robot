# StarVLA Local Provider Lifecycle (R17)

R17 makes StarVLA the second Provider that uses RLW's canonical local Run
lifecycle. RLW owns metadata, runtime selection, preflight, execution attempts,
and artifact reconciliation; StarVLA continues to own its framework, native
configuration, and training code.

## Root-scoped workflow

Run all commands from the project root. Register an existing checkout:

```powershell
rlw provider configure starvla --environment starvla --provider-root D:\path\to\starVLA
rlw provider doctor starvla
```

Or inspect and explicitly execute the managed installation plan:

```powershell
rlw provider install starvla
rlw provider install starvla --confirm starvla
rlw provider doctor starvla
```

Prepare and operate a canonical Run:

```powershell
rlw run prepare starvla-qwenoft --dataset-revision REVISION
rlw run preflight RUN_ID
rlw run execute RUN_ID
rlw run inspect RUN_ID
rlw run reconcile RUN_ID
```

## Runtime and safety contract

- `.rlw/providers/starvla.json` is machine-local and never portable source.
- Explicit runtime flags override saved configuration; saved configuration
  overrides the registry default.
- `provider install` is plan-only until `--confirm starvla` is exact.
- A failed required install step stops the plan and does not register a runtime.
- Provider Doctor and preflight are read-only.
- FlashAttention, CUDA, GPU drivers, firewall, SSH, and remote nodes are not
  silently installed or mutated by R17.
- GUI actions call the same API services and launch no Provider subprocesses.

## Canonical records

StarVLA preparation writes the same portable Run documents as LeRobot, including
the Provider/framework identity, provider-native dataset identity and revision,
native config path, source Git commit, resolved command, and runtime provenance.
Machine-specific paths stay in runtime facts rather than the recipe.

Execution still passes through `LocalExecutor`, creating durable Job,
ExecutionAttempt, lifecycle event, and bounded log records. Reconciliation uses
Provider-owned checkpoint patterns and registers `.pt`, `.pth`, `.bin`, and
`.safetensors` outputs as provider-attributed artifacts. Reconciliation is
idempotent.

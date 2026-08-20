# StarVLA Provider Boundary R16

R16 adds StarVLA as Robot Learning Workbench's second registered Provider while
keeping Architecture V3's stable Core free of Provider SDK imports.

## Delivered boundary

- One registry supplies Provider descriptors to services, API, CLI, and GUI.
- `StarVLAAdapter` owns QwenOFT capability projection, native configuration
  validation, and declarative `CommandSpec` construction.
- Provider doctor selects the declared Conda environment and can validate an
  explicitly supplied StarVLA checkout.
- Provider command preview loads a repository recipe and returns a
  schema-versioned, non-executing result.
- The GUI Providers page displays provider-owned architecture capabilities and
  calls the same doctor endpoint as the CLI.

## Root-scoped acceptance commands

```powershell
rlw provider list
rlw provider doctor lerobot
rlw provider doctor starvla --environment starvla --provider-root D:\path\to\starVLA
rlw provider command starvla --recipe recipes/train/starvla_qwenoft.yaml --environment starvla --provider-root D:\path\to\starVLA
rlw gui start
```

The last two StarVLA commands do not install or start StarVLA. The command
preview explicitly reports `executed: false`.

## Deferred intentionally

StarVLA Provider installation, canonical Run preparation/execution, output
discovery, and checkpoint Artifact mapping need a separately tested local slice.
Remote Compute and SSH remain out of scope.

# RLW Runtime Contract V1 R8

Base commit: `c16f264`

R8 repairs the failed R7 delivery and introduces three concrete contracts:

1. **Control-plane Doctor** — `rlw system doctor` no longer treats `torch` or `lerobot`
   in the RLW environment as system-health failures.
2. **Provider Doctor** — `rlw provider list` and
   `rlw provider doctor lerobot-win` probe the isolated provider environment.
3. **Durable Test Transcript** — `rlw dev test` streams pytest to the console and
   persists the complete transcript under `.rlw/logs/tests/`.

It also completes the resource/action CLI compatibility surface:

```text
rlw system ...
rlw provider ...
rlw catalog ...
rlw legacy ...
rlw run ...
rlw dev ...
rlw golden ...   # compatibility
```

Run aliases:

- `rlw run show RUN_ID` / `rlw run status RUN_ID`
- `rlw run reconcile RUN_ID` → GoldenPath artifact/metric discovery
- `rlw run discover RUN_ID` remains as a compatibility synonym.

`rlw run prepare pusht-act` resolves the canonical PushT ACT recipe and, when
`--dataset-revision` is omitted, uses the detected immutable revision only if the
local cache yields exactly one unambiguous candidate.

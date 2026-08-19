from __future__ import annotations

from pathlib import Path


def find_project_root(start: str | Path | None = None) -> Path:
    current = Path(start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists() or (candidate / "pyproject.toml").exists():
            return candidate
    raise RuntimeError("RLW project root not found; run inside the robot repository")


def ensure_runtime_dirs(root: Path) -> dict[str, Path]:
    base = root / ".rlw"
    names = ("envs", "worktrees", "cache", "state", "locks", "tmp", "secrets", "import_candidates")
    out = {name: base / name for name in names}
    for path in (base, *out.values()):
        path.mkdir(parents=True, exist_ok=True)
    return out

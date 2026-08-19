from __future__ import annotations

import subprocess
import sys


def main() -> int:
    cmds = [
        [sys.executable, "-m", "pip", "install", "-e", ".[dev]"],
        [sys.executable, "-m", "workbench.cli.main", "init"],
        [sys.executable, "-m", "workbench.cli.main", "doctor"],
    ]
    for command in cmds:
        print("+", " ".join(command))
        code = subprocess.call(command)
        if code:
            return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

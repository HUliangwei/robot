import os
import subprocess
import uuid
import zipfile
from pathlib import Path

FORBIDDEN_TERMINAL_GLYPHS = ("·", "─", "✓", "✗", "○")


def test_human_terminal_output_is_ascii_safe():
    for rel in ("workbench/cli/main.py", "workbench/services/test_runner.py"):
        text = Path(rel).read_text(encoding="utf-8")
        for glyph in FORBIDDEN_TERMINAL_GLYPHS:
            assert glyph not in text, f"{rel} still contains terminal glyph {glyph!r}"


def test_round_runner_captures_native_command_output(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    bundle = tmp_path / "probe_update.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr(
            "apply_update.py",
            "import sys\n"
            "assert '--dry-run' in sys.argv\n"
            "print('APPLY-DRY-RUN-NATIVE-STDOUT')\n"
            "print('APPLY-DRY-RUN-NATIVE-STDERR', file=sys.stderr)\n",
        )
        archive.writestr("verify_update.py", "print('VERIFY-NATIVE-OUTPUT')\n")

    round_name = f"R8_2_PROBE_{uuid.uuid4().hex[:8]}"
    powershell = (
        Path(os.environ.get("SystemRoot", r"C:\\Windows"))
        / "System32"
        / "WindowsPowerShell"
        / "v1.0"
        / "powershell.exe"
    )
    child_env = os.environ.copy()
    child_env["PSMODULEPATH"] = str(
        Path(os.environ.get("SystemRoot", r"C:\\Windows"))
        / "System32"
        / "WindowsPowerShell"
        / "v1.0"
        / "Modules"
    )
    completed = subprocess.run(
        [
            str(powershell),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(repo_root / "scripts" / "run_update_round.ps1"),
            "-ZipPath",
            str(bundle),
            "-RepoRoot",
            str(repo_root),
            "-RoundName",
            round_name,
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=child_env,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    logs = list((repo_root / ".rlw" / "logs" / "update_rounds").glob(f"{round_name}_*.log"))
    assert len(logs) == 1
    transcript = logs[0].read_text(encoding="utf-8-sig")
    assert "APPLY-DRY-RUN-NATIVE-STDOUT" in transcript
    assert "APPLY-DRY-RUN-NATIVE-STDERR" in transcript
    assert "RESULT: DRY-RUN ONLY" in transcript
    assert "ROUND ERROR" not in transcript
    assert "COMMAND: git rev-parse HEAD" in transcript


def test_workflow_requires_one_round_log_handoff():
    text = Path("RLW_DEVELOPMENT_WORKFLOW.md").read_text(encoding="utf-8")
    assert ".rlw/logs/update_rounds/" in text
    assert "round log" in text.lower()
    assert "suggestions" in text.lower()

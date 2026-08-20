from pathlib import Path

FORBIDDEN_TERMINAL_GLYPHS = ("·", "─", "✓", "✗", "○")


def test_human_terminal_output_is_ascii_safe():
    for rel in ("workbench/cli/main.py", "workbench/services/test_runner.py"):
        text = Path(rel).read_text(encoding="utf-8")
        for glyph in FORBIDDEN_TERMINAL_GLYPHS:
            assert glyph not in text, f"{rel} still contains terminal glyph {glyph!r}"


def test_round_runner_captures_update_lifecycle():
    path = Path("scripts/run_update_round.ps1")
    assert path.exists(), "round transcript runner is missing"
    text = path.read_text(encoding="utf-8")
    for token in (
        "Start-Transcript",
        "Stop-Transcript",
        "PYTHONUTF8",
        "PYTHONIOENCODING",
        "apply_update.py",
        "--dry-run",
        "verify_update.py",
        "dev test",
        "git status",
        "git rev-parse HEAD",
        "git push",
        ".rlw\\logs\\update_rounds",
    ):
        assert token in text, f"round runner missing {token!r}"


def test_workflow_requires_one_round_log_handoff():
    text = Path("RLW_DEVELOPMENT_WORKFLOW.md").read_text(encoding="utf-8")
    assert ".rlw/logs/update_rounds/" in text
    assert "round log" in text.lower()
    assert "suggestions" in text.lower()

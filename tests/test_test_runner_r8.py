from pathlib import Path

from workbench.services.test_runner import run_pytest


def test_dev_test_preserves_complete_transcript(tmp_path: Path):
    test_file = tmp_path / "test_sample.py"
    test_file.write_text("def test_sample():\n    assert 2 + 2 == 4\n", encoding="utf-8")
    result = run_pytest(tmp_path, quiet=True)
    assert result["exit_code"] == 0
    log = Path(result["log_path"])
    assert log.exists()
    text = log.read_text(encoding="utf-8")
    assert "passed" in text
    assert "COMMAND" in text

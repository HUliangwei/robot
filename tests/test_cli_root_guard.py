from pathlib import Path

from workbench.cli.main import build_parser, main


def _project(root: Path) -> Path:
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='test-rlw'\n", encoding="utf-8")
    (root / "workspace").mkdir()
    return root


def test_normal_command_rejects_a_project_subdirectory_before_writing_state(
    tmp_path, monkeypatch, capsys
):
    root = _project(tmp_path / "robot")
    child = root / "gui"
    child.mkdir()
    monkeypatch.chdir(child)

    exit_code = main(["system", "doctor"])

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "RLW commands must be run from the project root" in output
    assert f"Project root: {root.resolve()}" in output
    assert f"Current path: {child.resolve()}" in output
    assert not (root / ".rlw").exists()


def test_normal_command_outside_a_project_returns_a_clear_error(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)

    exit_code = main(["system", "doctor"])

    assert exit_code == 2
    assert "RLW project root not found" in capsys.readouterr().out


def test_explicit_root_remains_available_for_automation(tmp_path, monkeypatch):
    root = _project(tmp_path / "robot")
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)

    exit_code = main(["--root", str(root), "system", "init", "--json"])

    assert exit_code == 0
    assert (root / ".rlw").is_dir()


def test_root_override_is_hidden_from_normal_help():
    assert "--root" not in build_parser().format_help()

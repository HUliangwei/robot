import sys
from pathlib import Path

from workbench.cli.main import main
from workbench.services.doctor import run_doctor


def test_system_doctor_reports_core_environment_and_gui_state(
    tmp_path, monkeypatch
):
    root = tmp_path / "robot"
    (root / "workspace").mkdir(parents=True)
    gui = root / "gui"
    (gui / "node_modules").mkdir(parents=True)
    (gui / "package.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(root)
    monkeypatch.setenv("CONDA_DEFAULT_ENV", "rlw")

    report = run_doctor(root)

    assert report["schema_version"] == "rlw.doctor/v3"
    assert report["checks"]["python_executable"]["value"] == str(
        Path(sys.executable).resolve()
    )
    assert report["checks"]["conda_environment"]["value"] == "rlw"
    assert report["checks"]["current_path"]["value"] == str(root.resolve())
    assert report["checks"]["root_match"] == {
        "ok": True,
        "value": True,
        "required": False,
    }
    assert report["checks"]["gui_package"]["ok"] is True
    assert report["checks"]["gui_dependencies"]["ok"] is True
    assert "node_executable" in report["checks"]
    assert "npm_executable" in report["checks"]
    assert report["next_steps"] == [
        "rlw gui start",
        "rlw provider doctor lerobot-win",
    ]


def test_system_doctor_cli_prints_the_state_driven_next_steps(
    tmp_path, monkeypatch, capsys
):
    root = tmp_path / "robot"
    (root / "workspace").mkdir(parents=True)
    gui = root / "gui"
    (gui / "node_modules").mkdir(parents=True)
    (gui / "package.json").write_text("{}", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname='test-rlw'\n", encoding="utf-8")
    monkeypatch.chdir(root)

    exit_code = main(["system", "doctor"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "rlw gui start" in output
    assert "rlw provider doctor lerobot-win" in output


def test_system_doctor_distinguishes_python_env_from_the_parent_shell(
    tmp_path, monkeypatch
):
    root = tmp_path / "robot"
    (root / "workspace").mkdir(parents=True)
    python_prefix = tmp_path / ".conda" / "envs" / "rlw"
    monkeypatch.setattr(sys, "prefix", str(python_prefix))
    monkeypatch.setenv("CONDA_DEFAULT_ENV", "base")

    report = run_doctor(root)

    assert report["checks"]["conda_environment"]["value"] == "rlw"
    assert report["checks"]["shell_conda_environment"]["value"] == "base"

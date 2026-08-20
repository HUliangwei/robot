import importlib.util
import importlib
from pathlib import Path
import socket

import pytest

from workbench.cli import main as cli_main
from workbench.cli.main import build_parser


class _Process:
    def __init__(self, name, polls):
        self.name = name
        self._polls = iter(polls)
        self.returncode = None

    def poll(self):
        try:
            value = next(self._polls)
        except StopIteration:
            value = self.returncode
        if value is not None:
            self.returncode = value
        return value


def test_cli_exposes_gui_install_and_start_contract():
    parser = build_parser()

    install = parser.parse_args(["gui", "install", "--json"])
    start = parser.parse_args(
        [
            "gui",
            "start",
            "--no-open",
            "--api-port",
            "8100",
            "--gui-port",
            "5200",
        ]
    )

    assert install.command == "gui"
    assert install.gui_command == "install"
    assert install.json is True
    assert start.command == "gui"
    assert start.gui_command == "start"
    assert start.no_open is True
    assert start.api_port == 8100
    assert start.gui_port == 5200


def test_gui_launch_plan_wraps_api_and_vite_commands():
    spec = importlib.util.find_spec("workbench.services.gui_launcher")
    assert spec is not None, "GUI launcher service is missing"
    from workbench.services.gui_launcher import build_gui_launch_plan

    plan = build_gui_launch_plan(
        Path("C:/robot"),
        api_port=8100,
        gui_port=5200,
        python_executable="python.exe",
        npm_executable="npm.cmd",
    )

    assert plan.api_argv == (
        "python.exe",
        "-m",
        "uvicorn",
        "workbench.api.app:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8100",
    )
    assert plan.gui_argv == (
        "npm.cmd",
        "--prefix",
        "gui",
        "run",
        "dev",
        "--",
        "--host",
        "127.0.0.1",
        "--port",
        "5200",
    )
    assert plan.api_url == "http://127.0.0.1:8100/api/v1"
    assert plan.gui_url == "http://127.0.0.1:5200"
    assert plan.env_overrides == {
        "RLW_GUI_ORIGIN": "http://127.0.0.1:5200",
        "VITE_RLW_API": "http://127.0.0.1:8100/api/v1",
    }

    with pytest.raises(ValueError, match="must use different ports"):
        build_gui_launch_plan(
            Path("C:/robot"),
            api_port=8000,
            gui_port=8000,
            python_executable="python.exe",
            npm_executable="npm.cmd",
        )

    for invalid_port in (0, 65536):
        with pytest.raises(ValueError, match="between 1 and 65535"):
            build_gui_launch_plan(
                Path("C:/robot"),
                api_port=invalid_port,
                python_executable="python.exe",
                npm_executable="npm.cmd",
            )


def test_start_gui_opens_browser_after_readiness_and_cleans_both_processes(tmp_path):
    module = importlib.import_module("workbench.services.gui_launcher")
    start_gui = getattr(module, "start_gui", None)
    assert callable(start_gui), "GUI process supervisor is missing"
    plan = module.build_gui_launch_plan(
        tmp_path,
        python_executable="python.exe",
        npm_executable="npm.cmd",
    )
    api = _Process("api", [None, None])
    gui = _Process("gui", [0])
    pending = iter((api, gui))
    started = []
    ready = []
    opened = []
    stopped = []

    def process_factory(argv, **kwargs):
        process = next(pending)
        started.append((tuple(argv), kwargs))
        return process

    exit_code = start_gui(
        plan,
        process_factory=process_factory,
        wait_ready=lambda url, process, label: ready.append((url, process.name, label)),
        browser_open=opened.append,
        stop_process=lambda process: stopped.append(process.name),
        sleep=lambda _: None,
    )

    assert exit_code == 0
    assert [item[0] for item in started] == [plan.api_argv, plan.gui_argv]
    assert ready == [
        (plan.api_url + "/health", "api", "API"),
        (plan.gui_url, "gui", "GUI"),
    ]
    assert opened == [plan.gui_url]
    assert stopped == ["gui", "api"]


def test_start_gui_ctrl_c_cleans_both_processes(tmp_path):
    module = importlib.import_module("workbench.services.gui_launcher")
    start_gui = getattr(module, "start_gui", None)
    assert callable(start_gui), "GUI process supervisor is missing"
    plan = module.build_gui_launch_plan(
        tmp_path,
        python_executable="python.exe",
        npm_executable="npm.cmd",
    )
    pending = iter((_Process("api", [None]), _Process("gui", [None])))
    stopped = []

    def interrupt(*_):
        raise KeyboardInterrupt

    exit_code = start_gui(
        plan,
        process_factory=lambda *_args, **_kwargs: next(pending),
        wait_ready=interrupt,
        browser_open=lambda _: None,
        stop_process=lambda process: stopped.append(process.name),
        sleep=lambda _: None,
    )

    assert exit_code == 130
    assert stopped == ["gui", "api"]


def test_install_gui_dependencies_runs_npm_inside_project(tmp_path):
    module = importlib.import_module("workbench.services.gui_launcher")
    install_gui_dependencies = getattr(module, "install_gui_dependencies", None)
    assert callable(install_gui_dependencies), "GUI dependency installer is missing"
    gui = tmp_path / "gui"
    gui.mkdir()
    (gui / "package.json").write_text("{}", encoding="utf-8")
    calls = []

    class _Completed:
        returncode = 0

    def run_command(argv, **kwargs):
        calls.append((tuple(argv), kwargs))
        return _Completed()

    result = install_gui_dependencies(
        tmp_path,
        npm_executable="npm.cmd",
        run_command=run_command,
    )

    assert result == {
        "schema_version": "rlw.gui_install/v1",
        "status": "installed",
        "exit_code": 0,
    }
    assert calls == [
        (
            ("npm.cmd", "--prefix", "gui", "install"),
            {"cwd": tmp_path.resolve(), "check": False},
        )
    ]


def test_validate_gui_launch_requires_installed_dependencies(tmp_path):
    module = importlib.import_module("workbench.services.gui_launcher")
    validate_gui_launch = getattr(module, "validate_gui_launch", None)
    assert callable(validate_gui_launch), "GUI launch preflight is missing"
    gui = tmp_path / "gui"
    gui.mkdir()
    (gui / "package.json").write_text("{}", encoding="utf-8")
    plan = module.build_gui_launch_plan(
        tmp_path,
        python_executable="python.exe",
        npm_executable="npm.cmd",
    )

    with pytest.raises(RuntimeError, match="rlw gui install"):
        validate_gui_launch(plan)


def test_validate_gui_launch_rejects_an_occupied_port(tmp_path):
    module = importlib.import_module("workbench.services.gui_launcher")
    validate_gui_launch = getattr(module, "validate_gui_launch", None)
    assert callable(validate_gui_launch), "GUI launch preflight is missing"
    gui = tmp_path / "gui"
    (gui / "node_modules").mkdir(parents=True)
    (gui / "package.json").write_text("{}", encoding="utf-8")
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        port = occupied.getsockname()[1]
        plan = module.build_gui_launch_plan(
            tmp_path,
            api_port=port,
            gui_port=port + 1,
            python_executable="python.exe",
            npm_executable="npm.cmd",
        )

        with pytest.raises(RuntimeError, match=f"API port {port} is already in use"):
            validate_gui_launch(plan)


def test_gui_install_cli_reports_the_service_result(tmp_path, monkeypatch, capsys):
    calls = []

    def install(root):
        calls.append(root)
        return {
            "schema_version": "rlw.gui_install/v1",
            "status": "installed",
            "exit_code": 0,
        }

    monkeypatch.setattr(cli_main, "install_gui_dependencies", install, raising=False)

    exit_code = cli_main.main(
        ["--root", str(tmp_path), "gui", "install", "--json"]
    )

    assert exit_code == 0
    assert calls == [tmp_path.resolve()]
    assert '"schema_version": "rlw.gui_install/v1"' in capsys.readouterr().out


def test_gui_start_cli_forwards_ports_and_no_open(tmp_path, monkeypatch):
    calls = []
    plan = object()

    def build(root, **kwargs):
        calls.append(("build", root, kwargs))
        return plan

    def start(received, **kwargs):
        calls.append(("start", received, kwargs))
        return 23

    monkeypatch.setattr(cli_main, "build_gui_launch_plan", build, raising=False)
    monkeypatch.setattr(cli_main, "start_gui", start, raising=False)

    exit_code = cli_main.main(
        [
            "--root",
            str(tmp_path),
            "gui",
            "start",
            "--no-open",
            "--api-port",
            "8100",
            "--gui-port",
            "5200",
        ]
    )

    assert exit_code == 23
    assert calls == [
        ("build", tmp_path.resolve(), {"api_port": 8100, "gui_port": 5200}),
        ("start", plan, {"open_browser": False}),
    ]


def test_gui_start_cli_reports_a_clear_preflight_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        cli_main,
        "build_gui_launch_plan",
        lambda *_args, **_kwargs: object(),
    )

    def fail(*_args, **_kwargs):
        raise RuntimeError("GUI dependencies are missing; run 'rlw gui install' first")

    monkeypatch.setattr(cli_main, "start_gui", fail)

    exit_code = cli_main.main(
        ["--root", str(tmp_path), "gui", "start", "--no-open"]
    )

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "RLW - GUI Start" in output
    assert "rlw gui install" in output

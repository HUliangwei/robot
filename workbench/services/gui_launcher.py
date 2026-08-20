"""Local GUI launch planning and process lifecycle."""
from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class GuiLaunchPlan:
    root: Path
    api_argv: tuple[str, ...]
    gui_argv: tuple[str, ...]
    api_url: str
    gui_url: str
    env_overrides: dict[str, str]


def build_gui_launch_plan(
    root: str | Path,
    *,
    api_port: int = 8000,
    gui_port: int = 5173,
    python_executable: str | None = None,
    npm_executable: str | None = None,
) -> GuiLaunchPlan:
    for label, port in (("API", api_port), ("GUI", gui_port)):
        if not 1 <= port <= 65535:
            raise ValueError(f"{label} port must be between 1 and 65535")
    if api_port == gui_port:
        raise ValueError("API and GUI must use different ports")
    project_root = Path(root).resolve()
    python = python_executable or sys.executable
    npm = npm_executable or shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not npm:
        raise RuntimeError("npm was not found; install Node.js before starting the GUI")
    api_url = f"http://127.0.0.1:{api_port}/api/v1"
    gui_url = f"http://127.0.0.1:{gui_port}"
    return GuiLaunchPlan(
        root=project_root,
        api_argv=(
            python,
            "-m",
            "uvicorn",
            "workbench.api.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(api_port),
        ),
        gui_argv=(
            npm,
            "--prefix",
            "gui",
            "run",
            "dev",
            "--",
            "--host",
            "127.0.0.1",
            "--port",
            str(gui_port),
        ),
        api_url=api_url,
        gui_url=gui_url,
        env_overrides={
            "RLW_GUI_ORIGIN": gui_url,
            "VITE_RLW_API": api_url,
        },
    )


def install_gui_dependencies(
    root: str | Path,
    *,
    npm_executable: str | None = None,
    run_command: Callable[..., subprocess.CompletedProcess[Any]] | None = None,
) -> dict[str, Any]:
    project_root = Path(root).resolve()
    npm = npm_executable or shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not npm:
        raise RuntimeError("npm was not found; install Node.js before installing the GUI")
    run = run_command or subprocess.run
    completed = run(
        [npm, "--prefix", "gui", "install"],
        cwd=project_root,
        check=False,
    )
    return {
        "schema_version": "rlw.gui_install/v1",
        "status": "installed" if completed.returncode == 0 else "failed",
        "exit_code": int(completed.returncode),
    }


def _require_available_port(port: int, label: str) -> None:
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as exc:
            raise RuntimeError(f"{label} port {port} is already in use") from exc


def validate_gui_launch(plan: GuiLaunchPlan) -> None:
    gui_root = plan.root / "gui"
    if not (gui_root / "package.json").is_file():
        raise RuntimeError(f"GUI package.json was not found below {gui_root}")
    if not (gui_root / "node_modules").is_dir():
        raise RuntimeError("GUI dependencies are missing; run 'rlw gui install' first")
    api_port = int(plan.api_url.rsplit(":", 1)[1].split("/", 1)[0])
    gui_port = int(plan.gui_url.rsplit(":", 1)[1])
    _require_available_port(api_port, "API")
    _require_available_port(gui_port, "GUI")


def _wait_for_http(
    url: str,
    process: subprocess.Popen[Any],
    label: str,
    *,
    timeout: float = 30.0,
) -> None:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        exit_code = process.poll()
        if exit_code is not None:
            raise RuntimeError(f"{label} exited before it became ready (exit {exit_code})")
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                if response.status < 500:
                    return
        except (OSError, urllib.error.URLError) as exc:
            last_error = str(exc)
        time.sleep(0.2)
    suffix = f": {last_error}" if last_error else ""
    raise RuntimeError(f"{label} did not become ready at {url}{suffix}")


def _stop_process_tree(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def start_gui(
    plan: GuiLaunchPlan,
    *,
    open_browser: bool = True,
    process_factory: Callable[..., subprocess.Popen[Any]] | None = None,
    wait_ready: Callable[[str, subprocess.Popen[Any], str], None] | None = None,
    browser_open: Callable[[str], Any] | None = None,
    stop_process: Callable[[subprocess.Popen[Any]], None] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> int:
    if process_factory is None:
        validate_gui_launch(plan)
    factory = process_factory or subprocess.Popen
    ready = wait_ready or _wait_for_http
    open_url = browser_open or webbrowser.open
    stop = stop_process or _stop_process_tree
    pause = sleep or time.sleep
    environment = os.environ.copy()
    environment.update(plan.env_overrides)
    popen_options: dict[str, Any] = {
        "cwd": plan.root,
        "env": environment,
    }
    if os.name == "nt":
        popen_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_options["start_new_session"] = True

    processes: list[subprocess.Popen[Any]] = []
    try:
        print("RLW - GUI Start")
        print("------------------------------------------------------------")
        print(f"API  {plan.api_url}")
        print(f"GUI  {plan.gui_url}")
        print("Press Ctrl+C to stop both services.")
        api_process = factory(plan.api_argv, **popen_options)
        processes.append(api_process)
        gui_process = factory(plan.gui_argv, **popen_options)
        processes.append(gui_process)
        ready(plan.api_url + "/health", api_process, "API")
        ready(plan.gui_url, gui_process, "GUI")
        if open_browser:
            open_url(plan.gui_url)
        while True:
            for process in processes:
                exit_code = process.poll()
                if exit_code is not None:
                    return int(exit_code)
            pause(0.2)
    except KeyboardInterrupt:
        print("")
        print("Stopping RLW GUI...")
        return 130
    finally:
        for process in reversed(processes):
            stop(process)

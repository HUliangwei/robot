from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from workbench.providers.lerobot import LeRobotAdapter
from workbench.services.golden_path import GoldenPathService
from workbench.services.provider_doctor import run_provider_doctor
from workbench.services.provider_runtime import (
    configure_provider_runtime,
    resolve_provider_runtime,
)
from workbench.storage.catalog import Catalog


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(root: Path) -> Path:
    _git(root, "init")
    _git(root, "config", "user.email", "rlw-test@example.invalid")
    _git(root, "config", "user.name", "RLW Test")
    recipe = root / "recipes" / "train" / "pusht_act_smoke.yaml"
    recipe.parent.mkdir(parents=True)
    recipe.write_text(
        "schema_version: rlw.recipe/v1\n"
        "name: pusht_act_smoke\n"
        "kind: train\n"
        "provider: lerobot\n"
        "policy_type: act\n"
        "dataset_repo_id: lerobot/pusht\n"
        "evaluation:\n"
        "  env_type: pusht\n"
        "  n_episodes: 1\n"
        "  batch_size: 1\n",
        encoding="utf-8",
    )
    snapshot = root / "datasets" / "hub" / "datasets--lerobot--pusht" / "snapshots" / ("a" * 40)
    snapshot.mkdir(parents=True)
    (snapshot / "marker").write_text("dataset", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "baseline")
    return recipe


def test_runtime_accepts_exact_conda_prefix_and_resolves_its_python(tmp_path: Path):
    prefix = tmp_path / "envs" / "lerobot"
    python = prefix / ("python.exe" if sys.platform == "win32" else "bin/python")
    python.parent.mkdir(parents=True)
    python.write_text("binary", encoding="utf-8")

    record = configure_provider_runtime(tmp_path, "lerobot", conda_prefix=prefix)
    resolved = resolve_provider_runtime(tmp_path, "lerobot")

    assert record["conda_prefix"] == str(prefix.resolve())
    assert record["python_executable"] == str(python.resolve())
    assert record["environment"] is None
    assert resolved["conda_prefix"] == str(prefix.resolve())
    assert resolved["python_executable"] == str(python.resolve())


def test_doctor_probes_the_exact_python_without_requiring_conda(tmp_path: Path, monkeypatch):
    python = tmp_path / "python.exe"
    python.write_text("binary", encoding="utf-8")
    seen: list[list[str]] = []

    def fake_run(argv, timeout=60):
        seen.append(argv)
        payload = {
            "python": "3.12.1",
            "torch_installed": True,
            "torch_version": "2.7",
            "lerobot_installed": True,
            "lerobot_version": "0.6.1",
            "cuda_available": True,
        }
        return {"ok": True, "exit_code": 0, "stdout": json.dumps(payload), "stderr": ""}

    monkeypatch.setattr("workbench.services.provider_doctor._resolve_conda", lambda: None)
    monkeypatch.setattr("workbench.services.provider_doctor._run", fake_run)

    report = run_provider_doctor("lerobot", python_executable=python)

    assert report["ready"] is True
    assert report["checks"]["conda"]["required"] is False
    assert seen[0][:2] == [str(python.resolve()), "-c"]


def test_lerobot_adapter_builds_native_pusht_evaluation_command():
    command = LeRobotAdapter().build_command(
        "evaluate",
        {
            "policy_path": "D:/runs/run_1/checkpoints/000002/pretrained_model",
            "output_dir": "D:/runs/run_1/artifacts/evaluation",
            "env_type": "pusht",
            "n_episodes": 1,
            "batch_size": 1,
        },
        python_executable="D:/envs/lerobot/python.exe",
        cwd="D:/robot",
    )

    assert command.argv == (
        "D:/envs/lerobot/python.exe",
        "-m",
        "lerobot.scripts.lerobot_eval",
        "--policy.path=D:/runs/run_1/checkpoints/000002/pretrained_model",
        "--env.type=pusht",
        "--eval.n_episodes=1",
        "--eval.batch_size=1",
        "--output_dir=D:/runs/run_1/artifacts/evaluation",
    )


def test_evaluate_creates_durable_job_attempt_and_normalized_metrics(tmp_path: Path):
    recipe = _init_repo(tmp_path)
    configure_provider_runtime(tmp_path, "lerobot", python_executable=sys.executable)
    service = GoldenPathService(tmp_path)
    prepared = service.prepare(recipe, dataset_revision="a" * 40)
    run_dir = Path(prepared["run_dir"])
    checkpoint = run_dir / "artifacts" / "training" / "checkpoints" / "000002" / "pretrained_model"
    checkpoint.mkdir(parents=True)
    (checkpoint / "config.json").write_text("{}", encoding="utf-8")

    package = tmp_path / "lerobot" / "scripts"
    package.mkdir(parents=True)
    (tmp_path / "lerobot" / "__init__.py").write_text("__version__='test'\n", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "lerobot_eval.py").write_text(
        "import json,sys\n"
        "from pathlib import Path\n"
        "out=next(x.split('=',1)[1] for x in sys.argv if x.startswith('--output_dir='))\n"
        "p=Path(out); p.mkdir(parents=True,exist_ok=True)\n"
        "(p/'videos').mkdir()\n"
        "(p/'videos'/'eval_episode_0.mp4').write_bytes(b'video')\n"
        "json.dump({'aggregated': {'avg_sum_reward': 7.5, 'avg_max_reward': 0.4, "
        "'pc_success': 100.0, 'eval_s': 1.2, 'eval_ep_s': 1.2}}, "
        "open(p/'eval_info.json','w'))\n",
        encoding="utf-8",
    )
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "eval fixture")
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["git_commit"] = subprocess.check_output(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True
    ).strip()
    manifest["git_state"]["commit"] = manifest["git_commit"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = service.evaluate(prepared["run_id"])

    assert result["state"] == "SUCCEEDED"
    assert result["job_kind"] == "evaluate"
    job = json.loads((run_dir / "jobs" / "evaluate" / "job.json").read_text(encoding="utf-8"))
    attempt = json.loads(next((run_dir / "jobs" / "evaluate" / "attempts").glob("attempt_*.json")).read_text(encoding="utf-8"))
    assert job["state"] == "SUCCEEDED"
    assert attempt["state"] == "SUCCEEDED"
    assert (run_dir / "artifacts" / "training" / "evaluation" / "metrics.json").is_file()
    catalog = Catalog(tmp_path / ".rlw" / "catalog.sqlite3")
    catalog.rebuild(tmp_path)
    metrics = {item["name"]: item for item in catalog.list_records("metric")}
    assert metrics["success_rate"]["value"] == 1.0
    assert metrics["avg_sum_reward"]["value"] == 7.5

from workbench.services.provider_install import build_provider_install_plan

def test_starvla_default_install_is_project_prefix_scoped(tmp_path: Path):
    plan = build_provider_install_plan(tmp_path, "starvla")
    prefix = (tmp_path / "envs" / "starvla").resolve()

    assert plan["conda_prefix"] == str(prefix)
    create = next(step for step in plan["steps"] if step["id"] == "create_environment")
    requirements = next(step for step in plan["steps"] if step["id"] == "install_requirements")
    assert create["argv"][-3:] == ["--prefix", str(prefix), "-y"]
    assert requirements["argv"][1:4] == ["run", "--prefix", str(prefix)]

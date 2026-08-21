from pathlib import Path

import pytest

from workbench.services.provider_install import (
    build_provider_install_plan,
    execute_provider_install,
)
from workbench.services.provider_runtime import read_provider_runtime


def test_starvla_install_plan_is_side_effect_free_and_uses_upstream_stable_branch(tmp_path: Path):
    checkout = tmp_path / ".rlw" / "providers" / "starvla" / "source"

    plan = build_provider_install_plan(tmp_path, "starvla")

    assert plan["schema_version"] == "rlw.provider_install_plan/v1"
    assert plan["provider"] == "starvla"
    assert plan["environment"] == "starvla"
    assert plan["checkout_root"] == str(checkout.resolve())
    assert plan["repository"] == "https://github.com/starVLA/starVLA.git"
    assert plan["revision"] == "starVLA"
    assert plan["python_version"] == "3.10"
    assert plan["confirmation"] == "starvla"
    assert plan["executed"] is False
    step_ids = [step["id"] for step in plan["steps"]]
    assert step_ids[:3] == ["clone", "create_environment", "install_pytorch"]
    assert step_ids[-2:] == ["install_requirements", "install_editable"]
    requirements_step = next(step for step in plan["steps"] if step["id"] == "install_requirements")
    assert requirements_step["env"] == {
        "DS_BUILD_OPS": "0", "DS_SKIP_CUDA_CHECK": "1"
    }
    if __import__("os").name == "nt":
        assert step_ids[3:6] == [
            "install_cython", "install_accumulation_tree", "install_deepspeed"
        ]
        deepspeed_step = next(step for step in plan["steps"] if step["id"] == "install_deepspeed")
        assert "github.com/deepspeedai/DeepSpeed.git@v0.16.9" in deepspeed_step["argv"][8]
    assert plan["steps"][0]["argv"] == [
        "git", "clone", "--branch", "starVLA", "--single-branch",
        "https://github.com/starVLA/starVLA.git", str(checkout.resolve()),
    ]
    assert plan["manual_requirements"][0]["name"] == "flash-attn"
    assert not (tmp_path / ".rlw").exists(), "planning must not mutate machine state"


def test_starvla_install_plan_reuses_existing_environment_and_pytorch(tmp_path: Path):
    prefix = tmp_path / "envs" / "starvla"
    python = prefix / "python.exe"
    python.parent.mkdir(parents=True)
    python.touch()
    history = prefix / "conda-meta" / "history"
    history.parent.mkdir()
    history.touch()
    site_packages = prefix / "Lib" / "site-packages"
    (site_packages / "torch-2.6.0+cu124.dist-info").mkdir(parents=True)
    (site_packages / "torchvision-0.21.0+cu124.dist-info").mkdir()

    plan = build_provider_install_plan(tmp_path, "starvla")

    assert [step["id"] for step in plan["steps"]][1:3] == [
        "verify_environment", "verify_pytorch"
    ]
    if __import__("os").name == "nt":
        assert "install_cython" in [step["id"] for step in plan["steps"]]
        assert "install_deepspeed" in [step["id"] for step in plan["steps"]]
    assert plan["steps"][1]["argv"][0] == str(python)


def test_install_rejects_mismatched_confirmation_before_running_any_step(tmp_path: Path):
    plan = build_provider_install_plan(tmp_path, "starvla")
    calls: list[object] = []

    with pytest.raises(ValueError, match="confirmation must exactly match"):
        execute_provider_install(
            tmp_path,
            plan,
            confirmation="yes",
            runner=lambda argv, cwd=None: calls.append((argv, cwd)),
        )

    assert calls == []
    assert read_provider_runtime(tmp_path, "starvla") is None


def test_install_stops_at_first_failed_required_step_without_runtime_record(tmp_path: Path):
    plan = build_provider_install_plan(tmp_path, "starvla")
    calls: list[list[str]] = []

    def fail_clone(argv, cwd=None):
        calls.append(list(argv))
        return {"ok": False, "exit_code": 128, "stdout": "", "stderr": "network unavailable"}

    result = execute_provider_install(
        tmp_path, plan, confirmation="starvla", runner=fail_clone
    )

    assert result["schema_version"] == "rlw.provider_install_result/v1"
    assert result["status"] == "FAILED"
    assert result["failed_step"] == "clone"
    assert len(calls) == 1
    assert read_provider_runtime(tmp_path, "starvla") is None


def test_successful_install_registers_runtime_only_after_all_steps(tmp_path: Path):
    plan = build_provider_install_plan(tmp_path, "starvla", environment="vla-local")
    checkout = Path(plan["checkout_root"])
    calls: list[list[str]] = []

    def succeed(argv, cwd=None):
        calls.append(list(argv))
        if argv[0:2] == ["git", "clone"]:
            entrypoint = checkout / "starVLA" / "training" / "train_starvla.py"
            accelerate = checkout / "starVLA" / "config" / "deepseeds" / "deepspeed_zero2.yaml"
            entrypoint.parent.mkdir(parents=True)
            accelerate.parent.mkdir(parents=True)
            entrypoint.write_text("# installed\n", encoding="utf-8")
            accelerate.write_text("compute_environment: LOCAL_MACHINE\n", encoding="utf-8")
        assert read_provider_runtime(tmp_path, "starvla") is None
        return {"ok": True, "exit_code": 0, "stdout": "ok", "stderr": ""}

    result = execute_provider_install(
        tmp_path, plan, confirmation="starvla", runner=succeed
    )

    runtime = read_provider_runtime(tmp_path, "starvla")
    assert result["status"] == "SUCCEEDED"
    assert result["steps_completed"] == len(plan["steps"])
    assert len(calls) == len(plan["steps"])
    assert runtime is not None
    assert runtime["environment"] == "vla-local"
    assert runtime["checkout_root"] == str(checkout)
    assert runtime["source"] == {
        "repository": "https://github.com/starVLA/starVLA.git",
        "revision": "starVLA",
    }

from pathlib import Path

import pytest

from workbench.cli.main import main
from workbench.providers.registry import get_provider, provider_descriptors
from workbench.providers.starvla import StarVLAAdapter
from workbench.services.provider_doctor import preview_provider_command, run_provider_doctor


def test_registry_projects_two_provider_descriptors_from_one_source():
    items = provider_descriptors()

    assert [item["name"] for item in items] == ["lerobot", "starvla"]
    assert items[0]["default_environment"] == "lerobot-win"
    assert items[1]["default_environment"] == "starvla"
    assert items[1]["capabilities"]["frameworks"][0] == {
        "id": "qwen_oft",
        "native_name": "QwenOFT",
        "backbone": "Qwen-VL",
        "action_head": "OFT",
        "fusion": "action-token hidden-state regression",
    }
    assert get_provider("starvla").spec().name == "starvla"
    with pytest.raises(ValueError, match="unknown provider"):
        get_provider("missing")


def test_starvla_adapter_validates_and_builds_exact_conda_command():
    adapter = StarVLAAdapter()
    config = {
        "framework": "qwen_oft",
        "native_config": "examples/LIBERO/train.yaml",
        "accelerate_config": "starVLA/config/deepseeds/deepspeed_zero2.yaml",
        "num_processes": 2,
        "native_overrides": {"seed": 7, "use_wandb": False},
    }

    resolved = adapter.resolve_config(config)
    command = adapter.build_command(
        "train",
        resolved,
        provider_env="starvla",
        cwd="D:/Providers/starVLA",
    )

    assert resolved["framework"] == "qwen_oft"
    assert resolved["native_framework"] == "QwenOFT"
    assert command.cwd == "D:/Providers/starVLA"
    assert command.argv == (
        "conda", "run", "-n", "starvla", "accelerate", "launch",
        "--config_file", "starVLA/config/deepseeds/deepspeed_zero2.yaml",
        "--num_processes", "2", "starVLA/training/train_starvla.py",
        "--config_yaml", "examples/LIBERO/train.yaml",
        "--framework.name", "QwenOFT",
        "--seed", "7", "--use_wandb", "false",
    )


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({"native_config": "train.yaml"}, "framework is required"),
        ({"framework": "unknown", "native_config": "train.yaml"}, "unsupported framework"),
        ({"framework": "qwen_oft"}, "native_config is required"),
        ({"framework": "qwen_oft", "native_config": "train.yaml", "num_processes": 0}, "positive integer"),
    ],
)
def test_starvla_adapter_rejects_invalid_native_config(config, message):
    with pytest.raises(ValueError, match=message):
        StarVLAAdapter().resolve_config(config)


def test_provider_doctor_supports_canonical_and_legacy_targets(monkeypatch):
    monkeypatch.setattr("workbench.services.provider_doctor._resolve_conda", lambda: "conda")

    def fake_run(argv, timeout=60):
        packages = {
            "python": "3.11.9",
            "torch_installed": True,
            "torch_version": "2.7",
            "lerobot_installed": True,
            "lerobot_version": "0.4",
            "starVLA_installed": True,
            "starVLA_version": None,
            "accelerate_installed": True,
            "accelerate_version": "1.9",
            "cuda_available": False,
        }
        import json
        return {"ok": True, "exit_code": 0, "stdout": json.dumps(packages), "stderr": ""}

    monkeypatch.setattr("workbench.services.provider_doctor._run", fake_run)

    canonical = run_provider_doctor("starvla", environment="vla-dev")
    legacy = run_provider_doctor("lerobot-win")

    assert (canonical["provider"], canonical["environment"], canonical["ready"]) == ("starvla", "vla-dev", True)
    assert canonical["checks"]["starVLA"]["ok"] is True
    assert canonical["checks"]["accelerate"]["required"] is True
    assert (legacy["provider"], legacy["environment"]) == ("lerobot", "lerobot-win")


def test_provider_doctor_checks_a_supplied_starvla_checkout(tmp_path, monkeypatch):
    monkeypatch.setattr("workbench.services.provider_doctor._resolve_conda", lambda: None)
    root = tmp_path / "starvla"
    (root / "starVLA" / "training").mkdir(parents=True)
    (root / "starVLA" / "training" / "train_starvla.py").write_text("", encoding="utf-8")

    report = run_provider_doctor("starvla", provider_root=root)

    assert report["checks"]["provider_root"]["ok"] is True
    assert report["checks"]["training_entrypoint"]["ok"] is True
    assert report["checks"]["accelerate_config"]["ok"] is False
    assert report["ready"] is False


def test_provider_command_preview_loads_project_recipe_without_execution(tmp_path: Path):
    recipe = tmp_path / "recipes" / "train" / "starvla.yaml"
    recipe.parent.mkdir(parents=True)
    recipe.write_text(
        "schema_version: rlw.recipe/v1\n"
        "provider: starvla\n"
        "kind: train\n"
        "framework: qwen_oft\n"
        "native_config: configs/train.yaml\n",
        encoding="utf-8",
    )

    preview = preview_provider_command(
        tmp_path,
        "starvla",
        "recipes/train/starvla.yaml",
        provider_env="starvla",
        provider_root="D:/Providers/starVLA",
    )

    assert preview["schema_version"] == "rlw.provider_command_preview/v1"
    assert preview["provider"] == "starvla"
    assert preview["executed"] is False
    assert preview["command"]["cwd"] == "D:/Providers/starVLA"
    assert preview["command"]["argv"][:6] == ["conda", "run", "-n", "starvla", "accelerate", "launch"]


def test_root_scoped_cli_emits_the_same_non_executing_preview(tmp_path: Path, capsys):
    recipe = tmp_path / "recipes" / "train" / "starvla.yaml"
    recipe.parent.mkdir(parents=True)
    recipe.write_text(
        "schema_version: rlw.recipe/v1\nprovider: starvla\nkind: train\n"
        "framework: qwen_oft\nnative_config: configs/train.yaml\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--root", str(tmp_path), "provider", "command", "starvla",
            "--recipe", "recipes/train/starvla.yaml", "--environment", "starvla", "--json",
        ]
    )

    import json
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["schema_version"] == "rlw.provider_command_preview/v1"
    assert payload["executed"] is False

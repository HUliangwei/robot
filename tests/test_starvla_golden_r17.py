from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

from workbench.services.golden_path import GoldenPathService
from workbench.services.provider_runtime import configure_provider_runtime
from workbench.storage.catalog import Catalog


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )


def _fixture(root: Path) -> tuple[Path, Path]:
    _git(root, "init")
    _git(root, "config", "user.email", "rlw-test@example.invalid")
    _git(root, "config", "user.name", "RLW Test")
    recipe = root / "recipes" / "train" / "starvla_qwenoft.yaml"
    recipe.parent.mkdir(parents=True)
    recipe.write_text(
        "schema_version: rlw.recipe/v1\n"
        "name: starvla_qwenoft_local\n"
        "question: Can QwenOFT train through RLW?\n"
        "kind: train\n"
        "provider: starvla\n"
        "framework: qwen_oft\n"
        "native_config: configs/train.yaml\n"
        "dataset_id: libero_provider_native\n"
        "num_processes: 1\n"
        "native_overrides:\n  seed: 7\n",
        encoding="utf-8",
    )
    _git(root, "add", ".")
    _git(root, "commit", "-m", "starvla test baseline")

    checkout = root / ".rlw" / "provider-fixture" / "starvla"
    files = {
        "starVLA/__init__.py": "__version__ = 'test'\n",
        "starVLA/training/train_starvla.py": "# fixture\n",
        "starVLA/config/deepseeds/deepspeed_zero2.yaml": "compute_environment: LOCAL_MACHINE\n",
        "configs/train.yaml": "datasets: {}\n",
        "accelerate/__init__.py": "__version__ = 'test'\n",
        "torch.py": "__version__ = 'test'\nclass cuda:\n @staticmethod\n def is_available(): return False\n",
    }
    for relative, content in files.items():
        path = checkout / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    configure_provider_runtime(
        root,
        "starvla",
        python_executable=sys.executable,
        provider_root=checkout,
    )
    return recipe, checkout


def test_starvla_prepare_and_preflight_use_configured_runtime_without_core_changes(tmp_path: Path):
    recipe, checkout = _fixture(tmp_path)

    prepared = GoldenPathService(tmp_path).prepare(
        recipe,
        dataset_revision="e" * 40,
    )

    run_dir = Path(prepared["run_dir"])
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    command = json.loads((run_dir / "resolved_command.json").read_text(encoding="utf-8"))
    run_spec = yaml.safe_load((run_dir / "run.yaml").read_text(encoding="utf-8"))
    dataset = yaml.safe_load(Path(prepared["dataset_manifest"]).read_text(encoding="utf-8"))
    report = GoldenPathService(tmp_path).preflight(prepared["run_id"])
    checks = {item["name"]: item for item in report["checks"]}

    assert manifest["provider"]["name"] == "starvla"
    assert manifest["provider_runtime"]["source"] == "configured"
    assert manifest["provider_runtime"]["provider_root"] == str(checkout.resolve())
    assert run_spec["policy"] == {"provider": "starvla", "architecture": "qwen_oft"}
    assert run_spec["dataset"] == {"dataset_id": "libero_provider_native", "revision": "e" * 40}
    assert dataset["source"] == {
        "provider": "starvla",
        "kind": "provider_native",
        "native_config": "configs/train.yaml",
    }
    assert command["cwd"] == str(checkout.resolve())
    assert command["argv"][:3] == [sys.executable, "-m", "accelerate.commands.launch"]
    output_index = command["argv"].index("--run_root_dir") + 1
    assert Path(command["argv"][output_index]).is_absolute()
    failed = {
        item["name"]: item["detail"]
        for item in report["checks"]
        if item["required"] and not item["ok"]
    }
    assert report["ok"] is True, failed
    assert checks["provider_import"]["ok"] is True
    assert checks["starVLA_import"]["ok"] is True
    assert checks["provider_checkout_valid"]["ok"] is True
    assert checks["provider_native_config_available"]["ok"] is True
    assert checks["dataset_revision_available"] == {
        "name": "dataset_revision_available",
        "ok": True,
        "required": False,
        "detail": {"kind": "provider_native", "provider": "starvla", "native_config": "configs/train.yaml"},
    }


def test_starvla_execute_and_reconcile_register_checkpoint_idempotently(tmp_path: Path):
    recipe, _ = _fixture(tmp_path)
    service = GoldenPathService(tmp_path)
    prepared = service.prepare(recipe, dataset_revision="f" * 40)
    run_dir = Path(prepared["run_dir"])
    output_dir = run_dir / "artifacts" / "training"
    command_path = run_dir / "resolved_command.json"
    command = json.loads(command_path.read_text(encoding="utf-8"))
    script = (
        "from pathlib import Path; "
        f"p=Path({str(output_dir / 'checkpoints' / 'steps_0001_pytorch_model.pt')!r}); "
        "p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(b'checkpoint')"
    )
    command["argv"] = [sys.executable, "-c", script]
    command_path.write_text(json.dumps(command), encoding="utf-8")

    executed = service.execute(prepared["run_id"])
    reconciled = service.discover(prepared["run_id"])

    assert executed["state"] == "SUCCEEDED"
    assert executed["discovered"]["artifacts"] == 1
    assert reconciled["artifacts"] == 1
    catalog = Catalog(tmp_path / ".rlw" / "catalog.sqlite3")
    catalog.rebuild(tmp_path)
    checkpoints = [item for item in catalog.list_records("artifact") if item["kind"] == "checkpoint"]
    assert len(checkpoints) == 1
    assert checkpoints[0]["provider"] == "starvla"
    attempt = json.loads(
        next((run_dir / "jobs" / "train" / "attempts").glob("attempt_*.json")).read_text(encoding="utf-8")
    )
    assert attempt["state"] == "SUCCEEDED"

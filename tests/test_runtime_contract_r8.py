from pathlib import Path

from workbench.cli.main import build_parser
from workbench.services.doctor import run_doctor


def test_cli_exposes_provider_dev_and_run_contract():
    parser = build_parser()
    assert parser.parse_args(["provider", "list"]).provider_command == "list"
    legacy_doctor = parser.parse_args(["provider", "doctor", "lerobot-win"])
    assert legacy_doctor.target == "lerobot-win"
    canonical_doctor = parser.parse_args(
        ["provider", "doctor", "starvla", "--environment", "vla-dev", "--provider-root", "D:/starVLA"]
    )
    assert canonical_doctor.target == "starvla"
    assert canonical_doctor.environment == "vla-dev"
    command = parser.parse_args(
        ["provider", "command", "starvla", "--recipe", "recipes/train/starvla_qwenoft.yaml"]
    )
    assert command.provider == "starvla"
    configure = parser.parse_args(
        ["provider", "configure", "starvla", "--environment", "starvla", "--provider-root", "D:/starVLA"]
    )
    assert configure.provider == "starvla"
    install = parser.parse_args(["provider", "install", "starvla", "--confirm", "starvla"])
    assert install.confirm == "starvla"
    assert parser.parse_args(["dev", "test"]).dev_command == "test"
    prepared = parser.parse_args(
        ["run", "prepare", "pusht-act", "--dataset-revision", "a" * 40]
    )
    assert prepared.workflow == "pusht-act"
    assert prepared.dataset_revision == "a" * 40
    starvla = parser.parse_args(
        ["run", "prepare", "starvla-qwenoft", "--dataset-revision", "c" * 40]
    )
    assert starvla.workflow == "starvla-qwenoft"
    assert starvla.recipe is None
    assert starvla.provider_env is None
    assert parser.parse_args(["run", "reconcile", "run_x"]).run_id == "run_x"


def test_golden_compatibility_parser_keeps_prepare_arguments():
    parser = build_parser()
    args = parser.parse_args(
        ["golden", "prepare", "--dataset-revision", "b" * 40, "--provider-env", "lerobot-win"]
    )
    assert args.golden_command == "prepare"
    assert args.dataset_revision == "b" * 40
    assert args.provider_env == "lerobot-win"


def test_system_doctor_excludes_provider_packages(tmp_path: Path):
    (tmp_path / "workspace").mkdir()
    report = run_doctor(tmp_path)
    assert report["scope"] == "control_plane"
    assert "torch" not in report["checks"]
    assert "lerobot" not in report["checks"]
    assert all("required" in item for item in report["checks"].values())

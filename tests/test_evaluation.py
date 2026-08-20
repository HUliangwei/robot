import json

from workbench.cli.main import main
from workbench.storage.manifests import atomic_write_json


def _write_metric(root, run_id, metric_id, name, value, direction):
    atomic_write_json(
        root / "runs" / run_id / "records" / "metrics" / metric_id / "metric.json",
        {
            "schema_version": "rlw.metric_record/v1",
            "metric_id": metric_id,
            "run_id": run_id,
            "name": name,
            "namespace": "pusht",
            "scope": "task",
            "unit": "ratio" if name == "success_rate" else "ms",
            "direction": direction,
            "aggregation": "mean",
            "definition_version": "pusht/v1",
            "value": value,
        },
    )


def _write_comparison_fixture(root):
    _write_metric(root, "run_a", "metric_a_success", "success_rate", 0.75, "higher_is_better")
    _write_metric(root, "run_b", "metric_b_success", "success_rate", 0.9, "higher_is_better")
    _write_metric(root, "run_a", "metric_a_latency", "latency", 10.0, "lower_is_better")
    _write_metric(root, "run_b", "metric_b_latency", "latency", 12.0, "lower_is_better")


def test_cli_compares_metric_records_across_runs(tmp_path, capsys):
    _write_comparison_fixture(tmp_path)

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "evaluation",
            "compare",
            "run_a",
            "run_b",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "rlw.metric_comparison/v1"
    assert payload["run_ids"] == ["run_a", "run_b"]
    rows = {row["name"]: row for row in payload["rows"]}
    assert rows["success_rate"]["values"] == {"run_a": 0.75, "run_b": 0.9}
    assert rows["success_rate"]["best_run_ids"] == ["run_b"]
    assert rows["latency"]["values"] == {"run_a": 10.0, "run_b": 12.0}
    assert rows["latency"]["best_run_ids"] == ["run_a"]

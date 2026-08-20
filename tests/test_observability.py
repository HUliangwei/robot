import json
from pathlib import Path

import pytest

from workbench.services.observability import (
    LifecycleEventWriter,
    RunObservabilityService,
    read_lifecycle_events,
)
from workbench.storage.manifests import atomic_write_json


def test_lifecycle_event_writer_deduplicates_retried_facts(tmp_path: Path):
    writer = LifecycleEventWriter(tmp_path, "run_test")

    first = writer.emit(
        "RunCreated",
        occurred_at="2026-08-21T00:00:00+00:00",
        dedupe_key="RunCreated:run_test",
        payload={"status": "READY"},
    )
    again = writer.emit(
        "RunCreated",
        occurred_at="2026-08-21T00:01:00+00:00",
        dedupe_key="RunCreated:run_test",
        payload={"status": "IGNORED"},
    )

    events = read_lifecycle_events(tmp_path / "runs" / "run_test" / "events.jsonl")
    assert events == [first]
    assert again == first
    assert events[0]["schema_version"] == "rlw.lifecycle_event/v1"
    assert events[0]["payload"] == {"status": "READY"}


def test_lifecycle_event_reader_keeps_valid_facts_before_a_torn_tail(tmp_path: Path):
    path = tmp_path / "events.jsonl"
    valid = {
        "schema_version": "rlw.lifecycle_event/v1",
        "event_id": "event_one",
        "event_type": "JobCreated",
        "occurred_at": "2026-08-21T00:00:00+00:00",
        "run_id": "run_one",
        "payload": {},
    }
    path.write_text(json.dumps(valid) + "\n{\"event_id\":", encoding="utf-8")

    assert read_lifecycle_events(path) == [valid]


def _failed_run_fixture(root: Path) -> str:
    run_id = "run_detail"
    job_id = "job_detail"
    attempt_id = "attempt_detail"
    run_dir = root / "runs" / run_id
    job_dir = run_dir / "jobs" / "train"
    runtime_dir = root / ".rlw" / "state" / "jobs" / job_id / attempt_id
    runtime_dir.mkdir(parents=True)
    stdout = "first\nsecond\nthird\nfourth\n"
    stderr = "provider exploded\n"
    (runtime_dir / "stdout.log").write_text(stdout, encoding="utf-8")
    (runtime_dir / "stderr.log").write_text(stderr, encoding="utf-8")
    atomic_write_json(
        run_dir / "manifest.json",
        {
            "schema_version": "rlw.run_manifest/v1",
            "run_id": run_id,
            "status": "FAILED",
        },
    )
    atomic_write_json(
        job_dir / "job.json",
        {
            "schema_version": "rlw.job/v1",
            "job_id": job_id,
            "run_id": run_id,
            "kind": "train",
            "state": "FAILED",
        },
    )
    atomic_write_json(
        job_dir / "attempts" / f"{attempt_id}.json",
        {
            "schema_version": "rlw.execution_attempt/v1",
            "attempt_id": attempt_id,
            "job_id": job_id,
            "state": "FAILED",
            "exit_code": 7,
            "stdout_path": f".rlw/state/jobs/{job_id}/{attempt_id}/stdout.log",
            "stderr_path": f".rlw/state/jobs/{job_id}/{attempt_id}/stderr.log",
        },
    )
    atomic_write_json(
        run_dir / "records" / "artifacts" / "artifact_one" / "artifact.json",
        {
            "schema_version": "rlw.artifact/v1",
            "artifact_id": "artifact_one",
            "kind": "checkpoint",
            "producer_run": run_id,
        },
    )
    atomic_write_json(
        run_dir / "records" / "metrics" / "metric_one" / "metric.json",
        {
            "schema_version": "rlw.metric_record/v1",
            "metric_id": "metric_one",
            "run_id": run_id,
            "name": "success_rate",
            "value": 0.25,
        },
    )
    LifecycleEventWriter(root, run_id).emit(
        "AttemptFailed",
        job_id=job_id,
        attempt_id=attempt_id,
        dedupe_key=f"AttemptFailed:{attempt_id}",
    )
    return run_id


def test_run_observability_aggregates_records_logs_and_failure_guidance(tmp_path: Path):
    run_id = _failed_run_fixture(tmp_path)

    detail = RunObservabilityService(tmp_path).inspect(run_id, log_tail_lines=2)

    attempt = detail["jobs"][0]["attempts"][0]
    assert detail["schema_version"] == "rlw.run_observability/v1"
    assert detail["run"]["status"] == "FAILED"
    assert attempt["logs"]["stdout"]["tail"] == ["third", "fourth"]
    assert attempt["logs"]["stdout"]["truncated"] is True
    assert attempt["logs"]["stderr"]["tail"] == ["provider exploded"]
    assert attempt["failure"] == {
        "category": "ExecutionError",
        "reason": "Command exited with code 7.",
        "retriable": False,
        "recommended_action": (
            "Inspect stdout and stderr, correct the command or provider input, then retry."
        ),
    }
    assert [item["artifact_id"] for item in detail["artifacts"]] == ["artifact_one"]
    assert [item["metric_id"] for item in detail["metrics"]] == ["metric_one"]
    assert [item["event_type"] for item in detail["events"]] == ["AttemptFailed"]
    assert detail["summary"] == {
        "jobs": 1,
        "attempts": 1,
        "artifacts": 1,
        "metrics": 1,
        "events": 1,
        "failures": 1,
        "latest_event_type": "AttemptFailed",
    }


def test_run_observability_rejects_log_paths_outside_the_project(tmp_path: Path):
    run_id = _failed_run_fixture(tmp_path)
    attempt_path = (
        tmp_path
        / "runs"
        / run_id
        / "jobs"
        / "train"
        / "attempts"
        / "attempt_detail.json"
    )
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    attempt["stdout_path"] = str(tmp_path.parent / "outside-secret.log")
    atomic_write_json(attempt_path, attempt)

    log = RunObservabilityService(tmp_path).inspect(run_id)["jobs"][0]["attempts"][0][
        "logs"
    ]["stdout"]

    assert log["exists"] is False
    assert log["tail"] == []
    assert log["error"] == "log path is outside project root"


def test_run_observability_rejects_unsafe_or_missing_run_ids(tmp_path: Path):
    service = RunObservabilityService(tmp_path)

    with pytest.raises(ValueError, match="invalid Run ID"):
        service.inspect("../outside")
    with pytest.raises(FileNotFoundError, match="does not exist"):
        service.inspect("run_missing")


def test_run_observability_keeps_pre_r9_embedded_jobs_visible(tmp_path: Path):
    atomic_write_json(
        tmp_path / "runs" / "run_legacy" / "manifest.json",
        {
            "schema_version": "rlw.run_manifest/v1",
            "run_id": "run_legacy",
            "status": "READY",
            "job": {
                "schema_version": "rlw.job/v1",
                "job_id": "job_embedded",
                "run_id": "run_legacy",
                "kind": "train",
                "state": "READY",
            },
        },
    )

    detail = RunObservabilityService(tmp_path).inspect("run_legacy")

    assert detail["jobs"] == [
        {
            "job": {
                "schema_version": "rlw.job/v1",
                "job_id": "job_embedded",
                "run_id": "run_legacy",
                "kind": "train",
                "state": "READY",
            },
            "attempts": [],
        }
    ]
    assert detail["summary"]["jobs"] == 1

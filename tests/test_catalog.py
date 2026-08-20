from pathlib import Path
from workbench.storage.catalog import Catalog
from workbench.storage.manifests import atomic_write_json

def test_catalog_rebuild_reads_run_and_dataset_manifests(tmp_path: Path):
    (tmp_path/"runs"/"demo"/"run_1").mkdir(parents=True)
    atomic_write_json(tmp_path/"runs"/"demo"/"run_1"/"manifest.json",
                      {"schema_version":"rlw.run_manifest/v1","run_id":"run_1","status":"SUCCEEDED"})
    (tmp_path/"datasets"/"pusht").mkdir(parents=True)
    (tmp_path/"datasets"/"pusht"/"dataset.yaml").write_text(
        "schema_version: rlw.dataset_manifest/v1\ndataset_id: ds_pusht\nrevision: rev_1\n", encoding="utf-8")
    catalog=Catalog(tmp_path/".rlw"/"catalog.sqlite3")
    summary=catalog.rebuild(tmp_path)
    assert summary == {"run":1,"dataset":1,"artifact":0,"metric":0,"job":0,"attempt":0}
    assert catalog.count("run")==1
    assert catalog.count("dataset")==1


def test_catalog_rebuild_indexes_durable_jobs_and_attempts(tmp_path: Path):
    job_root = tmp_path / "runs" / "run_1" / "jobs" / "train"
    atomic_write_json(
        job_root / "job.json",
        {
            "schema_version": "rlw.job/v1",
            "job_id": "job_1",
            "run_id": "run_1",
            "kind": "train",
            "state": "SUCCEEDED",
        },
    )
    atomic_write_json(
        job_root / "attempts" / "attempt_1.json",
        {
            "schema_version": "rlw.execution_attempt/v1",
            "attempt_id": "attempt_1",
            "job_id": "job_1",
            "state": "SUCCEEDED",
            "exit_code": 0,
        },
    )

    catalog = Catalog(tmp_path / ".rlw" / "catalog.sqlite3")
    summary = catalog.rebuild(tmp_path)

    assert summary.get("job") == 1
    assert summary.get("attempt") == 1
    assert catalog.list_records("job")[0]["job_id"] == "job_1"
    assert catalog.list_records("attempt")[0]["attempt_id"] == "attempt_1"

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
    assert summary == {"run":1,"dataset":1,"artifact":0,"metric":0}
    assert catalog.count("run")==1
    assert catalog.count("dataset")==1

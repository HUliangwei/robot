"""Shared MetricRecord comparison for CLI, API, and GUI."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from workbench.storage.catalog import Catalog


_IDENTITY_FIELDS = (
    "namespace",
    "name",
    "scope",
    "unit",
    "direction",
    "aggregation",
    "definition_version",
)


def compare_metric_records(
    records: Iterable[dict[str, Any]],
    run_ids: Iterable[str],
) -> dict[str, Any]:
    selected = list(dict.fromkeys(str(run_id) for run_id in run_ids))
    if len(selected) < 2:
        raise ValueError("compare requires at least two distinct Run IDs")

    selected_set = set(selected)
    grouped: dict[tuple[str, ...], dict[str, float]] = defaultdict(dict)
    for record in records:
        run_id = str(record.get("run_id") or "")
        value = record.get("value")
        if run_id not in selected_set or isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        identity = tuple(str(record.get(field) or "") for field in _IDENTITY_FIELDS)
        grouped[identity].setdefault(run_id, float(value))

    rows = []
    for identity, observed in grouped.items():
        metadata = dict(zip(_IDENTITY_FIELDS, identity))
        values = {run_id: observed.get(run_id) for run_id in selected}
        candidates = {run_id: value for run_id, value in values.items() if value is not None}
        direction = metadata["direction"]
        best_run_ids: list[str] = []
        if candidates and direction in {"higher_is_better", "lower_is_better"}:
            best_value = (
                max(candidates.values())
                if direction == "higher_is_better"
                else min(candidates.values())
            )
            best_run_ids = [
                run_id for run_id in selected if candidates.get(run_id) == best_value
            ]
        rows.append(
            {
                "metric_key": "/".join(
                    (
                        metadata["namespace"] or "rlw",
                        metadata["name"],
                        metadata["scope"] or "global",
                        metadata["definition_version"] or "unversioned",
                    )
                ),
                **metadata,
                "values": values,
                "best_run_ids": best_run_ids,
            }
        )

    rows.sort(key=lambda row: row["metric_key"])
    return {
        "schema_version": "rlw.metric_comparison/v1",
        "run_ids": selected,
        "rows": rows,
    }


def compare_catalog_metrics(catalog: Catalog, run_ids: Iterable[str]) -> dict[str, Any]:
    return compare_metric_records(catalog.list_records("metric", limit=10_000), run_ids)

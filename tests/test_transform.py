from __future__ import annotations

from typing import Any

from lineage_syncer.commons.models import LineageMapping
from lineage_syncer.services.transform import (
    DatabricksCoordinate,
    _build_datasource_index,
    _parse_databricks_coordinate,
    normalize_pbi_scan_result,
)

DBX_CONNECTION = {"server": "adb-123.azuredatabricks.net", "database": "gold.finance"}


def _scan_result(
    *,
    reports: list[dict[str, Any]] | None = None,
    datasets: list[dict[str, Any]] | None = None,
    instances: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a minimal scan_result dict for a single workspace."""
    return {
        "workspaces": [
            {
                "id": "ws-1",
                "name": "Finance",
                "reports": reports or [],
                "datasets": datasets or [],
            }
        ],
        "datasourceInstances": instances or [],
    }


def _dbx_dataset(dataset_id: str = "ds-1") -> dict[str, Any]:
    """A Databricks-backed dataset with one table and endorsement."""
    return {
        "id": dataset_id,
        "name": "finance_model",
        "contentProviderType": "PbixInImportMode",
        "targetStorageMode": "Abf",
        "endorsementDetails": {"endorsement": "Certified"},
        "datasourceUsages": [{"datasourceInstanceId": "dsi-1"}],
        "tables": [
            {"name": "revenue", "columns": [{"name": "amount"}, {"name": "region"}]}
        ],
    }


def _dbx_instance() -> dict[str, Any]:
    return {"datasourceInstanceId": "dsi-1", "connectionDetails": dict(DBX_CONNECTION)}


# --- _build_datasource_index ---


def test_build_datasource_index_keys_by_instance_id() -> None:
    instances = [
        {"datasourceInstanceId": "dsi-1", "connectionDetails": {}},
        {"datasourceInstanceId": "dsi-2", "connectionDetails": {}},
        {"connectionDetails": {}},  # missing id -> excluded
    ]
    index = _build_datasource_index(instances)
    assert set(index) == {"dsi-1", "dsi-2"}


# --- _parse_databricks_coordinate ---


def test_parse_coordinate_database_catalog_schema() -> None:
    coord = _parse_databricks_coordinate(
        {"server": "adb-1.azuredatabricks.net", "database": "gold.finance"},
        "revenue",
    )
    assert coord == DatabricksCoordinate("gold", "finance", "revenue")


def test_parse_coordinate_database_catalog_only() -> None:
    coord = _parse_databricks_coordinate(
        {"server": "adb-1.azuredatabricks.net", "database": "gold"},
        "finance.revenue",
    )
    assert coord == DatabricksCoordinate("gold", "finance", "revenue")


def test_parse_coordinate_three_part_table_no_database() -> None:
    coord = _parse_databricks_coordinate(
        {"server": "adb-1.azuredatabricks.net"},
        "gold.finance.revenue",
    )
    assert coord == DatabricksCoordinate("gold", "finance", "revenue")


def test_parse_coordinate_strips_backticks_and_spaces() -> None:
    coord = _parse_databricks_coordinate(
        {"server": "dbc-abc.cloud.databricks.com", "database": "gold"},
        "`finance`.`revenue table`",
    )
    assert coord == DatabricksCoordinate("gold", "finance", "revenue table")


def test_parse_coordinate_non_databricks_returns_none() -> None:
    coord = _parse_databricks_coordinate(
        {"server": "myserver.database.windows.net", "database": "gold.finance"},
        "revenue",
    )
    assert coord is None


def test_parse_coordinate_extension_path_host() -> None:
    coord = _parse_databricks_coordinate(
        {
            "extensionDataSourcePath": (
                '{"host": "adb-9.azuredatabricks.net", "httpPath": "/sql/1.0/wh"}'
            ),
            "database": "gold.finance",
        },
        "revenue",
    )
    assert coord == DatabricksCoordinate("gold", "finance", "revenue")


# --- normalize_pbi_scan_result ---


def test_normalize_report_dataset_table_happy_path() -> None:
    scan = _scan_result(
        reports=[
            {
                "id": "rep-1",
                "name": "Q3 Revenue",
                "datasetId": "ds-1",
            }
        ],
        datasets=[_dbx_dataset()],
        instances=[_dbx_instance()],
    )
    mappings = normalize_pbi_scan_result(scan)
    assert len(mappings) == 1
    mapping = mappings[0]
    assert isinstance(mapping, LineageMapping)
    assert mapping.pbi_report_id == "rep-1"
    assert mapping.databricks_catalog == "gold"
    assert mapping.databricks_schema == "finance"
    assert mapping.databricks_table == "revenue"
    assert mapping.connection_mode == "PbixInImportMode"
    assert mapping.storage_mode == "Abf"
    assert mapping.columns == ["amount", "region"]


def test_normalize_orphan_dataset_without_report() -> None:
    scan = _scan_result(
        reports=[],
        datasets=[_dbx_dataset()],
        instances=[_dbx_instance()],
    )
    mappings = normalize_pbi_scan_result(scan)
    assert len(mappings) == 1
    # Orphan dataset uses the dataset id/name as the report identity
    assert mappings[0].pbi_report_id == "ds-1"
    assert mappings[0].pbi_dataset_id == "ds-1"


def test_normalize_report_missing_dataset_id_skipped() -> None:
    scan = _scan_result(
        reports=[{"id": "rep-1", "name": "No Dataset"}],
        datasets=[],
        instances=[_dbx_instance()],
    )
    assert normalize_pbi_scan_result(scan) == []


def test_normalize_report_unknown_dataset_skipped() -> None:
    scan = _scan_result(
        reports=[{"id": "rep-1", "name": "R", "datasetId": "missing"}],
        datasets=[_dbx_dataset()],
        instances=[_dbx_instance()],
    )
    # Report references unknown dataset; ds-1 still emitted as orphan
    mappings = normalize_pbi_scan_result(scan)
    assert len(mappings) == 1
    assert mappings[0].pbi_report_id == "ds-1"


def test_normalize_dataset_without_endorsement_skipped() -> None:
    dataset = _dbx_dataset()
    del dataset["endorsementDetails"]
    scan = _scan_result(
        reports=[{"id": "rep-1", "name": "R", "datasetId": "ds-1"}],
        datasets=[dataset],
        instances=[_dbx_instance()],
    )
    assert normalize_pbi_scan_result(scan) == []


def test_normalize_unknown_datasource_instance_skipped() -> None:
    dataset = _dbx_dataset()
    dataset["datasourceUsages"] = [{"datasourceInstanceId": "does-not-exist"}]
    scan = _scan_result(
        reports=[{"id": "rep-1", "name": "R", "datasetId": "ds-1"}],
        datasets=[dataset],
        instances=[_dbx_instance()],
    )
    assert normalize_pbi_scan_result(scan) == []


def test_normalize_non_databricks_datasource_skipped() -> None:
    scan = _scan_result(
        reports=[{"id": "rep-1", "name": "R", "datasetId": "ds-1"}],
        datasets=[_dbx_dataset()],
        instances=[
            {
                "datasourceInstanceId": "dsi-1",
                "connectionDetails": {
                    "server": "myserver.database.windows.net",
                    "database": "gold.finance",
                },
            }
        ],
    )
    assert normalize_pbi_scan_result(scan) == []

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from defensive_lineage.commons.models import LineageMapping
from defensive_lineage.services.transform import (
    _build_datasource_index,
    _parse_databricks_coordinate,
    normalize_pbi_scan_result,
)


@pytest.fixture
def scan_result_fixture() -> dict[str, Any]:
    """Load the expanded scan_result.json fixture."""
    fixture_path = Path(__file__).parent / "fixtures" / "scan_result.json"
    with open(fixture_path, encoding="utf-8") as f:
        result: dict[str, Any] = json.load(f)
        return result


@pytest.fixture
def minimal_scan_result() -> dict[str, Any]:
    """Create a minimal valid scan result for testing."""
    return {
        "workspaces": [
            {
                "id": "ws-1",
                "name": "TestWorkspace",
                "reports": [
                    {
                        "id": "rep-1",
                        "name": "Test Report",
                        "datasetId": "ds-1",
                        "endorsementDetails": {"endorsement": "Certified"},
                    }
                ],
                "datasets": [
                    {
                        "id": "ds-1",
                        "name": "TestDataset",
                        "endorsementDetails": {"endorsement": "Certified"},
                        "targetStorageMode": "DirectQuery",
                        "datasourceUsages": [
                            {"datasourceInstanceId": "dsi-1"}
                        ],
                        "tables": [
                            {
                                "name": "test_table",
                                "columns": [{"name": "col1"}, {"name": "col2"}],
                            }
                        ],
                    }
                ],
            }
        ],
        "datasourceInstances": [
            {
                "datasourceInstanceId": "dsi-1",
                "datasourceType": "Sql",
                "connectionDetails": {
                    "server": "adb-123.1.azuredatabricks.net",
                    "database": "gold",
                },
            }
        ],
    }


def test_normalize_produces_correct_mappings(
    scan_result_fixture: dict[str, Any]
) -> None:
    """Test that full fixture produces correct count and field values."""
    mappings = normalize_pbi_scan_result(scan_result_fixture)

    # Should produce mappings for:
    # - rep-1 (Certified) → ds-1 (Certified) → 2 tables (revenue, costs)
    # - rep-2 (Promoted) → ds-2 (Promoted) → 1 table (finance.expenses)
    # - rep-3 (Certified) → ds-3 (Certified) → 1 table (opportunities)
    # Total: 4 mappings
    assert len(mappings) == 4

    # Check first mapping details
    first = mappings[0]
    assert first.pbi_workspace_name == "FinanceWorkspace"
    assert first.pbi_report_name == "Q3 Revenue Report"
    assert first.pbi_dataset_name == "finance_model"
    assert first.endorsement == "Certified"
    assert first.connection_mode == "PbixInDirectQueryMode"
    assert first.databricks_catalog == "gold"
    assert first.columns == ["amount", "region", "quarter"]


def test_normalize_skips_unendorsed_datasets(
    minimal_scan_result: dict[str, Any],
) -> None:
    """Test that datasets without endorsement are not in output."""
    # Add unendorsed dataset
    minimal_scan_result["workspaces"][0]["datasets"].append(
        {
            "id": "ds-unendorsed",
            "name": "UnendorsedDataset",
            "targetStorageMode": "Import",
            "datasourceUsages": [{"datasourceInstanceId": "dsi-1"}],
            "tables": [{"name": "test_table", "columns": [{"name": "col1"}]}],
        }
    )
    # Add report referencing it
    minimal_scan_result["workspaces"][0]["reports"].append(
        {
            "id": "rep-unendorsed",
            "name": "Unendorsed Report",
            "datasetId": "ds-unendorsed",
        }
    )

    mappings = normalize_pbi_scan_result(minimal_scan_result)

    # Should only have the original certified mapping
    assert len(mappings) == 1
    assert mappings[0].pbi_dataset_id == "ds-1"


def test_normalize_handles_multi_table_dataset(
    minimal_scan_result: dict[str, Any],
) -> None:
    """Test that dataset with 3 tables produces 3 mappings per report."""
    # Add two more tables to the dataset
    minimal_scan_result["workspaces"][0]["datasets"][0]["tables"].extend(
        [
            {"name": "table2", "columns": [{"name": "col3"}]},
            {"name": "table3", "columns": [{"name": "col4"}]},
        ]
    )

    mappings = normalize_pbi_scan_result(minimal_scan_result)

    # Should have 3 mappings (one per table)
    assert len(mappings) == 3
    table_names = {m.databricks_table for m in mappings}
    assert table_names == {"test_table", "table2", "table3"}


def test_normalize_handles_missing_datasource(
    minimal_scan_result: dict[str, Any],
) -> None:
    """Test that dataset with unknown datasourceInstanceId is skipped."""
    # Change datasource usage to reference non-existent instance
    minimal_scan_result["workspaces"][0]["datasets"][0]["datasourceUsages"][0][
        "datasourceInstanceId"
    ] = "non-existent-dsi"

    mappings = normalize_pbi_scan_result(minimal_scan_result)

    # Should produce no mappings since datasource can't be resolved
    assert len(mappings) == 0


def test_normalize_handles_empty_columns(minimal_scan_result: dict[str, Any]) -> None:
    """Test that table with no columns produces columns: []."""
    # Set empty columns
    minimal_scan_result["workspaces"][0]["datasets"][0]["tables"][0][
        "columns"
    ] = []

    mappings = normalize_pbi_scan_result(minimal_scan_result)

    assert len(mappings) == 1
    assert mappings[0].columns == []


def test_normalize_handles_empty_input() -> None:
    """Test that empty workspaces produces []."""
    empty_result: dict[str, Any] = {
        "workspaces": [],
        "datasourceInstances": [],
    }
    mappings = normalize_pbi_scan_result(empty_result)
    assert mappings == []


def test_normalize_handles_dataset_without_datasource_usages(
    minimal_scan_result: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    """Test that dataset with no datasourceUsages logs warning and skips."""
    caplog.set_level(logging.WARNING)

    # Remove datasource usages
    minimal_scan_result["workspaces"][0]["datasets"][0]["datasourceUsages"] = []

    mappings = normalize_pbi_scan_result(minimal_scan_result)

    assert len(mappings) == 0
    assert "has no datasourceUsages" in caplog.text


def test_parse_coordinate_catalog_only() -> None:
    """Test database="gold" → catalog=gold, schema=default."""
    conn_details = {"server": "adb-123.1.azuredatabricks.net", "database": "gold"}

    result = _parse_databricks_coordinate(conn_details, "revenue")

    assert result is not None
    assert result.catalog == "gold"
    assert result.schema == "default"
    assert result.table == "revenue"


def test_parse_coordinate_catalog_dot_schema() -> None:
    """Test database="gold.finance" → splits correctly."""
    conn_details = {
        "server": "adb-123.1.azuredatabricks.net",
        "database": "gold.finance",
    }

    result = _parse_databricks_coordinate(conn_details, "revenue")

    assert result is not None
    assert result.catalog == "gold"
    assert result.schema == "finance"
    assert result.table == "revenue"


def test_parse_coordinate_table_with_schema() -> None:
    """Test table="finance.revenue" → splits correctly."""
    conn_details = {"server": "adb-123.1.azuredatabricks.net", "database": "gold"}

    result = _parse_databricks_coordinate(conn_details, "finance.revenue")

    assert result is not None
    assert result.catalog == "gold"
    assert result.schema == "finance"
    assert result.table == "revenue"


def test_parse_coordinate_both_have_schema() -> None:
    """Test when both database and table have schema - table wins."""
    conn_details = {
        "server": "adb-123.1.azuredatabricks.net",
        "database": "gold.db_schema",
    }

    result = _parse_databricks_coordinate(conn_details, "table_schema.revenue")

    assert result is not None
    assert result.catalog == "gold"
    assert result.schema == "table_schema"
    assert result.table == "revenue"


def test_parse_coordinate_non_databricks() -> None:
    """Test non-Databricks server → returns None."""
    conn_details = {"server": "some-sql-server.database.windows.net", "database": "db"}

    result = _parse_databricks_coordinate(conn_details, "table")

    assert result is None


def test_parse_coordinate_missing_database() -> None:
    """Test missing database → returns None."""
    conn_details = {"server": "adb-123.1.azuredatabricks.net"}

    result = _parse_databricks_coordinate(conn_details, "table")

    assert result is None


def test_parse_coordinate_unexpected_database_format(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test database with too many dots → returns None and logs warning."""
    caplog.set_level(logging.WARNING)
    conn_details = {
        "server": "adb-123.1.azuredatabricks.net",
        "database": "a.b.c.d",
    }

    result = _parse_databricks_coordinate(conn_details, "table")

    assert result is None
    assert "Unexpected database format" in caplog.text


def test_datasource_index_builds_correctly() -> None:
    """Test that list of instances produces correct lookup dict."""
    instances = [
        {
            "datasourceInstanceId": "dsi-1",
            "datasourceType": "Sql",
            "connectionDetails": {"server": "server1", "database": "db1"},
        },
        {
            "datasourceInstanceId": "dsi-2",
            "datasourceType": "Sql",
            "connectionDetails": {"server": "server2", "database": "db2"},
        },
    ]

    index = _build_datasource_index(instances)

    assert len(index) == 2
    assert "dsi-1" in index
    assert "dsi-2" in index
    assert index["dsi-1"]["connectionDetails"]["server"] == "server1"


def test_datasource_index_empty_input() -> None:
    """Test empty input → returns {}."""
    index = _build_datasource_index([])
    assert index == {}


def test_datasource_index_skips_missing_id() -> None:
    """Test that instances without datasourceInstanceId are skipped."""
    instances: list[dict[str, Any]] = [
        {"datasourceType": "Sql", "connectionDetails": {}},
        {"datasourceInstanceId": "dsi-1", "datasourceType": "Sql"},
    ]

    index = _build_datasource_index(instances)

    assert len(index) == 1
    assert "dsi-1" in index


def test_datasource_index_duplicate_ids(caplog: pytest.LogCaptureFixture) -> None:
    """Test duplicate IDs → last wins with warning."""
    caplog.set_level(logging.WARNING)
    instances = [
        {
            "datasourceInstanceId": "dsi-1",
            "datasourceType": "Sql",
            "connectionDetails": {"server": "first"},
        },
        {
            "datasourceInstanceId": "dsi-1",
            "datasourceType": "Sql",
            "connectionDetails": {"server": "second"},
        },
    ]

    index = _build_datasource_index(instances)

    assert len(index) == 1
    assert index["dsi-1"]["connectionDetails"]["server"] == "second"
    assert "Duplicate datasourceInstanceId" in caplog.text


def test_lineage_mapping_frozen() -> None:
    """Test that attempting to modify field raises error."""
    mapping = LineageMapping(
        pbi_workspace_id="ws-1",
        pbi_workspace_name="Test",
        pbi_report_id="rep-1",
        pbi_report_name="Test Report",
        pbi_dataset_id="ds-1",
        pbi_dataset_name="Test Dataset",
        endorsement="Certified",
        connection_mode="DirectQuery",
        storage_mode="DirectQuery",
        databricks_catalog="gold",
        databricks_schema="default",
        databricks_table="test_table",
        columns=["col1"],
    )

    # frozen=True raises ValidationError on mutation
    with pytest.raises(ValidationError):
        mapping.pbi_workspace_id = "new-id"


def test_lineage_mapping_invalid_endorsement() -> None:
    """Test that invalid endorsement value raises validation error."""
    with pytest.raises(ValueError):  # pydantic.ValidationError wraps as ValueError
        LineageMapping(
            pbi_workspace_id="ws-1",
            pbi_workspace_name="Test",
            pbi_report_id="rep-1",
            pbi_report_name="Test Report",
            pbi_dataset_id="ds-1",
            pbi_dataset_name="Test Dataset",
            endorsement="InvalidEndorsement",  # Invalid value
            connection_mode="DirectQuery",
            storage_mode="DirectQuery",
            databricks_catalog="gold",
            databricks_schema="default",
            databricks_table="test_table",
            columns=["col1"],
        )


def test_lineage_mapping_valid_endorsements() -> None:
    """Test that both 'Certified' and 'Promoted' are accepted."""
    # Certified
    mapping1 = LineageMapping(
        pbi_workspace_id="ws-1",
        pbi_workspace_name="Test",
        pbi_report_id="rep-1",
        pbi_report_name="Test Report",
        pbi_dataset_id="ds-1",
        pbi_dataset_name="Test Dataset",
        endorsement="Certified",
        connection_mode="DirectQuery",
        storage_mode="DirectQuery",
        databricks_catalog="gold",
        databricks_schema="default",
        databricks_table="test_table",
        columns=["col1"],
    )
    assert mapping1.endorsement == "Certified"

    # Promoted
    mapping2 = LineageMapping(
        pbi_workspace_id="ws-2",
        pbi_workspace_name="Test2",
        pbi_report_id="rep-2",
        pbi_report_name="Test Report 2",
        pbi_dataset_id="ds-2",
        pbi_dataset_name="Test Dataset 2",
        endorsement="Promoted",
        connection_mode="Import",
        storage_mode="Abf",
        databricks_catalog="silver",
        databricks_schema="schema2",
        databricks_table="table2",
        columns=[],
    )
    assert mapping2.endorsement == "Promoted"


def test_connection_mode_directquery(minimal_scan_result: dict[str, Any]) -> None:
    """Test that DirectQuery mode is detected from contentProviderType."""
    minimal_scan_result["workspaces"][0]["datasets"][0][
        "contentProviderType"
    ] = "PbixInDirectQueryMode"

    mappings = normalize_pbi_scan_result(minimal_scan_result)

    assert len(mappings) == 1
    assert mappings[0].connection_mode == "PbixInDirectQueryMode"


def test_connection_mode_unknown(minimal_scan_result: dict[str, Any]) -> None:
    """Test that missing contentProviderType defaults to Unknown."""
    # Remove contentProviderType to test default
    if "contentProviderType" in minimal_scan_result["workspaces"][0]["datasets"][0]:
        del minimal_scan_result["workspaces"][0]["datasets"][0]["contentProviderType"]

    mappings = normalize_pbi_scan_result(minimal_scan_result)

    assert len(mappings) == 1
    assert mappings[0].connection_mode == "Unknown"


def test_cross_workspace_dataset_reference() -> None:
    """Test that report can reference dataset in different workspace."""
    scan_result = {
        "workspaces": [
            {
                "id": "ws-1",
                "name": "ReportsWorkspace",
                "reports": [
                    {
                        "id": "rep-1",
                        "name": "Cross-Workspace Report",
                        "datasetId": "ds-external",
                        "datasetWorkspaceId": "ws-2",
                        "endorsementDetails": {"endorsement": "Certified"},
                    }
                ],
                "datasets": [],
            },
            {
                "id": "ws-2",
                "name": "DataWorkspace",
                "reports": [],
                "datasets": [
                    {
                        "id": "ds-external",
                        "name": "ExternalDataset",
                        "endorsementDetails": {"endorsement": "Certified"},
                        "targetStorageMode": "DirectQuery",
                        "datasourceUsages": [{"datasourceInstanceId": "dsi-1"}],
                        "tables": [
                            {"name": "ext_table", "columns": [{"name": "col1"}]}
                        ],
                    }
                ],
            },
        ],
        "datasourceInstances": [
            {
                "datasourceInstanceId": "dsi-1",
                "datasourceType": "Sql",
                "connectionDetails": {
                    "server": "adb-123.1.azuredatabricks.net",
                    "database": "gold",
                },
            }
        ],
    }

    mappings = normalize_pbi_scan_result(scan_result)

    assert len(mappings) == 1
    assert mappings[0].pbi_workspace_id == "ws-2"  # Dataset's workspace
    assert mappings[0].pbi_workspace_name == "DataWorkspace"
    assert mappings[0].pbi_report_id == "rep-1"


def test_parse_coordinate_table_with_too_many_dots(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test table name with >2 dot segments returns None and logs warning."""
    caplog.set_level(logging.WARNING)
    conn_details = {
        "server": "adb-123.1.azuredatabricks.net",
        "database": "gold",
    }

    result = _parse_databricks_coordinate(conn_details, "a.b.c.d")

    assert result is None
    assert "Unexpected table name format" in caplog.text


def test_report_without_dataset_id_logs_warning(
    minimal_scan_result: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    """Test that report without datasetId is skipped with warning."""
    caplog.set_level(logging.WARNING)
    # Add report without datasetId
    minimal_scan_result["workspaces"][0]["reports"].append(
        {
            "id": "rep-no-ds",
            "name": "Orphan Report",
            # No datasetId field
        }
    )

    mappings = normalize_pbi_scan_result(minimal_scan_result)

    # Should still have 1 mapping from the original report
    assert len(mappings) == 1
    assert "has no datasetId" in caplog.text


def test_dataset_without_report_produces_lineage(
    minimal_scan_result: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    """Test that endorsed datasets without reports still produce lineage."""
    caplog.set_level(logging.INFO)
    # Remove all reports - dataset becomes "orphan"
    minimal_scan_result["workspaces"][0]["reports"] = []

    mappings = normalize_pbi_scan_result(minimal_scan_result)

    # Should still produce 1 mapping from the orphan dataset
    assert len(mappings) == 1
    assert mappings[0].pbi_dataset_id == "ds-1"
    assert mappings[0].pbi_report_id == "ds-1"  # Uses dataset ID as report ID
    assert mappings[0].pbi_report_name == "TestDataset"  # Uses dataset name
    assert "Processing dataset" in caplog.text


def test_cross_workspace_dataset_not_found(
    minimal_scan_result: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    """Test that report referencing non-existent dataset logs warning.

    When a report references a non-existent dataset, the report is skipped
    but the actual dataset in the workspace (if any) is still processed
    as an orphan dataset.
    """
    caplog.set_level(logging.WARNING)
    # Change report to reference non-existent dataset
    minimal_scan_result["workspaces"][0]["reports"][0]["datasetId"] = "non-existent-ds"

    mappings = normalize_pbi_scan_result(minimal_scan_result)

    # The report fails, but ds-1 still exists as an orphan dataset
    # and produces 1 mapping
    assert len(mappings) == 1
    assert mappings[0].pbi_dataset_id == "ds-1"
    assert "references unknown dataset" in caplog.text


def test_skips_non_databricks_datasource(minimal_scan_result: dict[str, Any]) -> None:
    """Test that tables from non-Databricks sources are skipped."""
    # Change datasource to non-Databricks
    minimal_scan_result["datasourceInstances"][0]["connectionDetails"][
        "server"
    ] = "some-sql-server.database.windows.net"

    mappings = normalize_pbi_scan_result(minimal_scan_result)

    assert len(mappings) == 0

from __future__ import annotations

from unittest.mock import MagicMock

from databricks.sdk.errors import DatabricksError, ResourceAlreadyExists

from lineage_syncer.commons.models import LineageMapping
from lineage_syncer.services.push import (
    _build_external_name,
    push_lineage,
)


def _mapping(
    *,
    workspace_name: str = "Finance",
    report_name: str = "Q3 Revenue",
    table: str = "revenue",
    columns: list[str] | None = None,
) -> LineageMapping:
    """Build a LineageMapping for push tests."""
    return LineageMapping(
        pbi_workspace_id="ws-1",
        pbi_workspace_name=workspace_name,
        pbi_report_id="rep-1",
        pbi_report_name=report_name,
        pbi_dataset_id="ds-1",
        pbi_dataset_name="model",
        endorsement="Certified",
        connection_mode="PbixInImportMode",
        storage_mode="Abf",
        databricks_catalog="gold",
        databricks_schema="finance",
        databricks_table=table,
        columns=columns if columns is not None else ["amount", "region"],
    )


def _mock_client() -> MagicMock:
    """A WorkspaceClient mock with external_metadata/external_lineage APIs."""
    client = MagicMock()
    client.external_metadata.create_external_metadata = MagicMock()
    client.external_lineage.create_external_lineage_relationship = MagicMock()
    return client


# --- _build_external_name ---


def test_build_external_name_sanitizes_to_alphanumeric_underscore() -> None:
    name = _build_external_name("My Workspace", "Q3 Revenue.Report/v2")
    assert name == "powerbi_My_Workspace_Q3_Revenue_Report_v2"
    # Databricks only permits alphanumeric characters and underscores
    assert all(c.isalnum() or c == "_" for c in name)


# --- push_lineage happy path ---


def test_push_creates_metadata_and_link() -> None:
    client = _mock_client()
    summary = push_lineage(client, [_mapping()])

    assert summary.total == 1
    assert summary.succeeded == 1
    assert summary.failed == 0
    client.external_metadata.create_external_metadata.assert_called_once()
    client.external_lineage.create_external_lineage_relationship.assert_called_once()


def test_push_passes_column_level_relationships() -> None:
    client = _mock_client()
    push_lineage(client, [_mapping(columns=["a", "b", "c"])])

    call = client.external_lineage.create_external_lineage_relationship.call_args
    request = call.args[0]
    assert request.columns is not None
    assert [c.source for c in request.columns] == ["a", "b", "c"]
    assert [c.target for c in request.columns] == ["a", "b", "c"]


# --- deduplication ---


def test_push_dedupes_metadata_creation() -> None:
    client = _mock_client()
    # Same workspace/report, two different tables
    mappings = [_mapping(table="revenue"), _mapping(table="costs")]
    summary = push_lineage(client, mappings)

    assert summary.succeeded == 2
    # Metadata created once, links created twice
    assert client.external_metadata.create_external_metadata.call_count == 1
    assert (
        client.external_lineage.create_external_lineage_relationship.call_count == 2
    )


# --- 409 conflict handling ---


def test_push_metadata_conflict_is_success() -> None:
    client = _mock_client()
    client.external_metadata.create_external_metadata.side_effect = (
        ResourceAlreadyExists("already exists")
    )
    summary = push_lineage(client, [_mapping()])

    assert summary.succeeded == 1
    assert summary.failed == 0
    # Link still attempted despite metadata conflict
    client.external_lineage.create_external_lineage_relationship.assert_called_once()


def test_push_link_conflict_is_success() -> None:
    client = _mock_client()
    client.external_lineage.create_external_lineage_relationship.side_effect = (
        ResourceAlreadyExists("already exists")
    )
    summary = push_lineage(client, [_mapping()])

    assert summary.succeeded == 1
    assert summary.failed == 0


# --- API error handling ---


def test_push_api_error_records_failure() -> None:
    client = _mock_client()
    client.external_metadata.create_external_metadata.side_effect = DatabricksError(
        "boom"
    )
    summary = push_lineage(client, [_mapping()])

    assert summary.succeeded == 0
    assert summary.failed == 1
    assert len(summary.errors) == 1
    assert "boom" in summary.errors[0]


def test_push_continues_after_individual_failure() -> None:
    client = _mock_client()
    # First mapping's metadata fails; second succeeds (different report)
    client.external_metadata.create_external_metadata.side_effect = [
        DatabricksError("boom"),
        None,
    ]
    mappings = [
        _mapping(report_name="Report A"),
        _mapping(report_name="Report B"),
    ]
    summary = push_lineage(client, mappings)

    assert summary.total == 2
    assert summary.succeeded == 1
    assert summary.failed == 1


# --- dry run ---


def test_push_dry_run_makes_no_writes() -> None:
    client = _mock_client()
    summary = push_lineage(client, [_mapping(), _mapping(table="costs")], dry_run=True)

    assert summary.total == 2
    assert summary.skipped == 2
    assert summary.succeeded == 0
    client.external_metadata.create_external_metadata.assert_not_called()
    client.external_lineage.create_external_lineage_relationship.assert_not_called()


# --- summary counts ---


def test_push_summary_counts_mixed() -> None:
    client = _mock_client()
    client.external_metadata.create_external_metadata.side_effect = [
        None,
        DatabricksError("boom"),
    ]
    mappings = [
        _mapping(report_name="Report A"),
        _mapping(report_name="Report B"),
    ]
    summary = push_lineage(client, mappings)

    assert summary.total == 2
    assert summary.succeeded == 1
    assert summary.failed == 1
    assert summary.skipped == 0

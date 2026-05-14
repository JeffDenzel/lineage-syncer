from __future__ import annotations

from unittest.mock import patch

import pytest

from defensive_lineage.commons.settings import Settings
from defensive_lineage.orchestrators.pbi_scanner import ScannerClient


@pytest.fixture
def mock_settings() -> Settings:
    """Create mock settings for testing."""
    return Settings(
        dl_scan_timeout=300,
        dl_log_level="INFO",
        databricks_host="https://test.databricks.net",
        databricks_client_id="test-client-id",
        databricks_client_secret="test-secret",
        azure_tenant_id="test-tenant",
        azure_client_id="test-client",
        azure_client_secret="test-secret",
    )


def test_get_full_scan_result_aggregates_workspaces(mock_settings: Settings) -> None:
    """Test that get_full_scan_result aggregates workspaces correctly."""
    client = ScannerClient(token="test-token", settings=mock_settings)

    # Mock run_full_scan to yield sample data
    mock_workspaces = [
        {"id": "ws-1", "name": "Workspace 1", "datasets": [], "reports": []},
        {"id": "ws-2", "name": "Workspace 2", "datasets": [], "reports": []},
    ]
    mock_datasource_instances = [
        {"datasourceInstanceId": "dsi-1", "datasourceType": "Sql"},
        {"datasourceInstanceId": "dsi-2", "datasourceType": "Sql"},
    ]

    def mock_run_full_scan():
        yield {"type": "datasourceInstances", "instances": mock_datasource_instances}
        for ws in mock_workspaces:
            yield ws

    with patch.object(client, "run_full_scan", mock_run_full_scan):
        result = client.get_full_scan_result()

    assert "workspaces" in result
    assert "datasourceInstances" in result
    assert len(result["workspaces"]) == 2
    assert len(result["datasourceInstances"]) == 2
    assert result["workspaces"][0]["id"] == "ws-1"
    assert result["datasourceInstances"][0]["datasourceInstanceId"] == "dsi-1"


def test_get_full_scan_result_handles_multiple_datasource_batches(
    mock_settings: Settings,
) -> None:
    """Test that multiple datasourceInstances batches are merged."""
    client = ScannerClient(token="test-token", settings=mock_settings)

    def mock_run_full_scan():
        yield {
            "type": "datasourceInstances",
            "instances": [{"datasourceInstanceId": "dsi-1"}],
        }
        yield {"id": "ws-1", "name": "Workspace 1"}
        yield {
            "type": "datasourceInstances",
            "instances": [{"datasourceInstanceId": "dsi-2"}],
        }
        yield {"id": "ws-2", "name": "Workspace 2"}

    with patch.object(client, "run_full_scan", mock_run_full_scan):
        result = client.get_full_scan_result()

    assert len(result["workspaces"]) == 2
    assert len(result["datasourceInstances"]) == 2
    assert result["datasourceInstances"][0]["datasourceInstanceId"] == "dsi-1"
    assert result["datasourceInstances"][1]["datasourceInstanceId"] == "dsi-2"


def test_get_full_scan_result_empty_scan(mock_settings: Settings) -> None:
    """Test that empty scan returns empty lists."""
    client = ScannerClient(token="test-token", settings=mock_settings)

    def mock_run_full_scan():
        return
        yield  # Make it a generator

    with patch.object(client, "run_full_scan", mock_run_full_scan):
        result = client.get_full_scan_result()

    assert result["workspaces"] == []
    assert result["datasourceInstances"] == []

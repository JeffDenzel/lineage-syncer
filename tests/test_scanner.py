from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import responses as resp

from defensive_lineage.orchestrators.pbi_scanner import ScannerClient
from defensive_lineage.commons.exceptions import ScanTimeoutError
from defensive_lineage.services.scanner import (
    PBI_ADMIN_BASE_URL,
    get_scan_results,
    get_workspace_ids,
    poll_scan_status,
    trigger_scan,
)
from defensive_lineage.commons.settings import Settings

FIXTURES_DIR = Path(__file__).parent / "fixtures"

with open(FIXTURES_DIR / "workspace_ids.json") as f:
    FIXTURE_WORKSPACE_IDS = json.load(f)

with open(FIXTURES_DIR / "scan_trigger.json") as f:
    FIXTURE_SCAN_TRIGGER = json.load(f)

with open(FIXTURES_DIR / "scan_status_running.json") as f:
    FIXTURE_SCAN_STATUS_RUNNING = json.load(f)

with open(FIXTURES_DIR / "scan_status_succeeded.json") as f:
    FIXTURE_SCAN_STATUS_SUCCEEDED = json.load(f)

with open(FIXTURES_DIR / "scan_status_failed.json") as f:
    FIXTURE_SCAN_STATUS_FAILED = json.load(f)

with open(FIXTURES_DIR / "scan_result.json") as f:
    FIXTURE_SCAN_RESULT = json.load(f)

FAKE_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.fake.token"


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        azure_tenant_id="tenant-123",
        azure_client_id="client-abc",
        azure_client_secret="secret-xyz",
        databricks_host="https://adb-1234.azuredatabricks.net",
        databricks_client_id="dbx-client",
        databricks_client_secret="dbx-secret",
        dl_scan_timeout=5,
    )


# --- get_workspace_ids ---


@resp.activate
def test_get_workspace_ids_returns_ids() -> None:
    resp.add(
        resp.GET,
        f"{PBI_ADMIN_BASE_URL}/workspaces/modified",
        json=FIXTURE_WORKSPACE_IDS,
        status=200,
    )
    result = get_workspace_ids(FAKE_TOKEN)
    assert result == [
        "97d03602-4873-4760-b37e-1563ef5358e3",
        "67b7e93a-3fb3-493c-9e41-2c5051008f24",
    ]


@resp.activate
def test_get_workspace_ids_empty_tenant() -> None:
    resp.add(
        resp.GET,
        f"{PBI_ADMIN_BASE_URL}/workspaces/modified",
        json=[],
        status=200,
    )
    assert get_workspace_ids(FAKE_TOKEN) == []


@resp.activate
def test_get_workspace_ids_passes_modified_since() -> None:
    from datetime import datetime, timezone

    resp.add(
        resp.GET,
        f"{PBI_ADMIN_BASE_URL}/workspaces/modified",
        json=FIXTURE_WORKSPACE_IDS,
        status=200,
    )
    dt = datetime(2023, 1, 1, tzinfo=timezone.utc)
    get_workspace_ids(FAKE_TOKEN, modified_since=dt)

    url = resp.calls[0].request.url
    assert (
        "modifiedSince=2023-01-01T00%3A00%3A00%2B00%3A00" in url
        or "modifiedSince=2023-01-01" in url
    )


# --- trigger_scan ---


@resp.activate
def test_trigger_scan_single_batch() -> None:
    resp.add(
        resp.POST,
        f"{PBI_ADMIN_BASE_URL}/workspaces/getInfo",
        json=FIXTURE_SCAN_TRIGGER,
        status=202,
    )
    workspace_ids = [f"id-{i}" for i in range(50)]
    scan_ids = trigger_scan(FAKE_TOKEN, workspace_ids)

    assert scan_ids == ["e7d03602-4873-4760-b37e-1563ef5358e3"]
    assert len(resp.calls) == 1


@resp.activate
def test_trigger_scan_multiple_batches() -> None:
    resp.add(
        resp.POST,
        f"{PBI_ADMIN_BASE_URL}/workspaces/getInfo",
        json=FIXTURE_SCAN_TRIGGER,
        status=202,
    )
    workspace_ids = [f"id-{i}" for i in range(150)]
    scan_ids = trigger_scan(FAKE_TOKEN, workspace_ids)

    assert len(scan_ids) == 2
    assert len(resp.calls) == 2


@resp.activate
def test_trigger_scan_raises_on_api_error() -> None:
    resp.add(
        resp.POST,
        f"{PBI_ADMIN_BASE_URL}/workspaces/getInfo",
        json={"error": "bad request"},
        status=400,
    )
    with pytest.raises(ScanTimeoutError, match="400"):
        trigger_scan(FAKE_TOKEN, ["id-1"])


# --- poll_scan_status ---


@resp.activate
@patch("defensive_lineage.services.scanner._POLL_INTERVAL_SECONDS", 0.01)
def test_poll_scan_status_succeeds() -> None:
    resp.add(
        resp.GET,
        f"{PBI_ADMIN_BASE_URL}/workspaces/scanStatus/test-scan-id",
        json=FIXTURE_SCAN_STATUS_RUNNING,
        status=200,
    )
    resp.add(
        resp.GET,
        f"{PBI_ADMIN_BASE_URL}/workspaces/scanStatus/test-scan-id",
        json=FIXTURE_SCAN_STATUS_SUCCEEDED,
        status=200,
    )
    status = poll_scan_status(FAKE_TOKEN, "test-scan-id")
    assert status == "Succeeded"
    assert len(resp.calls) == 2


@resp.activate
@patch("defensive_lineage.services.scanner._POLL_INTERVAL_SECONDS", 0.1)
def test_poll_scan_status_timeout() -> None:
    resp.add(
        resp.GET,
        f"{PBI_ADMIN_BASE_URL}/workspaces/scanStatus/test-scan-id",
        json=FIXTURE_SCAN_STATUS_RUNNING,
        status=200,
    )
    with pytest.raises(ScanTimeoutError, match="exceeded timeout"):
        poll_scan_status(FAKE_TOKEN, "test-scan-id", timeout_seconds=0)


@resp.activate
def test_poll_scan_status_failed() -> None:
    resp.add(
        resp.GET,
        f"{PBI_ADMIN_BASE_URL}/workspaces/scanStatus/test-scan-id",
        json=FIXTURE_SCAN_STATUS_FAILED,
        status=200,
    )
    with pytest.raises(ScanTimeoutError, match="ScanFailed"):
        poll_scan_status(FAKE_TOKEN, "test-scan-id")


# --- get_scan_results ---


@resp.activate
def test_get_scan_results_filters_endorsed() -> None:
    resp.add(
        resp.GET,
        f"{PBI_ADMIN_BASE_URL}/workspaces/scanResult/test-scan-id",
        json=FIXTURE_SCAN_RESULT,
        status=200,
    )
    results = get_scan_results(FAKE_TOKEN, "test-scan-id")
    workspaces = results["workspaces"]
    assert len(workspaces) == 1

    ws = workspaces[0]
    assert len(ws["reports"]) == 1
    assert ws["reports"][0]["name"] == "CompositeModelParams-RLS"

    assert len(ws["datasets"]) == 1
    assert ws["datasets"][0]["name"] == "ExportB"


@resp.activate
def test_get_scan_results_no_endorsed() -> None:
    no_endorsed = {
        "workspaces": [{"id": "ws-1", "reports": [{"id": "rep-1", "tags": []}]}]
    }
    resp.add(
        resp.GET,
        f"{PBI_ADMIN_BASE_URL}/workspaces/scanResult/test-scan-id",
        json=no_endorsed,
        status=200,
    )
    results = get_scan_results(FAKE_TOKEN, "test-scan-id")
    assert results["workspaces"] == []


# --- _pbi_request ---


@resp.activate
@patch("defensive_lineage.services.scanner.INITIAL_BACKOFF_SECONDS", 0.01)
def test_pbi_request_retries_on_429() -> None:
    resp.add(
        resp.GET,
        f"{PBI_ADMIN_BASE_URL}/workspaces/modified",
        status=429,
        headers={"Retry-After": "0"},
    )
    resp.add(
        resp.GET,
        f"{PBI_ADMIN_BASE_URL}/workspaces/modified",
        json=FIXTURE_WORKSPACE_IDS,
        status=200,
    )
    result = get_workspace_ids(FAKE_TOKEN)
    assert result == [
        "97d03602-4873-4760-b37e-1563ef5358e3",
        "67b7e93a-3fb3-493c-9e41-2c5051008f24",
    ]
    assert len(resp.calls) == 2


@resp.activate
@patch("defensive_lineage.services.scanner.INITIAL_BACKOFF_SECONDS", 0.01)
def test_pbi_request_exhausts_retries() -> None:
    resp.add(
        resp.GET,
        f"{PBI_ADMIN_BASE_URL}/workspaces/modified",
        status=429,
    )
    with pytest.raises(ScanTimeoutError, match="Rate limit exceeded"):
        get_workspace_ids(FAKE_TOKEN)


# --- run_full_scan ---


@resp.activate
@patch(
    "defensive_lineage.orchestrators.pbi_scanner.get_workspace_ids",
    return_value=["e7d03602-4873-4760-b37e-1563ef5358e3"],
)
@patch(
    "defensive_lineage.orchestrators.pbi_scanner.trigger_scan",
    return_value=["e7d03602-4873-4760-b37e-1563ef5358e3"],
)
@patch("defensive_lineage.orchestrators.pbi_scanner.poll_scan_status")
@patch(
    "defensive_lineage.orchestrators.pbi_scanner.get_scan_results",
    return_value=FIXTURE_SCAN_RESULT,
)
def test_run_full_scan_integration(
    mock_get_scan_results: patch,
    mock_poll_scan_status: patch,
    mock_trigger_scan: patch,
    mock_get_workspace_ids: patch,
    settings: Settings,
) -> None:
    # 1. get_workspace_ids
    resp.add(
        resp.GET,
        f"{PBI_ADMIN_BASE_URL}/workspaces/modified",
        json=FIXTURE_WORKSPACE_IDS,
        status=200,
    )
    # 2. trigger_scan
    resp.add(
        resp.POST,
        f"{PBI_ADMIN_BASE_URL}/workspaces/getInfo",
        json=FIXTURE_SCAN_TRIGGER,
        status=202,
    )
    # 3. poll_scan_status
    resp.add(
        resp.GET,
        f"{PBI_ADMIN_BASE_URL}/workspaces/scanStatus/e7d03602-4873-4760-b37e-1563ef5358e3",
        json=FIXTURE_SCAN_STATUS_SUCCEEDED,
        status=200,
    )
    # 4. get_scan_results
    resp.add(
        resp.GET,
        f"{PBI_ADMIN_BASE_URL}/workspaces/scanResult/e7d03602-4873-4760-b37e-1563ef5358e3",
        json=FIXTURE_SCAN_RESULT,
        status=200,
    )

    scanner = ScannerClient(FAKE_TOKEN, settings)
    results = list(scanner.run_full_scan())

    assert len(results) == 1
    assert len(results[0]["datasets"]) == 1

    pass

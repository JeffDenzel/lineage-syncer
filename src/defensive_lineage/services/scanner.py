from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..commons.exceptions import ScanTimeoutError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PBI_ADMIN_BASE_URL = "https://api.powerbi.com/v1.0/myorg/admin"

MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 2.0

_MAX_WORKSPACES_PER_SCAN = 100
_POLL_INTERVAL_SECONDS = 5
_ENDORSED_STATUSES = frozenset({"Certified", "Promoted"})


class RateLimitError(Exception):
    """Raised when a 429 response is received."""

    pass


# ---------------------------------------------------------------------------
# HTTP Helper
# ---------------------------------------------------------------------------


@retry(
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=INITIAL_BACKOFF_SECONDS),
    retry=retry_if_exception_type(
        (requests.exceptions.RequestException, RateLimitError)
    ),
    reraise=True,
)
def _pbi_request(
    method: str,
    path: str,
    token: str,
    *,
    json_body: dict[str, Any] | None = None,
    params: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Make an authenticated request to the Power BI Admin API.

    Handles rate limiting and network errors using tenacity.
    Raises on all other HTTP errors.

    Args:
        method (str): The HTTP method (e.g., 'GET', 'POST').
        path (str): The API endpoint path, appended to the base URL.
        token (str): The Power BI bearer token.
        json_body (dict[str, Any] | None, optional): The JSON payload to send.
        params (dict[str, str] | None, optional): The query parameters to include.

    Returns:
        dict[str, Any]: The parsed JSON response body.
        Returns an empty dict if the response has no JSON body.

    Raises:
        RateLimitError: If a 429 response is received and retries are exhausted.
        ScanTimeoutError: If a network error occurs.
    """
    url = f"{PBI_ADMIN_BASE_URL}{path}"
    headers = {"Authorization": f"Bearer {token}"}

    logger.debug("PBI API Request: %s %s", method, path)
    response = requests.request(
        method=method,
        url=url,
        headers=headers,
        json=json_body,
        params=params,
        timeout=30,
    )

    if response.status_code == 429:
        logger.warning("Rate limited (429) on %s %s. Retrying...", method, path)
        raise RateLimitError(f"Rate limit exceeded on {method} {path}")

    if response.status_code not in (200, 202):
        error_text = response.text
        raise ScanTimeoutError(
            f"PBI API error {response.status_code} on {method} {path}: {error_text}"
        )  # noqa: E501

    try:
        return response.json()
    except ValueError:
        return {}


# ---------------------------------------------------------------------------
# API Functions
# ---------------------------------------------------------------------------


def get_workspace_ids(
    token: str,
    *,
    modified_since: datetime | None = None,
) -> list[str]:
    """Retrieve workspace IDs from the Power BI Admin API.

    Calls GET /admin/workspaces/modified to discover all workspaces
    in the tenant. Personal and inactive workspaces are excluded.

    Args:
        token (str): The Power BI bearer token.
        modified_since (datetime | None, optional): Only retrieve workspaces modified
        since this date.

    Returns:
        list[str]: A list of workspace ID strings.
    """
    params = {
        "excludePersonalWorkspaces": "True",
        "excludeInActiveWorkspaces": "True",
    }
    if modified_since:
        params["modifiedSince"] = modified_since.isoformat()

    response = _pbi_request("GET", "/workspaces/modified", token, params=params)

    # Can return an array of objects
    items = (
        response if isinstance(response, list) else response.get("workspaces", response)
    )

    workspace_ids = []
    for item in items:
        if isinstance(item, dict) and "id" in item:
            workspace_ids.append(item["id"])
        elif isinstance(item, str):
            workspace_ids.append(item)

    logger.info("Discovered %d workspaces.", len(workspace_ids))
    return workspace_ids


def trigger_scan(token: str, workspace_ids: list[str]) -> list[str]:
    """Trigger metadata scans for the given workspaces.

    Batches workspaces into groups of up to 100 per request.

    Args:
        token (str): The Power BI bearer token.
        workspace_ids (list[str]): The list of workspace IDs to scan.

    Returns:
        list[str]: A list of scan IDs returned by the API.

    Raises:
        ScanTimeoutError: If the API fails to return a scan ID.
    """
    if not workspace_ids:
        return []

    scan_ids = []

    # Batch into groups of 100
    for i in range(0, len(workspace_ids), _MAX_WORKSPACES_PER_SCAN):
        batch = workspace_ids[i : i + _MAX_WORKSPACES_PER_SCAN]

        body = {"workspaces": batch}
        params = {
            "lineage": "True",
            "datasourceDetails": "True",
            "datasetSchema": "True",
            "datasetExpressions": "False",
            "getArtifactUsers": "False",
        }

        response = _pbi_request(
            "POST", "/workspaces/getInfo", token, json_body=body, params=params
        )

        scan_id = response.get("id")
        if not scan_id:
            raise ScanTimeoutError(f"Failed to get scan ID from response: {response}")

        scan_ids.append(scan_id)
        logger.info(
            "Triggered scan batch %d/%d (ID: %s, %d workspaces)",
            (i // _MAX_WORKSPACES_PER_SCAN) + 1,
            (len(workspace_ids) + _MAX_WORKSPACES_PER_SCAN - 1)
            // _MAX_WORKSPACES_PER_SCAN,  # noqa: E501
            scan_id,
            len(batch),
        )

    return scan_ids


def poll_scan_status(
    token: str,
    scan_id: str,
    *,
    timeout_seconds: int = 300,
) -> str:
    """Poll the status of a Power BI scan until completion or timeout.

    Args:
        token (str): The Power BI bearer token.
        scan_id (str): The scan ID to check.
        timeout_seconds (int, optional): The maximum time to wait in seconds.

    Returns:
        str: The final status string (e.g., 'Succeeded').

    Raises:
        ScanTimeoutError: If the scan fails or times out.
    """
    start_time = time.monotonic()
    last_status = "Unknown"

    while True:
        elapsed = time.monotonic() - start_time
        if elapsed > timeout_seconds:
            raise ScanTimeoutError(
                f"Scan {scan_id} exceeded timeout of {timeout_seconds}s."
            )  # noqa: E501

        response = _pbi_request("GET", f"/workspaces/scanStatus/{scan_id}", token)
        status = response.get("status")

        if status != last_status:
            logger.info("Scan %s status: %s -> %s", scan_id, last_status, status)
            last_status = status

        if status == "Succeeded":
            return status

        if status == "Failed":
            error_details = response.get("error", "Unknown error")
            raise ScanTimeoutError(f"Scan {scan_id} failed: {error_details}")

        time.sleep(_POLL_INTERVAL_SECONDS)


def get_scan_results(token: str, scan_id: str) -> dict[str, Any]:
    """Fetch scan results and filter to endorsed assets.

    Args:
        token (str): The Power BI bearer token.
        scan_id (str): The scan ID to retrieve results for.

    Returns:
        dict[str, Any]: The filtered scan results.
    """
    response = _pbi_request("GET", f"/workspaces/scanResult/{scan_id}", token)

    workspaces = response.get("workspaces", [])

    total_datasets = 0
    endorsed_datasets = 0
    total_reports = 0
    endorsed_reports = 0

    filtered_workspaces = []

    for workspace in workspaces:
        datasets = workspace.get("datasets", [])
        reports = workspace.get("reports", [])

        filtered_datasets = []
        for ds in datasets:
            total_datasets += 1
            endorsement = ds.get("endorsementDetails", {}).get("endorsement")
            if endorsement in _ENDORSED_STATUSES:
                filtered_datasets.append(ds)
                endorsed_datasets += 1

        filtered_reports = []
        for rep in reports:
            total_reports += 1
            endorsement = rep.get("endorsementDetails", {}).get("endorsement")
            if endorsement in _ENDORSED_STATUSES:
                filtered_reports.append(rep)
                endorsed_reports += 1

        workspace["datasets"] = filtered_datasets
        workspace["reports"] = filtered_reports

        if filtered_datasets or filtered_reports:
            filtered_workspaces.append(workspace)

    response["workspaces"] = filtered_workspaces

    logger.info(
        "Scan %s results: %d/%d endorsed datasets, %d/%d endorsed reports",
        scan_id,
        endorsed_datasets,
        total_datasets,
        endorsed_reports,
        total_reports,
    )

    return response

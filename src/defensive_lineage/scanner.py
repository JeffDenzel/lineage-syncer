from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Any

import requests

from .auth import get_pbi_token
from .exceptions import ScanTimeoutError
from .settings import Settings

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


# ---------------------------------------------------------------------------
# HTTP Helper
# ---------------------------------------------------------------------------

def _pbi_request(
    method: str,
    path: str,
    token: str,
    *,
    json_body: dict[str, Any] | None = None,
    params: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Make an authenticated request to the Power BI Admin API.

    Handles 429 rate limiting with exponential backoff (max 3 retries).
    Raises on all other HTTP errors.
    """
    url = f"{PBI_ADMIN_BASE_URL}{path}"
    headers = {"Authorization": f"Bearer {token}"}
    
    backoff = INITIAL_BACKOFF_SECONDS
    
    for attempt in range(MAX_RETRIES + 1):
        logger.debug("PBI API Request: %s %s", method, path)
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=json_body,
                params=params,
                timeout=30
            )
        except requests.exceptions.RequestException as e:
            if attempt < MAX_RETRIES:
                logger.warning("Network error on %s %s: %s. Retrying in %ss...", method, path, e, backoff)
                time.sleep(backoff)
                backoff *= 2
                continue
            raise ScanTimeoutError(f"Network error on {method} {path} after {MAX_RETRIES} retries: {e}") from e

        if response.status_code == 429:
            if attempt < MAX_RETRIES:
                retry_after = response.headers.get("Retry-After")
                wait_time = int(retry_after) if retry_after and retry_after.isdigit() else backoff
                logger.warning("Rate limited (429) on %s %s. Retrying in %ss...", method, path, wait_time)
                time.sleep(wait_time)
                backoff *= 2
                continue
            raise ScanTimeoutError(f"Rate limit exceeded on {method} {path} after {MAX_RETRIES} retries.")

        if response.status_code not in (200, 202):
            error_text = response.text
            raise ScanTimeoutError(f"PBI API error {response.status_code} on {method} {path}: {error_text}")

        # Return empty dict if there's no JSON (e.g., 202 without a body, though 202 usually has a body here)
        try:
            return response.json()
        except ValueError:
            return {}
            
    raise ScanTimeoutError(f"Failed to complete {method} {path} after retries.")


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
    """
    params = {
        "excludePersonalWorkspaces": "True",
        "excludeInActiveWorkspaces": "True",
    }
    if modified_since:
        params["modifiedSince"] = modified_since.isoformat()

    response = _pbi_request("GET", "/workspaces/modified", token, params=params)
    
    # Can return an array of objects
    items = response if isinstance(response, list) else response.get("workspaces", response)
    
    workspace_ids = []
    for item in items:
        if isinstance(item, dict) and "id" in item:
            workspace_ids.append(item["id"])
        elif isinstance(item, str):
            workspace_ids.append(item)
            
    logger.info("Discovered %d workspaces.", len(workspace_ids))
    return workspace_ids


def trigger_scan(token: str, workspace_ids: list[str]) -> list[str]:
    """Trigger metadata scans for the given workspaces."""
    if not workspace_ids:
        return []
        
    scan_ids = []
    
    # Batch into groups of 100
    for i in range(0, len(workspace_ids), _MAX_WORKSPACES_PER_SCAN):
        batch = workspace_ids[i:i + _MAX_WORKSPACES_PER_SCAN]
        
        body = {"workspaces": batch}
        params = {
            "lineage": "True",
            "datasourceDetails": "True",
            "datasetSchema": "True",
            "datasetExpressions": "False",
            "getArtifactUsers": "False",
        }
        
        response = _pbi_request("POST", "/workspaces/getInfo", token, json_body=body, params=params)
        
        scan_id = response.get("id")
        if not scan_id:
            raise ScanTimeoutError(f"Failed to get scan ID from response: {response}")
            
        scan_ids.append(scan_id)
        logger.info("Triggered scan batch %d/%d (ID: %s, %d workspaces)", 
                    (i // _MAX_WORKSPACES_PER_SCAN) + 1,
                    (len(workspace_ids) + _MAX_WORKSPACES_PER_SCAN - 1) // _MAX_WORKSPACES_PER_SCAN,
                    scan_id, len(batch))
                    
    return scan_ids


def poll_scan_status(
    token: str,
    scan_id: str,
    *,
    timeout_seconds: int = 300,
) -> str:
    """Poll the status of a Power BI scan until completion or timeout."""
    start_time = time.monotonic()
    last_status = "Unknown"
    
    while True:
        elapsed = time.monotonic() - start_time
        if elapsed > timeout_seconds:
            raise ScanTimeoutError(f"Scan {scan_id} exceeded timeout of {timeout_seconds}s.")
            
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
    """Fetch scan results and filter to endorsed assets."""
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
        scan_id, endorsed_datasets, total_datasets, endorsed_reports, total_reports
    )
    
    return response


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_full_scan(settings: Settings) -> dict[str, Any]:
    """Execute the complete Power BI scan flow."""
    token = get_pbi_token(settings)
    logger.info("PBI token acquired for scanning.")
    
    workspace_ids = get_workspace_ids(token)
    if not workspace_ids:
        logger.warning("No workspaces found.")
        return {"workspaces": [], "datasourceInstances": []}
        
    scan_ids = trigger_scan(token, workspace_ids)
    
    combined_result: dict[str, Any] = {"workspaces": [], "datasourceInstances": []}
    seen_datasources = set()
    
    for idx, scan_id in enumerate(scan_ids):
        logger.info("Polling scan %d/%d...", idx + 1, len(scan_ids))
        poll_scan_status(token, scan_id, timeout_seconds=settings.dl_scan_timeout)
        
        batch_results = get_scan_results(token, scan_id)
        
        combined_result["workspaces"].extend(batch_results.get("workspaces", []))
        
        # Deduplicate datasource instances
        for ds in batch_results.get("datasourceInstances", []):
            ds_id = ds.get("datasourceId")
            if ds_id and ds_id not in seen_datasources:
                seen_datasources.add(ds_id)
                combined_result["datasourceInstances"].append(ds)
                
    try:
        with open("scan_output.json", "w") as f:
            json.dump(combined_result, f, indent=2)
        logger.info("Raw JSON results saved to scan_output.json")
    except Exception as e:
        logger.error("Failed to write scan_output.json: %s", e)
        
    return combined_result

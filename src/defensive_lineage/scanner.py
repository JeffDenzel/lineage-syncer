from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

def trigger_scan() -> str:
    """Trigger a new Power BI metadata scan."""
    return "scan_id"

def poll_scan_status(scan_id: str) -> str:
    """Poll the status of an ongoing scan."""
    return "Succeeded"

def get_scan_results(scan_id: str) -> dict:
    """Fetch the results of a succeeded scan."""
    return {}

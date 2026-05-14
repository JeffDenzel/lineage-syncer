from __future__ import annotations

import logging
from typing import Any, Iterator

from ..commons.settings import Settings
from ..services.scanner import (
    get_scan_results,
    get_workspace_ids,
    poll_scan_status,
    trigger_scan,
)

logger = logging.getLogger(__name__)


class ScannerClient:
    """Orchestrator client for the Power BI Scanner API.

    Handles high-level workflow, tying together discovery, triggering,
    polling, and result extraction.

    Args:
        token (str): The Power BI bearer token.
        settings (Settings): The validated application settings.
    """

    def __init__(self, token: str, settings: Settings) -> None:
        self.token = token
        self.settings = settings

    def run_full_scan(self) -> Iterator[dict[str, Any]]:
        """Execute the complete Power BI scan flow, yielding datasourceInstances
        and workspaces.

        Yields:
            dict[str, Any]: A dictionary containing either datasourceInstances
                (with type field) or the raw Power BI metadata for a single workspace.
        """
        logger.info("Starting PBI scan with provided token.")

        workspace_ids = get_workspace_ids(self.token)
        if not workspace_ids:
            logger.warning("No workspaces found.")
            return

        scan_ids = trigger_scan(self.token, workspace_ids)

        for idx, scan_id in enumerate(scan_ids):
            logger.info("Polling scan %d/%d...", idx + 1, len(scan_ids))
            poll_scan_status(
                self.token, scan_id, timeout_seconds=self.settings.dl_scan_timeout
            )

            batch_results = get_scan_results(self.token, scan_id)
            datasource_instances = batch_results.get("datasourceInstances", [])
            workspaces = batch_results.get("workspaces", [])

            if datasource_instances:
                logger.debug(
                    "Yielding %d datasource instances for scan %s",
                    len(datasource_instances),
                    scan_id,
                )
                yield {"type": "datasourceInstances", "instances": datasource_instances}

            for workspace in workspaces:
                yield workspace

    def get_full_scan_result(self) -> dict[str, Any]:
        """Execute full scan and return aggregated result for transform.

        Aggregates all yielded workspaces and datasourceInstances into a
        single dict matching the Scanner API response format expected by
        normalize_pbi_scan_result().

        Returns:
            dict[str, Any]: Dict with 'workspaces' and 'datasourceInstances' keys.
        """
        all_workspaces: list[dict[str, Any]] = []
        all_datasource_instances: list[dict[str, Any]] = []

        for item in self.run_full_scan():
            if item.get("type") == "datasourceInstances":
                all_datasource_instances.extend(item.get("instances", []))
            else:
                all_workspaces.append(item)

        return {
            "workspaces": all_workspaces,
            "datasourceInstances": all_datasource_instances,
        }

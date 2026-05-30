from __future__ import annotations

import logging
from typing import Iterable

from databricks.sdk import WorkspaceClient

from ..commons.models import LineageMapping, PushSummary
from ..services.push import push_lineage

logger = logging.getLogger(__name__)


class DatabricksLineageClient:
    """Orchestrator client for pushing lineage metadata into Databricks Unity Catalog.

    Args:
        workspace_client: An authenticated Databricks WorkspaceClient.
    """

    def __init__(self, workspace_client: WorkspaceClient) -> None:
        self.client = workspace_client

    def push_lineage(
        self,
        mappings: Iterable[LineageMapping],
        dry_run: bool = False,
    ) -> PushSummary:
        """Push normalized lineage mappings to Databricks Unity Catalog.

        Args:
            mappings (Iterable[LineageMapping]): Normalized lineage mappings to push.
            dry_run (bool): If ``True``, log intended actions without writing.

        Returns:
            PushSummary: The outcome of the push operation.
        """
        logger.info("Starting Databricks lineage push workflow...")
        return push_lineage(self.client, mappings, dry_run=dry_run)

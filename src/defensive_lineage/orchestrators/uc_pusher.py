from __future__ import annotations

import logging
from typing import Any, Iterable

from ..commons.models import LineageMapping
from ..services.push import push_lineage

logger = logging.getLogger(__name__)


class DatabricksLineageClient:
    """Orchestrator client for pushing lineage metadata into Databricks Unity Catalog.

    Args:
        workspace_client: An authenticated Databricks WorkspaceClient.
    """

    def __init__(self, workspace_client: Any) -> None:
        self.client = workspace_client

    def push_lineage(self, mappings: Iterable[LineageMapping]) -> None:
        """Push normalized lineage mappings to Databricks Unity Catalog.

        Args:
            mappings (Iterable[LineageMapping]): Normalized lineage mappings to push.
        """
        logger.info("Starting Databricks lineage push workflow...")
        push_lineage(mappings)

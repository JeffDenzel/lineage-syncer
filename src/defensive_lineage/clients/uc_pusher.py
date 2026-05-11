from __future__ import annotations

import logging
from .transform import LineageMapping

logger = logging.getLogger(__name__)

def push_lineage(mappings: list[LineageMapping]) -> None:
    """Push normalized lineage mappings to Databricks Unity Catalog."""
    logger.info(f"Pushing {len(mappings)} mappings to Databricks...")

from __future__ import annotations

import logging
from typing import Iterable

from ..commons.models import LineageMapping

logger = logging.getLogger(__name__)


def push_lineage(mappings: Iterable[LineageMapping]) -> None:
    """Push normalized lineage mappings to Databricks Unity Catalog.

    Args:
        mappings (Iterable[LineageMapping]): An iterable of validated lineage mappings to push.
    """
    mappings_list = list(mappings)  # Temporary materialization until fully implemented
    logger.info(f"Pushing {len(mappings_list)} mappings to Databricks...")

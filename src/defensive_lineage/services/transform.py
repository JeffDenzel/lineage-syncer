from __future__ import annotations

import logging
from typing import Any, Iterable, Iterator

from ..commons.models import LineageMapping

logger = logging.getLogger(__name__)


def normalize_pbi_workspaces(
    workspaces: Iterable[dict[str, Any]],
) -> Iterator[LineageMapping]:
    """Transform an iterable of raw Power BI workspaces into LineageMapping objects.

    Yields LineageMapping objects as they are discovered.

    Args:
        workspaces (Iterable[dict[str, Any]]): An iterable of workspace dictionaries.

    Yields:
        LineageMapping: A lineage mapping linking PBI asset to Databricks asset.
    """
    for _workspace in workspaces:
        # Transformation logic goes here
        # yield LineageMapping(...)
        pass

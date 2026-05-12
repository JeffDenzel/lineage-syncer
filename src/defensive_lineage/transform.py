from __future__ import annotations

import logging
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class LineageMapping(BaseModel):
    """Schema for a single lineage link."""
    pbi_workspace_name: str
    pbi_report_name: str
    databricks_catalog: str
    databricks_schema: str
    databricks_table: str

def normalize_pbi_json(raw_json: dict) -> list[LineageMapping]:
    """Transform raw Power BI JSON into a list of LineageMapping objects."""
    return []

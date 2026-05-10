# Defensive Lineage — Architecture

## System Overview

Defensive Lineage bridges the gap between Databricks Unity Catalog and **Power BI Semantic Models**. It identifies which certified models depend on specific Databricks tables and pushes that metadata back into Unity Catalog.

## Data Flow

1. **Scan:** Pull metadata for **Certified/Promoted Semantic Models** via the PBI Admin Scanner API.
2. **Categorize:** 
   - **Evaluatable:** Models using the native Databricks Connector (we can see the tables).
   - **Opaque:** Models using Native Queries (we can see the server, but not the tables).
3. **Transform:** Map Databricks table paths to Semantic Model IDs.
4. **Push:** Inject lineage into Unity Catalog via the BYOL API.

## Core Data Model: `LineageMapping`

```python
from pydantic import BaseModel

class LineageMapping(BaseModel):
    """A link between a UC table and a PBI Semantic Model."""

    # Power BI Metadata (The 'What' and 'Who')
    pbi_workspace_id: str
    pbi_workspace_name: str
    pbi_semantic_model_id: str
    pbi_semantic_model_name: str
    endorsement: str  # "Certified" | "Promoted"
    is_opaque: bool  # True if using Native Query
    downstream_reports: list[str]  # Human-readable report names for context

    # Databricks Metadata (The 'Source')
    databricks_catalog: str
    databricks_schema: str
    databricks_table: str
    columns: list[str]  # Optional: Column-level if available
```

## Module Responsibilities

- `auth.py`: OAuth2 token acquisition.
- `scanner.py`: Async PBI Scanner API client. Focuses on **Semantic Model** entities.
- `transform.py`: Normalizes raw PBI JSON. Identifies "Opaque" vs "Evaluatable" models.
- `push.py`: Databricks BYOL API client. Creates nodes for **Semantic Models**.
- `cli.py`: Orchestration.

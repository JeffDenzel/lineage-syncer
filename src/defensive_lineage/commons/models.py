from __future__ import annotations

from pydantic import BaseModel, Field


class LineageMapping(BaseModel):
    """Schema for a single lineage link between a PBI report and a Databricks table.

    Attributes:
        pbi_workspace_id (str): The unique GUID of the Power BI workspace.
        pbi_workspace_name (str): The display name of the Power BI workspace.
        pbi_report_id (str): The unique GUID of the Power BI report.
        pbi_report_name (str): The display name of the Power BI report.
        pbi_dataset_id (str): The unique GUID of the underlying Power BI dataset.
        pbi_dataset_name (str): The display name of the Power BI dataset.
        endorsement (str): The endorsement status (ex:"Certified", "Promoted").
        connection_mode (str): The dataset content provider type, from the
            Scanner API ``contentProviderType`` (ex:"PbixInImportMode",
            "PbixInDirectQueryMode").
        storage_mode (str): The dataset target storage mode, from the Scanner
            API ``targetStorageMode`` (ex:"Abf", "DirectQuery").
        databricks_catalog (str): The Unity Catalog catalog name.
        databricks_schema (str): The Unity Catalog schema name.
        databricks_table (str): The Unity Catalog table name.
        columns (list[str]): List of column names used in the dataset.
    """

    # Power BI side
    pbi_workspace_id: str
    pbi_workspace_name: str
    pbi_report_id: str
    pbi_report_name: str
    pbi_dataset_id: str
    pbi_dataset_name: str
    endorsement: str
    connection_mode: str
    storage_mode: str

    # Databricks side
    databricks_catalog: str
    databricks_schema: str
    databricks_table: str
    columns: list[str]


class PushSummary(BaseModel):
    """Outcome of a Unity Catalog lineage push operation.

    Attributes:
        total (int): Total number of lineage mappings processed.
        succeeded (int): Number of mappings pushed successfully.
        failed (int): Number of mappings that raised an error.
        skipped (int): Number of mappings skipped (e.g. during a dry run).
        errors (list[str]): Human-readable messages for each failure.
    """

    total: int
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    errors: list[str] = Field(default_factory=list)

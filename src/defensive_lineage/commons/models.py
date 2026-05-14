from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator


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
        connection_mode (str): The content provider type (ex:"PbixInDirectQueryMode").
        storage_mode (str): The dataset storage mode (ex:"Abf", "DirectQuery").
        databricks_catalog (str): The Unity Catalog catalog name.
        databricks_schema (str): The Unity Catalog schema name.
        databricks_table (str): The Unity Catalog table name.
        columns (list[str]): List of column names used in the dataset.
    """

    model_config = ConfigDict(frozen=True)

    # Power BI side
    pbi_workspace_id: str
    pbi_workspace_name: str
    pbi_report_id: str
    pbi_report_name: str
    pbi_dataset_id: str
    pbi_dataset_name: str
    endorsement: str
    connection_mode: str  # From contentProviderType (e.g., PbixInDirectQueryMode)
    storage_mode: str  # From targetStorageMode (e.g., Abf, DirectQuery)

    # Databricks side
    databricks_catalog: str
    databricks_schema: str
    databricks_table: str
    columns: list[str]

    @field_validator("endorsement")
    @classmethod
    def validate_endorsement(cls, v: str) -> str:
        """Validate that endorsement is either 'Certified' or 'Promoted'."""
        allowed = {"Certified", "Promoted"}
        if v not in allowed:
            raise ValueError(f"endorsement must be one of {allowed}, got {v}")
        return v


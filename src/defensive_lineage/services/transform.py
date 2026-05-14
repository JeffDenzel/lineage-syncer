from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..commons.models import LineageMapping

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DatabricksCoordinate:
    """A resolved catalog.schema.table reference.

    Attributes:
        catalog: The Unity Catalog catalog name.
        schema: The Unity Catalog schema name.
        table: The Unity Catalog table name.
    """

    catalog: str
    schema: str
    table: str


def _build_datasource_index(
    datasource_instances: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Build a lookup dict: datasourceInstanceId → datasource instance.

    Args:
        datasource_instances: The top-level datasourceInstances array
            from the scan result.

    Returns:
        Dict mapping datasource instance IDs to their full instance dicts,
        including connectionDetails.
    """
    index: dict[str, dict[str, Any]] = {}
    seen_ids: set[str] = set()

    for instance in datasource_instances:
        instance_id = instance.get("datasourceInstanceId") or instance.get(
            "datasourceId"
        )
        if not instance_id:
            continue

        if instance_id in seen_ids:
            logger.warning(
                "Duplicate datasourceInstanceId '%s' found. Last one wins.",
                instance_id,
            )
        seen_ids.add(instance_id)
        index[instance_id] = instance

    logger.debug("Indexed %d datasource instances", len(index))
    return index


def _parse_databricks_coordinate(
    connection_details: dict[str, str],
    table_name: str,
) -> DatabricksCoordinate | None:
    """Parse Databricks catalog/schema/table from PBI connection details.

    Supports two Databricks connection formats:
    1. Standard SQL connector: server="*.azuredatabricks.net", database="catalog"
    2. DatabricksMultiCloud extension: extensionDataSourcePath with JSON

    Resolution strategy for standard format:
    - database="gold" + table="revenue" → catalog=gold, schema=default, table=revenue
    - database="gold.finance" + table="revenue" →
        catalog=gold, schema=finance, table=revenue
    - database="gold" + table="finance.revenue" →
        catalog=gold, schema=finance, table=revenue

    Args:
        connection_details: Dict with connection info (varies by datasource type).
        table_name: The table name from the dataset (may include schema prefix).

    Returns:
        DatabricksCoordinate with resolved catalog, schema, and table.
        Returns None if not a Databricks source or parsing fails.
    """
    server = connection_details.get("server", "")
    database = connection_details.get("database", "")

    extension_path = connection_details.get("extensionDataSourcePath", "")
    if extension_path:
        try:
            import json

            ext_config = json.loads(extension_path)
            host = ext_config.get("host", "")
            http_path = ext_config.get("httpPath", "")
            logger.debug(
                "DatabricksMultiCloud host=%s, httpPath=%s", host, http_path
            )
            # Fall through to table name parsing
            server = host  # Use host for Databricks detection
        except json.JSONDecodeError:
            logger.warning(
                "Failed to parse extensionDataSourcePath: %s", extension_path
            )
            return None

    is_databricks = (
        server.endswith(".azuredatabricks.net")
        or server.endswith(".databricks.net")
        or server.startswith("dbc-")
    )
    if not is_databricks:
        logger.debug("Non-Databricks server '%s', skipping", server)
        return None

    # For DatabricksMultiCloud without database field, table must include catalog.schema
    if not database and not table_name:
        logger.debug("Missing database and table_name, skipping")
        return None

    catalog = ""
    schema_from_db = None
    if database:
        db_parts = database.split(".")
        if len(db_parts) == 1:
            catalog = db_parts[0]
        elif len(db_parts) == 2:
            catalog = db_parts[0]
            schema_from_db = db_parts[1]
        else:
            logger.warning("Unexpected database format '%s', skipping", database)
            return None

    # Handle backtick-quoted and space-separated table names from Power BI
    clean_table_name = table_name.replace("`", "").strip()
    clean_table_name = " ".join(clean_table_name.split())  # Normalize whitespace

    # Handle "catalog schema table" or "catalog.schema.table" formats
    if " " in clean_table_name and "." not in clean_table_name:
        # Space-separated: "catalog schema table"
        table_parts = clean_table_name.split(" ")
    else:
        # Dot-separated: "catalog.schema.table" or "schema.table" or "table"
        table_parts = clean_table_name.split(".")
    if len(table_parts) == 1:
        if not catalog:
            # No database and no catalog in table - can't determine catalog
            logger.warning(
                "Table '%s' has no catalog info (no database field, "
                "no catalog.schema.table format)",
                table_name,
            )
            return None
        schema = schema_from_db if schema_from_db else "default"
        table = table_parts[0]
    elif len(table_parts) == 2:
        # schema.table format
        if not catalog:
            logger.warning(
                "Table '%s' missing catalog (expected catalog.schema.table)",
                table_name,
            )
            return None
        # Table has schema prefix, database is just catalog
        schema = table_parts[0]
        table = table_parts[1]
    elif len(table_parts) == 3:
        # catalog.schema.table format (common for DatabricksMultiCloud)
        catalog = table_parts[0]
        schema = table_parts[1]
        table = table_parts[2]
    else:
        logger.warning("Unexpected table name format '%s', skipping", table_name)
        return None

    coordinate = DatabricksCoordinate(
        catalog=catalog,
        schema=schema,
        table=table,
    )
    logger.debug(
        "Parsed coordinate: catalog=%s, schema=%s, table=%s "
        "from database=%s, table_name=%s",
        catalog,
        schema,
        table,
        database,
        table_name,
    )
    return coordinate


def _create_mappings_for_dataset(
    dataset: dict[str, Any],
    workspace_id: str,
    workspace_name: str,
    report_id: str,
    report_name: str,
    endorsement: str,
    datasource_index: dict[str, dict[str, Any]],
) -> list[LineageMapping]:
    """Create LineageMapping objects for a dataset.

    Args:
        dataset: The dataset dict from the scan result.
        workspace_id: The workspace ID containing the dataset.
        workspace_name: The workspace name containing the dataset.
        report_id: The report ID (or dataset ID if no report).
        report_name: The report name (or dataset name if no report).
        endorsement: The endorsement status (Certified/Promoted).
        datasource_index: Lookup dict for datasource instances.

    Returns:
        List of LineageMapping objects for this dataset's tables.
    """
    mappings: list[LineageMapping] = []
    dataset_id = dataset.get("id", "")
    dataset_name = dataset.get("name", "")
    # Use contentProviderType for connection_mode, targetStorageMode for storage_mode
    # These are separate concepts in Power BI
    connection_mode = dataset.get("contentProviderType", "Unknown")
    storage_mode = dataset.get("targetStorageMode", "Unknown")

    # Get datasource usages
    datasource_usages = dataset.get("datasourceUsages", [])
    if not datasource_usages:
        logger.warning(
            "Dataset '%s' (%s) has no datasourceUsages, skipping",
            dataset_name,
            dataset_id,
        )
        return mappings

    tables = dataset.get("tables", [])

    # Process each datasource usage
    for usage in datasource_usages:
        ds_instance_id = usage.get("datasourceInstanceId", "")
        ds_instance = datasource_index.get(ds_instance_id)

        if not ds_instance:
            logger.warning(
                "Dataset '%s' references unknown "
                "datasourceInstanceId '%s', skipping",
                dataset_id,
                ds_instance_id,
            )
            continue

        connection_details = ds_instance.get("connectionDetails", {})

        # Process each table in the dataset
        for table in tables:
            table_name = table.get("name", "")
            columns_data = table.get("columns", [])
            column_names = [
                col.get("name") for col in columns_data if col.get("name")
            ]

            # Parse Databricks coordinate
            coordinate = _parse_databricks_coordinate(
                connection_details, table_name
            )

            if not coordinate:
                # Non-Databricks source or unparseable - skip this table
                continue

            # Create LineageMapping
            mapping = LineageMapping(
                pbi_workspace_id=workspace_id,
                pbi_workspace_name=workspace_name,
                pbi_report_id=report_id,
                pbi_report_name=report_name,
                pbi_dataset_id=dataset_id,
                pbi_dataset_name=dataset_name,
                endorsement=endorsement,
                connection_mode=connection_mode,
                storage_mode=storage_mode,
                databricks_catalog=coordinate.catalog,
                databricks_schema=coordinate.schema,
                databricks_table=coordinate.table,
                columns=column_names,
            )
            mappings.append(mapping)

    return mappings


def normalize_pbi_scan_result(
    scan_result: dict[str, Any],
) -> list[LineageMapping]:
    """Transform raw Power BI Scanner API result into LineageMapping objects.

    This function takes the raw Scanner API response (with workspaces and
    datasourceInstances) and produces a flat list of LineageMapping objects
    linking PBI reports/datasets to Databricks tables.

    Creates lineage for:
    - Reports → their datasets → Databricks tables
    - Datasets without reports (using dataset as the "asset")

    Args:
        scan_result: Raw dict from Scanner API with 'workspaces' and
            'datasourceInstances' keys.

    Returns:
        List of LineageMapping objects representing all valid lineage links.
    """
    workspaces = scan_result.get("workspaces", [])
    datasource_instances = scan_result.get("datasourceInstances", [])

    # Build datasource lookup index
    datasource_index = _build_datasource_index(datasource_instances)

    # Build cross-workspace dataset lookup for resolving external dataset refs
    dataset_index: dict[str, dict[str, Any]] = {}  # dataset_id -> dataset info
    for workspace in workspaces:
        workspace_id = workspace.get("id", "")
        for dataset in workspace.get("datasets", []):
            dataset_id = dataset.get("id", "")
            if dataset_id:
                dataset_index[dataset_id] = {
                    "dataset": dataset,
                    "workspace_id": workspace_id,
                    "workspace_name": workspace.get("name", ""),
                }

    mappings: list[LineageMapping] = []
    total_reports = 0
    skipped_datasets = 0
    processed_dataset_ids: set[str] = set()

    for workspace in workspaces:
        workspace_id = workspace.get("id", "")
        workspace_name = workspace.get("name", "")
        reports = workspace.get("reports", [])
        datasets = workspace.get("datasets", [])

        # Build dataset lookup for this workspace
        workspace_dataset_index: dict[str, dict[str, Any]] = {}
        for ds in datasets:
            ds_id = ds.get("id", "")
            if ds_id:
                workspace_dataset_index[ds_id] = ds

        # Process reports and their datasets
        for report in reports:
            total_reports += 1
            report_id = report.get("id", "")
            report_name = report.get("name", "")
            dataset_id = report.get("datasetId", "")

            if not dataset_id:
                logger.warning(
                    "Report '%s' (%s) has no datasetId, skipping",
                    report_name,
                    report_id,
                )
                continue

            # Find the dataset (may be in this workspace or another)
            dataset_info = workspace_dataset_index.get(dataset_id)
            if not dataset_info:
                # Try cross-workspace lookup
                dataset_info = dataset_index.get(dataset_id)
                if dataset_info:
                    dataset = dataset_info["dataset"]
                    ds_workspace_id = dataset_info["workspace_id"]
                    ds_workspace_name = dataset_info["workspace_name"]
                else:
                    logger.warning(
                        "Report '%s' (%s) references unknown dataset '%s', "
                        "skipping",
                        report_name,
                        report_id,
                        dataset_id,
                    )
                    continue
            else:
                dataset = dataset_info
                ds_workspace_id = workspace_id
                ds_workspace_name = workspace_name

            # Get endorsement from report (fallback to dataset if not present)
            endorsement = report.get("endorsementDetails", {}).get(
                "endorsement", ""
            )
            if not endorsement:
                endorsement = dataset.get(
                    "endorsementDetails", {}
                ).get("endorsement", "")

            if not endorsement:
                logger.debug(
                    "Dataset '%s' has no endorsement, skipping "
                    "(scanner should have filtered)",
                    dataset_id,
                )
                skipped_datasets += 1
                continue

            # Create mappings for this report's dataset
            report_mappings = _create_mappings_for_dataset(
                dataset=dataset,
                workspace_id=ds_workspace_id,
                workspace_name=ds_workspace_name,
                report_id=report_id,
                report_name=report_name,
                endorsement=endorsement,
                datasource_index=datasource_index,
            )
            mappings.extend(report_mappings)
            processed_dataset_ids.add(dataset_id)

        # Process datasets without reports (orphan datasets)
        for dataset in datasets:
            dataset_id = dataset.get("id", "")
            if dataset_id in processed_dataset_ids:
                continue  # Already processed via a report

            # Get endorsement from dataset
            endorsement = dataset.get("endorsementDetails", {}).get(
                "endorsement", ""
            )
            if not endorsement:
                logger.debug(
                    "Dataset '%s' has no endorsement, skipping "
                    "(scanner should have filtered)",
                    dataset_id,
                )
                skipped_datasets += 1
                continue

            logger.info(
                "Processing dataset '%s' without associated report",
                dataset.get("name", ""),
            )

            # Create mappings using dataset info as "report" info
            # (since there's no report, the dataset IS the asset)
            dataset_mappings = _create_mappings_for_dataset(
                dataset=dataset,
                workspace_id=workspace_id,
                workspace_name=workspace_name,
                report_id=dataset_id,  # Use dataset ID as report ID
                report_name=dataset.get("name", ""),  # Use dataset name
                endorsement=endorsement,
                datasource_index=datasource_index,
            )
            mappings.extend(dataset_mappings)
            processed_dataset_ids.add(dataset_id)

    logger.info(
        "Transformation complete: %d reports processed, "
        "%d mappings produced, %d datasets skipped",
        total_reports,
        len(mappings),
        skipped_datasets,
    )
    return mappings



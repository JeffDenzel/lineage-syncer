from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from ..commons.models import LineageMapping

logger = logging.getLogger(__name__)

DATABRICKS_SERVER_PATTERNS = (".azuredatabricks.net", ".databricks.net", "dbc-")


@dataclass(frozen=True)
class DatabricksCoordinate:
    """A fully-qualified Unity Catalog table reference.

    Attributes:
        catalog (str): The Unity Catalog catalog name.
        schema (str): The Unity Catalog schema name.
        table (str): The Unity Catalog table name.
    """

    catalog: str
    schema: str
    table: str


def _build_datasource_index(
    datasource_instances: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Index datasource instances by their ID for fast lookup.

    The Scanner API uses ``datasourceId`` on the instance object itself, while
    dataset ``datasourceUsages`` reference ``datasourceInstanceId``. Both keys
    hold the same value so we index under whichever is present.

    Args:
        datasource_instances (list[dict[str, Any]]): The raw
            ``datasourceInstances`` list from the Scanner API result.

    Returns:
        dict[str, dict[str, Any]]: A lookup mapping each ID to its instance.
    """
    index: dict[str, dict[str, Any]] = {}
    for instance in datasource_instances:
        instance_id = instance.get("datasourceInstanceId") or instance.get(
            "datasourceId"
        )
        if instance_id:
            index[instance_id] = instance
    return index


def _resolve_server(connection_details: dict[str, Any]) -> str:
    """Resolve the server hostname from connection details.

    Handles both the standard ``server`` field and the
    ``extensionDataSourcePath`` used by the DatabricksMultiCloud connector.

    Args:
        connection_details (dict[str, Any]): The ``connectionDetails`` dict
            of a datasource instance.

    Returns:
        str: The resolved server hostname, or an empty string if none found.
    """
    server = connection_details.get("server", "")

    extension = connection_details.get("extensionDataSourcePath")
    if extension:
        try:
            if isinstance(extension, str):
                extension = json.loads(extension)
            host = extension.get("host", "")
            http_path = extension.get("httpPath", "")
            logger.debug("DatabricksMultiCloud host=%s, httpPath=%s", host, http_path)
            if host:
                server = host
        except (ValueError, AttributeError) as exc:
            logger.warning("Failed to parse extensionDataSourcePath: %s", exc)

    return server


def _parse_databricks_coordinate(
    connection_details: dict[str, Any],
    table_name: str,
) -> DatabricksCoordinate | None:
    """Resolve a Databricks Unity Catalog coordinate from PBI connection info.

    Combines the datasource ``database`` field with the dataset table name to
    derive ``catalog``, ``schema``, and ``table``. Examples:

    - database="gold.finance" + table="revenue" →
      catalog=gold, schema=finance, table=revenue
    - database="gold" + table="finance.revenue" →
      catalog=gold, schema=finance, table=revenue
    - database="" + table="gold.finance.revenue" →
      catalog=gold, schema=finance, table=revenue

    Args:
        connection_details (dict[str, Any]): Connection info for the datasource
            (varies by datasource type).
        table_name (str): The table name from the dataset (may include a
            schema or catalog prefix, and may be backtick-quoted).

    Returns:
        DatabricksCoordinate | None: The resolved coordinate, or ``None`` if
            the source is not Databricks or the coordinate cannot be parsed.
    """
    server = _resolve_server(connection_details)
    if not any(pattern in server for pattern in DATABRICKS_SERVER_PATTERNS):
        logger.debug("Non-Databricks server '%s', skipping", server)
        return None

    database = connection_details.get("database", "")

    # Strip backticks; normalize whitespace
    stripped = table_name.replace("`", "").strip()
    # Scanner API may emit space-separated parts: "cat schema table"
    # If no dots but multiple space-delimited tokens, treat as dot-separated
    if "." not in stripped and " " in stripped:
        stripped = ".".join(stripped.split())
    clean_table = " ".join(stripped.split())

    if not database and not clean_table:
        logger.debug("Missing database and table_name, skipping")
        return None

    table_parts = clean_table.split(".") if clean_table else []

    if database:
        db_parts = database.split(".")
        if len(db_parts) == 2:
            catalog, schema = db_parts
            table = table_parts[-1] if table_parts else ""
        elif len(db_parts) == 1:
            catalog = db_parts[0]
            if len(table_parts) >= 2:
                schema, table = table_parts[-2], table_parts[-1]
            elif len(table_parts) == 1:
                schema, table = "default", table_parts[0]
            else:
                logger.debug("Table '%s' missing catalog/schema", clean_table)
                return None
        else:
            logger.debug("Unexpected database format '%s', skipping", database)
            return None
    else:
        if len(table_parts) == 3:
            catalog, schema, table = table_parts
        elif len(table_parts) < 3:
            logger.debug(
                "Table '%s' has no catalog info "
                "(no database field, no catalog.schema.table format)",
                clean_table,
            )
            return None
        else:
            logger.debug("Unexpected table name format '%s', skipping", clean_table)
            return None

    if not catalog:
        logger.debug(
            "Table '%s' missing catalog (expected catalog.schema.table)",
            clean_table,
        )
        return None

    logger.debug(
        "Parsed coordinate: catalog=%s, schema=%s, table=%s "
        "from database=%s, table_name=%s",
        catalog,
        schema,
        table,
        database,
        clean_table,
    )
    return DatabricksCoordinate(catalog=catalog, schema=schema, table=table)


def _create_mappings_for_dataset(
    dataset: dict[str, Any],
    workspace_id: str,
    workspace_name: str,
    report_id: str,
    report_name: str,
    endorsement: str,
    datasource_index: dict[str, dict[str, Any]],
) -> list[LineageMapping]:
    """Create LineageMapping objects for a single dataset's Databricks tables.

    Args:
        dataset (dict[str, Any]): The dataset dict from the scan result.
        workspace_id (str): The workspace ID containing the dataset.
        workspace_name (str): The workspace name containing the dataset.
        report_id (str): The report ID (or dataset ID if no report).
        report_name (str): The report name (or dataset name if no report).
        endorsement (str): The endorsement status (Certified/Promoted).
        datasource_index (dict[str, dict[str, Any]]): Lookup of datasource
            instances by ``datasourceInstanceId``.

    Returns:
        list[LineageMapping]: Lineage mappings for this dataset's tables.
    """
    dataset_id = dataset.get("id", "")
    dataset_name = dataset.get("name", "")
    connection_mode = dataset.get("contentProviderType", "Unknown")
    storage_mode = dataset.get("targetStorageMode", "Unknown")

    usages = dataset.get("datasourceUsages", [])
    if not usages:
        logger.debug(
            "Dataset '%s' (%s) has no datasourceUsages, skipping",
            dataset_name,
            dataset_id,
        )
        return []

    tables = dataset.get("tables", [])
    mappings: list[LineageMapping] = []

    for usage in usages:
        instance_id = usage.get("datasourceInstanceId")
        instance = datasource_index.get(instance_id)
        if instance is None:
            logger.debug(
                "Dataset '%s' references unknown datasourceInstanceId '%s', skipping",
                dataset_name,
                instance_id,
            )
            continue

        connection_details = instance.get("connectionDetails", {})
        for table in tables:
            coordinate = _parse_databricks_coordinate(
                connection_details, table.get("name", "")
            )
            if coordinate is None:
                continue

            columns = [
                col.get("name", "")
                for col in table.get("columns", [])
                if col.get("name")
            ]
            mappings.append(
                LineageMapping(
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
                    columns=columns,
                )
            )

    return mappings


def normalize_pbi_scan_result(
    scan_result: dict[str, Any],
) -> list[LineageMapping]:
    """Transform a raw Power BI Scanner API result into LineageMapping objects.

    Takes the raw Scanner API response (with ``workspaces`` and
    ``datasourceInstances``) and produces a flat list of LineageMapping objects
    linking PBI reports/datasets to Databricks tables.

    Creates lineage for:
    - Reports → their datasets → Databricks tables.
    - Datasets without reports (using the dataset as the asset).

    Args:
        scan_result (dict[str, Any]): Raw dict from the Scanner API with
            ``workspaces`` and ``datasourceInstances`` keys.

    Returns:
        list[LineageMapping]: All valid lineage links discovered.
    """
    workspaces = scan_result.get("workspaces", [])
    datasource_index = _build_datasource_index(
        scan_result.get("datasourceInstances", [])
    )

    mappings: list[LineageMapping] = []
    reports_processed = 0
    datasets_skipped = 0

    for workspace in workspaces:
        workspace_id = workspace.get("id", "")
        workspace_name = workspace.get("name", "")
        datasets = workspace.get("datasets", [])
        dataset_by_id = {ds.get("id"): ds for ds in datasets}
        consumed_dataset_ids: set[str] = set()

        for report in workspace.get("reports", []):
            reports_processed += 1
            report_id = report.get("id", "")
            report_name = report.get("name", "")

            dataset_id = report.get("datasetId")
            if not dataset_id:
                logger.debug(
                    "Report '%s' (%s) has no datasetId, skipping",
                    report_name,
                    report_id,
                )
                continue

            dataset = dataset_by_id.get(dataset_id)
            if dataset is None:
                logger.debug(
                    "Report '%s' (%s) references unknown dataset '%s', skipping",
                    report_name,
                    report_id,
                    dataset_id,
                )
                continue

            endorsement = dataset.get("endorsementDetails", {}).get("endorsement")
            if not endorsement:
                logger.debug(
                    "Dataset '%s' has no endorsement, skipping "
                    "(scanner should have filtered)",
                    dataset_id,
                )
                continue

            consumed_dataset_ids.add(dataset_id)
            mappings.extend(
                _create_mappings_for_dataset(
                    dataset,
                    workspace_id,
                    workspace_name,
                    report_id,
                    report_name,
                    endorsement,
                    datasource_index,
                )
            )

        for dataset in datasets:
            dataset_id = dataset.get("id", "")
            if dataset_id in consumed_dataset_ids:
                continue

            endorsement = dataset.get("endorsementDetails", {}).get("endorsement")
            if not endorsement:
                datasets_skipped += 1
                continue

            logger.debug(
                "Processing dataset '%s' without associated report", dataset_id
            )
            mappings.extend(
                _create_mappings_for_dataset(
                    dataset,
                    workspace_id,
                    workspace_name,
                    dataset_id,
                    dataset.get("name", ""),
                    endorsement,
                    datasource_index,
                )
            )

    logger.info(
        "Transformation complete: %d reports processed, "
        "%d mappings produced, %d datasets skipped",
        reports_processed,
        len(mappings),
        datasets_skipped,
    )
    return mappings

from __future__ import annotations

import logging
import re
from typing import Iterable

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import (
    DatabricksError,
    ResourceAlreadyExists,
    ResourceConflict,
)
from databricks.sdk.service.catalog import (
    ColumnRelationship,
    CreateRequestExternalLineage,
    ExternalLineageExternalMetadata,
    ExternalLineageObject,
    ExternalLineageTable,
    ExternalMetadata,
    SystemType,
)

from ..commons.exceptions import PushError
from ..commons.models import LineageMapping, PushSummary

logger = logging.getLogger(__name__)

# Unity Catalog external metadata classification for Power BI assets.
SYSTEM_TYPE = SystemType.POWER_BI
ENTITY_TYPE = "dashboard"

# Exceptions that indicate the object already exists (idempotent success).
_CONFLICT_ERRORS = (ResourceAlreadyExists, ResourceConflict)


def _sanitize_name_part(value: str) -> str:
    """Reduce a string to alphanumeric characters and underscores.

    Any run of characters that are not alphanumeric is collapsed to a single
    underscore, and leading/trailing underscores are stripped.

    Args:
        value (str): The raw string to sanitize.

    Returns:
        str: The sanitized, underscore-delimited string.
    """
    return re.sub(r"[^0-9A-Za-z]+", "_", value).strip("_")


def _build_external_name(workspace_name: str, report_name: str) -> str:
    """Build a deterministic external metadata name.

    Unity Catalog external metadata names may contain only alphanumeric
    characters and underscores (no spaces, periods, or slashes). Each component
    is sanitized accordingly. The result is stable across runs, making creation
    idempotent.

    Args:
        workspace_name (str): The Power BI workspace display name.
        report_name (str): The Power BI report/dataset display name.

    Returns:
        str: A name of the form ``powerbi_{workspace}_{report}``.
    """
    workspace = _sanitize_name_part(workspace_name)
    report = _sanitize_name_part(report_name)
    return f"powerbi_{workspace}_{report}"


def _create_external_metadata(
    client: WorkspaceClient,
    mapping: LineageMapping,
    name: str,
) -> None:
    """Register a Power BI report as an external metadata object.

    Treats an already-existing object as success so the operation is
    idempotent across repeated runs.

    Args:
        client (WorkspaceClient): An authenticated Databricks client.
        mapping (LineageMapping): The lineage mapping describing the PBI asset.
        name (str): The deterministic external metadata name.

    Raises:
        PushError: If the Databricks API returns a non-conflict error.
    """
    description = (
        f"Power BI report '{mapping.pbi_report_name}' "
        f"in workspace '{mapping.pbi_workspace_name}'"
    )
    properties = {
        "pbi_workspace_id": mapping.pbi_workspace_id,
        "pbi_report_id": mapping.pbi_report_id,
        "pbi_dataset_id": mapping.pbi_dataset_id,
        "endorsement": mapping.endorsement,
        "connection_mode": mapping.connection_mode,
        "storage_mode": mapping.storage_mode,
    }
    try:
        client.external_metadata.create_external_metadata(
            ExternalMetadata(
                name=name,
                system_type=SYSTEM_TYPE,
                entity_type=ENTITY_TYPE,
                columns=mapping.columns or None,
                description=description,
                properties=properties,
            )
        )
        logger.info("Created external metadata '%s'", name)
    except _CONFLICT_ERRORS:
        logger.info("External metadata '%s' already exists, skipping", name)
    except DatabricksError as exc:
        raise PushError(
            f"Failed to create external metadata '{name}': {exc}"
        ) from exc


def _create_lineage_link(
    client: WorkspaceClient,
    mapping: LineageMapping,
    external_name: str,
) -> None:
    """Link a Databricks table (source) to a PBI external entity (target).

    Establishes the Databricks table as upstream of the Power BI report so the
    report appears as a downstream consumer in the Unity Catalog lineage graph.
    Column-level relationships are added when columns are available.

    Args:
        client (WorkspaceClient): An authenticated Databricks client.
        mapping (LineageMapping): The lineage mapping to link.
        external_name (str): The external metadata name created beforehand.

    Raises:
        PushError: If the Databricks API returns a non-conflict error.
    """
    table_name = (
        f"{mapping.databricks_catalog}."
        f"{mapping.databricks_schema}."
        f"{mapping.databricks_table}"
    )
    source = ExternalLineageObject(table=ExternalLineageTable(name=table_name))
    target = ExternalLineageObject(
        external_metadata=ExternalLineageExternalMetadata(name=external_name)
    )
    columns = [
        ColumnRelationship(source=column, target=column)
        for column in mapping.columns
    ] or None

    try:
        client.external_lineage.create_external_lineage_relationship(
            CreateRequestExternalLineage(
                source=source,
                target=target,
                columns=columns,
            )
        )
        logger.info("Linked %s -> %s", table_name, external_name)
    except _CONFLICT_ERRORS:
        logger.info(
            "Lineage link %s -> %s already exists, skipping",
            table_name,
            external_name,
        )
    except DatabricksError as exc:
        raise PushError(
            f"Failed to link {table_name} -> {external_name}: {exc}"
        ) from exc


def push_lineage(
    client: WorkspaceClient,
    mappings: Iterable[LineageMapping],
    dry_run: bool = False,
) -> PushSummary:
    """Push normalized lineage mappings to Databricks Unity Catalog.

    For each mapping, registers the Power BI report as external metadata
    (deduplicated by name) and links the Databricks table to it. Individual
    failures are recorded and do not abort the run.

    Args:
        client (WorkspaceClient): An authenticated Databricks client.
        mappings (Iterable[LineageMapping]): Validated lineage mappings.
        dry_run (bool): If ``True``, log intended actions without writing.

    Returns:
        PushSummary: Counts of succeeded, failed, and skipped mappings plus
            any error messages.
    """
    mappings_list = list(mappings)
    summary = PushSummary(total=len(mappings_list))
    created_metadata: set[str] = set()

    logger.info(
        "Pushing %d mappings to Databricks%s...",
        summary.total,
        " (dry run)" if dry_run else "",
    )

    for mapping in mappings_list:
        name = _build_external_name(
            mapping.pbi_workspace_name, mapping.pbi_report_name
        )
        table_name = (
            f"{mapping.databricks_catalog}."
            f"{mapping.databricks_schema}."
            f"{mapping.databricks_table}"
        )

        if dry_run:
            logger.info("[DRY-RUN] Would link %s -> %s", table_name, name)
            summary.skipped += 1
            continue

        try:
            if name not in created_metadata:
                _create_external_metadata(client, mapping, name)
                created_metadata.add(name)
            _create_lineage_link(client, mapping, name)
            summary.succeeded += 1
        except PushError as exc:
            summary.failed += 1
            summary.errors.append(str(exc))
            logger.error("Push failed for %s: %s", table_name, exc)

    logger.info(
        "Push complete: %d succeeded, %d failed, %d skipped",
        summary.succeeded,
        summary.failed,
        summary.skipped,
    )
    return summary

from __future__ import annotations

import json
import logging
import sys

import click
from dotenv import load_dotenv
from pydantic import ValidationError

from .commons.exceptions import AuthenticationError, ScanTimeoutError
from .commons.models import LineageMapping, PushSummary
from .commons.settings import Settings, load_settings
from .orchestrators.pbi_scanner import ScannerClient
from .orchestrators.uc_pusher import DatabricksLineageClient
from .services.auth import get_databricks_client, get_pbi_token
from .services.transform import normalize_pbi_scan_result

load_dotenv()

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


@click.group()
@click.option(
    "--log-level",
    default=None,
    help="Override the DL_LOG_LEVEL environment variable.",
)
def cli(log_level: str | None) -> None:
    """Parent command for all CLI commands, formats logging structure for all commands,
    and allows for optional log level override.

    Args:
        log_level (str | None): Override the DL_LOG_LEVEL environment variable.
    """
    level = log_level or "INFO"
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def _load_settings_or_exit() -> Settings:
    """Load settings from the environment, exiting with code 1 on failure.

    Returns:
        Settings: The validated application settings.

    Raises:
        SystemExit: If any required environment variable is missing or invalid.
    """
    try:
        settings = load_settings()
    except (ValueError, ValidationError) as exc:
        click.echo(f"[ERROR] Failed to load settings: {exc}", err=True)
        sys.exit(1)
    click.echo("[OK] Settings loaded")
    return settings


@cli.command("verify-auth")
def verify_auth() -> None:
    """Verify authentication to both Databricks and Power BI.

    Loads settings from environment variables, then attempts to acquire
    tokens for both platforms. Prints a clear success/failure status for each and
    exits with code 1 if any authentication fails.

    Raises:
        SystemExit: If settings loading fails or if authentication fails.
    """
    success = True

    # --- 1. Settings --------------------------------------------------------
    settings = _load_settings_or_exit()

    # --- 2. Databricks ------------------------------------------------------
    try:
        get_databricks_client(settings)
        click.echo(
            f"[OK] Databricks authenticated (workspace: {settings.databricks_host})"
        )
    except AuthenticationError as exc:
        click.echo(f"[ERROR] Databricks authentication failed: {exc}", err=True)
        success = False

    # --- 3. Power BI --------------------------------------------------------
    try:
        get_pbi_token(settings)
        click.echo("[OK] Power BI token acquired")
    except AuthenticationError as exc:
        click.echo(f"[ERROR] Power BI token acquisition failed: {exc}", err=True)
        success = False

    # --- Summary ------------------------------------------------------------
    click.echo("")
    if success:
        click.echo("All systems authenticated successfully.")
    else:
        click.echo("Authentication failed. See errors above.", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--output",
    default="scan_output.jsonl",
    help="Path to save the raw JSONL scan results.",
)
def scan(output: str) -> None:
    """Run Power BI metadata extraction (Phase 2).

    Args:
        output (str): Path to save the raw JSONL scan results.

    Raises:
        SystemExit: If settings loading, authentication, or scanning fails.
    """
    settings = _load_settings_or_exit()

    try:
        click.echo("Starting Power BI scan flow...")
        token = get_pbi_token(settings)
        scanner = ScannerClient(token, settings)
        workspaces = scanner.run_full_scan()

        workspaces_count = 0
        with open(output, "w") as f:
            for workspace in workspaces:
                f.write(json.dumps(workspace) + "\n")
                workspaces_count += 1

        click.echo("[OK] Scan completed successfully")
        click.echo(f"[OK] Processed {workspaces_count} workspaces with endorsed assets")
        click.echo(f"[OK] Results saved to {output}")

    except AuthenticationError as exc:
        click.echo(f"[ERROR] Authentication failed: {exc}", err=True)
        sys.exit(1)
    except ScanTimeoutError as exc:
        click.echo(f"[ERROR] Scan failed: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(f"[ERROR] Unexpected error: {exc}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--input",
    "input_path",
    default="scan_output.jsonl",
    help="Path to the raw JSONL scan results produced by `scan`.",
)
@click.option(
    "--output",
    default="mappings.jsonl",
    help="Path to save the normalized LineageMapping JSONL.",
)
def transform(input_path: str, output: str) -> None:
    """Normalize raw Power BI scan results into lineage mappings (Phase 3).

    Reads the raw JSONL emitted by `scan`, reassembles it into a single
    Scanner API result, and writes one LineageMapping per line to ``output``.

    Args:
        input_path (str): Path to the raw JSONL scan results.
        output (str): Path to save the normalized LineageMapping JSONL.

    Raises:
        SystemExit: If the input file cannot be read or transformation fails.
    """
    try:
        workspaces: list[dict] = []
        datasource_instances: list[dict] = []
        with open(input_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                if record.get("type") == "datasourceInstances":
                    datasource_instances.extend(record.get("instances", []))
                else:
                    workspaces.append(record)

        scan_result = {
            "workspaces": workspaces,
            "datasourceInstances": datasource_instances,
        }
        mappings = normalize_pbi_scan_result(scan_result)

        with open(output, "w") as f:
            for mapping in mappings:
                f.write(mapping.model_dump_json() + "\n")

        click.echo(f"[OK] Transformed {len(mappings)} lineage mappings")
        click.echo(f"[OK] Results saved to {output}")

    except FileNotFoundError:
        click.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(f"[ERROR] Transformation failed: {exc}", err=True)
        sys.exit(1)


def _load_mappings(input_path: str) -> list[LineageMapping]:
    """Load LineageMapping objects from a JSONL file.

    Args:
        input_path (str): Path to the mappings JSONL produced by `transform`.

    Returns:
        list[LineageMapping]: The parsed and validated mappings.
    """
    mappings: list[LineageMapping] = []
    with open(input_path) as f:
        for line in f:
            line = line.strip()
            if line:
                mappings.append(LineageMapping.model_validate_json(line))
    return mappings


def _scan_and_transform(settings: Settings) -> list[LineageMapping]:
    """Run scan and transform in-memory, returning lineage mappings.

    Args:
        settings (Settings): The validated application settings.

    Returns:
        list[LineageMapping]: Normalized lineage mappings.
    """
    token = get_pbi_token(settings)
    scanner = ScannerClient(token, settings)

    workspaces: list[dict] = []
    datasource_instances: list[dict] = []
    for item in scanner.run_full_scan():
        if item.get("type") == "datasourceInstances":
            datasource_instances.extend(item.get("instances", []))
        else:
            workspaces.append(item)

    return normalize_pbi_scan_result(
        {"workspaces": workspaces, "datasourceInstances": datasource_instances}
    )


def _echo_push_summary(summary: PushSummary) -> None:
    """Print a PushSummary to the console.

    Args:
        summary (PushSummary): The result counts from a push operation.
    """
    click.echo(
        f"[OK] Push complete: {summary.succeeded} succeeded, "
        f"{summary.failed} failed, {summary.skipped} skipped "
        f"(of {summary.total})"
    )
    for error in summary.errors:
        click.echo(f"[ERROR] {error}", err=True)


@cli.command()
@click.option(
    "--input",
    "input_path",
    default="mappings.jsonl",
    help="Path to the LineageMapping JSONL produced by `transform`.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Validate and log intended actions without writing to Databricks.",
)
def push(input_path: str, dry_run: bool) -> None:
    """Push lineage mappings to Databricks Unity Catalog (Phase 4).

    Reads the local mappings JSONL and registers each Power BI report as
    external metadata, then links it to its Databricks table.

    Args:
        input_path (str): Path to the mappings JSONL.
        dry_run (bool): If set, perform no writes to Databricks.

    Raises:
        SystemExit: If settings, auth, or input loading fails.
    """
    settings = _load_settings_or_exit()

    try:
        mappings = _load_mappings(input_path)
    except FileNotFoundError:
        click.echo(f"[ERROR] Input file not found: {input_path}", err=True)
        sys.exit(1)

    try:
        client = get_databricks_client(settings)
        pusher = DatabricksLineageClient(client)
        summary = pusher.push_lineage(mappings, dry_run=dry_run)
        _echo_push_summary(summary)
    except AuthenticationError as exc:
        click.echo(f"[ERROR] Authentication failed: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(f"[ERROR] Push failed: {exc}", err=True)
        sys.exit(1)


@cli.command()
def sync() -> None:
    """Run the full pipeline: scan → transform → push (Phase 4).

    Executes the entire end-to-end lineage extraction and injection process
    in-memory, writing the resulting lineage to Unity Catalog.

    Raises:
        SystemExit: If settings, auth, scanning, or pushing fails.
    """
    settings = _load_settings_or_exit()

    try:
        click.echo("Running full sync (scan -> transform -> push)...")
        mappings = _scan_and_transform(settings)
        click.echo(f"[OK] Produced {len(mappings)} lineage mappings")

        client = get_databricks_client(settings)
        pusher = DatabricksLineageClient(client)
        summary = pusher.push_lineage(mappings, dry_run=False)
        _echo_push_summary(summary)
    except AuthenticationError as exc:
        click.echo(f"[ERROR] Authentication failed: {exc}", err=True)
        sys.exit(1)
    except ScanTimeoutError as exc:
        click.echo(f"[ERROR] Scan failed: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(f"[ERROR] Sync failed: {exc}", err=True)
        sys.exit(1)


@cli.command("dry-run")
def dry_run() -> None:
    """Run the full pipeline without writing to Databricks (Phase 4).

    Executes scan and transform, then simulates the push so the intended
    lineage links are logged without mutating Unity Catalog.

    Raises:
        SystemExit: If settings, auth, or scanning fails.
    """
    settings = _load_settings_or_exit()

    try:
        click.echo("Running dry-run (scan -> transform -> simulated push)...")
        mappings = _scan_and_transform(settings)
        click.echo(f"[OK] Produced {len(mappings)} lineage mappings")

        client = get_databricks_client(settings)
        pusher = DatabricksLineageClient(client)
        summary = pusher.push_lineage(mappings, dry_run=True)
        _echo_push_summary(summary)
    except AuthenticationError as exc:
        click.echo(f"[ERROR] Authentication failed: {exc}", err=True)
        sys.exit(1)
    except ScanTimeoutError as exc:
        click.echo(f"[ERROR] Scan failed: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(f"[ERROR] Dry-run failed: {exc}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entrypoint registered in pyproject.toml."""
    cli()


if __name__ == "__main__":
    main()

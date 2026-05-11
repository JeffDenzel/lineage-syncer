from __future__ import annotations

import json
import logging
import sys

import click
from dotenv import load_dotenv

from .services.auth import get_databricks_client, get_pbi_token
from .orchestrators.pbi_scanner import ScannerClient
from .commons.exceptions import AuthenticationError, ScanTimeoutError
from .commons.settings import Settings, load_settings

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
    try:
        settings: Settings = load_settings()
        click.echo("[OK] Settings loaded from environment")
    except Exception as exc:  # noqa: BLE001 — pydantic ValidationError is not specific
        click.echo(f"[ERROR] Failed to load settings: {exc}", err=True)
        sys.exit(1)

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
    try:
        settings: Settings = load_settings()
        click.echo("[OK] Settings loaded")
    except Exception as exc:  # noqa: BLE001
        click.echo(f"[ERROR] Failed to load settings: {exc}", err=True)
        sys.exit(1)

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
def push() -> None:
    """Push metadata to Databricks Unity Catalog (Phase 4).

    Reads the local JSONL mappings and synchronizes them to Unity Catalog.
    Currently a stub; not yet implemented.
    """
    click.echo("Pushing to Databricks... (not yet implemented)")


@cli.command()
def sync() -> None:
    """Run full pipeline: scan → transform → push (Phase 4).

    Executes the entire end-to-end lineage extraction and injection process.
    Currently a stub; not yet implemented.
    """
    click.echo("Running full sync... (not yet implemented)")


@cli.command("dry-run")
def dry_run() -> None:
    """Run full pipeline without writing to Databricks (Phase 4).

    Executes the pipeline up to the transform phase, validating data but
    preventing any mutations to Unity Catalog.
    Currently a stub; not yet implemented.
    """
    click.echo("Running dry-run... (not yet implemented)")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entrypoint registered in pyproject.toml."""
    cli()


if __name__ == "__main__":
    main()

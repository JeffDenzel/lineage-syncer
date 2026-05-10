from __future__ import annotations

import logging
import sys

import click
from dotenv import load_dotenv

from .auth import get_databricks_client, get_pbi_token
from .exceptions import AuthenticationError
from .settings import Settings, load_settings

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
    """Defensive Lineage: Bridge Power BI into Databricks Unity Catalog."""
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
    tokens for both platforms. Prints a clear ✓/✗ status for each and
    exits with code 1 if any authentication fails.
    """
    success = True

    # --- 1. Settings --------------------------------------------------------
    try:
        settings: Settings = load_settings()
        click.echo("✓ Settings loaded from environment")
    except Exception as exc:  # noqa: BLE001 — pydantic ValidationError is not specific
        click.echo(f"✗ Failed to load settings: {exc}", err=True)
        sys.exit(1)

    # --- 2. Databricks ------------------------------------------------------
    try:
        get_databricks_client(settings)
        click.echo(f"✓ Databricks authenticated (workspace: {settings.databricks_host})")
    except AuthenticationError as exc:
        click.echo(f"✗ Databricks authentication failed: {exc}", err=True)
        success = False

    # --- 3. Power BI --------------------------------------------------------
    try:
        get_pbi_token(settings)
        click.echo("✓ Power BI token acquired")
    except AuthenticationError as exc:
        click.echo(f"✗ Power BI token acquisition failed: {exc}", err=True)
        success = False

    # --- Summary ------------------------------------------------------------
    click.echo("")
    if success:
        click.echo("All systems authenticated successfully.")
    else:
        click.echo("Authentication failed. See errors above.", err=True)
        sys.exit(1)


@cli.command()
def scan() -> None:
    """Run Power BI metadata extraction (Phase 2)."""
    click.echo("Scanning Power BI... (not yet implemented)")


@cli.command()
def push() -> None:
    """Push metadata to Databricks Unity Catalog (Phase 4)."""
    click.echo("Pushing to Databricks... (not yet implemented)")


@cli.command()
def sync() -> None:
    """Run full pipeline: scan → transform → push (Phase 4)."""
    click.echo("Running full sync... (not yet implemented)")


@cli.command("dry-run")
def dry_run() -> None:
    """Run full pipeline without writing to Databricks (Phase 4)."""
    click.echo("Running dry-run... (not yet implemented)")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entrypoint registered in pyproject.toml."""
    cli()


if __name__ == "__main__":
    main()

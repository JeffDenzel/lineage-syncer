from __future__ import annotations

import logging
from typing import Any

import click
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

@click.group()
def cli() -> None:
    """Defensive Lineage: Bridge Power BI into Databricks Unity Catalog."""
    logging.basicConfig(level=logging.INFO)

@cli.command()
def scan() -> None:
    """Run Power BI metadata extraction."""
    click.echo("Scanning Power BI...")

@cli.command()
def push() -> None:
    """Push metadata to Databricks."""
    click.echo("Pushing to Databricks...")

@cli.command()
def sync() -> None:
    """Run full pipeline (scan -> transform -> push)."""
    click.echo("Running full sync...")

def main() -> None:
    """CLI Entrypoint."""
    cli()

if __name__ == "__main__":
    main()

from __future__ import annotations

import logging
import os

from pydantic import BaseModel, ValidationError, field_validator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

_REQUIRED_VARS: tuple[str, ...] = (
    "AZURE_TENANT_ID",
    "AZURE_CLIENT_ID",
    "AZURE_CLIENT_SECRET",
    "DATABRICKS_HOST",
    "DATABRICKS_CLIENT_ID",
    "DATABRICKS_CLIENT_SECRET",
)


# ---------------------------------------------------------------------------
# Settings model
# ---------------------------------------------------------------------------


class Settings(BaseModel):
    """Validated configuration loaded from environment variables.

    All fields map directly to the environment variable names defined in
    ``ARCHITECTURE.md``. Required fields raise ``ValidationError`` if absent.
    Optional fields default to the values specified in ``ARCHITECTURE.md``.

    This model is intentionally read-only after construction — treat it as
    an immutable snapshot of the environment at startup.
    """

    model_config = {"frozen": True}

    # -- Azure / Power BI ------------------------------------------------
    azure_tenant_id: str
    azure_client_id: str
    azure_client_secret: str

    # -- Databricks ------------------------------------------------------
    databricks_host: str
    databricks_client_id: str
    databricks_client_secret: str

    # -- App settings (optional, with defaults from ARCHITECTURE.md) -----
    dl_log_level: str = "INFO"
    dl_scan_timeout: int = 300
    dl_dry_run: bool = False

    @field_validator("databricks_host")
    @classmethod
    def _normalize_host(cls, v: str) -> str:
        """Strip trailing slashes from the Databricks host URL.

        Args:
            v: Raw host string from the environment.

        Returns:
            Host string with trailing slashes removed.
        """
        return v.rstrip("/")

    @field_validator("dl_log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        """Ensure dl_log_level is a valid Python logging level name.

        Args:
            v: Raw log level string.

        Returns:
            Upper-cased log level string.

        Raises:
            ValueError: If the level name is not recognized by ``logging``.
        """
        upper = v.upper()
        if upper not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(
                f"Invalid log level '{v}'. EX: DEBUG, INFO, WARNING, ERROR, CRITICAL"
            )
        return upper


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------


def load_settings() -> Settings:
    """Load and validate application settings from environment variables.

    Reads directly from ``os.environ``. The caller (``cli.py``) is
    responsible for loading ``.env`` via ``python-dotenv`` before calling
    this function.

    Returns:
        A validated, immutable ``Settings`` instance.

    Raises:
        ValueError: If any required environment variable is missing.
        ValidationError: If any present value fails Pydantic validation.
    """
    # Check for missing required environment variables
    missing = [key for key in _REQUIRED_VARS if key not in os.environ]
    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}"
        )

    # Collect required string fields
    str_fields: dict[str, str] = {
        key.lower(): os.environ[key] for key in _REQUIRED_VARS
    }

    # Collect and parse optional fields with their correct types
    dl_log_level: str = os.environ.get("DL_LOG_LEVEL", "INFO")
    dl_scan_timeout: int = int(os.environ.get("DL_SCAN_TIMEOUT", "300"))
    dl_dry_run: bool = os.environ.get("DL_DRY_RUN", "false").lower() in {
        "1",
        "true",
        "yes",
    }  # noqa: E501

    try:
        settings = Settings(
            **str_fields,
            dl_log_level=dl_log_level,
            dl_scan_timeout=dl_scan_timeout,
            dl_dry_run=dl_dry_run,
        )
    except ValidationError:
        logger.error(
            "Settings validation failed. Required environment variables: %s",
            ", ".join(_REQUIRED_VARS),
        )
        raise

    logger.debug("Settings loaded successfully.")
    return settings

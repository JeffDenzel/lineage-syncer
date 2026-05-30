from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from pbi_dbx_lineage_push.commons.settings import Settings, load_settings

# ---------------------------------------------------------------------------
# Settings model tests
# ---------------------------------------------------------------------------


def test_load_settings_with_all_vars() -> None:
    """Happy path: all required env vars present → returns valid Settings."""
    env = {
        "AZURE_TENANT_ID": "tenant-123",
        "AZURE_CLIENT_ID": "client-abc",
        "AZURE_CLIENT_SECRET": "secret-xyz",
        "DATABRICKS_HOST": "https://adb-1234.azuredatabricks.net",
        "DATABRICKS_CLIENT_ID": "dbx-client",
        "DATABRICKS_CLIENT_SECRET": "dbx-secret",
    }
    with patch.dict(os.environ, env, clear=True):
        settings = load_settings()

    assert settings.azure_tenant_id == "tenant-123"
    assert settings.azure_client_id == "client-abc"
    assert settings.databricks_host == "https://adb-1234.azuredatabricks.net"


def test_load_settings_applies_defaults() -> None:
    """Optional env vars absent → Settings uses defaults from ARCHITECTURE.md."""
    env = {
        "AZURE_TENANT_ID": "tenant-123",
        "AZURE_CLIENT_ID": "client-abc",
        "AZURE_CLIENT_SECRET": "secret-xyz",
        "DATABRICKS_HOST": "https://adb-1234.azuredatabricks.net",
        "DATABRICKS_CLIENT_ID": "dbx-client",
        "DATABRICKS_CLIENT_SECRET": "dbx-secret",
    }
    with patch.dict(os.environ, env, clear=True):
        settings = load_settings()

    assert settings.dl_log_level == "INFO"
    assert settings.dl_scan_timeout == 300
    assert settings.dl_dry_run is False


def test_load_settings_optional_vars_override_defaults() -> None:
    """Optional env vars present → Settings uses the provided values."""
    env = {
        "AZURE_TENANT_ID": "tenant-123",
        "AZURE_CLIENT_ID": "client-abc",
        "AZURE_CLIENT_SECRET": "secret-xyz",
        "DATABRICKS_HOST": "https://adb-1234.azuredatabricks.net",
        "DATABRICKS_CLIENT_ID": "dbx-client",
        "DATABRICKS_CLIENT_SECRET": "dbx-secret",
        "DL_LOG_LEVEL": "DEBUG",
        "DL_SCAN_TIMEOUT": "600",
        "DL_DRY_RUN": "true",
    }
    with patch.dict(os.environ, env, clear=True):
        settings = load_settings()

    assert settings.dl_log_level == "DEBUG"
    assert settings.dl_scan_timeout == 600
    assert settings.dl_dry_run is True


def test_load_settings_raises_on_missing_databricks_host() -> None:
    """Error path: DATABRICKS_HOST missing → raises ValidationError."""
    env = {
        "AZURE_TENANT_ID": "tenant-123",
        "AZURE_CLIENT_ID": "client-abc",
        "AZURE_CLIENT_SECRET": "secret-xyz",
        # DATABRICKS_HOST intentionally absent
        "DATABRICKS_CLIENT_ID": "dbx-client",
        "DATABRICKS_CLIENT_SECRET": "dbx-secret",
    }
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(ValueError):
            load_settings()


def test_load_settings_raises_on_missing_azure_secret() -> None:
    """Error path: AZURE_CLIENT_SECRET missing → raises ValidationError."""
    env = {
        "AZURE_TENANT_ID": "tenant-123",
        "AZURE_CLIENT_ID": "client-abc",
        # AZURE_CLIENT_SECRET intentionally absent
        "DATABRICKS_HOST": "https://adb-1234.azuredatabricks.net",
        "DATABRICKS_CLIENT_ID": "dbx-client",
        "DATABRICKS_CLIENT_SECRET": "dbx-secret",
    }
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(ValueError):
            load_settings()


# ---------------------------------------------------------------------------
# Settings model validator tests
# ---------------------------------------------------------------------------


def test_settings_normalizes_databricks_host_trailing_slash() -> None:
    """Databricks host with trailing slash is normalized on construction."""
    settings = Settings(
        azure_tenant_id="t",
        azure_client_id="c",
        azure_client_secret="s",
        databricks_host="https://adb-1234.azuredatabricks.net/",
        databricks_client_id="d",
        databricks_client_secret="ds",
    )
    assert settings.databricks_host == "https://adb-1234.azuredatabricks.net"


def test_settings_raises_on_invalid_log_level() -> None:
    """Invalid DL_LOG_LEVEL value → raises ValidationError."""
    with pytest.raises(ValidationError, match="Invalid log level"):
        Settings(
            azure_tenant_id="t",
            azure_client_id="c",
            azure_client_secret="s",
            databricks_host="https://adb-1234.azuredatabricks.net",
            databricks_client_id="d",
            databricks_client_secret="ds",
            dl_log_level="VERBOSE",  # not a valid Python log level
        )


def test_settings_is_frozen() -> None:
    """Settings object is immutable — attribute assignment raises."""
    settings = Settings(
        azure_tenant_id="t",
        azure_client_id="c",
        azure_client_secret="s",
        databricks_host="https://adb-1234.azuredatabricks.net",
        databricks_client_id="d",
        databricks_client_secret="ds",
    )
    # Frozen model raises TypeError when attempting to modify
    with pytest.raises(TypeError):
        settings.dl_log_level = "DEBUG"  # type: ignore[misc]

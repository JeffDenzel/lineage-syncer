from __future__ import annotations

import pytest

from pbi_dbx_lineage_push.commons.settings import Settings


@pytest.fixture()
def settings() -> Settings:
    """Return a fully-populated Settings object with test credentials."""
    return Settings(
        azure_tenant_id="00000000-0000-0000-0000-000000000001",
        azure_client_id="00000000-0000-0000-0000-000000000002",
        azure_client_secret="fake-azure-secret",
        databricks_host="https://adb-test.azuredatabricks.net",
        databricks_client_id="fake-dbx-client-id",
        databricks_client_secret="fake-dbx-client-secret",
        dl_scan_timeout=5,
    )

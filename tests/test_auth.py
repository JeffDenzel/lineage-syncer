from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import responses as resp

from defensive_lineage.services.auth import PBI_SCOPE, get_databricks_client, get_pbi_token
from defensive_lineage.commons.exceptions import AuthenticationError
from defensive_lineage.commons.settings import Settings

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAKE_TENANT_ID = "00000000-0000-0000-0000-000000000001"
FAKE_CLIENT_ID = "00000000-0000-0000-0000-000000000002"
FAKE_CLIENT_SECRET = "super-secret"
FAKE_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.fake.token"
ENTRA_URL = f"https://login.microsoftonline.com/{FAKE_TENANT_ID}/oauth2/v2.0/token"


@pytest.fixture()
def settings() -> Settings:
    """Return a fully-populated Settings object with test credentials."""
    return Settings(
        azure_tenant_id=FAKE_TENANT_ID,
        azure_client_id=FAKE_CLIENT_ID,
        azure_client_secret=FAKE_CLIENT_SECRET,
        databricks_host="https://adb-test.azuredatabricks.net",
        databricks_client_id="dbx-client-id",
        databricks_client_secret="dbx-client-secret",
    )


# ---------------------------------------------------------------------------
# get_pbi_token tests
# ---------------------------------------------------------------------------


@resp.activate
def test_get_pbi_token_returns_valid_token(settings: Settings) -> None:
    """Happy path: Entra returns 200 with access_token → function returns it."""
    resp.add(
        resp.POST,
        ENTRA_URL,
        json={"access_token": FAKE_TOKEN, "expires_in": 3599, "token_type": "Bearer"},
        status=200,
    )

    token = get_pbi_token(settings)

    assert token == FAKE_TOKEN


@resp.activate
def test_get_pbi_token_raises_on_401(settings: Settings) -> None:
    """Error path: Entra returns 401 → raises AuthenticationError."""
    resp.add(
        resp.POST,
        ENTRA_URL,
        json={"error": "invalid_client", "error_description": "Bad credentials"},
        status=401,
    )

    with pytest.raises(AuthenticationError, match="401"):
        get_pbi_token(settings)


@resp.activate
def test_get_pbi_token_raises_on_403(settings: Settings) -> None:
    """Error path: Entra returns 403, raises AuthenticationError."""
    resp.add(
        resp.POST,
        ENTRA_URL,
        json={"error": "access_denied"},
        status=403,
    )

    with pytest.raises(AuthenticationError, match="403"):
        get_pbi_token(settings)


@resp.activate
def test_get_pbi_token_raises_on_missing_access_token(settings: Settings) -> None:
    """Error path: Entra returns 200 but response has no access_token field."""
    resp.add(
        resp.POST,
        ENTRA_URL,
        json={"token_type": "Bearer"},  # missing access_token
        status=200,
    )

    with pytest.raises(AuthenticationError, match="access_token"):
        get_pbi_token(settings)


@resp.activate
def test_get_pbi_token_raises_on_network_error(settings: Settings) -> None:
    """Error path: Connection refused → raises AuthenticationError."""
    resp.add(
        resp.POST,
        ENTRA_URL,
        body=ConnectionError("Connection refused"),
    )

    with pytest.raises(AuthenticationError, match="network error"):
        get_pbi_token(settings)


@resp.activate
def test_get_pbi_token_uses_correct_scope(settings: Settings) -> None:
    """The POST body must contain the Power BI API scope."""
    resp.add(
        resp.POST,
        ENTRA_URL,
        json={"access_token": FAKE_TOKEN, "expires_in": 3599},
        status=200,
    )

    get_pbi_token(settings)

    assert len(resp.calls) == 1
    body = resp.calls[0].request.body
    assert isinstance(body, str)
    assert (
        f"scope={PBI_SCOPE.replace('/', '%2F').replace(':', '%3A')}" in body
        or f"scope={PBI_SCOPE}" in body
    )


@resp.activate
def test_get_pbi_token_uses_correct_grant_type(settings: Settings) -> None:
    """The POST body must use grant_type=client_credentials."""
    resp.add(
        resp.POST,
        ENTRA_URL,
        json={"access_token": FAKE_TOKEN, "expires_in": 3599},
        status=200,
    )

    get_pbi_token(settings)

    body = resp.calls[0].request.body
    assert isinstance(body, str)
    assert "grant_type=client_credentials" in body


# ---------------------------------------------------------------------------
# get_databricks_client tests
# ---------------------------------------------------------------------------


def test_get_databricks_client_returns_client(settings: Settings) -> None:
    """Happy path: SDK authenticates and me() returns, returns WorkspaceClient."""
    mock_me = MagicMock()
    mock_me.user_name = "service-principal@tenant.com"

    with patch("defensive_lineage.auth.WorkspaceClient") as mock_ws_cls:
        mock_client = MagicMock()
        mock_client.current_user.me.return_value = mock_me
        mock_ws_cls.return_value = mock_client

        result = get_databricks_client(settings)

        assert result is mock_client
        mock_ws_cls.assert_called_once_with(
            host=settings.databricks_host,
            client_id=settings.databricks_client_id,
            client_secret=settings.databricks_client_secret,
        )
        mock_client.current_user.me.assert_called_once()


def test_get_databricks_client_raises_on_auth_failure(settings: Settings) -> None:
    """Error path: WorkspaceClient constructor raises → AuthenticationError."""
    with patch("defensive_lineage.auth.WorkspaceClient") as mock_ws_cls:
        mock_ws_cls.side_effect = ValueError("invalid credentials")

        with pytest.raises(AuthenticationError, match="Databricks auth failed"):
            get_databricks_client(settings)


def test_get_databricks_client_raises_on_me_failure(settings: Settings) -> None:
    """Error path: current_user.me() raises, raises AuthenticationError."""
    with patch("defensive_lineage.services.auth.WorkspaceClient") as mock_ws_cls:
        mock_client = MagicMock()
        mock_client.current_user.me.side_effect = PermissionError("Not authorized")
        mock_ws_cls.return_value = mock_client

        with pytest.raises(AuthenticationError, match="Databricks auth failed"):
            get_databricks_client(settings)

from __future__ import annotations

import logging

import requests
from databricks.sdk import WorkspaceClient

from ..commons.exceptions import AuthenticationError
from ..commons.settings import Settings

logger = logging.getLogger(__name__)

# --- Constants ---

PBI_SCOPE = "https://analysis.windows.net/powerbi/api/.default"
_ENTRA_TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
_REQUEST_TIMEOUT_SECONDS = 30


# --- Public functions ---

def get_databricks_client(settings: Settings) -> WorkspaceClient:
    """Initialize and validate an authenticated Databricks WorkspaceClient.

    Uses OAuth2 M2M (client_credentials) via the Databricks SDK. The SDK
    handles token acquisition and automatic refresh internally.

    Validates the connection by calling ``current_user.me()`` — a lightweight
    read-only API call that confirms both authentication and network access.

    Args:
        settings: Validated application settings containing Databricks
            ``host``, ``client_id``, and ``client_secret``.

    Returns:
        An authenticated and validated ``WorkspaceClient`` instance.

    Raises:
        AuthenticationError: If the client fails to authenticate or the
            validation call returns an error.
    """
    logger.info("Authenticating to Databricks workspace: %s", settings.databricks_host)
    try:
        client = WorkspaceClient(
            host=settings.databricks_host,
            client_id=settings.databricks_client_id,
            client_secret=settings.databricks_client_secret,
        )
        # Lightweight validation — confirms credentials are accepted
        me = client.current_user.me()
        logger.info(
            "Databricks authentication successful. Authenticated as: %s",
            getattr(me, "user_name", "unknown"),
        )
        return client
    except Exception as exc:
        logger.error("Databricks authentication failed: %s", exc)
        raise AuthenticationError(f"Databricks auth failed: {exc}") from exc


def get_pbi_token(settings: Settings) -> str:
    """Acquire a bearer token for the Power BI Admin API.

    Performs an OAuth2 ``client_credentials`` grant against Microsoft
    Entra ID. The returned token is scoped to the Power BI service and
    is suitable for all calls to ``https://api.powerbi.com/v1.0/myorg/admin/``.

    No additional libraries (``azure-identity``, ``msal``) are required —
    this function uses only the ``requests`` library already in the project
    dependencies.

    Args:
        settings: Validated application settings containing
            ``azure_tenant_id``, ``azure_client_id``, and
            ``azure_client_secret``.

    Returns:
        A bearer token string. Valid for approximately 3600 seconds.

    Raises:
        AuthenticationError: If the HTTP request fails, the token endpoint
            returns a non-200 status, or the response body does not contain
            an ``access_token`` field.
    """
    url = _ENTRA_TOKEN_URL.format(tenant_id=settings.azure_tenant_id)
    payload = {
        "grant_type": "client_credentials",
        "client_id": settings.azure_client_id,
        "client_secret": settings.azure_client_secret,
        "scope": PBI_SCOPE,
    }

    logger.info("Acquiring Power BI token for tenant: %s", settings.azure_tenant_id)

    try:
        response = requests.post(url, data=payload, timeout=_REQUEST_TIMEOUT_SECONDS)
    except (requests.exceptions.ConnectionError, ConnectionError) as exc:
        logger.error("Network error acquiring PBI token: %s", exc)
        raise AuthenticationError(
            f"PBI token request failed (network error): {exc}"
        ) from exc  # noqa: E501
    except requests.exceptions.Timeout as exc:
        logger.error("Timeout acquiring PBI token after %ss", _REQUEST_TIMEOUT_SECONDS)
        raise AuthenticationError("PBI token request timed out") from exc

    if response.status_code != 200:
        logger.error(
            "PBI token request failed. Status: %s, Body: %s",
            response.status_code,
            response.text,
        )
        raise AuthenticationError(
            f"PBI token request failed ({response.status_code}): {response.text}"
        )

    body = response.json()
    token: str | None = body.get("access_token")

    if not token:
        logger.error(
            "PBI token response missing 'access_token'. Body keys: %s",
            list(body.keys()),
        )  # noqa: E501
        raise AuthenticationError(
            "PBI token response did not contain 'access_token'. "
            f"Response keys: {list(body.keys())}"
        )

    expires_in: int = body.get("expires_in", 0)
    logger.info(
        "Power BI token acquired successfully (expires in %ss, prefix: %s...)",
        expires_in,
        token[:8],
    )
    return token

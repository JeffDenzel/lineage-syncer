from __future__ import annotations


class DefensiveLineageError(Exception):
    """Base exception for all Defensive Lineage errors.

    All project-specific exceptions inherit from this class so that
    callers can catch the entire exception hierarchy with a single
    ``except DefensiveLineageError`` clause if needed.
    """


class AuthenticationError(DefensiveLineageError):
    """Raised when authentication to any platform fails.

    This covers both Databricks OAuth2 M2M failures and Microsoft
    Entra ID client-credentials grant failures for Power BI.
    """


class ScanTimeoutError(DefensiveLineageError):
    """Raised when a Power BI Scanner API scan exceeds the timeout.

    Reserved for Phase 2 (Scanner). Defined here so that all custom
    exceptions are co-located and importable from a single module.
    """


class PushError(DefensiveLineageError):
    """Raised when a Databricks Unity Catalog lineage push fails.

    Reserved for Phase 4 (BYOL Push). Defined here so that all custom
    exceptions are co-located and importable from a single module.
    """

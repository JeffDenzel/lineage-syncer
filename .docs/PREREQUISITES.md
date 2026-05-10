# Defensive Lineage — Prerequisites

*This document lists all platform requirements and Python library dependencies needed to develop, test, and run the Defensive Lineage tool.*

---

## 1. Platform Prerequisites

### 1.1 Python Runtime

| Requirement | Details |
|-------------|---------|
| **Python Version** | `3.11` or higher |
| **Package Manager** | `pip` (managed via `pyproject.toml`; no `setup.py`) |
| **Virtual Environment** | `venv` (standard library — no Conda) |

### 1.2 Databricks Workspace

| Requirement | Details |
|-------------|---------|
| **Databricks Workspace** | An active Databricks workspace with Unity Catalog enabled |
| **Service Principal** | A Databricks Service Principal configured under *Settings > Identities* |
| **Service Principal Permissions** | The SP must have permissions to call the External Lineage / BYOL API and read/write Unity Catalog metadata |
| **Unity Catalog** | At least one catalog and schema must exist for lineage injection targets |

### 1.3 Power BI / Microsoft Fabric

| Requirement | Details |
|-------------|---------|
| **Power BI Tenant** | An active Power BI tenant with at least one workspace containing certified or promoted assets |
| **Admin API Access** | The Databricks Service Principal must be granted permission to call the Power BI Admin Scanner API (v1.0) |
| **Tenant Setting** | "Allow service principals to use Power BI APIs" must be enabled in the Power BI Admin Portal |
| **Security Group** | The Service Principal should be added to an Azure AD security group that is allowed API access in the tenant settings |

### 1.4 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABRICKS_HOST` | Yes | Databricks workspace URL (e.g., `https://adb-xxxx.azuredatabricks.net`) |
| `DATABRICKS_CLIENT_ID` | Yes | Databricks Service Principal client ID |
| `DATABRICKS_CLIENT_SECRET` | Yes | Databricks Service Principal client secret |
| `DL_LOG_LEVEL` | No | Logging level (default: `INFO`) |
| `DL_SCAN_TIMEOUT` | No | Maximum seconds to wait for a PBI scan (default: `300`) |
| `DL_DRY_RUN` | No | Set to `true` to disable writes (default: `false`) |

### 1.5 CI/CD (Optional — Phase 5)

| Requirement | Details |
|-------------|---------|
| **GitHub Repository** | Repository with GitHub Actions enabled |
| **GitHub Secrets** | `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET` stored as repository secrets |
| **GitHub Actions Runner** | Ubuntu latest (default hosted runner) |

---

## 2. Python Library Prerequisites

### 2.1 Core Dependencies (Required at Runtime)

| Package | Purpose |
|---------|---------|
| `databricks-sdk` | Databricks Service Principal authentication via OAuth2 client credentials flow; REST API client for Unity Catalog and BYOL endpoints |
| `requests` | HTTP client for Power BI Admin Scanner API calls and Databricks REST API interactions |
| `pydantic` | Data validation and schema enforcement for the `LineageMapping` data model and configuration objects |
| `click` | CLI framework for building the `defensive-lineage` command-line interface (`scan`, `push`, `sync`, `dry-run` commands) |

### 2.2 Development Dependencies (Dev/Test Only)

| Package | Purpose |
|---------|---------|
| `pytest` | Test framework for running unit and integration tests |
| `pytest-cov` | Coverage reporting plugin for pytest (minimum target: 80% on transformation logic) |
| `black` | Opinionated code formatter (default settings, line length 88) |
| `ruff` | Fast Python linter — replaces flake8, isort, and pyflakes |
| `mypy` | Static type checker (run in strict mode) |
| `responses` | Library for mocking HTTP responses in tests (ensures no real API calls during testing) |

### 2.3 Quick Install

> [!TIP]
> Once `pyproject.toml` is set up, install everything in one command.

**Runtime only:**
```bash
pip install .
```

**Runtime + Development:**
```bash
pip install ".[dev]"
```

**Manual install (all packages):**
```bash
pip install databricks-sdk requests pydantic click pytest pytest-cov black ruff mypy responses
```

---

## 3. Prerequisites Checklist

| # | Prerequisite | Category | Status |
|---|-------------|----------|--------|
| 1 | Python 3.11+ installed | Platform | ☐ |
| 2 | Virtual environment created (`venv`) | Platform | ☐ |
| 3 | Databricks workspace with Unity Catalog | Platform | ☐ |
| 4 | Databricks Service Principal provisioned | Platform | ☐ |
| 5 | Power BI tenant with Scanner API access enabled | Platform | ☐ |
| 6 | Service Principal added to PBI-allowed security group | Platform | ☐ |
| 7 | Environment variables configured | Platform | ☐ |
| 8 | `databricks-sdk` installed | Python Library | ☐ |
| 9 | `requests` installed | Python Library | ☐ |
| 10 | `pydantic` installed | Python Library | ☐ |
| 11 | `click` installed | Python Library | ☐ |
| 12 | Dev dependencies installed (`pytest`, `black`, `ruff`, `mypy`, etc.) | Python Library | ☐ |
| 13 | GitHub repo with Actions + Secrets (Phase 5) | CI/CD | ☐ |

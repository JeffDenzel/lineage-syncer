# Defensive Lineage — Coding Conventions

## Language & Runtime

- **Language:** Python 3.11+
- **Package Manager:** `pip` with `pyproject.toml` (no `setup.py`)
- **Virtual Environment:** `venv` (standard library, no conda)

---

## Project Structure

```
defensive-lineage/
├── .agent/                  # Agent definitions for AI-assisted development
│   ├── planner.md
│   ├── reviewer.md
│   └── implementer.md
├── .docs/                   # Project documentation
│   ├── ROADMAP.md
│   ├── CONVENTIONS.md
│   └── ARCHITECTURE.md
├── .github/
│   └── workflows/
│       └── sync-lineage.yml # GitHub Actions pipeline
├── src/
│   └── defensive_lineage/
│       ├── __init__.py
│       ├── auth.py          # Authentication for PBI + Databricks
│       ├── scanner.py       # Power BI Scanner API client
│       ├── transform.py     # JSON transformation logic
│       ├── push.py          # Databricks BYOL API client
│       └── cli.py           # CLI entrypoint (click or argparse)
├── tests/
│   ├── __init__.py
│   ├── test_auth.py
│   ├── test_scanner.py
│   ├── test_transform.py
│   └── test_push.py
├── pyproject.toml
├── README.md
└── .gitignore
```

---

## Naming Conventions

### Files & Modules
- All lowercase, underscores: `scanner.py`, `test_transform.py`
- No abbreviations in filenames unless universally understood (`auth` is fine, `trnsfrm` is not)

### Functions & Variables
- `snake_case` for all functions and variables: `get_access_token()`, `scan_result`
- Prefix private/internal functions with a single underscore: `_parse_dataset_entry()`
- Boolean variables start with `is_`, `has_`, or `should_`: `is_certified`, `has_lineage`

### Classes
- `PascalCase`: `ScannerClient`, `LineageMapping`
- No suffixes like `Manager`, `Handler`, `Helper` — name classes after what they **are**, not what they **do**

### Constants
- `UPPER_SNAKE_CASE`: `MAX_POLL_RETRIES`, `SCANNER_API_BASE_URL`
- All constants live at the top of the module they belong to

---

## Code Style

### Formatting
- **Formatter:** `black` (default settings, line length 88)
- **Linter:** `ruff` (replaces flake8, isort, pyflakes)
- **Type Checker:** `mypy` (strict mode)

### Type Hints
- **Required** on all public function signatures (parameters and return types)
- Use `from __future__ import annotations` at the top of every module
- Prefer built-in generics: `list[str]` over `List[str]`, `dict[str, Any]` over `Dict[str, Any]`

### Docstrings
- **Required** on all public functions and classes
- Use Google-style docstrings:

```python
def get_access_token(client_id: str, client_secret: str, tenant_id: str) -> str:
    """Acquire an OAuth2 bearer token from Azure Entra ID.

    Uses the MSAL client credentials flow to authenticate as a
    service principal. The returned token is valid for Power BI
    Admin API calls.

    Args:
        client_id: The Azure App Registration client ID.
        client_secret: The client secret associated with the app.
        tenant_id: The Azure tenant ID.

    Returns:
        A bearer token string.

    Raises:
        AuthenticationError: If the token request fails.
    """
```

### Error Handling
- **Never** use bare `except:` or `except Exception:`
- Define custom exceptions in a `exceptions.py` module when needed
- Always log the error before re-raising
- Use `httpx` or `requests` response status checks — never silently ignore HTTP errors

### Logging
- Use the standard `logging` module, never `print()` for operational output
- Use `print()` only in the CLI entrypoint for user-facing output
- Log levels:
  - `DEBUG` — API request/response details
  - `INFO` — High-level progress ("Scanning workspace: Finance...")
  - `WARNING` — Non-fatal issues ("Dataset has no lineage metadata, skipping")
  - `ERROR` — Failures that stop a single item but not the whole run
  - `CRITICAL` — Failures that stop the entire pipeline

---

## Dependencies

### Core (Required)
| Package | Purpose |
|---------|---------|
| `databricks-sdk` | Databricks Service Principal auth + REST API client |
| `requests` | HTTP client for REST APIs |
| `pydantic` | Data validation and schema enforcement |
| `click` | CLI framework |

### Development (Dev Only)
| Package | Purpose |
|---------|---------|
| `pytest` | Test framework |
| `pytest-cov` | Coverage reporting |
| `black` | Code formatting |
| `ruff` | Linting |
| `mypy` | Type checking |
| `responses` | Mock HTTP responses in tests |

---

## Testing Conventions

- Every module in `src/` has a corresponding `test_` file in `tests/`
- Use `responses` or `pytest-mock` to mock all HTTP calls — **never hit real APIs in tests**
- Test files follow the pattern: `test_<module_name>.py`
- Test functions follow the pattern: `test_<function_name>_<scenario>()`
  - Example: `test_get_access_token_returns_valid_token()`
  - Example: `test_get_access_token_raises_on_invalid_credentials()`
- Minimum coverage target: **80%** on transformation logic

---

## Git Conventions

### Branching
- `main` — Always deployable. Protected branch.
- `feat/<short-description>` — Feature branches (e.g., `feat/scanner-api`)
- `fix/<short-description>` — Bug fix branches
- `docs/<short-description>` — Documentation-only changes

### Commit Messages
- Use [Conventional Commits](https://www.conventionalcommits.org/):
  - `feat: add scanner API polling logic`
  - `fix: handle empty workspace response from PBI`
  - `docs: update roadmap with Phase 2 details`
  - `test: add unit tests for transform module`
  - `chore: update dependencies in pyproject.toml`

### Pull Requests
- Every PR must be reviewed by the **Reviewer Agent** (or a human) before merge
- PR title matches the conventional commit format
- PR description must include: **What**, **Why**, and **How to test**

---

## Secrets & Security

- **Never** commit credentials, tokens, or secrets to the repository
- Use environment variables for all sensitive values:
  - `DATABRICKS_HOST`
  - `DATABRICKS_CLIENT_ID`
  - `DATABRICKS_CLIENT_SECRET`
- `.env` files are gitignored and used only for local development
- In CI/CD, use GitHub Secrets

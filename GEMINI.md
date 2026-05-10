# Defensive Lineage — Agent Instructions

## Before Any Work
1. Read `.docs/ARCHITECTURE.md` for system design and module boundaries
2. Read `.docs/CONVENTIONS.md` for coding standards
3. Read `.docs/ROADMAP.md` for scope and phase definitions
4. Read `.docs/PREREQUISITES.md` for environment setup

## Agent Personas
- **Planning tasks:** Follow `.agent/planner.md`
- **Writing code:** Follow `.agent/implementer.md`
- **Reviewing code:** Follow `.agent/reviewer.md`

## Workflows
- **New module:** Follow `.agent/workflows/implement_module.md`
- **New feature:** Follow `.agent/workflows/add_feature.md`
- **Code review:** Follow `.agent/workflows/review_code.md`
- **Debugging:** Follow `.agent/workflows/debug_issue.md`

## Key Rules
- Python 3.11+, `black`, `ruff`, `mypy` strict
- All secrets via environment variables (never hardcoded)
- Every public function needs type hints + Google-style docstrings
- Every module needs tests (happy path + error path)
- No `print()` outside `cli.py` — use `logging`
- Respect module boundaries from ARCHITECTURE.md — no cross-cutting
- This is a CLI tool, NOT a web app

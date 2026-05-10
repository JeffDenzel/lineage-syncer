# Workflow: Implement a New Module

Use this workflow any time a new `.py` module needs to be built (e.g. `auth.py`, `scanner.py`).

---

## Trigger

> "Implement [module name]" or "Build Phase N"

---

## Steps

### Step 1 — Read Context
Before writing a single line of code:
- [ ] Read `.docs/ROADMAP.md` → confirm which phase this belongs to and its Definition of Done
- [ ] Read `.docs/ARCHITECTURE.md` → find the module's Single Responsibility and boundaries
- [ ] Read `.docs/CONVENTIONS.md` → refresh naming, docstring style, error handling rules
- [ ] Read `.agent/implementer.md` → pre-submission checklist

### Step 2 — Plan the Module
Produce a brief task plan (use the Planner template):
- List every public function needed
- Define input types, output types, and error conditions for each
- Identify which env vars will be read
- Identify which external APIs will be called

### Step 3 — Create the File
- Path: `src/defensive_lineage/<module_name>.py`
- First lines must be:
  ```python
  from __future__ import annotations
  import logging

  logger = logging.getLogger(__name__)
  ```

### Step 4 — Implement Functions
For each function:
1. Write the signature with full type hints
2. Write the Google-style docstring
3. Implement the body
4. Add specific error handling — never bare `except:`
5. Use `logger.debug/info/warning/error` appropriately — never `print()`

### Step 5 — Write Tests
- File: `tests/test_<module_name>.py`
- For every public function, write:
  - One happy path test
  - One failure/edge case test
- Mock all HTTP calls with `responses` library
- Never hit real APIs in tests

### Step 6 — Self-Review
Run through the Reviewer checklist in `.agent/reviewer.md` before declaring done.

### Step 7 — Verify
Run the following commands and confirm they pass:
```powershell
python -m pytest tests/test_<module_name>.py -v
python -m mypy src/defensive_lineage/<module_name>.py
python -m ruff check src/defensive_lineage/<module_name>.py
python -m black --check src/defensive_lineage/<module_name>.py
```

### Step 8 — Done
Definition of Done = matches the ROADMAP Definition of Done for this phase.

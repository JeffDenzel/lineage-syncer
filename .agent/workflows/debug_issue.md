# Workflow: Debug an Issue

Use this when something is broken, erroring, or behaving unexpectedly.

---

## Trigger

> "This isn't working", "I'm getting an error", "Fix this bug"

---

## Steps

### Step 1 — Reproduce First
Never fix what you cannot reproduce:
- What is the exact error message or symptom?
- What command / input triggers it?
- Is it consistent or intermittent?

### Step 2 — Locate the Failure Layer
Map the error to the architecture:

| Symptom | Likely Layer |
|---------|-------------|
| Auth / token error | `auth.py` |
| HTTP 4xx/5xx from Power BI | `scanner.py` |
| KeyError / missing field | `transform.py` |
| Databricks API error | `push.py` |
| Wrong CLI args / exit code | `cli.py` |

### Step 3 — Isolate
- Add a targeted `logger.debug()` call at the entry point of the suspect function
- Do NOT use `print()` — use the logging module
- Run with `DL_LOG_LEVEL=DEBUG` to get full output:
  ```powershell
  $env:DL_LOG_LEVEL="DEBUG"; python -m defensive_lineage.cli sync
  ```

### Step 4 — Write a Failing Test First
Before fixing, write a test that reproduces the bug:
```python
def test_<function>_<bug_scenario>():
    # Arrange: set up the exact conditions that cause the bug
    # Act: call the function
    # Assert: confirm the broken behavior
```
This test should FAIL before the fix and PASS after.

### Step 5 — Fix
- Fix only what is broken — do not refactor unrelated code in the same commit
- Keep the fix minimal and targeted

### Step 6 — Verify
```powershell
python -m pytest tests/ -v
```
- The new test must now pass
- No previously passing tests should be broken

### Step 7 — Commit
```powershell
git commit -m "fix: <short description of the bug and fix>"
```

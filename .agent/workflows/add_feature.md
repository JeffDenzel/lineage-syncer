# Workflow: Add a Feature (End-to-End)

Use this when a new feature request comes in. Covers the full loop from idea → plan → implement → review → merge.

---

## Trigger

> "Add [feature]" or "I want [capability]"

---

## Steps

### Step 1 — Scope Check
Before planning:
- Does this feature appear in the ROADMAP or is it new scope?
- Is it in the "Out of Scope" section of ROADMAP.md? → **Stop. Decline.**
- Does it cross a module boundary defined in ARCHITECTURE.md? → Flag it and redesign.

### Step 2 — Plan (use `implement_module.md` or Planner template)
- Break the feature into atomic tasks
- Map each task to a module in `src/defensive_lineage/`
- Estimate time

### Step 3 — Create a Feature Branch
```powershell
git checkout -b feat/<short-description>
```

### Step 4 — Implement
Follow `implement_module.md` for each affected module.

### Step 5 — Run Full Test Suite
```powershell
python -m pytest tests/ -v --cov=src/defensive_lineage --cov-report=term-missing
```
- Coverage must not drop below 80% on transformation logic
- All tests must pass

### Step 6 — Lint & Format
```powershell
python -m ruff check src/
python -m black src/ tests/
python -m mypy src/
```
All must exit with code 0.

### Step 7 — Self-Review
Run through `review_code.md` yourself before requesting a review.

### Step 8 — Commit
```powershell
git add .
git commit -m "feat: <short description of what was added>"
```
Follow Conventional Commits format from CONVENTIONS.md.

### Step 9 — Open PR
PR description must include:
- **What:** What was built
- **Why:** Why it was needed
- **How to test:** Exact commands to verify

### Step 10 — Review Gate
Wait for the Reviewer Agent (or a human) to approve before merging to `main`.

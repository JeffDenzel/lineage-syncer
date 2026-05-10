# Workflow: Code Review

Use this workflow when asked to review a module, a diff, or a pull request.

---

## Trigger

> "Review [module/file]" or "Check this code" or "Is this ready to merge?"

---

## Steps

### Step 1 — Adopt the Reviewer Persona
Read `.agent/reviewer.md`. Assume the code is broken until proven otherwise.

### Step 2 — Read the Code
- Read the full file, not just the changed lines
- Note every public function, class, and constant

### Step 3 — Run the Checklist
Work through every item in the Reviewer checklist:

| Check | Pass / Fail |
|-------|-------------|
| Type hints on all public signatures | |
| Google-style docstrings on all public functions | |
| No bare `except:` or `except Exception:` | |
| No `print()` outside of `cli.py` | |
| Logging at correct levels | |
| All secrets from env vars | |
| Module boundaries respected (no cross-module logic) | |
| Naming follows CONVENTIONS.md | |
| Tests exist (happy path + failure path) | |
| Idempotency for any write operations | |

### Step 4 — Hunt for Edge Cases
For every function that calls an external API:
- What happens if the API returns 429?
- What happens if the response is empty or malformed?
- What happens if a required field is missing from the JSON?

### Step 5 — Produce the Review
Use the Reviewer output template:

```markdown
## Review: [Module/PR Name]

### Verdict: REJECT / CHANGES REQUESTED / APPROVE

### Critical Issues (Must Fix)
1. [File:Line] — Problem. Why it matters. Suggested fix.

### Warnings (Should Fix)
1. [File:Line] — Description. Suggested fix.

### Nits (Optional)
1. [File:Line] — Minor suggestion.

### What Was Done Well
- (Only if genuinely earned.)
```

### Step 6 — Block or Approve
- **REJECT** → Do not proceed. List blocking issues.
- **CHANGES REQUESTED** → Implementer must address all Critical Issues before re-review.
- **APPROVE** → Code is ready to merge to `main`.

# Defensive Lineage — Product Roadmap

## Product Goal

**Defensive Lineage** is a lightweight Python CLI/library that automatically maps Power BI report dependencies into Databricks Unity Catalog, giving Data Engineers immediate visibility into downstream dependencies before they make breaking changes. Producing reports to notify stakeholders of the upcoming changes.

### The Problem We Solve

Data lineage dies the moment it leaves Databricks. When a Data Engineer runs `ALTER TABLE DROP COLUMN`, they have **zero visibility** into which certified Power BI dashboards depend on a gold data product. The result: broken dashboards and urgent manual work to find the root cause, either in the semantic model or within the gold layer.

Microsoft Purview catalogs assets but does not **stitch** the actual data flow between Databricks and Power BI. Our tool fills that gap.

### The Solution: A Blast-Radius Calculator

Instead of building a heavy governance UI, we build a **script** that:

1. Extracts Power BI workspace metadata via the **Scanner (Admin) API**
2. Transforms the JSON into a clean dependency map (Dashboard → Dataset → Table → Column)
3. Pushes that map into **Databricks Unity Catalog** via the **External Metadata / BYOL API**
4. Runs automatically on a schedule via **GitHub Actions** or a **Databricks Job**

---

## Implementation Phases

### Phase 1: Authentication Layer ("The Bouncer")
**Goal:** Prove we can authenticate to both Power BI and Databricks using a single Databricks Service Principal.

**Deliverables:**
- Databricks Service Principal (configured under Databricks > Settings > Identities)
- Python script using `databricks-sdk` to acquire OAuth2 tokens for both Power BI and Databricks
- A single script that prints valid tokens for both platforms to stdout

**Key Technologies:**
- `databricks-sdk` (handles SP OAuth2 client credentials flow)
- Databricks Service Principal with permissions granted to the Power BI Admin API

**Estimated Time:** 5–8 hours

**Definition of Done:** Running `python auth.py` prints two valid access tokens without any manual browser login.

---

### Phase 2: Power BI Scanner API ("The Extraction")
**Goal:** Pull structured metadata from Power BI workspaces, including dataset-to-table-to-column lineage.

**Deliverables:**
- Python module that implements the 3-step Scanner API async flow:
  1. `POST /admin/workspaces/getInfo` (trigger scan with `lineage=True`)
  2. `GET /admin/workspaces/scanStatus/{scanId}` (poll until `Succeeded`)
  3. `GET /admin/workspaces/scanResult/{scanId}` (download full JSON payload)
- Filter logic to isolate **Certified** and **Promoted** assets only
- Raw JSON output saved to a local file for debugging

**Key Technologies:**
- `requests` library
- Power BI REST Admin API v1.0
- JSON parsing and pagination handling

**Estimated Time:** 10–15 hours

**Definition of Done:** Running `python scan.py` produces a local JSON file containing workspace metadata with table/column-level lineage for certified assets.

---

### Phase 3: JSON Transformation ("The Bridge")
**Goal:** Transform the Power BI Scanner JSON into a clean, normalized dependency map that Databricks can consume.

**Deliverables:**
- Transformation module that flattens the nested Power BI JSON into a list of mappings:
  ```json
  [
    {
      "pbi_workspace": "Finance",
      "pbi_report": "Q3 Revenue",
      "pbi_dataset": "finance_model",
      "endorsement": "Certified",
      "databricks_catalog": "gold",
      "databricks_schema": "finance",
      "databricks_table": "revenue",
      "columns": ["amount", "region", "quarter"]
    }
  ]
  ```
- Edge-case handling for:
  - Datasets with multiple Databricks source tables
  - Reports connected to datasets in different workspaces
  - Import Mode vs DirectQuery detection (flag only, no RLS parsing)
- Unit tests for the transformation logic

**Key Technologies:**
- Python dictionaries / list comprehensions
- `dataclasses` or `pydantic` for schema validation
- `pytest` for testing

**Estimated Time:** 6–10 hours

**Definition of Done:** Running `python transform.py scan_output.json` produces a clean, validated JSON mapping file.

---

### Phase 4: Databricks Unity Catalog BYOL Push ("The Destination")
**Goal:** Inject the Power BI dependency map into Unity Catalog so it appears in the native lineage graph.

**Deliverables:**
- Python module that uses the Databricks Data Lineage API to:
  1. Create external table/dashboard nodes representing Power BI assets
  2. Link those nodes to existing Unity Catalog tables
- Idempotency: re-running the script updates existing links rather than creating duplicates
- Dry-run mode that prints what *would* be pushed without making API calls

**Key Technologies:**
- Databricks REST API (External Lineage / BYOL endpoints)
- `requests` library with Bearer token auth

**Estimated Time:** 10–12 hours

**Definition of Done:** After running `python push.py`, opening Unity Catalog in the Databricks UI shows Power BI dashboards as downstream consumers of the source table.

---

### Phase 5: Automation ("Set and Forget")
**Goal:** Run the entire pipeline automatically on a schedule without human intervention.

**Deliverables:**
- GitHub Actions workflow (`.github/workflows/sync-lineage.yml`) that:
  1. Installs Python dependencies
  2. Authenticates to both platforms using GitHub Secrets
  3. Runs the full scan → transform → push pipeline
  4. Posts a summary to a Slack webhook or GitHub Issue (optional)
- Cron schedule (e.g., nightly at 01:00 UTC)
- Alternative: Databricks Workflow job definition

**Key Technologies:**
- GitHub Actions (YAML workflow files)
- GitHub Secrets for credential storage
- `cron` scheduling

**Estimated Time:** 4–6 hours

**Definition of Done:** A push to `main` or a scheduled cron trigger runs the full pipeline end-to-end with no manual steps.

---

## Total Estimated Timeline

| Phase | Hours | Milestone |
|-------|-------|-----------|
| Phase 1: Auth | 5–8 | Tokens printed to stdout |
| Phase 2: Scanner | 10–15 | Raw PBI JSON saved locally |
| Phase 3: Transform | 6–10 | Clean mapping JSON produced |
| Phase 4: BYOL Push | 10–12 | Lineage visible in Unity Catalog |
| Phase 5: Automation | 4–6 | GitHub Action runs nightly |
| **Total** | **35–51** | **Full pipeline operational** |

At ~10 hours/week, this is a **4–5 week project**.

---

## Out of Scope (Intentionally Killed)

The following were evaluated and deliberately excluded to keep this project viable:

- ❌ **DAX/RLS parsing** — Too complex, requires XMLA/TOM, needs Premium. Let Purview handle it.
- ❌ **XMLA Endpoint access** — Requires Power BI Premium or Fabric capacity. Not free.
- ❌ **Security auditing** — Comparing PBI RLS to Unity Catalog Row Filters is a separate, much harder problem.
- ❌ **Heavy UI / Dashboard** — This is a CLI tool and a library, not a web app.

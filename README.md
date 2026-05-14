# defensive-lineage
A lightweight Python bridge that extracts Power BI dependencies using the Scanner API and helps injects them into Databricks Unity Catalog. Calculate your radius impact before you alter a table, preventing accidentally breaking downstream dashboards.

## Prerequisites

### Power BI Admin Portal Settings (REQUIRED)

Before running lineage extraction, enable these tenant settings:

1. **Enhance admin APIs responses with detailed metadata** — Required to extract table/column definitions
2. **Allow service principals to use read-only Power BI admin APIs** — Required for programmatic scanning

Location: Power BI Admin Portal → Tenant settings → Admin API settings

**Verification:** Run `defensive-lineage scan --output test.jsonl` and verify datasets have `tables[]` populated with columns. Empty `tables[]` indicates missing configuration.

See `.docs/PLAN_PHASE3.md` for detailed configuration instructions.

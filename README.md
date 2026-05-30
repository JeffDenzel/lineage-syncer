# pbi-dbx-lineage-push
A lightweight Python tool that extracts Power BI dependencies using the Scanner API and pushes them to Databricks Unity Catalog. Calculate your radius impact before you alter a table, preventing accidentally breaking downstream dashboards.

## Prerequisites

### Power BI Admin Portal Settings (REQUIRED)

Before running lineage extraction, enable these tenant settings:

1. **Enhance admin APIs responses with detailed metadata** — Required to extract table/column definitions
   - ⚠️ *Do not enable if you don't want to expose metadata. Consider for sensitive data environments.*
2. **Allow service principals to use read-only Power BI admin APIs** — Required for programmatic scanning
   - ⚠️ *Consider the risks of allowing service principals to access Power BI admin APIs*
3. **Apply dataset permissions to read-only admins** — Recommended to ensure scanner can access all workspace datasets
   - ⚠️ *Do take into account the risk of read-only admins bypassing the security boundaries that are set on workspace-level*

Location: Power BI Admin Portal → Tenant settings → Admin API settings

**Verification:** Run `pbi-dbx-lineage-push scan --output test.jsonl` and verify datasets have `tables[]` populated with columns. Empty `tables[]` indicates missing configuration.

See `.docs/PLAN_PHASE3.md` for detailed configuration instructions.

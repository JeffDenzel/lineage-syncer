# defensive-lineage
A lightweight Python bridge that extracts Power BI dependencies using the Scanner API and injects them into Databricks Unity Catalog. Calculate your blast radius before altering a table, preventing accidentally breaking downstream dashboards.

## Prerequisites

### Power BI

> ⚠️ The Scanner API requires **Power BI Admin Portal** settings to be enabled:
> - **Allow service principals to use read-only Power BI admin APIs** — required for the service principal to call the Scanner API.
> - **Enhance admin APIs responses with detailed metadata** — required to return dataset tables, columns, and datasource usage details.

### Databricks Unity Catalog

> ⚠️ The service principal used to push lineage must be granted the following privileges by a **metastore admin** before `push` or `sync` will succeed:

```sql
-- Register Power BI assets as external metadata objects
GRANT CREATE EXTERNAL METADATA ON METASTORE
  TO `<your-service-principal-client-id>`;

-- Allow reading the target catalog and schema for lineage linking
GRANT USE CATALOG ON CATALOG <databricks_catalog>
  TO `<your-service-principal-client-id>`;

GRANT USE SCHEMA ON SCHEMA <databricks_catalog>.<databricks_schema>
  TO `<your-service-principal-client-id>`;

-- Allow referencing tables as lineage sources (grant per schema or per table)
GRANT SELECT ON SCHEMA <databricks_catalog>.<databricks_schema>
  TO `<your-service-principal-client-id>`;
```

## Usage

```bash
# 1. Scan Power BI workspaces (writes scan_output.jsonl)
defensive-lineage scan

# 2. Normalize scan output into lineage mappings (writes mappings.jsonl)
defensive-lineage transform

# 3. Push lineage to Unity Catalog
defensive-lineage push

# Or run the full pipeline in one step
defensive-lineage sync

# Simulate a push without writing to Databricks
defensive-lineage push --dry-run
defensive-lineage dry-run
```

## Environment Variables

Create a `.env` file in the project root (or export these variables):

```env
AZURE_TENANT_ID=...
AZURE_CLIENT_ID=...
AZURE_CLIENT_SECRET=...
DATABRICKS_HOST=...
DATABRICKS_CLIENT_ID=...
DATABRICKS_CLIENT_SECRET=...
```

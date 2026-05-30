# lineage-syncer
This project is a tool to sync the power bi lineage stemming from reports and the associated semantic models to Databricks Unity Catalog.

Using Power BI's Scanner API and Databricks Unity Catalog's BYOL (Bring Your Own Lineage) API, this tool scans your workspace via service principal and pushes lineage metadata directly into UC.

- Promoted/Curated Power BI Report -> Semantic Model (Dataset) lineage
- Semantic Model (Dataset) -> Databricks Table lineage

This tool was designed as Databricks' UC currently supports external assets but does not automatically discover them. It requires manual configuration through the Catalog Explorer UI or via REST API to register Power BI assets in Unity Catalog. With this tool I aim to automate this process.

## Prerequisites

### Power BI

>  The Scanner API requires **Power BI Admin Portal** settings to be enabled:
> - **Allow service principals to use read-only Power BI admin APIs** — required for the service principal to call the Scanner API.
> - **Enhance admin APIs responses with detailed metadata** — required to return dataset tables, columns, and datasource usage details.

### Databricks Unity Catalog

>  The service principal used to push lineage must be granted the following privileges by a **metastore admin** before `push` or `sync` will succeed:

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
lineage-syncer scan

# 2. Normalize scan output into lineage mappings (writes mappings.jsonl)
lineage-syncer transform

# 3. Push lineage to Unity Catalog
lineage-syncer push

# Or run the full pipeline in one step
lineage-syncer sync

# Simulate a push without writing to Databricks
lineage-syncer push --dry-run
lineage-syncer dry-run
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

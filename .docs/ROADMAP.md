# Defensive Lineage — Product Roadmap

## Product Goal

**Defensive Lineage** is a lightweight Python CLI/library that automatically maps **Power BI Semantic Models** to Databricks Unity Catalog, giving Data Engineers immediate visibility into downstream dependencies before they make breaking changes.

### The Problem We Solve

Data lineage dies the moment it leaves Databricks. When a Data Engineer runs `ALTER TABLE DROP COLUMN`, they have **zero visibility** into which **Certified Semantic Models** depend on that column. The result: broken executive reports, 2:00 AM pager alerts, and hours of manual forensic work.

### The Solution: A Blast-Radius Calculator

Instead of building a heavy governance UI, we build a **script** that:

1. Extracts **Semantic Model** metadata via the **Scanner (Admin) API**
2. Categorizes models into **Tiers**:
   - **Tier 1 (Protected):** Uses the native Databricks Connector (Traceable)
   - **Tier 2 (High Risk):** Uses Native Queries / Raw SQL (Opaque)
3. Transforms the JSON into a clean dependency map (Databricks Table → Semantic Model → Reports)
4. Pushes that map into **Databricks Unity Catalog** via the **External Metadata / BYOL API**

---

## Implementation Phases

### Phase 1: Authentication Layer ("The Bouncer")
**Goal:** Programmatic authentication to Entra ID (for Power BI) and Databricks.
- Azure Service Principal + Client Secret
- Databricks PAT or Service Principal
- Deliverable: `auth.py` returning valid Bearer tokens

### Phase 2: Semantic Model Discovery ("The Extraction")
**Goal:** Pull structured metadata for **Promoted/Certified Semantic Models**.
- Implement async Scanner API flow (`getInfo` -> `scanStatus` -> `scanResult`)
- **Tiering Logic:** Flag models as "Evaluatable" (Connector-based) or "Opaque" (Native Query-based)
- Deliverable: `scanner.py` producing raw JSON with dataset/table/column-level lineage

### Phase 3: JSON Transformation ("The Bridge")
**Goal:** Normalize PBI JSON into a flat dependency map.
- Map Databricks Server/Table references to PBI Semantic Model IDs
- Include "Human Impact" metadata (List of downstream Report names)
- Deliverable: `transform.py` producing validated mapping JSON

### Phase 4: Databricks Unity Catalog BYOL Push ("The Destination")
**Goal:** Inject the map into the Unity Catalog lineage graph.
- Create external asset nodes for Semantic Models
- Link nodes to existing UC Tables
- Support `--dry-run` and idempotency
- Deliverable: `push.py`

### Phase 5: Automation ("Set and Forget")
- GitHub Actions / Databricks Job scheduling
- Deliverable: Cron-triggered pipeline

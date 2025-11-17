# Open Targets Schema Diagram

## Entity Relationship Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         OPEN TARGETS INTEGRATION                            │
│                   (Links to existing MEDIABASE schema)                      │
└─────────────────────────────────────────────────────────────────────────────┘

                    EXISTING MEDIABASE TABLES
                    ┌──────────────────┐
                    │ gene_transcript  │
                    │──────────────────│
                    │ gene_id (PK)     │◄──────────┐
                    │ gene_symbol      │           │
                    │ gene_name        │           │ Links to
                    │ cancer_fold      │◄──┐       │ existing
                    └──────────────────┘   │       │ gene data
                                           │       │
                    ┌──────────────────┐   │       │
                    │ gene_id_map      │   │       │
                    │──────────────────│   │       │
                    │ gene_id (FK)     │   │       │
                    │ ensembl_gene_id  │   │       │
                    │ hgnc_id          │   │       │
                    └──────────────────┘   │       │
                                           │       │
                                           │       │
════════════════════════════════════════════════════════════════════════════════
                         NEW OPEN TARGETS TABLES
════════════════════════════════════════════════════════════════════════════════

┌─────────────────────────────────┐
│  opentargets_diseases           │  ◄─── Disease Ontology (EFO/MONDO)
│─────────────────────────────────│
│ disease_id (PK)                 │      Examples:
│ disease_name                    │      - EFO_0000305 = breast carcinoma
│ is_cancer ⚡                     │      - EFO_0000571 = lung carcinoma
│ therapeutic_areas               │      - EFO_0000182 = AML
│ parent_disease_ids              │
└─────────────────────────────────┘
         │                  △
         │                  │
         │ FK               │ FK
         │                  │
         ▼                  │
┌──────────────────────────────────────────┐
│ opentargets_gene_disease_associations    │  ◄─── CORE: Gene-Cancer Evidence
│──────────────────────────────────────────│
│ association_id (PK)                      │      The most important table!
│ gene_id (FK) ───────────┐                │
│ disease_id (FK)         │                │      Overall scores: 0-1 scale
│ overall_score ⭐         │                │      ≥0.5 = moderate evidence
│ somatic_mutation_score ⭐│                │      ≥0.7 = strong evidence
│ known_drug_score ⭐      │                │      ≥0.85 = very strong
│ literature_score        │                │
│ rna_expression_score    │                │      Evidence breakdown:
│ evidence_count          │                │      - Somatic mutations (cancer-specific)
│ ot_version              │                │      - Known drugs (actionability)
└──────────────────────────────────────────┘      - Literature (validation)
         △                 │                      - RNA expression
         │                 │
         │                 └───────────┐
         │                             │
         │ FK                          │ Links to
         │                             │ gene_id
         │                             │
         │                             ▼
┌──────────────────────────────────────────┐
│ opentargets_known_drugs                  │  ◄─── ACTIONABLE: Drugs & Trials
│──────────────────────────────────────────│
│ drug_id (PK)                             │      Clinical phases:
│ molecule_name                            │      0 = preclinical
│ molecule_chembl_id                       │      1 = Phase I (safety)
│ target_gene_id (FK) ────────────────┐    │      2 = Phase II (efficacy)
│ disease_id (FK) ─────────────┐      │    │      3 = Phase III (confirmatory)
│ clinical_phase ⚡             │      │    │      4 = Approved ⭐
│ is_approved ⚡                │      │    │
│ mechanism_of_action          │      │    │      Molecule types:
│ action_type                  │      │    │      - Small molecule
│ clinical_trial_ids[]         │      │    │      - Antibody
│ ot_version                   │      │    │      - Protein
└──────────────────────────────────────────┘      - Oligonucleotide
                                    │      │
                                    │      │
                                    │      └──────────┐
                                    │                 │
                                    │                 │
                                    └──────┐          │
                                           │          │
                                           ▼          ▼
                                    ┌──────────────────────────────┐
                                    │ opentargets_target_          │
                                    │ tractability                 │
                                    │──────────────────────────────│
                                    │ gene_id (PK, FK) ────────────┘
                                    │ sm_clinical_precedence ⚡    │
                                    │ ab_clinical_precedence ⚡    │
                                    │ sm_predicted_tractable       │
                                    │ tractability_summary         │
                                    └──────────────────────────────┘
                                           ▲
                                           │
                                           │ DRUGGABILITY
                                           │ Assessment

════════════════════════════════════════════════════════════════════════════════
                        MATERIALIZED VIEW (Fast Queries)
════════════════════════════════════════════════════════════════════════════════

┌────────────────────────────────────────────────────────────────────────┐
│ gene_clinical_summary (MATERIALIZED VIEW)                              │
│────────────────────────────────────────────────────────────────────────│
│ Pre-aggregated data from 6+ tables for fast LLM queries               │
│                                                                        │
│ FROM: gene_transcript                                                  │
│   + opentargets_gene_disease_associations (cancer associations)        │
│   + opentargets_diseases (cancer types)                                │
│   + opentargets_known_drugs (drug counts)                              │
│   + opentargets_target_tractability (druggability)                     │
│   + gene_product, gene_go, gene_pathway (existing annotations)         │
│                                                                        │
│ Columns:                                                               │
│ - gene_id, gene_symbol, gene_name, cancer_fold                         │
│ - cancer_association_count (# of cancer types)                         │
│ - max_cancer_association_score (best evidence)                         │
│ - approved_drug_count ⚡ (actionability)                               │
│ - small_molecule_tractable ⚡ (druggable?)                             │
│                                                                        │
│ Refresh: REFRESH MATERIALIZED VIEW CONCURRENTLY gene_clinical_summary │
│ Use for: Dashboard queries, summaries, top-N rankings                 │
└────────────────────────────────────────────────────────────────────────┘

════════════════════════════════════════════════════════════════════════════════
                           METADATA & VERSIONING
════════════════════════════════════════════════════════════════════════════════

┌───────────────────────────────┐
│ opentargets_metadata          │
│───────────────────────────────│
│ version (PK)                  │  Track OT releases
│ release_date                  │  Example: "24.09"
│ loaded_date                   │  Update quarterly
│ record_counts (JSONB)         │
│ validation_results (JSONB)    │
└───────────────────────────────┘

Legend:
  ⭐ = Critical field for clinical queries
  ⚡ = Boolean or precomputed flag (LLM-friendly)
  (PK) = Primary Key
  (FK) = Foreign Key
  [] = Array type
```

## Query Flow Examples

### Example 1: "Find approved drugs for overexpressed genes"

```
Query Path:
1. gene_transcript (filter: cancer_fold > 2.0)
   │
   ├─→ Join opentargets_known_drugs ON gene_id
   │   (filter: is_approved = true)
   │
   └─→ Return: gene_symbol, cancer_fold, molecule_name

Indexes used:
- idx_ot_drugs_target (target_gene_id)
- idx_ot_drugs_approved (is_approved)

Performance: ~50-100ms
```

### Example 2: "Rank genes by cancer evidence"

```
Query Path:
1. gene_transcript (filter: cancer_fold > 1.5)
   │
   ├─→ Join opentargets_gene_disease_associations ON gene_id
   │   │
   │   └─→ Join opentargets_diseases ON disease_id
   │       (filter: is_cancer = true)
   │
   ├─→ Aggregate: MAX(overall_score), COUNT(disease_id)
   │
   └─→ Order by: overall_score DESC, cancer_fold DESC

Indexes used:
- idx_ot_assoc_gene (gene_id)
- idx_ot_assoc_score (overall_score)
- idx_ot_diseases_cancer (is_cancer)

Performance: ~100-200ms
```

### Example 3: "Fast summary using materialized view"

```
Query Path:
1. gene_clinical_summary (pre-aggregated!)
   │
   ├─→ Filter: cancer_fold > 2.0 AND approved_drug_count > 0
   │
   └─→ Order by: approved_drug_count DESC

No joins needed! All data pre-computed.

Performance: ~20-50ms (10x faster)
```

## Index Strategy

### Primary Indexes (Always Created)

```sql
-- Gene lookups (most common)
CREATE INDEX idx_ot_assoc_gene
  ON opentargets_gene_disease_associations(gene_id);

-- Evidence filtering
CREATE INDEX idx_ot_assoc_score
  ON opentargets_gene_disease_associations(overall_score DESC);

-- Cancer disease filtering
CREATE INDEX idx_ot_diseases_cancer
  ON opentargets_diseases(is_cancer) WHERE is_cancer = true;

-- Drug target lookups
CREATE INDEX idx_ot_drugs_target
  ON opentargets_known_drugs(target_gene_id);

-- Approved drug filtering
CREATE INDEX idx_ot_drugs_approved
  ON opentargets_known_drugs(is_approved) WHERE is_approved = true;
```

### Composite Indexes (Common Query Patterns)

```sql
-- Gene + evidence score (common LLM pattern)
CREATE INDEX idx_ot_assoc_gene_score
  ON opentargets_gene_disease_associations(gene_id, overall_score DESC);

-- Cancer genes with moderate+ evidence (filtered)
CREATE INDEX idx_ot_assoc_cancer_genes
  ON opentargets_gene_disease_associations(gene_id, overall_score)
  WHERE overall_score >= 0.5;
```

### Full-Text Search Indexes

```sql
-- Disease name search
CREATE INDEX idx_ot_diseases_name
  ON opentargets_diseases USING gin(to_tsvector('english', disease_name));

-- Drug name search
CREATE INDEX idx_ot_drugs_name
  ON opentargets_known_drugs USING gin(to_tsvector('english', molecule_name));
```

## Data Flow: ETL to Query

```
┌──────────────────────────┐
│ Open Targets FTP Server  │
│                          │
│ ftp.ebi.ac.uk            │
└────────────┬─────────────┘
             │
             │ Download
             │ Parquet files
             ▼
┌──────────────────────────┐
│ MEDIABASE Cache          │
│                          │
│ /tmp/mediabase/cache/    │
│ opentargets_24.09/       │
└────────────┬─────────────┘
             │
             │ ETL Process
             │ (src/etl/opentargets.py)
             ▼
┌──────────────────────────┐
│ Transform & Filter       │
│                          │
│ - Map gene IDs           │
│ - Filter cancer diseases │
│ - Apply score thresholds │
│ - Precompute flags       │
└────────────┬─────────────┘
             │
             │ Batch Insert
             │ (1000 records/batch)
             ▼
┌──────────────────────────┐
│ PostgreSQL Database      │
│                          │
│ - 5 Core Tables          │
│ - 20+ Indexes            │
│ - 1 Materialized View    │
└────────────┬─────────────┘
             │
             │ Query via API
             │ or LLM-generated SQL
             ▼
┌──────────────────────────┐
│ Oncologist               │
│                          │
│ "Show approved drugs for │
│  my patient's EGFR       │
│  overexpression"         │
└──────────────────────────┘
```

## Table Size Estimates

After ETL completion, expect these sizes:

```
opentargets_diseases
  ~15,000 rows, ~50 MB
  (3,500 cancer-specific)

opentargets_gene_disease_associations
  ~150,000 rows, ~300 MB
  (cancer-filtered, score ≥ 0.5)

opentargets_known_drugs
  ~25,000 rows, ~100 MB
  (all clinical phases)

opentargets_target_tractability
  ~18,000 rows, ~50 MB

gene_clinical_summary (materialized view)
  ~20,000 rows, ~100 MB
  (genes with any annotations)

Total: ~600 MB in database
Cache: ~4-5 GB (source Parquet files)
```

## Critical Fields for LLM Queries

### Most Important Columns (Always Include in Schema Comments)

```sql
-- For filtering overexpressed genes
gene_transcript.cancer_fold

-- For cancer disease filtering
opentargets_diseases.is_cancer

-- For evidence strength
opentargets_gene_disease_associations.overall_score
opentargets_gene_disease_associations.somatic_mutation_score

-- For actionability
opentargets_known_drugs.is_approved
opentargets_known_drugs.clinical_phase

-- For druggability
opentargets_target_tractability.sm_clinical_precedence
opentargets_target_tractability.ab_clinical_precedence
```

### Common LLM Query Patterns

```sql
-- Pattern 1: Overexpressed + approved drugs
WHERE cancer_fold > 2.0
  AND is_approved = true

-- Pattern 2: Cancer-relevant genes
WHERE is_cancer = true
  AND overall_score >= 0.5

-- Pattern 3: Strong evidence + high expression
WHERE overall_score >= 0.7
  AND cancer_fold > 3.0

-- Pattern 4: Druggable targets
WHERE sm_clinical_precedence = true
  OR ab_clinical_precedence = true
```

## Version Management Strategy

```
┌─────────────────────────────────────────────────────────────┐
│ Data Versioning Approach                                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ All data tables include: ot_version TEXT NOT NULL          │
│                                                             │
│ Option 1: Single Version (Simpler)                         │
│   - DELETE old data before loading new version             │
│   - All tables have same ot_version                        │
│   - Easier to manage, less storage                         │
│   - Use for production                                     │
│                                                             │
│ Option 2: Multi-Version (Research)                         │
│   - Keep multiple versions side-by-side                    │
│   - Query with WHERE ot_version = '24.09'                  │
│   - Compare versions over time                             │
│   - 2-3x storage requirements                              │
│   - Use for research/validation only                       │
│                                                             │
│ Recommendation: Start with Option 1                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

**File Location:** `/home/itsatony/code/mediabase/docs/OPENTARGETS_SCHEMA_DIAGRAM.md`
**Related Files:**
- Schema: `src/db/migrations/006_opentargets_schema.sql`
- Queries: `docs/OPENTARGETS_QUERY_EXAMPLES.sql`
- ETL: `src/etl/opentargets.py`

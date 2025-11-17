# Open Targets Integration - Executive Summary

## Overview

This document provides concise answers to your Open Targets Platform integration questions, with references to detailed documentation created for implementation.

**Target User:** Non-informatician oncologists
**Use Case:** LLM-assisted SQL query generation for clinical decision support
**Database:** PostgreSQL with comprehensive schema comments for LLM accessibility

---

## Quick Answers to Your Questions

### 1. Data Structure & Download

**Recommended Format:** **Parquet files** - columnar, compressed, efficient
- Alternative: JSON (larger, slower)
- Avoid: CSV (not available for bulk downloads)

**Priority Datasets for Oncology:**
1. **associationByOverallDirect** (~3GB) - Gene-disease associations with scores
2. **knownDrugsAggregated** (~500MB) - Approved/clinical drugs with targets
3. **diseases** (~50MB) - Cancer ontology (EFO/MONDO)
4. **targets** (~200MB) - Tractability assessments
5. **mechanismOfAction** (~100MB) - Drug mechanisms

**Download Location:**
```
ftp://ftp.ebi.ac.uk/pub/databases/opentargets/platform/24.09/output/etl/parquet/
```

**Version Management:**
- Quarterly releases: March, June, September, December
- Format: `YY.MM` (e.g., `24.09`, `24.12`)
- Always track version in database (`ot_version` column)

**Typical Sizes:**
- Total for priority datasets: ~4-5 GB compressed
- Full platform: ~200+ GB (not all needed)

**See:** `/home/itsatony/code/mediabase/docs/OPENTARGETS_IMPLEMENTATION_GUIDE.md` (Phase 1) for download scripts

---

### 2. Essential Tables for Oncology

**Tier 1: Must-Have**

#### A. `opentargets_diseases`
- **Purpose:** Cancer type classification and ontology
- **Key Fields:**
  - `disease_id`: EFO/MONDO identifier (e.g., `EFO_0000305` = breast carcinoma)
  - `is_cancer`: Boolean flag for filtering
  - `therapeutic_areas`: Array of classifications
  - `parent_disease_ids`: Ontology hierarchy

**Cancer Organization:**
- Root term: `EFO_0000616` (neoplasm)
- Hierarchical: breast cancer → carcinoma → neoplasm
- ~15,000 diseases, ~3,500 cancer-specific

#### B. `opentargets_gene_disease_associations`
- **Purpose:** Evidence linking genes to cancers with confidence scores
- **Key Fields:**
  - `overall_score`: 0-1 combined evidence (≥0.5 = moderate, ≥0.7 = strong)
  - `somatic_mutation_score`: Cancer-specific evidence (most important for oncology)
  - `known_drug_score`: Druggability indicator
  - `literature_score`, `rna_expression_score`, etc.

**Expected Data:** ~150,000 cancer associations after filtering

#### C. `opentargets_known_drugs`
- **Purpose:** Actionable drug-target-disease combinations
- **Key Fields:**
  - `clinical_phase`: 0-4 (4 = approved)
  - `is_approved`: Boolean for quick filtering
  - `molecule_chembl_id`: Cross-reference to ChEMBL
  - `mechanism_of_action`: Human-readable mechanism
  - `clinical_trial_ids`: Array of NCT numbers

**Drug Classification:**
- Phase 4 (Approved): ~2,000+ entries
- Phase 2-3 (Late clinical): ~5,000+ entries
- Molecule types: Small molecule, Antibody, Protein, etc.

**Tier 2: High Value**

#### D. `opentargets_target_tractability`
- **Purpose:** Druggability prediction for novel targets
- **Key Fields:**
  - `sm_clinical_precedence`: Drugs exist for this target family
  - `ab_clinical_precedence`: Antibody feasibility
  - `tractability_summary`: Human-readable assessment

**Use Case:** Identifying novel targets worth pursuing

**See:** `/home/itsatony/code/mediabase/src/db/migrations/006_opentargets_schema.sql` for complete schema with detailed comments

---

### 3. Data Model Best Practices

#### Evidence Scores (0-1 scale)

**Overall Score Thresholds:**
- **0.85-1.0:** Very strong - Well-established associations (TP53, EGFR in their cancers)
- **0.70-0.84:** Strong - Multiple evidence sources, clinically relevant
- **0.50-0.69:** Moderate - Emerging evidence, requires validation
- **< 0.50:** Weak - Filter out for clinical use

**Storage Strategy:**
- ✅ **Store individual evidence scores** (somatic_mutation_score, known_drug_score, etc.)
- ✅ **Keep overall_score** for quick filtering
- ❌ **Don't store full evidence strings** (50-200GB) - aggregate instead
- ✅ **Store metadata JSONB** for additional details if needed

**Gene ID Mapping:**
- Open Targets uses Ensembl gene IDs (ENSG00000139618)
- Map to your existing `gene_transcript.gene_id` during ETL
- Handle versioned IDs: `ENSG00000139618.15` → `ENSG00000139618`
- Store mapping in `gene_id_map` table

**Key Filtering Fields for Quality:**
```sql
WHERE overall_score >= 0.5          -- Moderate evidence threshold
  AND is_cancer = true              -- Cancer-specific diseases
  AND somatic_mutation_score > 0.3  -- Cancer-relevant evidence
  AND evidence_count >= 2           -- Multiple evidence sources
```

---

### 4. Clinical Relevance Filtering

#### Score-Based Actionability

**For Treatment Selection (High Priority):**
1. `known_drug_score > 0.5` - Direct drug availability
2. `somatic_mutation_score > 0.7` - Established cancer gene
3. `is_approved = true` - FDA/EMA approved drugs
4. `tractability_clinical_precedence = true` - Druggable target

**For Diagnosis/Prognosis:**
1. `somatic_mutation_score > 0.6` - Known cancer driver
2. `literature_score > 0.5` - Published clinical associations
3. `overall_score > 0.7` - Strong multi-source evidence

**For Research/Novel Targets:**
1. `tractability_predicted_tractable = true` - Druggability potential
2. `overall_score > 0.5` - Moderate evidence
3. `rna_expression_score > 0.4` - Differential expression

#### Cancer Type Specificity

**High-Quality Data (Prioritize):**
- Solid tumors: breast, lung, colorectal (TCGA comprehensive)
- Hematological: AML, CLL (molecular subtypes well-defined)
- Melanoma (immunotherapy data rich)

**EFO Terms to Highlight:**
```sql
-- Store in priority configuration
'EFO_0000305' - breast carcinoma
'EFO_0000571' - lung carcinoma
'EFO_0000182' - acute myeloid leukemia
'EFO_0000313' - melanoma
'EFO_0005842' - colorectal carcinoma
```

**Cancer-Specific Filtering:**
```sql
SELECT * FROM opentargets_diseases
WHERE is_cancer = true
  AND (
    therapeutic_areas && ARRAY['neoplasm', 'cancer']
    OR disease_name ILIKE '%carcinoma%'
    OR disease_name ILIKE '%leukemia%'
  );
```

**See:** `/home/itsatony/code/mediabase/docs/OPENTARGETS_INTEGRATION_PLAN.md` (Clinical Relevance Guidelines section)

---

### 5. Schema Design Recommendations

#### Core Tables (2-3 Most Valuable)

**Table 1: `opentargets_gene_disease_associations` - HIGHEST VALUE**
```sql
CREATE TABLE opentargets_gene_disease_associations (
    gene_id TEXT NOT NULL,              -- Links to gene_transcript
    disease_id TEXT NOT NULL,           -- Links to opentargets_diseases
    overall_score NUMERIC(5,4),         -- 0-1 evidence strength
    somatic_mutation_score NUMERIC(5,4), -- Cancer-specific score
    known_drug_score NUMERIC(5,4),      -- Actionability score
    -- ... other evidence scores
);
```
**Why:** Directly answers "Is this gene relevant to cancer?"

**Table 2: `opentargets_known_drugs` - HIGH VALUE**
```sql
CREATE TABLE opentargets_known_drugs (
    molecule_name TEXT NOT NULL,
    target_gene_id TEXT,                -- Links to gene_transcript
    disease_id TEXT,                    -- Links to opentargets_diseases
    clinical_phase NUMERIC(3,1),        -- 0-4 (4=approved)
    is_approved BOOLEAN,                -- Quick filter
    mechanism_of_action TEXT,
);
```
**Why:** Directly answers "What drugs target this gene?"

**Table 3: `opentargets_diseases` - SUPPORTING**
```sql
CREATE TABLE opentargets_diseases (
    disease_id TEXT PRIMARY KEY,
    disease_name TEXT NOT NULL,
    is_cancer BOOLEAN,                  -- Precomputed flag
    therapeutic_areas TEXT[],
);
```
**Why:** Cancer classification for filtering

#### Key Indexes for LLM Queries

**Most Important (Create First):**
```sql
-- Gene lookups (most common pattern)
CREATE INDEX idx_ot_assoc_gene ON opentargets_gene_disease_associations(gene_id);

-- Evidence filtering
CREATE INDEX idx_ot_assoc_score ON opentargets_gene_disease_associations(overall_score DESC);

-- Cancer filtering
CREATE INDEX idx_ot_diseases_cancer ON opentargets_diseases(is_cancer) WHERE is_cancer = true;

-- Drug actionability
CREATE INDEX idx_ot_drugs_target ON opentargets_known_drugs(target_gene_id);
CREATE INDEX idx_ot_drugs_approved ON opentargets_known_drugs(is_approved) WHERE is_approved = true;
```

**Performance Target:** < 200ms for common queries

#### Disease Ontology Hierarchy Handling

**Simple Approach (Recommended):**
```sql
-- Flatten hierarchy with is_cancer boolean flag
-- Store parent_disease_ids as array for traversal if needed
CREATE INDEX ON opentargets_diseases USING gin(parent_disease_ids);

-- Query: Find all breast cancer subtypes
SELECT * FROM opentargets_diseases
WHERE 'EFO_0000305' = ANY(parent_disease_ids)  -- breast carcinoma
   OR disease_id = 'EFO_0000305';
```

**Complex Approach (If Needed):**
- Create separate `disease_hierarchy` table with recursive relationships
- Use PostgreSQL recursive CTEs for hierarchy traversal
- Only implement if users need "all breast cancer subtypes" queries

**Recommendation:** Start simple (boolean + array), add hierarchy table if needed

---

## LLM-Friendly Design Principles Applied

### 1. Clear Naming Conventions
✅ **Good:**
- `opentargets_gene_disease_associations` (clear source + content)
- `overall_score` (descriptive, no abbreviation)
- `is_approved` (boolean convention)

❌ **Avoid:**
- `ot_assoc` (abbreviation)
- `oa_score` (unclear)
- `approved` (boolean without `is_`)

### 2. Comprehensive Comments
```sql
COMMENT ON COLUMN overall_score IS
'Combined evidence score from 0-1. Threshold: ≥0.5 moderate, ≥0.7 strong,
≥0.85 very strong evidence. Higher scores indicate more established associations.';
```

**Every column has:**
- What it represents
- How to interpret values (ranges, thresholds)
- Clinical significance
- Example values

### 3. Denormalization for Simplicity
```sql
-- Store BOTH numeric and text versions
clinical_phase NUMERIC(3,1),        -- For comparisons: >= 2
clinical_phase_label TEXT,          -- For display: "Phase II"

-- Precompute common filters
is_cancer BOOLEAN,                  -- Don't require ontology traversal
is_approved BOOLEAN,                -- Don't require phase = 4 calculation
```

**Rationale:** LLMs can generate simpler queries, better for oncologists reviewing SQL

### 4. Example LLM Query Pattern

**Oncologist:** "Show me approved drugs for overexpressed genes"

**LLM Generates:**
```sql
SELECT
    gt.gene_symbol,
    gt.cancer_fold,
    okd.molecule_name,
    okd.mechanism_of_action
FROM gene_transcript gt
JOIN opentargets_known_drugs okd ON gt.gene_id = okd.target_gene_id
WHERE gt.cancer_fold > 2.0
  AND okd.is_approved = true
ORDER BY gt.cancer_fold DESC;
```

**Clear, simple, performant** - enabled by LLM-friendly schema

**See:** `/home/itsatony/code/mediabase/docs/OPENTARGETS_QUERY_EXAMPLES.sql` for 10 complete examples

---

## Materialized View: `gene_clinical_summary`

**Purpose:** Pre-aggregated view for dashboard queries

**Benefits:**
- 10-100x faster than joining 5+ tables
- Combines expression + evidence + druggability
- Perfect for LLM-generated "summary" queries

**Structure:**
```sql
CREATE MATERIALIZED VIEW gene_clinical_summary AS
SELECT
    gene_id,
    gene_symbol,
    cancer_fold,                        -- Patient expression
    cancer_association_count,           -- Number of cancer types
    max_cancer_association_score,       -- Best evidence
    max_somatic_mutation_score,         -- Cancer gene score
    small_molecule_tractable,           -- Druggable?
    approved_drug_count,                -- Actionability
    clinical_stage_drug_count
FROM [complex multi-table join]
GROUP BY gene_id;
```

**Refresh Strategy:**
```sql
-- After data updates (takes ~5 minutes)
REFRESH MATERIALIZED VIEW CONCURRENTLY gene_clinical_summary;

-- Schedule daily refresh via cron
0 2 * * * psql -c "REFRESH MATERIALIZED VIEW CONCURRENTLY gene_clinical_summary"
```

**When to Use:**
- ✅ High-level summaries (top 50 genes)
- ✅ Dashboard/report generation
- ✅ Multi-patient analysis
- ❌ Real-time single-gene detail (use base tables)

---

## Implementation Roadmap

### Phase 1: Core Integration (Weeks 1-2)
- Download datasets (~4GB)
- Apply schema migration
- Implement ETL for diseases + associations
- **Deliverable:** Gene-cancer associations queryable

### Phase 2: Drug Data (Week 3)
- Process known drugs
- Add tractability
- **Deliverable:** Actionable drug recommendations

### Phase 3: Optimization (Week 4)
- Create materialized view
- Validate with known cancer genes
- Performance tuning
- **Deliverable:** < 200ms query response

### Phase 4: Production (Week 5)
- API integration
- Documentation
- LLM training on schema
- **Deliverable:** Full clinical workflow

**See:** `/home/itsatony/code/mediabase/docs/OPENTARGETS_IMPLEMENTATION_GUIDE.md` for detailed steps

---

## Files Created for Your Implementation

### 1. Strategic Planning
- **`OPENTARGETS_INTEGRATION_PLAN.md`** - Comprehensive integration strategy
  - Data sources and priorities
  - Schema design rationale
  - Clinical filtering guidelines
  - LLM query patterns

### 2. Technical Implementation
- **`src/etl/opentargets.py`** - ETL processor (skeleton, needs completion)
  - Download and caching logic
  - Data transformation
  - Batch insert methods

- **`src/db/migrations/006_opentargets_schema.sql`** - Database schema
  - 5 tables with full comments
  - 20+ optimized indexes
  - Materialized view
  - Helper functions

### 3. Examples & Testing
- **`docs/OPENTARGETS_QUERY_EXAMPLES.sql`** - 10 complete query examples
  - Approved drug discovery
  - Novel target identification
  - Clinical trial matching
  - Evidence-based ranking

- **`docs/OPENTARGETS_IMPLEMENTATION_GUIDE.md`** - Step-by-step guide
  - Phase-by-phase implementation
  - Validation procedures
  - Troubleshooting
  - Maintenance procedures

### 4. Reference
- **`docs/OPENTARGETS_EXECUTIVE_SUMMARY.md`** - This document
  - Quick answers to your questions
  - Best practices
  - Design rationale

---

## Key Recommendations

### Do's ✅
1. **Start with Tier 1 tables** (diseases, associations, drugs) - 90% of clinical value
2. **Filter during ETL** - Only load cancer associations with score ≥ 0.5
3. **Use Parquet format** - 10x faster than JSON
4. **Precompute is_cancer** - Don't make LLM traverse ontology
5. **Add comprehensive comments** - Every table, every important column
6. **Create materialized view** - Essential for summary queries
7. **Version tracking** - Always record `ot_version` in data

### Don'ts ❌
1. **Don't load all evidence strings** - 200GB, too large, aggregate instead
2. **Don't abbreviate names** - `opentargets_known_drugs` not `ot_kd`
3. **Don't skip indexes** - Critical for performance
4. **Don't ignore gene ID mapping** - 20% data loss if poorly implemented
5. **Don't forget materialized view refresh** - Stale data confuses users
6. **Don't over-normalize** - LLM query complexity grows quickly

### Quick Wins 🎯
1. **Week 1:** Load associations + diseases → "Is gene cancer-relevant?" queries work
2. **Week 2:** Load drugs → Actionable recommendations available
3. **Week 3:** Create materialized view → Fast summary queries
4. **Week 4:** Validate with oncologist on real patient → Clinical utility confirmed

---

## Expected Outcomes

### Data Metrics
- ~15,000 diseases (3,500 cancer-specific)
- ~150,000 gene-disease associations (cancer-filtered)
- ~25,000 drug-target-disease entries
- ~18,000 tractability assessments
- 80%+ gene ID mapping coverage

### Query Performance
- Simple gene lookup: < 50ms
- Drug recommendation: < 200ms
- Complex multi-join: < 1s
- Materialized view queries: < 100ms

### Clinical Value
- Immediate drug recommendations for overexpressed genes
- Evidence-based gene prioritization
- Novel target discovery
- Clinical trial matching
- Multi-source evidence integration

---

## Next Steps

1. **Review documentation** - Start with `OPENTARGETS_INTEGRATION_PLAN.md`
2. **Approve schema** - Review `006_opentargets_schema.sql`
3. **Allocate resources** - ~4-5 weeks development time
4. **Begin Phase 1** - Download data and apply migration
5. **Iterate with feedback** - Test with oncologists early and often

---

## Questions?

**Technical Implementation:**
- See: `OPENTARGETS_IMPLEMENTATION_GUIDE.md` (detailed procedures)
- Code: `src/etl/opentargets.py` (implementation template)

**Schema Design:**
- See: `src/db/migrations/006_opentargets_schema.sql` (full schema with comments)
- Examples: `OPENTARGETS_QUERY_EXAMPLES.sql` (10 query patterns)

**Strategic Planning:**
- See: `OPENTARGETS_INTEGRATION_PLAN.md` (comprehensive strategy)

**Open Targets Resources:**
- Platform: https://platform.opentargets.org/
- Documentation: https://platform-docs.opentargets.org/
- FTP: ftp://ftp.ebi.ac.uk/pub/databases/opentargets/platform/

---

**Document Version:** 1.0
**Created:** 2025-11-16
**Author:** Claude (Sonnet 4.5) - MEDIABASE Expert Assistant
**All file paths:** Absolute paths in `/home/itsatony/code/mediabase/`

# Open Targets Platform Integration Plan for MEDIABASE

## Overview
Integration strategy for Open Targets Platform data to enhance clinical oncology queries via LLM-assisted SQL generation.

**Version:** 1.0
**Target Open Targets Release:** 24.09+
**Author:** MEDIABASE Development Team
**Date:** 2025-11-16

## Priority Datasets for Oncology

### Tier 1: Essential (Implement First)

1. **associationByOverallDirect**
   - Direct disease-target associations with overall scores
   - Size: ~3GB Parquet
   - Update: Per release
   - Purpose: Primary gene-cancer association evidence

2. **knownDrugsAggregated**
   - Approved and clinical-stage drugs with targets
   - Size: ~500MB
   - Update: Per release
   - Purpose: Actionable drug-target pairs with clinical phase

3. **diseases**
   - Disease ontology with EFO IDs and therapeutic areas
   - Size: ~50MB
   - Update: Per release
   - Purpose: Cancer type classification and hierarchy

### Tier 2: High Value (Implement Second)

4. **mechanismOfAction**
   - Drug mechanisms with target and action type
   - Size: ~100MB
   - Purpose: Understanding drug-target interactions

5. **targets**
   - Target annotations including tractability
   - Size: ~200MB
   - Purpose: Druggability assessment

6. **associationByDatatypeDirect**
   - Evidence scores by datatype (genetics, somatic, drugs)
   - Size: ~4GB
   - Purpose: Evidence source breakdown

### Tier 3: Optional Enrichment

7. **evidence** (filtered subset)
   - Detailed evidence strings - VERY LARGE
   - Size: 50-200GB unfiltered
   - Recommendation: Filter for cancer-specific + score threshold during ETL
   - Purpose: Deep evidence exploration

## Download Strategy

### Initial Setup
```bash
# Base URL for current release
RELEASE_VERSION="24.09"
BASE_URL="ftp://ftp.ebi.ac.uk/pub/databases/opentargets/platform/${RELEASE_VERSION}/output/etl/parquet"

# Download priority datasets
wget -r -np -nH --cut-dirs=7 \
  ${BASE_URL}/associationByOverallDirect/
wget -r -np -nH --cut-dirs=7 \
  ${BASE_URL}/knownDrugsAggregated/
wget -r -np -nH --cut-dirs=7 \
  ${BASE_URL}/diseases/
wget -r -np -nH --cut-dirs=7 \
  ${BASE_URL}/mechanismOfAction/
wget -r -np -nH --cut-dirs=7 \
  ${BASE_URL}/targets/
```

### Update Management
- Check for new releases quarterly
- Maintain version in schema metadata
- Consider incremental updates vs full refresh based on data volume

## Data Processing Pipeline

### ETL Sequence Position
Add after `pathways` module, before `drugs` enrichment:
1. transcript (existing)
2. id_enrichment (existing)
3. go_terms (existing)
4. products (existing)
5. pathways (existing)
6. **opentargets_diseases** (NEW)
7. **opentargets_associations** (NEW)
8. **opentargets_drugs** (NEW)
9. drugs (existing - will be enhanced)
10. publications (existing)

### Cancer-Specific Filtering

#### EFO Disease Filtering
Focus on these therapeutic areas and disease categories:
- **EFO:0000616** - neoplasm (root term)
- **MONDO:0004992** - cancer
- **EFO:0000311** - carcinoma
- **EFO:0002422** - malignant tumor

#### Association Score Thresholds
Based on Open Targets documentation and clinical utility:
- **Overall score ≥ 0.50**: Moderate evidence (include)
- **Overall score ≥ 0.70**: Strong evidence (prioritize)
- **Overall score ≥ 0.85**: Very strong evidence (highlight)

#### Datatype Priority for Oncology
Weight these evidence types highest:
1. **Somatic mutations** (score weight: 1.0)
2. **Cancer Gene Census** (score weight: 1.0)
3. **Literature** (score weight: 0.8)
4. **Known drugs** (score weight: 0.9)
5. **GWAS** (score weight: 0.5)

## Schema Design

### Core Tables

#### 1. opentargets_diseases
```sql
CREATE TABLE opentargets_diseases (
    disease_id TEXT PRIMARY KEY,  -- EFO/MONDO ID
    disease_name TEXT NOT NULL,
    disease_description TEXT,
    therapeutic_areas TEXT[],  -- Array of therapeutic area names
    ontology_source TEXT,  -- 'EFO', 'MONDO', 'ORPHANET', etc.
    is_cancer BOOLEAN DEFAULT false,  -- Derived from therapeutic areas
    parent_disease_ids TEXT[],  -- Disease hierarchy
    metadata JSONB,  -- Additional ontology metadata
    ot_version TEXT NOT NULL,  -- Open Targets release version
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE opentargets_diseases IS
'Disease ontology from Open Targets Platform. Contains cancer classifications and hierarchies for disease-gene associations. Use disease_id to join with associations.';

COMMENT ON COLUMN opentargets_diseases.disease_id IS
'EFO, MONDO, or other ontology identifier (e.g., EFO_0000616 for neoplasm)';

COMMENT ON COLUMN opentargets_diseases.is_cancer IS
'Boolean flag: true if disease is classified under neoplasm/cancer therapeutic areas';

COMMENT ON COLUMN opentargets_diseases.parent_disease_ids IS
'Array of parent disease IDs in ontology hierarchy (e.g., breast cancer -> carcinoma -> neoplasm)';
```

#### 2. opentargets_gene_disease_associations
```sql
CREATE TABLE opentargets_gene_disease_associations (
    association_id SERIAL PRIMARY KEY,
    gene_id TEXT NOT NULL REFERENCES gene_transcript(gene_id),
    disease_id TEXT NOT NULL REFERENCES opentargets_diseases(disease_id),
    overall_score NUMERIC(5,4) NOT NULL,  -- 0.0000 to 1.0000

    -- Evidence scores by datatype
    genetic_association_score NUMERIC(5,4),  -- GWAS, rare variants
    somatic_mutation_score NUMERIC(5,4),     -- Cancer somatic evidence
    known_drug_score NUMERIC(5,4),           -- Approved/clinical drugs
    literature_score NUMERIC(5,4),           -- PubMed co-mentions
    rna_expression_score NUMERIC(5,4),       -- Differential expression
    pathways_systems_biology_score NUMERIC(5,4),  -- Pathway evidence
    animal_model_score NUMERIC(5,4),         -- Model organism data

    -- Clinical relevance metadata
    is_direct BOOLEAN DEFAULT true,          -- Direct vs indirect evidence
    evidence_count INTEGER,                  -- Number of evidence strings
    datasource_count INTEGER,                -- Number of unique datasources

    -- Tractability information
    tractability_clinical_precedence BOOLEAN,  -- Drugs for related targets
    tractability_discovery_precedence BOOLEAN, -- Structural features

    metadata JSONB,  -- Full evidence details if needed
    ot_version TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(gene_id, disease_id, ot_version)
);

COMMENT ON TABLE opentargets_gene_disease_associations IS
'Gene-disease associations from Open Targets with evidence scores. Overall_score ≥0.5 indicates moderate evidence, ≥0.7 strong evidence. Join with gene_transcript on gene_id and opentargets_diseases on disease_id for clinical queries.';

COMMENT ON COLUMN opentargets_gene_disease_associations.overall_score IS
'Combined evidence score from 0-1. Threshold: ≥0.5 moderate, ≥0.7 strong, ≥0.85 very strong evidence';

COMMENT ON COLUMN opentargets_gene_disease_associations.somatic_mutation_score IS
'Cancer somatic mutation evidence score (Cancer Gene Census, COSMIC, IntOGen). Higher scores indicate well-established cancer genes.';

COMMENT ON COLUMN opentargets_gene_disease_associations.known_drug_score IS
'Evidence from approved or clinical-phase drugs targeting this gene for this disease. Higher scores indicate actionable targets.';
```

#### 3. opentargets_known_drugs
```sql
CREATE TABLE opentargets_known_drugs (
    drug_id SERIAL PRIMARY KEY,
    molecule_chembl_id TEXT,  -- ChEMBL ID if available
    molecule_name TEXT NOT NULL,
    molecule_type TEXT,  -- 'Small molecule', 'Antibody', etc.

    target_gene_id TEXT REFERENCES gene_transcript(gene_id),
    disease_id TEXT REFERENCES opentargets_diseases(disease_id),

    -- Clinical status
    clinical_phase NUMERIC(3,1),  -- 0, 1, 2, 3, 4 (approved)
    clinical_phase_label TEXT,    -- 'Phase I', 'Approved', etc.
    clinical_status TEXT,          -- 'Recruiting', 'Completed', etc.

    -- Mechanism
    mechanism_of_action TEXT,
    action_type TEXT,  -- 'inhibitor', 'agonist', 'antagonist', etc.

    -- Drug metadata
    drug_type TEXT,  -- 'Prescription', 'Investigational', etc.
    is_approved BOOLEAN,
    approval_year INTEGER,

    -- Clinical trial references
    clinical_trial_ids TEXT[],  -- Array of NCT IDs

    metadata JSONB,
    ot_version TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE opentargets_known_drugs IS
'Approved and clinical-stage drugs with target and disease associations from Open Targets. Clinical_phase=4 indicates approved drugs. Use for identifying actionable drug-target-disease combinations.';

COMMENT ON COLUMN opentargets_known_drugs.clinical_phase IS
'Clinical development phase: 0=preclinical, 1-3=clinical trials, 4=approved. NULL for withdrawn/terminated.';

COMMENT ON COLUMN opentargets_known_drugs.is_approved IS
'True if drug is approved for any indication (may differ from specific disease indication in this row)';
```

### Supporting Tables

#### 4. opentargets_target_tractability
```sql
CREATE TABLE opentargets_target_tractability (
    gene_id TEXT PRIMARY KEY REFERENCES gene_transcript(gene_id),

    -- Small molecule tractability
    sm_clinical_precedence BOOLEAN,
    sm_discovery_precedence BOOLEAN,
    sm_predicted_tractable BOOLEAN,
    sm_top_bucket TEXT,  -- Highest tractability category

    -- Antibody tractability
    ab_clinical_precedence BOOLEAN,
    ab_predicted_tractable BOOLEAN,
    ab_top_bucket TEXT,

    -- Other modality tractability
    other_modality_tractable BOOLEAN,

    tractability_summary TEXT,  -- Human-readable summary

    metadata JSONB,
    ot_version TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE opentargets_target_tractability IS
'Druggability assessment for gene targets from Open Targets. Clinical_precedence indicates drugs exist for this target or related family members. Use to assess likelihood of successful drug development.';
```

### Indexes for LLM-Generated Query Performance

```sql
-- Disease lookups
CREATE INDEX idx_ot_diseases_name ON opentargets_diseases
    USING gin(to_tsvector('english', disease_name));
CREATE INDEX idx_ot_diseases_cancer ON opentargets_diseases(is_cancer)
    WHERE is_cancer = true;

-- Association queries (most common)
CREATE INDEX idx_ot_assoc_gene ON opentargets_gene_disease_associations(gene_id);
CREATE INDEX idx_ot_assoc_disease ON opentargets_gene_disease_associations(disease_id);
CREATE INDEX idx_ot_assoc_score ON opentargets_gene_disease_associations(overall_score DESC);
CREATE INDEX idx_ot_assoc_gene_score ON opentargets_gene_disease_associations(gene_id, overall_score DESC);

-- Composite index for cancer + high-score queries
CREATE INDEX idx_ot_assoc_cancer_genes ON opentargets_gene_disease_associations(gene_id, overall_score)
    WHERE overall_score >= 0.5;

-- Drug queries
CREATE INDEX idx_ot_drugs_target ON opentargets_known_drugs(target_gene_id);
CREATE INDEX idx_ot_drugs_disease ON opentargets_known_drugs(disease_id);
CREATE INDEX idx_ot_drugs_approved ON opentargets_known_drugs(is_approved, clinical_phase);
CREATE INDEX idx_ot_drugs_chembl ON opentargets_known_drugs(molecule_chembl_id)
    WHERE molecule_chembl_id IS NOT NULL;

-- Full-text search on drug names
CREATE INDEX idx_ot_drugs_name ON opentargets_known_drugs
    USING gin(to_tsvector('english', molecule_name));

-- Tractability
CREATE INDEX idx_ot_tract_sm ON opentargets_target_tractability(gene_id)
    WHERE sm_clinical_precedence = true OR sm_predicted_tractable = true;
```

## LLM-Friendly Design Principles

### 1. Clear Naming Conventions
- **Table names**: Prefix with `opentargets_` for clear data source
- **Column names**: Full words, no abbreviations (e.g., `overall_score` not `ot_score`)
- **Boolean flags**: Prefix with `is_` or `has_`
- **Score columns**: Suffix with `_score`, values 0-1
- **ID columns**: Suffix with `_id`, foreign keys explicitly named

### 2. Comprehensive Comments
Every table and important column must have COMMENT explaining:
- What the data represents
- How to interpret scores/values
- Which columns to use for joins
- Clinical interpretation guidelines

### 3. Denormalization for Query Simplicity
- Store both `clinical_phase` (numeric) and `clinical_phase_label` (text)
- Include `is_cancer` boolean rather than requiring ontology traversal
- Provide `tractability_summary` text alongside detailed flags

### 4. Query-Optimized Structure
```sql
-- Example LLM-generated query pattern:
-- "Find approved drugs targeting overexpressed genes in this patient"

SELECT
    gt.gene_symbol,
    gt.cancer_fold,
    okd.molecule_name,
    okd.mechanism_of_action,
    oga.overall_score as evidence_score,
    ot_diseases.disease_name
FROM gene_transcript gt
JOIN opentargets_gene_disease_associations oga ON gt.gene_id = oga.gene_id
JOIN opentargets_diseases od ON oga.disease_id = od.disease_id
JOIN opentargets_known_drugs okd ON gt.gene_id = okd.target_gene_id
    AND oga.disease_id = okd.disease_id
WHERE gt.cancer_fold > 2.0  -- Patient-specific overexpression
    AND od.is_cancer = true
    AND okd.is_approved = true
    AND oga.overall_score >= 0.7  -- Strong evidence
ORDER BY gt.cancer_fold DESC, oga.overall_score DESC
LIMIT 20;
```

## Clinical Relevance Guidelines

### Association Score Interpretation for Oncologists

**Overall Score Thresholds:**
- **0.85-1.0**: Very strong evidence - Well-established cancer genes (TP53, EGFR, KRAS)
- **0.70-0.84**: Strong evidence - Known cancer-associated genes with multiple evidence types
- **0.50-0.69**: Moderate evidence - Emerging targets, require additional validation
- **< 0.50**: Weak evidence - Include only if supported by other evidence in context

### Evidence Type Prioritization

**For Treatment Selection (Actionability):**
1. `known_drug_score` - Direct drug availability
2. `somatic_mutation_score` - Cancer-specific alterations
3. `tractability_clinical_precedence` - Drug development feasibility

**For Diagnosis/Prognosis:**
1. `somatic_mutation_score` - Established cancer drivers
2. `literature_score` - Published clinical associations
3. `genetic_association_score` - Heritable risk factors

**For Research/Novel Targets:**
1. `pathways_systems_biology_score` - Mechanistic understanding
2. `rna_expression_score` - Differential expression evidence
3. `animal_model_score` - Preclinical validation

### Cancer Type Specificity

**High-Quality Cancer Associations (Prioritize):**
- Solid tumors with large genomic studies (TCGA, ICGC)
- Hematological malignancies with molecular subtyping
- Cancers with targeted therapy precedent

**Cancer EFO Terms to Highlight:**
```sql
-- Store in configuration table for easy LLM access
CREATE TABLE opentargets_priority_cancers (
    disease_id TEXT PRIMARY KEY,
    disease_name TEXT,
    priority_level TEXT,  -- 'HIGH', 'MEDIUM', 'LOW'
    rationale TEXT
);

-- Example high-priority entries:
INSERT INTO opentargets_priority_cancers VALUES
('EFO_0000616', 'neoplasm', 'HIGH', 'Root cancer term'),
('EFO_0000305', 'breast carcinoma', 'HIGH', 'Extensive genomic characterization'),
('EFO_0000571', 'lung carcinoma', 'HIGH', 'Large clinical trial data'),
('EFO_0000182', 'acute myeloid leukemia', 'HIGH', 'Molecular subtype classification'),
('EFO_0000313', 'melanoma', 'HIGH', 'Immunotherapy and targeted therapy data'),
('EFO_0005842', 'colorectal carcinoma', 'HIGH', 'TCGA comprehensive analysis');
```

## Implementation Roadmap

### Phase 1: Core Association Data (Week 1-2)
1. Download and process `associationByOverallDirect`
2. Download and process `diseases`
3. Implement `opentargets_diseases` and `opentargets_gene_disease_associations` tables
4. Create cancer-filtered subset (is_cancer = true)
5. Apply score threshold (overall_score >= 0.5)
6. Build indexes
7. Add comprehensive schema comments
8. Test LLM query generation with sample queries

### Phase 2: Drug Data Integration (Week 3)
1. Download `knownDrugsAggregated` and `mechanismOfAction`
2. Implement `opentargets_known_drugs` table
3. Cross-reference with existing DrugCentral/ChEMBL data
4. Identify drug-target-disease triads for actionability
5. Test clinical workflow: overexpressed gene → known drug query

### Phase 3: Tractability & Evidence Detail (Week 4)
1. Download `targets` for tractability data
2. Implement `opentargets_target_tractability` table
3. Download filtered `associationByDatatypeDirect` for evidence breakdown
4. Enhance association table with datatype scores
5. Create views for common query patterns

### Phase 4: Validation & Documentation (Week 5)
1. Validate against known cancer genes (COSMIC, OncoKB)
2. Test with real patient transcriptome data
3. Document example LLM prompts and generated queries
4. Create oncologist-friendly query templates
5. Benchmark query performance

## Data Quality Considerations

### Validation Checks During ETL
```python
# Pseudocode for ETL validation
def validate_association_data(df):
    """Validate Open Targets association data quality."""
    checks = {
        'score_range': df['overall_score'].between(0, 1).all(),
        'gene_coverage': df['gene_id'].isin(existing_genes).sum() / len(df),
        'cancer_proportion': df['is_cancer'].sum() / len(df),
        'high_confidence': (df['overall_score'] >= 0.7).sum() / len(df)
    }

    # Expected ranges for oncology-focused dataset
    assert checks['score_range'], "Scores must be 0-1"
    assert checks['gene_coverage'] > 0.8, "Low gene ID match rate"
    assert checks['cancer_proportion'] > 0.3, "Too few cancer associations"

    return checks
```

### Known Data Quality Issues
1. **Gene ID mapping**: Open Targets uses Ensembl gene IDs - ensure alignment with your `gene_id` format
2. **Disease hierarchy complexity**: EFO includes very specific subtypes - balance granularity vs usability
3. **Evidence score interpretation**: Scores are not directly comparable across evidence types
4. **Clinical phase updates**: Drug development status changes frequently - note data age

## Integration with Existing MEDIABASE Schema

### Enhanced Gene View
```sql
-- Create materialized view combining all gene annotations
CREATE MATERIALIZED VIEW gene_clinical_summary AS
SELECT
    gt.gene_id,
    gt.gene_symbol,
    gt.gene_name,
    gt.cancer_fold,  -- Patient-specific

    -- Open Targets disease associations
    COALESCE(COUNT(DISTINCT oga.disease_id) FILTER (WHERE od.is_cancer), 0)
        as cancer_association_count,
    MAX(oga.overall_score) FILTER (WHERE od.is_cancer)
        as max_cancer_association_score,

    -- Druggability
    COALESCE(ott.sm_clinical_precedence, false) as small_molecule_tractable,
    COALESCE(ott.ab_clinical_precedence, false) as antibody_tractable,

    -- Known drugs
    COUNT(DISTINCT okd.drug_id) FILTER (WHERE okd.is_approved)
        as approved_drug_count,
    COUNT(DISTINCT okd.drug_id) FILTER (WHERE okd.clinical_phase >= 2)
        as clinical_drug_count,

    -- Existing MEDIABASE data
    COUNT(DISTINCT gp.product_id) as product_count,
    COUNT(DISTINCT ggo.go_id) as go_term_count,
    COUNT(DISTINCT gpa.pathway_id) as pathway_count

FROM gene_transcript gt
LEFT JOIN opentargets_gene_disease_associations oga ON gt.gene_id = oga.gene_id
LEFT JOIN opentargets_diseases od ON oga.disease_id = od.disease_id
LEFT JOIN opentargets_target_tractability ott ON gt.gene_id = ott.gene_id
LEFT JOIN opentargets_known_drugs okd ON gt.gene_id = okd.target_gene_id
LEFT JOIN gene_product gp ON gt.gene_id = gp.gene_id
LEFT JOIN gene_go ggo ON gt.gene_id = ggo.gene_id
LEFT JOIN gene_pathway gpa ON gt.gene_id = gpa.gene_id
GROUP BY gt.gene_id, gt.gene_symbol, gt.gene_name, gt.cancer_fold,
         ott.sm_clinical_precedence, ott.ab_clinical_precedence;

COMMENT ON MATERIALIZED VIEW gene_clinical_summary IS
'Comprehensive gene summary combining patient-specific expression, Open Targets disease associations, druggability, known drugs, and existing MEDIABASE annotations. Refresh after data updates. Use for high-level gene prioritization queries.';

-- Index for common query patterns
CREATE INDEX idx_gene_clinical_cancer_fold ON gene_clinical_summary(cancer_fold DESC);
CREATE INDEX idx_gene_clinical_druggable ON gene_clinical_summary(approved_drug_count DESC)
    WHERE approved_drug_count > 0;
```

## Example LLM Query Templates

### Template 1: Actionable Overexpressed Genes
```sql
-- Prompt: "Show me overexpressed genes with approved drugs"
-- Generated query:

SELECT
    gt.gene_symbol,
    gt.cancer_fold as fold_change,
    od.disease_name,
    oga.overall_score as association_strength,
    okd.molecule_name as drug_name,
    okd.mechanism_of_action,
    okd.clinical_phase
FROM gene_transcript gt
JOIN opentargets_gene_disease_associations oga ON gt.gene_id = oga.gene_id
JOIN opentargets_diseases od ON oga.disease_id = od.disease_id
JOIN opentargets_known_drugs okd ON gt.gene_id = okd.target_gene_id
WHERE gt.cancer_fold > 2.0
    AND od.is_cancer = true
    AND okd.is_approved = true
    AND oga.overall_score >= 0.5
ORDER BY gt.cancer_fold DESC, oga.overall_score DESC;
```

### Template 2: Novel Target Discovery
```sql
-- Prompt: "Find highly overexpressed genes that are druggable but lack approved therapies"
-- Generated query:

SELECT
    gt.gene_symbol,
    gt.cancer_fold,
    oga.overall_score as cancer_association,
    ott.sm_top_bucket as small_molecule_tractability,
    ott.ab_top_bucket as antibody_tractability,
    COUNT(DISTINCT okd.drug_id) FILTER (WHERE okd.clinical_phase <= 3) as investigational_drugs
FROM gene_transcript gt
JOIN opentargets_gene_disease_associations oga ON gt.gene_id = oga.gene_id
JOIN opentargets_diseases od ON oga.disease_id = od.disease_id
JOIN opentargets_target_tractability ott ON gt.gene_id = ott.gene_id
LEFT JOIN opentargets_known_drugs okd ON gt.gene_id = okd.target_gene_id
WHERE gt.cancer_fold > 3.0
    AND od.is_cancer = true
    AND oga.overall_score >= 0.6
    AND (ott.sm_clinical_precedence = true OR ott.ab_clinical_precedence = true)
    AND NOT EXISTS (
        SELECT 1 FROM opentargets_known_drugs okd2
        WHERE okd2.target_gene_id = gt.gene_id AND okd2.is_approved = true
    )
GROUP BY gt.gene_id, gt.gene_symbol, gt.cancer_fold, oga.overall_score,
         ott.sm_top_bucket, ott.ab_top_bucket
ORDER BY gt.cancer_fold DESC;
```

### Template 3: Evidence-Based Gene Ranking
```sql
-- Prompt: "Rank my patient's overexpressed genes by cancer relevance"
-- Generated query:

SELECT
    gt.gene_symbol,
    gt.cancer_fold,

    -- Multi-source evidence aggregation
    MAX(oga.overall_score) as max_cancer_association,
    MAX(oga.somatic_mutation_score) as somatic_evidence,
    MAX(oga.known_drug_score) as drug_evidence,
    MAX(oga.literature_score) as literature_evidence,

    -- Clinical actionability
    COUNT(DISTINCT okd.drug_id) FILTER (WHERE okd.is_approved) as approved_drugs,

    -- Composite score for ranking
    (gt.cancer_fold / 2.0) * MAX(oga.overall_score) as priority_score

FROM gene_transcript gt
LEFT JOIN opentargets_gene_disease_associations oga ON gt.gene_id = oga.gene_id
LEFT JOIN opentargets_diseases od ON oga.disease_id = od.disease_id
LEFT JOIN opentargets_known_drugs okd ON gt.gene_id = okd.target_gene_id
WHERE gt.cancer_fold > 1.5
    AND (od.is_cancer = true OR od.disease_id IS NULL)
GROUP BY gt.gene_id, gt.gene_symbol, gt.cancer_fold
HAVING MAX(oga.overall_score) >= 0.4 OR COUNT(DISTINCT okd.drug_id) > 0
ORDER BY priority_score DESC
LIMIT 50;
```

## Maintenance & Updates

### Quarterly Update Workflow
1. Check for new Open Targets release
2. Download new datasets to separate cache directory
3. Run ETL with `--ot-version` parameter
4. Validate data quality metrics
5. Compare association counts vs previous version
6. Update `ot_version` in all affected tables
7. Refresh materialized views
8. Re-run test queries
9. Update documentation with version notes

### Version Management
```sql
-- Track Open Targets versions
CREATE TABLE opentargets_metadata (
    version TEXT PRIMARY KEY,
    release_date DATE,
    loaded_date TIMESTAMP DEFAULT NOW(),
    record_counts JSONB,  -- Counts by table
    validation_results JSONB,
    notes TEXT
);
```

## Performance Monitoring

### Query Performance Targets
- Gene-disease lookup: < 50ms
- Drug recommendation query: < 200ms
- Complex multi-join analysis: < 1s
- Materialized view refresh: < 5 minutes

### Optimization Strategy
1. Partition large tables by `ot_version` if historical versions retained
2. Use materialized views for common aggregate queries
3. Implement query result caching at API layer
4. Monitor slow query log for LLM-generated patterns

## References & Resources

- Open Targets Platform: https://platform.opentargets.org/
- Data downloads: ftp://ftp.ebi.ac.uk/pub/databases/opentargets/platform/
- API documentation: https://platform-docs.opentargets.org/
- EFO ontology: https://www.ebi.ac.uk/efo/
- Data model: https://platform-docs.opentargets.org/data-access/graphql
- Scoring methodology: https://platform-docs.opentargets.org/associations

---

## Next Steps

1. Review and approve this integration plan
2. Create ETL module skeleton: `src/etl/opentargets.py`
3. Download sample datasets for testing
4. Implement Phase 1 (disease + association tables)
5. Test with real patient data
6. Iterate on LLM query patterns

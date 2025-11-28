# OpenTargets Platform Integration Guide

**Version:** v0.6.0.2
**Last Updated:** 2025-11-25
**Status:** Production-Ready

---

## Table of Contents

1. [Overview](#overview)
2. [What is OpenTargets Platform?](#what-is-opentargets-platform)
3. [Data Tables](#data-tables)
4. [Common Query Patterns](#common-query-patterns)
5. [Clinical Applications](#clinical-applications)
6. [Data Quality Notes](#data-quality-notes)
7. [ETL Process](#etl-process)

---

## Overview

OpenTargets Platform is a comprehensive, open-source resource that integrates genetic, genomic, transcriptomic, and chemical data to support systematic identification and prioritization of potential therapeutic drug targets. MEDIABASE integrates four core OpenTargets datasets with 47M+ gene-publication links from PubTator Central to provide:

- **Disease associations**: Gene-disease relationships with evidence scores
- **Known drugs**: FDA-approved and experimental drugs with target information
- **Target tractability**: Druggability assessments for gene targets
- **Disease ontology**: Standardized disease classifications and hierarchies

**Integration Statistics:**
- **Total Records:** 484,126
- **Total Size:** ~320 MB
- **Data Source:** OpenTargets Platform v24.09
- **Update Frequency:** Quarterly (recommended)

---

## What is OpenTargets Platform?

OpenTargets Platform (https://www.targetvalidation.org) aggregates data from multiple sources to provide evidence-based target identification and validation:

### Data Sources Integrated
- **Genetic associations**: GWAS catalog, PheWAS, Gene2Phenotype
- **Somatic mutations**: Cancer Gene Census, IntOGen
- **Drugs**: ChEMBL, FDA labels
- **Pathways**: Reactome, SLAPenrich
- **Literature**: Europe PMC text mining
- **RNA expression**: Expression Atlas
- **Animal models**: PhenoDigm

### Evidence Types
OpenTargets computes `overall_score` (0-1) by integrating:
- Genetic association evidence
- Somatic mutation evidence
- Known drug evidence
- Literature evidence
- Pathway evidence
- RNA expression evidence

---

## Data Tables

### 1. opentargets_diseases

**Purpose:** Disease ontology and classifications
**Records:** 28,327
**Size:** 44 MB

#### Schema
```sql
CREATE TABLE opentargets_diseases (
    disease_id TEXT PRIMARY KEY,         -- e.g., 'MONDO_0008903'
    disease_name TEXT NOT NULL,          -- Human-readable name
    disease_type TEXT,                   -- 'disease', 'phenotype', etc.
    therapeutic_areas TEXT[]             -- Broader disease categories
);
```

#### Example Query
```sql
-- Find all cancer-related diseases
SELECT disease_id, disease_name, disease_type
FROM opentargets_diseases
WHERE 'neoplasm' = ANY(therapeutic_areas)
   OR disease_name ILIKE '%cancer%'
ORDER BY disease_name
LIMIT 10;
```

**Sample Output:**
```
   disease_id    |        disease_name         | disease_type
-----------------+-----------------------------+--------------
 MONDO_0004992   | cancer                      | disease
 MONDO_0008170   | colorectal cancer           | disease
 MONDO_0007254   | breast carcinoma            | disease
```

---

### 2. opentargets_gene_disease_associations

**Purpose:** Gene-disease relationships with evidence scores
**Records:** 2,677
**Size:** 2.2 MB

#### Schema
```sql
CREATE TABLE opentargets_gene_disease_associations (
    gene_id TEXT,                        -- Foreign key to genes.gene_id
    disease_id TEXT,                     -- Foreign key to opentargets_diseases.disease_id
    overall_score NUMERIC(4,3),          -- Confidence score (0-1)
    genetic_association_score NUMERIC(4,3),  -- Currently NULL
    somatic_mutation_score NUMERIC(4,3),     -- Currently NULL
    known_drug_score NUMERIC(4,3),           -- Currently NULL
    literature_score NUMERIC(4,3),           -- Currently NULL
    PRIMARY KEY (gene_id, disease_id)
);
```

#### Important Notes
- **Populated fields:** `overall_score` is always present and reliable
- **Unpopulated fields:** Individual evidence scores (genetic_association, somatic_mutation, literature, known_drug) are currently NULL in this integration
- **Use case:** Prioritize genes by overall_score for disease associations

#### Example Query
```sql
-- Find top cancer driver genes
SELECT
    g.gene_symbol,
    od.disease_name,
    ogda.overall_score,
    COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
    CASE
        WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
        ELSE 'Limited publications'
    END as evidence_level
FROM opentargets_gene_disease_associations ogda
JOIN genes g ON ogda.gene_id = g.gene_id
JOIN opentargets_diseases od ON ogda.disease_id = od.disease_id
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
WHERE ogda.overall_score > 0.7
  AND od.disease_name ILIKE '%cancer%'
GROUP BY g.gene_symbol, od.disease_name, ogda.overall_score
ORDER BY publication_count DESC, ogda.overall_score DESC
LIMIT 10;
```

**Sample Output:**
```
 gene_symbol |   disease_name    | overall_score
-------------+-------------------+---------------
 BRAF        | colorectal cancer |        0.7806
 KRAS        | gastric cancer    |        0.7699
 PIK3CA      | ovarian cancer    |        0.7547
 EGFR        | lung cancer       |        0.7532
```

**Score Interpretation:**
- **≥ 0.85**: Very strong evidence (established targets)
- **≥ 0.70**: Strong evidence (validated targets)
- **≥ 0.50**: Moderate evidence (emerging targets)
- **< 0.50**: Weak evidence (deprioritize)

---

### 3. opentargets_known_drugs

**Purpose:** Drugs targeting specific genes across clinical phases
**Records:** 391,122
**Size:** 208 MB

#### Schema
```sql
CREATE TABLE opentargets_known_drugs (
    target_gene_id TEXT,                 -- Gene targeted by drug (TEXT, not INTEGER)
    disease_id TEXT,                     -- Disease being treated
    clinical_phase NUMERIC(3,1),        -- 0.5, 1.0, 2.0, 3.0, 4.0
    clinical_phase_label TEXT,          -- 'Phase IV', 'Phase III', etc.
    mechanism_of_action TEXT,           -- How drug works
    molecule_name TEXT,                 -- Drug name
    is_approved BOOLEAN                 -- FDA approval status
);
```

#### Important Schema Note
The column is named `target_gene_id` (not `gene_id`), and it stores **TEXT values** (not integers). Always use this column name when joining.

#### Example Query
```sql
-- Find FDA-approved drugs for a specific gene
SELECT
    okd.molecule_name as drug_name,
    okd.mechanism_of_action,
    od.disease_name,
    okd.clinical_phase_label,
    COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
    CASE
        WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
        ELSE 'Limited publications'
    END as evidence_level
FROM opentargets_known_drugs okd
JOIN opentargets_diseases od ON okd.disease_id = od.disease_id
LEFT JOIN gene_publications gp ON okd.target_gene_id = gp.gene_id
WHERE okd.target_gene_id = 'ENSG00000146648'  -- EGFR gene
  AND okd.is_approved = true
GROUP BY okd.molecule_name, okd.mechanism_of_action, od.disease_name, okd.clinical_phase_label, okd.clinical_phase
ORDER BY publication_count DESC, okd.clinical_phase DESC
LIMIT 10;
```

**Sample Output:**
```
    drug_name     |  mechanism_of_action   |    disease_name     | clinical_phase_label
------------------+------------------------+---------------------+---------------------
 ERLOTINIB        | EGFR inhibitor         | lung cancer         | Phase IV
 GEFITINIB        | EGFR inhibitor         | lung cancer         | Phase IV
 OSIMERTINIB      | EGFR inhibitor         | lung cancer         | Phase IV
```

**Clinical Phase Guide:**
- **Phase IV (4.0)**: FDA-approved, post-market surveillance
- **Phase III (3.0)**: Late-stage trials (500-3000 patients)
- **Phase II (2.0)**: Mid-stage trials (100-300 patients)
- **Phase I (1.0)**: Early safety trials (20-80 patients)
- **Phase 0 (0.5)**: Exploratory/pre-clinical

---

### 4. opentargets_target_tractability

**Purpose:** Druggability assessments for gene targets
**Records:** 62,000
**Size:** 66 MB

#### Schema
```sql
CREATE TABLE opentargets_target_tractability (
    gene_id TEXT PRIMARY KEY,
    small_molecule_tractable BOOLEAN,   -- Can be targeted by small molecules
    antibody_tractable BOOLEAN,         -- Can be targeted by antibodies
    tractability_category TEXT          -- Overall druggability assessment
);
```

#### Example Query
```sql
-- Find druggable targets with high disease association
SELECT
    g.gene_symbol,
    ogda.overall_score,
    ott.small_molecule_tractable,
    ott.antibody_tractable,
    ott.tractability_category,
    COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
    CASE
        WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
        ELSE 'Limited publications'
    END as evidence_level
FROM opentargets_gene_disease_associations ogda
JOIN genes g ON ogda.gene_id = g.gene_id
JOIN opentargets_target_tractability ott ON g.gene_id = ott.gene_id
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
WHERE ogda.overall_score > 0.7
  AND (ott.small_molecule_tractable = true OR ott.antibody_tractable = true)
GROUP BY g.gene_symbol, ogda.overall_score, ott.small_molecule_tractable, ott.antibody_tractable, ott.tractability_category
ORDER BY publication_count DESC, ogda.overall_score DESC
LIMIT 10;
```

**Sample Output:**
```
 gene_symbol | overall_score | small_molecule_tractable | antibody_tractable | tractability_category
-------------+---------------+--------------------------+--------------------+----------------------
 EGFR        |        0.8234 | t                        | t                  | Clinical_Precedence
 BRAF        |        0.8102 | t                        | f                  | Clinical_Precedence
 ALK         |        0.7956 | t                        | t                  | Clinical_Precedence
```

---

## Common Query Patterns

### Pattern 1: Find Druggable Targets for a Disease

```sql
-- Find druggable genes for colorectal cancer
SELECT
    g.gene_symbol,
    ogda.overall_score,
    COUNT(DISTINCT okd.molecule_name) as drug_count,
    ott.small_molecule_tractable,
    ott.antibody_tractable,
    COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
    CASE
        WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
        ELSE 'Limited publications'
    END as evidence_level
FROM opentargets_gene_disease_associations ogda
JOIN genes g ON ogda.gene_id = g.gene_id
JOIN opentargets_diseases od ON ogda.disease_id = od.disease_id
LEFT JOIN opentargets_known_drugs okd ON g.gene_id = okd.target_gene_id
LEFT JOIN opentargets_target_tractability ott ON g.gene_id = ott.gene_id
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
WHERE od.disease_name = 'colorectal cancer'
  AND ogda.overall_score > 0.5
GROUP BY g.gene_symbol, ogda.overall_score, ott.small_molecule_tractable, ott.antibody_tractable
ORDER BY publication_count DESC, ogda.overall_score DESC, drug_count DESC
LIMIT 20;
```

### Pattern 2: Drug Repurposing Candidates

```sql
-- Find drugs approved for one disease that target genes associated with another
SELECT
    okd.molecule_name as drug_name,
    od_approved.disease_name as approved_for,
    od_target.disease_name as potential_repurposing,
    ogda.overall_score as target_score,
    okd.mechanism_of_action,
    COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
    CASE
        WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
        ELSE 'Limited publications'
    END as evidence_level
FROM opentargets_known_drugs okd
JOIN opentargets_diseases od_approved ON okd.disease_id = od_approved.disease_id
JOIN opentargets_gene_disease_associations ogda ON okd.target_gene_id = ogda.gene_id
JOIN opentargets_diseases od_target ON ogda.disease_id = od_target.disease_id
LEFT JOIN gene_publications gp ON okd.target_gene_id = gp.gene_id
WHERE okd.is_approved = true
  AND od_approved.disease_id != od_target.disease_id
  AND ogda.overall_score > 0.7
  AND od_target.disease_name = 'breast carcinoma'
GROUP BY okd.molecule_name, od_approved.disease_name, od_target.disease_name, ogda.overall_score, okd.mechanism_of_action
ORDER BY publication_count DESC, ogda.overall_score DESC
LIMIT 20;
```

### Pattern 3: Patient-Specific Actionable Targets

```sql
-- Find actionable targets from patient's upregulated genes
SELECT
    ctb.gene_symbol,
    ctb.expression_fold_change,
    ogda.overall_score as disease_score,
    COUNT(DISTINCT okd.molecule_name) FILTER (WHERE okd.is_approved = true) as approved_drugs,
    COUNT(DISTINCT okd.molecule_name) as total_drugs,
    ott.small_molecule_tractable,
    ott.antibody_tractable,
    COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
    CASE
        WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
        ELSE 'Limited publications'
    END as evidence_level
FROM cancer_transcript_base ctb
JOIN genes g ON ctb.gene_symbol = g.gene_symbol
JOIN opentargets_gene_disease_associations ogda ON g.gene_id = ogda.gene_id
JOIN opentargets_diseases od ON ogda.disease_id = od.disease_id
LEFT JOIN opentargets_known_drugs okd ON g.gene_id = okd.target_gene_id
LEFT JOIN opentargets_target_tractability ott ON g.gene_id = ott.gene_id
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
WHERE ctb.expression_fold_change > 2.0
  AND od.disease_name = 'breast carcinoma'
  AND ogda.overall_score > 0.6
GROUP BY ctb.gene_symbol, ctb.expression_fold_change, ogda.overall_score,
         ott.small_molecule_tractable, ott.antibody_tractable
HAVING COUNT(DISTINCT okd.molecule_name) FILTER (WHERE okd.is_approved = true) > 0
ORDER BY publication_count DESC, ogda.overall_score DESC, approved_drugs DESC
LIMIT 20;
```

---

## Clinical Applications

### 1. Biomarker Panel Design

Use OpenTargets to prioritize genes for inclusion in diagnostic panels:

```sql
-- Top 50 cancer biomarkers by evidence strength
SELECT
    g.gene_symbol,
    ogda.overall_score,
    COUNT(DISTINCT od.disease_name) as disease_count,
    COUNT(DISTINCT okd.molecule_name) FILTER (WHERE okd.clinical_phase >= 3.0) as drug_count,
    COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
    CASE
        WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
        ELSE 'Limited publications'
    END as evidence_level
FROM opentargets_gene_disease_associations ogda
JOIN genes g ON ogda.gene_id = g.gene_id
JOIN opentargets_diseases od ON ogda.disease_id = od.disease_id
LEFT JOIN opentargets_known_drugs okd ON g.gene_id = okd.target_gene_id
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
WHERE 'neoplasm' = ANY(od.therapeutic_areas)
  AND ogda.overall_score > 0.75
GROUP BY g.gene_symbol, ogda.overall_score
ORDER BY publication_count DESC, ogda.overall_score DESC, disease_count DESC
LIMIT 50;
```

### 2. Treatment Selection

Match patient mutations to available therapies:

```sql
-- Patient-specific treatment options
SELECT
    ctb.gene_symbol,
    ctb.expression_fold_change,
    okd.molecule_name,
    okd.mechanism_of_action,
    okd.clinical_phase_label,
    ogda.overall_score,
    COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
    CASE
        WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
        ELSE 'Limited publications'
    END as evidence_level
FROM cancer_transcript_base ctb
JOIN genes g ON ctb.gene_symbol = g.gene_symbol
JOIN opentargets_gene_disease_associations ogda ON g.gene_id = ogda.gene_id
JOIN opentargets_diseases od ON ogda.disease_id = od.disease_id
JOIN opentargets_known_drugs okd ON g.gene_id = okd.target_gene_id
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
WHERE ctb.expression_fold_change > 3.0
  AND od.disease_name = 'lung cancer'
  AND okd.is_approved = true
  AND ogda.overall_score > 0.7
GROUP BY ctb.gene_symbol, ctb.expression_fold_change, okd.molecule_name, okd.mechanism_of_action, okd.clinical_phase_label, ogda.overall_score, okd.clinical_phase
ORDER BY publication_count DESC, ogda.overall_score DESC, okd.clinical_phase DESC;
```

### 3. Clinical Trial Matching

Identify ongoing clinical trials for patient's molecular profile:

```sql
-- Experimental therapies in development
SELECT
    g.gene_symbol,
    okd.molecule_name,
    okd.mechanism_of_action,
    okd.clinical_phase_label,
    od.disease_name,
    COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
    CASE
        WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
        ELSE 'Limited publications'
    END as evidence_level
FROM genes g
JOIN opentargets_known_drugs okd ON g.gene_id = okd.target_gene_id
JOIN opentargets_diseases od ON okd.disease_id = od.disease_id
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
WHERE g.gene_symbol IN ('BRAF', 'KRAS', 'EGFR', 'ALK', 'ROS1')
  AND okd.clinical_phase BETWEEN 2.0 AND 3.0
  AND od.disease_name = 'lung cancer'
GROUP BY g.gene_symbol, okd.molecule_name, okd.mechanism_of_action, okd.clinical_phase_label, od.disease_name, okd.clinical_phase
ORDER BY publication_count DESC, okd.clinical_phase DESC, g.gene_symbol;
```

---

## Data Quality Notes

### Populated Fields
- **opentargets_diseases**: All fields fully populated
- **opentargets_gene_disease_associations**: `overall_score` is reliable
- **opentargets_known_drugs**: All fields fully populated
- **opentargets_target_tractability**: All fields fully populated

### Unpopulated Fields
The following fields in `opentargets_gene_disease_associations` are currently NULL:
- `genetic_association_score`
- `somatic_mutation_score`
- `known_drug_score`
- `literature_score`

**Workaround**: Use `overall_score` as the primary confidence metric. It aggregates all evidence types into a single 0-1 score.

### Known Limitations

1. **Disease Coverage**: Focus on cancer, immunology, and neurological diseases
2. **Drug Information**: Primarily covers small molecules and biologics; limited coverage of cell therapies or gene therapies
3. **Clinical Phase**: Phase information may lag behind actual trial status by 1-2 quarters
4. **Gene ID Format**: `target_gene_id` uses Ensembl gene IDs (ENSG...) as TEXT

### Data Freshness

- **Last ETL Run**: November 2025
- **Source Version**: OpenTargets Platform v24.09
- **Recommended Refresh**: Every 3-6 months
- **ETL Command**: `poetry run python scripts/run_etl.py --modules opentargets`

---

## ETL Process

### Running the ETL

```bash
# Full OpenTargets ETL
MB_POSTGRES_HOST=localhost \
MB_POSTGRES_PORT=5432 \
MB_POSTGRES_NAME=mbase \
MB_POSTGRES_USER=your_user \
MB_POSTGRES_PASSWORD=your_password \
poetry run python scripts/run_etl.py --modules opentargets --log-level INFO

# ETL with prerequisite modules
poetry run python scripts/run_etl.py \
  --modules transcripts id_enrichment opentargets \
  --log-level INFO
```

### ETL Performance

- **Duration**: ~15-20 minutes
- **Downloads**: ~2.5 GB compressed data
- **Processing**: 4 main files
- **Memory Usage**: ~2-3 GB peak

### Data Sources Downloaded

1. **Diseases**: `https://ftp.ebi.ac.uk/pub/databases/opentargets/platform/24.09/output/etl/json/diseases/`
2. **Gene-Disease Associations**: `https://ftp.ebi.ac.uk/pub/databases/opentargets/platform/24.09/output/etl/json/associationByDatatypeDirect/`
3. **Known Drugs**: `https://ftp.ebi.ac.uk/pub/databases/opentargets/platform/24.09/output/etl/json/knownDrugsAggregated/`
4. **Target Tractability**: `https://ftp.ebi.ac.uk/pub/databases/opentargets/platform/24.09/output/etl/json/targets/`

### Troubleshooting

**Issue**: ETL fails with "target_gene_id does not exist"
**Solution**: Ensure you're using `target_gene_id` (not `gene_id`) in `opentargets_known_drugs` queries

**Issue**: Slow query performance on opentargets_known_drugs
**Solution**: Add indexes:
```sql
CREATE INDEX idx_opentargets_known_drugs_gene
  ON opentargets_known_drugs(target_gene_id);
CREATE INDEX idx_opentargets_known_drugs_disease
  ON opentargets_known_drugs(disease_id);
CREATE INDEX idx_opentargets_known_drugs_approved
  ON opentargets_known_drugs(is_approved) WHERE is_approved = true;
```

**Issue**: NULL scores in gene_disease_associations
**Solution**: This is expected. Use `overall_score` instead of individual evidence scores.

---

## Integration with Other MEDIABASE Tables

### With Gene Expression Data

```sql
-- Correlate patient expression with OpenTargets evidence
SELECT
    ctb.gene_symbol,
    ctb.expression_fold_change,
    ogda.overall_score,
    od.disease_name,
    COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
    CASE
        WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
        ELSE 'Limited publications'
    END as evidence_level
FROM cancer_transcript_base ctb
JOIN genes g ON ctb.gene_symbol = g.gene_symbol
JOIN opentargets_gene_disease_associations ogda ON g.gene_id = ogda.gene_id
JOIN opentargets_diseases od ON ogda.disease_id = od.disease_id
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
WHERE ctb.expression_fold_change > 2.0
  AND ogda.overall_score > 0.7
GROUP BY ctb.gene_symbol, ctb.expression_fold_change, ogda.overall_score, od.disease_name
ORDER BY publication_count DESC;
```

### With Pathway Data

```sql
-- Find druggable pathways
SELECT
    gp.pathway_name,
    COUNT(DISTINCT g.gene_symbol) as gene_count,
    AVG(ogda.overall_score) as avg_disease_score,
    COUNT(DISTINCT okd.molecule_name) FILTER (WHERE okd.is_approved = true) as approved_drugs,
    COALESCE(AVG(pub_counts.pmid_count), 0) as avg_publication_count,
    CASE
        WHEN AVG(pub_counts.pmid_count) >= 100000 THEN 'Extensively studied'
        WHEN AVG(pub_counts.pmid_count) >= 10000 THEN 'Well-studied'
        WHEN AVG(pub_counts.pmid_count) >= 1000 THEN 'Moderate evidence'
        ELSE 'Limited publications'
    END as evidence_level
FROM gene_pathways gp
JOIN genes g ON gp.gene_id = g.gene_id
JOIN opentargets_gene_disease_associations ogda ON g.gene_id = ogda.gene_id
LEFT JOIN opentargets_known_drugs okd ON g.gene_id = okd.target_gene_id
LEFT JOIN (SELECT gene_id, COUNT(DISTINCT pmid) as pmid_count FROM gene_publications GROUP BY gene_id) pub_counts ON g.gene_id = pub_counts.gene_id
WHERE ogda.overall_score > 0.6
GROUP BY gp.pathway_name
HAVING COUNT(DISTINCT okd.molecule_name) FILTER (WHERE okd.is_approved = true) > 0
ORDER BY avg_publication_count DESC, avg_disease_score DESC, approved_drugs DESC
LIMIT 20;
```

### With Literature Evidence

```sql
-- Combine OpenTargets evidence with PubMed literature
SELECT
    g.gene_symbol,
    ogda.overall_score as opentargets_score,
    COUNT(DISTINCT gp.pmid) as pubmed_citations,
    od.disease_name
FROM opentargets_gene_disease_associations ogda
JOIN genes g ON ogda.gene_id = g.gene_id
JOIN opentargets_diseases od ON ogda.disease_id = od.disease_id
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
WHERE ogda.overall_score > 0.7
GROUP BY g.gene_symbol, ogda.overall_score, od.disease_name
ORDER BY ogda.overall_score DESC, pubmed_citations DESC
LIMIT 20;
```

---

## References

- **OpenTargets Platform**: https://www.targetvalidation.org
- **OpenTargets Documentation**: https://platform-docs.opentargets.org
- **OpenTargets FTP**: https://ftp.ebi.ac.uk/pub/databases/opentargets/platform/
- **OpenTargets API**: https://api.platform.opentargets.org/api/v4/docs

---

**For additional query examples, see:**
- [MEDIABASE_QUERY_LIBRARY.md](MEDIABASE_QUERY_LIBRARY.md) - Queries #3.1, #4.1, #4.2, #5.3
- [BREAST_CANCER_HER2_GUIDE.md](BREAST_CANCER_HER2_GUIDE.md) - HER2+ specific examples
- [COLORECTAL_CANCER_GUIDE.md](COLORECTAL_CANCER_GUIDE.md) - MSS/KRAS+ specific examples

---

*This guide reflects the current OpenTargets Platform integration (v24.09). For the latest updates and schema changes, consult the OpenTargets Platform documentation.*

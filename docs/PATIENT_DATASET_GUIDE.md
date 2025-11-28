# Patient Dataset Generation Guide

## Overview

This guide provides complete instructions for generating and validating **biologically realistic patient datasets** for MEDIABASE testing and demonstration purposes.

## Quick Start

```bash
# 1. Ensure database is populated with ETL data
poetry run python scripts/run_etl.py

# 2. Generate synthetic patient data
poetry run python scripts/generate_synthetic_patient_data.py \
    --cancer-type HER2_POSITIVE \
    --output examples/synthetic_patient_HER2.csv \
    --num-genes 500

# 3. Create patient-specific database
poetry run python scripts/create_patient_copy.py \
    --patient-id DEMO_HER2 \
    --csv-file examples/synthetic_patient_HER2.csv

# 4. Validate biological accuracy
PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U mbase_user \
    -d mediabase_patient_DEMO_HER2 \
    -f docs/PATIENT_VALIDATION_QUERIES.sql
```

---

## Recommended Test Datasets

### Patient 1: HER2+ Breast Cancer

**Clinical Profile**:
- **Subtype**: Luminal B / HER2-enriched
- **IHC Profile**: HER2 3+, ER+ (variable), PR+ (variable)
- **Molecular Features**:
  - ERBB2 amplification (chromosome 17q12)
  - PI3K/AKT pathway activation (common)
  - High proliferation (Ki-67 >20%)
- **Treatment Strategy**: HER2-targeted therapy + chemotherapy ± endocrine therapy

**Generation Command**:
```bash
poetry run python scripts/generate_synthetic_patient_data.py \
    --cancer-type HER2_POSITIVE \
    --output examples/synthetic_patient_HER2.csv \
    --num-genes 500 \
    --seed 42
```

**Expected Signature Genes**:
| Gene Symbol | Expected FC | Biological Significance                  |
|-------------|-------------|------------------------------------------|
| ERBB2       | 6.0 ± 1.0   | HER2 receptor amplification (target)     |
| GRB7        | 4.5 ± 0.8   | Co-amplified with HER2 on 17q12          |
| PIK3CA      | 2.8 ± 0.5   | PI3K pathway activation (30% of HER2+)   |
| MKI67       | 3.5 ± 0.6   | High proliferation marker                |
| ESR1        | 2.0 ± 0.4   | Estrogen receptor (if Luminal B subtype) |

**Validation**:
```sql
-- Confirm HER2+ status
SELECT gene_symbol, expression_fold_change
FROM cancer_transcript_base
WHERE gene_symbol = 'ERBB2';
-- Expected: 5.0-7.0 fold

-- Check HER2 amplicon
SELECT gene_symbol, expression_fold_change
FROM cancer_transcript_base
WHERE gene_symbol IN ('ERBB2', 'GRB7', 'PGAP3')
ORDER BY expression_fold_change DESC;
-- Expected: All > 3.5 fold
```

**Clinical Queries to Run**:
1. Find FDA-approved HER2-targeted drugs
2. Assess PI3K pathway for alpelisib eligibility
3. Check ER status for endocrine therapy decision
4. Evaluate CDK4/6 inhibitor candidacy

---

### Patient 2: Triple-Negative Breast Cancer (TNBC)

**Clinical Profile**:
- **Subtype**: Basal-like (most common TNBC subtype)
- **IHC Profile**: ER-, PR-, HER2- (all negative)
- **Molecular Features**:
  - TP53 mutations (80% of TNBC)
  - BRCA1/2 pathway defects (20-30%)
  - Very high proliferation (Ki-67 >50%)
  - Variable immune infiltration (40% PD-L1+)
- **Treatment Strategy**: Chemotherapy + immunotherapy (if PD-L1+) or PARP inhibitors (if BRCA mutant)

**Generation Command**:
```bash
poetry run python scripts/generate_synthetic_patient_data.py \
    --cancer-type TNBC \
    --output examples/synthetic_patient_TNBC.csv \
    --num-genes 500 \
    --seed 123
```

**Expected Signature Genes**:
| Gene Symbol | Expected FC | Biological Significance                  |
|-------------|-------------|------------------------------------------|
| ESR1        | 0.2 ± 0.05  | ER negative (diagnostic criterion)       |
| PGR         | 0.25 ± 0.05 | PR negative (diagnostic criterion)       |
| ERBB2       | 0.8 ± 0.15  | HER2 negative/normal                     |
| KRT5        | 4.5 ± 0.8   | Basal-like marker                        |
| KRT14       | 4.2 ± 0.7   | Basal-like marker                        |
| MKI67       | 5.5 ± 1.0   | Very high proliferation                  |
| TP53        | 0.3 ± 0.1   | p53 pathway loss (frequent mutation)     |
| CD274       | 2.0 ± 0.4   | PD-L1 (40% TNBC are PD-L1+)             |

**Validation**:
```sql
-- Confirm triple-negative status
SELECT gene_symbol, expression_fold_change
FROM cancer_transcript_base
WHERE gene_symbol IN ('ESR1', 'PGR', 'ERBB2')
ORDER BY gene_symbol;
-- Expected: All < 1.0, ESR1 and PGR < 0.5

-- Check basal-like phenotype
SELECT gene_symbol, expression_fold_change
FROM cancer_transcript_base
WHERE gene_symbol IN ('KRT5', 'KRT14', 'KRT17', 'EGFR')
ORDER BY expression_fold_change DESC;
-- Expected: All > 3.5 fold
```

**Clinical Queries to Run**:
1. Assess PD-L1 status for pembrolizumab eligibility
2. Check BRCA1/DNA repair genes for PARP inhibitor candidacy
3. Evaluate proliferation markers for chemotherapy sensitivity
4. Assess immune infiltration (CD8A) for prognosis

---

### Patient 3: Lung Adenocarcinoma (EGFR-mutant)

**Clinical Profile**:
- **Subtype**: EGFR-mutant NSCLC (never-smoker, Asian ancestry common)
- **Molecular Features**:
  - EGFR overexpression/mutation (L858R or exon 19 del)
  - Loss of lung differentiation markers
  - High VEGF expression (angiogenic)
  - Mutually exclusive with KRAS (usually)
- **Treatment Strategy**: EGFR TKI (osimertinib first-line) → chemotherapy → immunotherapy

**Generation Command**:
```bash
poetry run python scripts/generate_synthetic_patient_data.py \
    --cancer-type LUAD_EGFR \
    --output examples/synthetic_patient_LUAD.csv \
    --num-genes 500 \
    --seed 456
```

**Expected Signature Genes**:
| Gene Symbol | Expected FC | Biological Significance                  |
|-------------|-------------|------------------------------------------|
| EGFR        | 4.5 ± 0.8   | EGFR mutation/overexpression (target)    |
| AKT1        | 3.2 ± 0.6   | Downstream EGFR signaling                |
| VEGFA       | 4.0 ± 0.7   | Angiogenesis (anti-VEGF target)          |
| SFTPA1      | 0.3 ± 0.1   | Loss of lung surfactant (dedifferentiation) |
| SFTPC       | 0.25 ± 0.08 | Loss of lung surfactant                  |
| MKI67       | 3.5 ± 0.6   | High proliferation                       |
| ESR1        | 0.1 ± 0.03  | Breast marker absent (tissue specificity) |

**Validation**:
```sql
-- Confirm EGFR overexpression
SELECT gene_symbol, expression_fold_change
FROM cancer_transcript_base
WHERE gene_symbol = 'EGFR';
-- Expected: 3.5-5.5 fold

-- Check loss of lung differentiation
SELECT gene_symbol, expression_fold_change
FROM cancer_transcript_base
WHERE gene_symbol IN ('SFTPA1', 'SFTPB', 'SFTPC', 'SCGB1A1')
ORDER BY expression_fold_change;
-- Expected: All < 0.5 fold

-- Confirm NOT breast cancer
SELECT gene_symbol, expression_fold_change
FROM cancer_transcript_base
WHERE gene_symbol IN ('ESR1', 'PGR', 'GATA3')
ORDER BY expression_fold_change;
-- Expected: All < 0.3 fold (absent)
```

**Clinical Queries to Run**:
1. Identify EGFR TKI options (osimertinib, erlotinib, etc.)
2. Assess VEGF expression for bevacizumab combination
3. Evaluate TP53/STK11 status for prognosis
4. Compare lung-specific vs. breast-specific gene expression

---

## Biological Validation Criteria

### HER2+ Breast Cancer Validation

**PASS Criteria**:
- ✅ ERBB2 expression >4.0 fold (IHC 3+ equivalent)
- ✅ GRB7 co-amplification >3.5 fold
- ✅ At least 2 of: PIK3CA, AKT1, MTOR elevated (>2.0)
- ✅ Proliferation markers (MKI67, CCND1) >2.5 fold

**FAIL Indicators**:
- ❌ ERBB2 <2.0 fold (not HER2+)
- ❌ No amplicon co-amplification (not 17q12 amplicon)
- ❌ ESR1, PGR, ERBB2 all low (would be TNBC)

### TNBC Validation

**PASS Criteria**:
- ✅ ESR1 <0.5 fold (ER negative)
- ✅ PGR <0.5 fold (PR negative)
- ✅ ERBB2 <1.5 fold (HER2 negative)
- ✅ At least 2 basal markers (KRT5, KRT14, EGFR) >4.0 fold
- ✅ MKI67 >4.5 fold (very high proliferation)

**FAIL Indicators**:
- ❌ ESR1 or PGR >1.5 fold (ER or PR positive → not TNBC)
- ❌ ERBB2 >2.0 fold (HER2 positive → not TNBC)
- ❌ Low proliferation (MKI67 <2.0) → atypical

### Lung Adenocarcinoma Validation

**PASS Criteria**:
- ✅ EGFR >4.0 fold
- ✅ Lung differentiation markers (surfactants) <0.5 fold
- ✅ Breast markers (ESR1, PGR, GATA3) <0.3 fold
- ✅ VEGFA >3.0 fold (angiogenic)

**FAIL Indicators**:
- ❌ EGFR normal (<2.0) → not EGFR-driven
- ❌ Breast markers present → wrong tissue
- ❌ Lung differentiation retained → well-differentiated (atypical)

---

## Creating Patient Databases

### Standard Workflow

```bash
# Step 1: Generate synthetic data
poetry run python scripts/generate_synthetic_patient_data.py \
    --cancer-type HER2_POSITIVE \
    --output examples/synthetic_patient_HER2.csv \
    --num-genes 500

# Step 2: Create patient database copy
poetry run python scripts/create_patient_copy.py \
    --patient-id DEMO_HER2 \
    --csv-file examples/synthetic_patient_HER2.csv

# Step 3: Connect to patient database
PGPASSWORD=mbase_secret psql -h localhost -p 5435 \
    -U mbase_user -d mediabase_patient_DEMO_HER2

# Step 4: Run validation queries
\i docs/PATIENT_VALIDATION_QUERIES.sql

# Step 5: Run clinical queries
\i docs/CROSS_PATIENT_COMPARISON_QUERIES.sql
```

### Batch Generation (All 3 Patients)

```bash
#!/bin/bash
# generate_all_demo_patients.sh

# Patient 1: HER2+
poetry run python scripts/generate_synthetic_patient_data.py \
    --cancer-type HER2_POSITIVE \
    --output examples/synthetic_patient_HER2.csv \
    --num-genes 500 --seed 42

poetry run python scripts/create_patient_copy.py \
    --patient-id DEMO_HER2 \
    --csv-file examples/synthetic_patient_HER2.csv

# Patient 2: TNBC
poetry run python scripts/generate_synthetic_patient_data.py \
    --cancer-type TNBC \
    --output examples/synthetic_patient_TNBC.csv \
    --num-genes 500 --seed 123

poetry run python scripts/create_patient_copy.py \
    --patient-id DEMO_TNBC \
    --csv-file examples/synthetic_patient_TNBC.csv

# Patient 3: Lung EGFR+
poetry run python scripts/generate_synthetic_patient_data.py \
    --cancer-type LUAD_EGFR \
    --output examples/synthetic_patient_LUAD.csv \
    --num-genes 500 --seed 456

poetry run python scripts/create_patient_copy.py \
    --patient-id DEMO_LUAD \
    --csv-file examples/synthetic_patient_LUAD.csv

echo "All demo patient databases created!"
echo "Databases available:"
echo "  - mediabase_patient_DEMO_HER2"
echo "  - mediabase_patient_DEMO_TNBC"
echo "  - mediabase_patient_DEMO_LUAD"
```

---

## Clinical Query Examples with Expected Results

### Query 1: Find Druggable Targets (HER2+ Patient)

```sql
SELECT
    ctb.gene_symbol,
    ctb.expression_fold_change,
    d.drug_name,
    d.max_phase
FROM cancer_transcript_base ctb
INNER JOIN genes g ON ctb.gene_id = g.gene_id
INNER JOIN drug_target_genes dtg ON g.gene_id = dtg.gene_id
INNER JOIN drugs d ON dtg.drug_id = d.drug_id
WHERE ctb.expression_fold_change > 2.0
  AND d.max_phase = 4  -- FDA approved only
ORDER BY ctb.expression_fold_change DESC
LIMIT 10;
```

**Expected Results**:
```
 gene_symbol | expression_fold_change | drug_name         | max_phase
-------------+------------------------+-------------------+-----------
 ERBB2       |                   6.20 | Trastuzumab       |         4
 ERBB2       |                   6.20 | Pertuzumab        |         4
 ERBB2       |                   6.20 | Trastuzumab emtansine (T-DM1) | 4
 GRB7        |                   4.80 | (no direct drugs) |
 PIK3CA      |                   2.80 | Alpelisib         |         4
 CCND1       |                   3.20 | Palbociclib       |         4
 CDK4        |                   2.50 | Ribociclib        |         4
 ESR1        |                   2.10 | Tamoxifen         |         4
 ESR1        |                   2.10 | Fulvestrant       |         4
```

**Clinical Interpretation**:
This HER2+ ER+ patient has multiple FDA-approved therapeutic options:
- **First-line**: Trastuzumab + pertuzumab + chemotherapy
- **Second-line**: T-DM1 (antibody-drug conjugate)
- **If PIK3CA mutant**: Add alpelisib to anti-HER2 therapy
- **Maintenance (if ER+)**: Endocrine therapy + CDK4/6 inhibitor

---

### Query 2: Immunotherapy Eligibility (TNBC Patient)

```sql
SELECT
    gene_symbol,
    expression_fold_change,
    CASE
        WHEN gene_symbol = 'CD274' AND expression_fold_change > 2.0
            THEN '✅ PD-L1 HIGH - Pembrolizumab eligible'
        WHEN gene_symbol = 'CD8A' AND expression_fold_change > 2.0
            THEN '✅ T cell inflamed tumor'
        ELSE 'Review additional biomarkers'
    END as immunotherapy_interpretation
FROM cancer_transcript_base
WHERE gene_symbol IN ('CD274', 'PDCD1', 'CD8A')
ORDER BY expression_fold_change DESC;
```

**Expected Results**:
```
 gene_symbol | expression_fold_change | immunotherapy_interpretation
-------------+------------------------+---------------------------------------
 CD274       |                   2.80 | ✅ PD-L1 HIGH - Pembrolizumab eligible
 CD8A        |                   2.50 | ✅ T cell inflamed tumor
 PDCD1       |                   1.80 | Review additional biomarkers
```

**Clinical Interpretation**:
This TNBC patient has high PD-L1 (CD274) and tumor-infiltrating lymphocytes (CD8A).
**Recommended Treatment**: Pembrolizumab + chemotherapy (carboplatin + paclitaxel)
**FDA Approval**: KEYNOTE-355 trial demonstrated improved PFS in PD-L1+ TNBC
**Expected Response Rate**: ~50-60% in PD-L1+ patients

---

### Query 3: Pathway Enrichment (HER2+ vs TNBC)

```sql
-- HER2+ Patient
SELECT
    gp.pathway_name,
    COUNT(*) as num_overexpressed_genes,
    ROUND(AVG(ctb.expression_fold_change), 2) as avg_fold_change
FROM cancer_transcript_base ctb
INNER JOIN genes g ON ctb.gene_id = g.gene_id
INNER JOIN gene_pathways gp ON g.gene_id = gp.gene_id
WHERE ctb.expression_fold_change > 2.5
GROUP BY gp.pathway_name
HAVING COUNT(*) >= 3
ORDER BY avg_fold_change DESC
LIMIT 10;
```

**Expected Results (HER2+ Patient)**:
```
 pathway_name                     | num_genes | avg_fold_change
----------------------------------+-----------+-----------------
 ERBB2 signaling pathway          |         8 |            4.80
 PI3K-AKT-mTOR signaling          |         6 |            3.50
 Cell cycle regulation            |         7 |            3.20
 MAPK signaling cascade           |         5 |            2.90
```

**Expected Results (TNBC Patient)**:
```
 pathway_name                     | num_genes | avg_fold_change
----------------------------------+-----------+-----------------
 Cell cycle and mitosis           |        12 |            5.20
 Basal epithelial differentiation |         6 |            4.80
 DNA damage response              |         5 |            3.50
 PD-1 signaling                   |         4 |            3.00
```

**Clinical Interpretation**:
- **HER2+**: Oncogene-driven (ERBB2, PI3K) → precision targeted therapy
- **TNBC**: Proliferation-driven + DNA repair defects → chemotherapy + PARP inhibitors + immunotherapy

---

## Using Real Data (Alternative to Synthetic)

### GEO Dataset Conversion

If you prefer real patient data from GEO:

```bash
# Step 1: Download GEO dataset
wget "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE96nnn/GSE96058/suppl/GSE96058_gene_expression.txt.gz"
gunzip GSE96058_gene_expression.txt.gz

# Step 2: Convert to MEDIABASE format
poetry run python scripts/convert_geo_to_mediabase.py \
    --input GSE96058_gene_expression.txt \
    --sample-id GSM2523181 \
    --gene-column gene_symbol \
    --output patient_HER2_real.csv

# Step 3: Create patient database
poetry run python scripts/create_patient_copy.py \
    --patient-id REAL_HER2_GSM2523181 \
    --csv-file patient_HER2_real.csv
```

### TCGA Data (via cBioPortal)

```bash
# 1. Download from cBioPortal
# Go to: https://www.cbioportal.org/
# Study: Breast Invasive Carcinoma (TCGA, PanCancer Atlas)
# Patient: TCGA-A7-A13E (HER2+ confirmed)
# Download: RNA-seq expression data (z-scores)

# 2. Convert z-scores to fold-change
# z-score > 2 → ~4-fold overexpression
# z-score < -2 → ~0.25-fold underexpression

# 3. Map to MEDIABASE format
poetry run python scripts/convert_tcga_to_mediabase.py \
    --input TCGA-A7-A13E_RNA_seq.txt \
    --output patient_TCGA_A7_A13E.csv
```

---

## Troubleshooting

### Low Mapping Rate

**Problem**: Only 30% of genes map to Ensembl transcript IDs

**Solution**:
- GEO data uses gene symbols, which may not match GENCODE
- Run id_enrichment ETL module to expand cross-references
- Use `--gene-column` to specify correct input column

### Expression Values Out of Range

**Problem**: Some fold-change values are negative or >1000

**Solution**:
- Check input format (log2 vs. linear)
- Use `--format-type` parameter to override auto-detection
- Filter outliers with `--min-fc 0.01 --max-fc 100`

### Signature Genes Missing

**Problem**: ERBB2 not found in HER2+ patient data

**Solution**:
- Gene may not be in database (run full ETL first)
- Gene symbol may differ (ERBB2 vs. HER2 vs. NEU)
- Check `cancer_transcript_base` table for gene availability

---

## Next Steps

1. **Generate all 3 demo patients** using synthetic data
2. **Run validation queries** to confirm biological accuracy
3. **Execute clinical queries** from `CROSS_PATIENT_COMPARISON_QUERIES.sql`
4. **Document results** for README.md and QUERY_EXAMPLES.md
5. **Integrate with API** (v0.6.0) for LLM-based querying

---

## References

### Clinical Guidelines
- NCCN Guidelines: Breast Cancer (2024)
- NCCN Guidelines: Non-Small Cell Lung Cancer (2024)
- FDA Drug Approvals: Trastuzumab, Pertuzumab, Pembrolizumab

### Molecular Classification
- Perou et al. Nature 2000 (Breast cancer subtypes)
- TCGA Breast Cancer (2012) - Comprehensive molecular portraits
- TCGA Lung Adenocarcinoma (2014) - Molecular characterization

### Clinical Trials
- KEYNOTE-355: Pembrolizumab + chemo in TNBC
- CLEOPATRA: Pertuzumab + trastuzumab in HER2+ breast
- FLAURA: Osimertinib in EGFR-mutant NSCLC

---

## Contact

For questions about patient dataset generation or clinical interpretation:
- Documentation: `/docs/PATIENT_DATASET_GUIDE.md`
- Validation queries: `/docs/PATIENT_VALIDATION_QUERIES.sql`
- Clinical examples: `/docs/CROSS_PATIENT_COMPARISON_QUERIES.sql`

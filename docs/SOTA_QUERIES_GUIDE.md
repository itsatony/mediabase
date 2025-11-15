# SOTA Queries Guide

## Overview

MEDIABASE provides State-Of-The-Art (SOTA) SQL queries for cancer transcriptomics analysis. These queries enable clinicians and researchers to identify therapeutic targets, assess pathway dysregulation, and prioritize treatment strategies based on patient-specific gene expression data.

## Query File Types

### 1. **legacy_sota_queries_for_patients.sql** ✅ RECOMMENDED

**Status**: Working, tested
**Schema**: Legacy `cancer_transcript_base` table
**Use Case**: General SOTA analysis on patient databases

**Queries Included**:
- **Query 1**: Oncogene and Tumor Suppressor Analysis
- **Query 2**: Therapeutic Target Prioritization
- **Query 3**: Pathway-Based Therapeutic Strategy
- **Query 4**: Patient-Specific Expression Pattern Analysis
- **Query 5**: Database Validation

**Key Features**:
- All PostgreSQL syntax errors fixed (v0.3.1)
- Works with current patient database schema
- Comprehensive therapeutic analysis
- Validated on multiple patient databases

### 2. **cancer_specific_sota_queries.sql** ✅ EASIEST TO USE

**Status**: Working, tested
**Schema**: Legacy `cancer_transcript_base` table
**Use Case**: Cancer-type-specific therapeutic analysis

**Cancer Types Covered**:
- HER2+ Breast Cancer
- Triple-Negative Breast Cancer (TNBC)
- EGFR-Mutant Lung Adenocarcinoma
- MSI-High Colorectal Cancer
- Pancreatic Ductal Adenocarcinoma (PDAC)
- Pan-Cancer Analysis

**Key Features**:
- Simpler SQL patterns (easier to understand)
- Cancer-specific therapeutic recommendations
- Direct clinical actionability
- No complex aggregations

### 3. **normalized_sota_queries_for_patients.sql** ⚠️ REQUIRES MIGRATION

**Status**: Working, but requires normalized schema
**Schema**: Normalized tables + materialized views
**Use Case**: High-performance analysis (10-100x faster)

**Requirements**:
- Patient databases must be migrated to normalized schema
- Requires `transcript_enrichment_view` and related tables
- Not compatible with current patient databases

**Benefits** (after migration):
- Sub-second query response times
- Cleaner data model
- No data redundancy
- Better maintainability

### 4. **working_sota_queries_for_patients.sql** ❌ DEPRECATED

**Status**: BROKEN - Do not use
**Issues**: 5 PostgreSQL syntax errors
**Replacement**: Use `legacy_sota_queries_for_patients.sql` instead

This file has been replaced by the fixed version and should not be used.

---

## Quick Start

### For Most Users: Use Cancer-Specific Queries

```bash
# 1. Connect to your patient database
PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U mbase_user \
  -d mediabase_patient_DEMO_BREAST_HER2

# 2. Run the appropriate cancer-specific query section
\i cancer_specific_sota_queries.sql

# 3. Execute the queries for your cancer type (copy/paste from file)
```

**Example - HER2+ Breast Cancer**:
```sql
SELECT
    gene_symbol,
    expression_fold_change as fold_change,
    CASE
        WHEN gene_symbol = 'ERBB2' AND expression_fold_change > 4.0
            THEN '🎯 TRASTUZUMAB/PERTUZUMAB TARGET (High Priority)'
        WHEN gene_symbol IN ('PIK3CA', 'AKT1') AND expression_fold_change > 3.0
            THEN '🎯 PI3K/AKT INHIBITOR TARGET'
        -- ... more cases
    END as her2_therapeutic_strategy
FROM cancer_transcript_base
WHERE expression_fold_change != 1.0
  AND gene_symbol IN ('ERBB2', 'PIK3CA', 'AKT1', 'ESR1', 'CDK4', 'CDK6', 'PTEN', 'TP53')
ORDER BY expression_fold_change DESC;
```

### For Advanced Analysis: Use Legacy SOTA Queries

```bash
# 1. Connect to patient database
PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U mbase_user \
  -d mediabase_patient_DEMO_BREAST_HER2

# 2. Load and run queries
\i legacy_sota_queries_for_patients.sql

# 3. Execute queries in sequence or individually
```

---

## Query Details

### Query 1: Oncogene and Tumor Suppressor Analysis

**Purpose**: Identifies dysregulation of known cancer-driving genes

**Key Genes Analyzed**:
- **Oncogenes**: MYC, ERBB2, EGFR, KRAS, PIK3CA, AKT1, BRAF, NRAS
- **Tumor Suppressors**: TP53, RB1, PTEN, BRCA1, BRCA2, CDKN2A
- **DNA Repair**: ATM, CHEK1, CHEK2, RAD51, PARP1, MLH1, MSH2
- **Hormone Receptors**: ESR1, PGR, AR

**Clinical Interpretation**:
- 🔴 **ACTIVATED ONCOGENE**: Overexpressed oncogenes (>2.0x) - primary therapeutic targets
- 🔴 **SUPPRESSED TUMOR SUPPRESSOR**: Underexpressed suppressors (<0.5x) - high-risk markers
- 🔴 **IMPAIRED DNA REPAIR**: Underexpressed DNA repair genes - PARP inhibitor candidates
- 💊 **TARGETABLE**: Genes with approved drug interactions

**Example Output**:
```
gene_category   | gene_symbol | max_expression_fold | clinical_significance
----------------+-------------+---------------------+------------------------------------------
oncogene        | ERBB2       | 12.62              | 🔴 ACTIVATED ONCOGENE (Therapeutic Target)
oncogene        | PIK3CA      | 4.71               | 🔴 ACTIVATED ONCOGENE (Therapeutic Target)
tumor_suppressor| PTEN        | 0.17               | 🔴 SUPPRESSED TUMOR SUPPRESSOR (High Risk)
```

### Query 2: Therapeutic Target Prioritization

**Purpose**: Ranks therapeutic targets by expression + druggability + pathway involvement

**Scoring System**:
- **Expression Score**: 0-4 points (higher fold-change = more points)
- **Druggability Score**: 0-3 points (kinases > receptors > enzymes)
- **Pathway Score**: 0-2 points (higher pathway involvement = more points)
- **Total Priority Score**: Sum of all scores (max ~12 points)

**Priority Levels**:
- **🎯 IMMEDIATE PRIORITY** (≥9 points): Strong expression + druggable + pathway involvement
- **🔵 HIGH PRIORITY** (≥6 points): Good expression with some druggability
- **🟡 MEDIUM PRIORITY** (≥4 points): Moderate signals
- **⚪ LOW PRIORITY** (≥2 points): Weak but detectable signals

**Example Output**:
```
gene_symbol | max_fold_change | therapeutic_priority | drug_availability      | therapeutic_strategy
------------+-----------------+----------------------+------------------------+-------------------------------------
ERBB2       | 12.62          | 🎯 IMMEDIATE PRIORITY | 💊 5 APPROVED DRUGS   | 💊 HIGH-PRIORITY DRUG TARGET
PIK3CA      | 4.71           | 🔵 HIGH PRIORITY      | 💊 3 APPROVED DRUGS   | 💊 DRUG TARGET (4/8 variants)
```

### Query 3: Pathway-Based Therapeutic Strategy

**Purpose**: Identifies dysregulated pathways for combination therapy strategies

**Pathway Categories**:
- **Growth/Survival**: PI3K/AKT/mTOR pathways
- **Proliferation**: RAS/MAPK/ERK signaling
- **Genome Stability**: p53, DNA repair, checkpoints
- **Apoptosis**: Cell death pathways
- **Angiogenesis**: VEGF signaling
- **Immune Response**: Interferon, immune checkpoints
- **Metabolism**: Glycolysis, metabolic adaptation

**Dysregulation Scoring**:
```
Score = (highly_upregulated × 3) + (upregulated × 2) +
        (highly_downregulated × 2) + (downregulated × 1) +
        (druggable_genes × 3) + (functionally_diverse × 1)
```

**Priority Levels**:
- **🚨 CRITICAL** (>20): Immediate multi-target intervention needed
- **🔴 HIGH PRIORITY** (>12): Major pathway dysregulation
- **🟡 MODERATE** (>8): Significant changes
- **⚪ LOW** (>4): Minor alterations

**Example Output**:
```
pathway_name                        | dysregulation_ratio | intervention_priority | therapeutic_strategy
------------------------------------+---------------------+-----------------------+------------------------------------------
EGFR tyrosine kinase signaling     | 15/23 genes (65%)  | 🚨 CRITICAL PATHWAY   | 💊 PATHWAY INHIBITION (8 drug targets)
PI3K/AKT signaling                 | 12/28 genes (43%)  | 🔴 HIGH PRIORITY      | 💊 PATHWAY INHIBITION (5 drug targets)
```

### Query 4: Patient-Specific Expression Pattern Analysis

**Purpose**: Overall expression profile summary with top candidates

**Metrics Provided**:
- Total genes with expression changes
- Distribution by dysregulation level
- Therapeutic target counts (druggable, kinases, receptors)
- Expression range statistics
- Top 5 most upregulated genes
- Top 5 most downregulated genes

**Example Output**:
```
PATIENT EXPRESSION PROFILE SUMMARY
-----------------------------------
Total Genes with Expression Changes: 499
🔴 Highly Upregulated (>2.0x): 87
🟡 Moderately Upregulated (1.5-2.0x): 142
🔵 Moderately Downregulated (0.5-0.7x): 98
🔴 Highly Downregulated (<0.5x): 52
💊 Upregulated Drug Targets: 34
🎯 Upregulated Kinases: 12
📡 Upregulated Receptors: 8
```

### Query 5: Database Validation

**Purpose**: Quick check to ensure patient database has expression data

**Validates**:
- Total transcript count
- Transcripts with expression changes (≠1.0)
- Percentage coverage
- Expression range (min/max fold-change)

**Example Output**:
```
check_type          | total_transcripts | transcripts_with_data | percentage | min_expr | max_expr
--------------------+-------------------+-----------------------+------------+----------+----------
Validation Results  | 385659           | 499                   | 0.1%       | 0.124    | 12.618
```

---

## Patient Databases

### Available Demo Databases

1. **mediabase_patient_DEMO_BREAST_HER2**
   - HER2+ Breast Cancer
   - ERBB2 amplification signature
   - PI3K/AKT pathway activation

2. **mediabase_patient_DEMO_BREAST_TNBC**
   - Triple-Negative Breast Cancer
   - BRCA deficiency pattern
   - DNA damage response impairment

3. **mediabase_patient_DEMO_LUNG_EGFR**
   - EGFR-Mutant Lung Adenocarcinoma
   - EGFR overexpression
   - MET amplification (resistance)

4. **mediabase_patient_DEMO_COLORECTAL_MSI**
   - MSI-High Colorectal Cancer
   - Mismatch repair deficiency
   - Immune activation signature

5. **mediabase_patient_DEMO_PANCREATIC_PDAC**
   - Pancreatic Ductal Adenocarcinoma
   - KRAS activation
   - TP53/CDKN2A loss

6. **mediabase_patient_DEMO_COMPREHENSIVE**
   - Pan-Cancer reference
   - Multiple pathway dysregulations

### Connection Template

```bash
PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U mbase_user \
  -d mediabase_patient_DEMO_BREAST_HER2
```

---

## Interpretation Guidelines

### Expression Thresholds

**Overexpression** (potential therapeutic targets):
- **Extreme** (>10x): Primary therapeutic target
- **Very High** (5-10x): High-priority target
- **High** (3-5x): Moderate-priority target
- **Moderate** (2-3x): Low-priority target
- **Mild** (1.5-2x): Monitor or pathway-level consideration

**Underexpression** (biomarkers, resistance mechanisms):
- **Severe Loss** (<0.2x or >80% loss): High-risk marker
- **Significant Loss** (0.2-0.5x): Moderate-risk marker
- **Moderate Loss** (0.5-0.8x): Mild concern
- **Mild Change** (0.8-1.2x): Near-normal expression

### Clinical Decision Framework

1. **Activated Oncogenes** (>2.0x expression):
   - **With approved drugs**: Immediate therapeutic candidates
   - **Without approved drugs**: Consider clinical trials
   - **With resistance markers**: Plan combination therapy

2. **Suppressed Tumor Suppressors** (<0.5x expression):
   - **TP53 loss**: Aggressive disease, consider DNA-damaging agents
   - **BRCA1/2 loss**: PARP inhibitor candidates
   - **PTEN loss**: PI3K/AKT/mTOR inhibitors

3. **Pathway Dysregulation**:
   - **Single pathway**: Targeted monotherapy
   - **Multiple pathways**: Combination therapy
   - **Resistance pathways**: Plan sequential therapy

4. **Drug Prioritization**:
   - **Clinical evidence > Preclinical > Computational**
   - **High expression + approved drug = Top priority**
   - **Consider drug interactions and toxicity profiles**

---

## Troubleshooting

### Common Issues

**Issue**: Query returns no results
```sql
-- Check if database has expression data
SELECT COUNT(*) FROM cancer_transcript_base WHERE expression_fold_change != 1.0;
```
- **If 0 or very low**: Database may not have patient-specific expression data
- **Solution**: Verify you're connected to a patient database, not the main reference database

**Issue**: "relation cancer_transcript_base does not exist"
```bash
# Check which tables exist
\dt
```
- **If you see genes/transcripts tables**: You're connected to normalized schema
- **Solution**: Use `normalized_sota_queries_for_patients.sql` instead (if migrated)

**Issue**: Queries are very slow (>10 seconds)
- **Cause**: Large patient database without indexes
- **Solution**: Indexes should exist on `gene_symbol`, `expression_fold_change`
- **Check**: `\d cancer_transcript_base` should show multiple indexes

**Issue**: "ERROR: jsonb_object_keys not allowed in CASE"
- **Cause**: Using old `working_sota_queries_for_patients.sql` (broken version)
- **Solution**: Use `legacy_sota_queries_for_patients.sql` instead

---

## Performance Tips

1. **Use LIMIT** for exploratory queries:
   ```sql
   -- Add LIMIT to test queries quickly
   SELECT * FROM cancer_transcript_base WHERE expression_fold_change > 2.0 LIMIT 10;
   ```

2. **Filter early** with WHERE clauses:
   ```sql
   -- Filter before aggregation
   WHERE expression_fold_change != 1.0  -- Reduces rows processed
   ```

3. **Use cancer-specific queries** for simpler analysis:
   - Faster to run
   - Easier to understand
   - Direct clinical actionability

4. **Consider migration** for large-scale analysis:
   - Normalized schema provides 10-100x speedup
   - Materialized views enable sub-second queries
   - Better for production environments

---

## Migration Path

### Current State (Legacy Schema)
- Patient databases use `cancer_transcript_base` table
- Works with: `legacy_sota_queries_for_patients.sql`, `cancer_specific_sota_queries.sql`
- Good performance for single-patient analysis

### Future State (Normalized Schema)
- Patient databases use normalized tables + materialized views
- Works with: `normalized_sota_queries_for_patients.sql`
- Excellent performance for all query types

### Migration Steps (Planned for v0.4.0)
1. Update `scripts/create_patient_copy.py` to create normalized schema
2. Run migration on existing patient databases
3. Switch to normalized SOTA queries
4. Deprecate legacy schema support

---

## Additional Resources

- **README.md**: Project overview and setup instructions
- **CLAUDE.md**: Development guidelines and common commands
- **MIGRATION_GUIDE.md**: Schema migration documentation
- **cancer_specific_sota_queries.sql**: Cancer-specific query examples
- **legacy_sota_queries_for_patients.sql**: Fixed SOTA queries for legacy schema

---

## Version History

- **v0.3.1 (2025-11-15)**: Fixed all 5 SQL errors, created `legacy_sota_queries_for_patients.sql`
- **v0.3.0**: Added normalized SOTA queries, created demo patient databases
- **v0.2.1**: Added flexible transcript ID matching
- **v0.2.0**: Added DESeq2 support and RESTful API
- **v0.1.0**: Initial MEDIABASE release

---

## Support

For issues or questions:
- GitHub Issues: https://github.com/[your-repo]/mediabase/issues
- Documentation: See `docs/` directory
- Query Examples: See `WORKING_QUERY_EXAMPLES.sql`

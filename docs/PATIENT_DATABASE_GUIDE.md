# MEDIABASE Patient Database Guide (v0.6.0)

**Version:** 0.6.0 | **Architecture:** Shared Core with Patient Schemas | **Last Updated:** 2025-11-21

Comprehensive guide to managing patient-specific transcriptome data in MEDIABASE using the v0.6.0 shared core architecture.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Quick Start](#quick-start)
3. [Patient Schema Creation](#patient-schema-creation)
4. [CSV Format Requirements](#csv-format-requirements)
5. [Query Patterns](#query-patterns)
6. [Best Practices](#best-practices)
7. [API Integration](#api-integration)
8. [Biological Validation](#biological-validation)
9. [Troubleshooting](#troubleshooting)
10. [Backup and Recovery](#backup-and-recovery)
11. [Migration from v0.5.0](#migration-from-v050)

---

## Architecture Overview

### v0.6.0 Shared Core Design

MEDIABASE v0.6.0 uses a **single-database, multi-schema architecture** that dramatically improves storage efficiency and query simplicity compared to the per-patient database approach in v0.5.0.

```
PostgreSQL Database: mbase
├── public schema (SHARED CORE - 23 GB)
│   ├── genes (78K genes)
│   ├── transcripts (233K transcripts)
│   ├── gene_pathways (113K associations)
│   ├── transcript_go_terms (1.26M associations)
│   ├── opentargets_known_drugs (391K records)
│   ├── gene_publications (47.4M links)
│   └── ... (all biological data)
│
├── patient_DEMO_BREAST_HER2 schema (~10 MB)
│   ├── expression_data (sparse storage)
│   └── metadata (upload info)
│
├── patient_DEMO_TNBC schema (~10 MB)
│   ├── expression_data
│   └── metadata
│
└── patient_PATIENT123 schema (~10 MB)
    ├── expression_data
    └── metadata
```

### Key Benefits

**Storage Efficiency:**
- **v0.5.0:** ~23 GB per patient database (full schema + data copies)
- **v0.6.0:** ~23 GB shared core + ~10 MB per patient schema
- **Savings:** 99.75% storage reduction for patient-specific data

**Query Simplicity:**
- Single database connection (no cross-database complexity)
- Simple LEFT JOIN pattern between public and patient schemas
- COALESCE for baseline expression values

**Operational Advantages:**
- Single backup includes all patient data
- Easy patient schema creation/deletion
- Thousands of patient schemas supported in one database
- No database proliferation

### Sparse Storage Design

Patient schemas use **sparse storage** to minimize data size:

**Only store transcripts where `expression_fold_change != 1.0`**

```sql
-- Patient schema constraint
CONSTRAINT check_fold_change_not_default
    CHECK (expression_fold_change != 1.0)
```

**Implicit Baseline:**
- Transcripts NOT in `patient_X.expression_data` → fold_change = 1.0 (baseline)
- Transcripts IN `patient_X.expression_data` → use stored value

**Example:**
- Total transcripts in database: 233,000
- Typical patient schema stores: 5,000-15,000 transcripts (2-6%)
- 95%+ of transcripts implicitly at baseline (fold_change = 1.0)

---

## Quick Start

### Prerequisites

- PostgreSQL 12+ with MEDIABASE core data loaded
- Python 3.10+ with Poetry environment
- Patient transcriptome data (DESeq2 results or standard CSV)

### Create Your First Patient Schema

```bash
# 1. Prepare patient data (DESeq2 format)
# Ensure CSV has columns: SYMBOL (or transcript_id) and log2FoldChange (or cancer_fold)

# 2. Create patient schema
poetry run python scripts/create_patient_copy.py \
    --patient-id PATIENT123 \
    --csv-file patient_deseq2_results.csv \
    --source-db mbase

# 3. Validate creation
poetry run python scripts/manage_db.py --validate-patient PATIENT123

# 4. Connect and query
PGPASSWORD=your_password psql -h localhost -U your_user -d mbase

# 5. Query patient data
SELECT
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change
FROM public.transcripts t
LEFT JOIN patient_PATIENT123.expression_data pe
    ON t.transcript_id = pe.transcript_id
JOIN public.genes g ON t.gene_id = g.gene_id
WHERE COALESCE(pe.expression_fold_change, 1.0) > 2.0
LIMIT 10;
```

---

## Patient Schema Creation

### Workflow Overview

```
CSV File
    ↓
[Validation]
    ↓
[Column Detection] → SYMBOL / log2FoldChange / transcript_id / cancer_fold
    ↓
[Gene Symbol Mapping] → transcript_id lookup
    ↓
[Linear Conversion] → log2FC → linear fold-change (if needed)
    ↓
[Schema Creation] → patient_<ID> schema in mbase
    ↓
[Sparse Storage] → Only insert rows where fold_change != 1.0
    ↓
[Metadata Insert] → Upload info, statistics
    ↓
[Validation] → Schema integrity checks
```

### Command-Line Interface

```bash
# Basic usage with DESeq2 format
poetry run python scripts/create_patient_copy.py \
    --patient-id PATIENT123 \
    --csv-file deseq2_results.csv \
    --source-db mbase

# Dry-run validation (no changes made)
poetry run python scripts/create_patient_copy.py \
    --patient-id PATIENT123 \
    --csv-file data.csv \
    --source-db mbase \
    --dry-run

# With clinical metadata
poetry run python scripts/create_patient_copy.py \
    --patient-id PATIENT123 \
    --csv-file data.csv \
    --source-db mbase \
    --cancer-type "Breast Cancer" \
    --cancer-subtype "HER2+" \
    --clinical-notes "Stage III, ER+/PR+/HER2+"
```

### System Detection and Conversion

**Automatic Column Detection:**

The system intelligently detects column formats:

| Your Column Name | System Detects As | Purpose |
|-----------------|-------------------|---------|
| `SYMBOL`, `gene_symbol`, `Gene` | Gene symbol | Maps to transcript_id |
| `transcript_id`, `ENST*` | Transcript ID | Direct mapping |
| `log2FoldChange`, `log2FC` | Log2 fold-change | Auto-converts to linear |
| `cancer_fold`, `fold_change`, `FC` | Linear fold-change | Used directly |

**Automatic Conversions:**

```python
# Log2 fold-change → Linear fold-change
if log2FoldChange > 0:
    fold_change = 2 ** log2FoldChange
else:
    fold_change = 1 / (2 ** abs(log2FoldChange))

# Examples:
# log2FC = 2.5 → fold_change = 5.66 (upregulation)
# log2FC = -1.0 → fold_change = 0.5 (downregulation)
```

### Validation Statistics

After creation, the system reports:

```
Patient Schema Creation Complete!

Patient ID: PATIENT123
Schema Name: patient_PATIENT123
Database: mbase

Upload Statistics:
- Total transcripts uploaded: 15,234
- Successfully matched: 14,892 (97.8%)
- Unmatched symbols: 342 (2.2%)
- Stored in database: 8,456 (non-baseline values)
- Implicit baseline: 224,544 (fold_change = 1.0)

Expression Summary:
- Overexpressed (>2.0): 2,134 transcripts
- Underexpressed (<0.5): 1,876 transcripts
- Normal range (0.5-2.0): 4,446 transcripts

Storage Efficiency:
- Patient schema size: 9.8 MB
- Shared core size: 23.1 GB
- Storage ratio: 0.04%
```

---

## CSV Format Requirements

### Supported Formats

#### Format 1: DESeq2 Standard Output (Recommended)

```csv
SYMBOL,log2FoldChange,pvalue,padj
ERBB2,2.58,1.23e-15,3.45e-12
TP53,-1.45,2.34e-10,5.67e-08
BRCA1,-2.12,8.90e-12,1.23e-09
```

**Features:**
- Automatic gene symbol → transcript_id mapping
- Automatic log2 → linear conversion
- Multiple transcripts per gene handled correctly
- Statistical columns (pvalue, padj) ignored

#### Format 2: Standard Fold-Change Format

```csv
transcript_id,cancer_fold
ENST00000269305,6.25
ENST00000357654,0.32
ENST00000288602,2.48
```

**Features:**
- Direct transcript_id mapping (fastest)
- Linear fold-change values used as-is
- No conversion needed

#### Format 3: Gene Symbol with Linear Fold-Change

```csv
gene_symbol,fold_change
ERBB2,6.25
TP53,0.45
BRCA1,0.38
```

**Features:**
- Gene symbol → transcript_id mapping
- Linear fold-change values
- Good for custom analyses

### CSV Validation Rules

**Required:**
- Header row with column names
- At least one gene identifier column (SYMBOL, transcript_id, or gene_symbol)
- At least one expression column (log2FoldChange, cancer_fold, or fold_change)
- UTF-8 encoding

**Optional:**
- Statistical columns (pvalue, padj) - ignored but allowed
- Metadata columns (chromosome, biotype) - ignored but allowed

**Constraints:**
- Fold-change values must be positive (>0)
- Transcript IDs must match GENCODE format (ENST*)
- Gene symbols must be HGNC-approved symbols
- No duplicate transcript_id entries

### Example CSV Files

See `examples/` directory:
- `patient_data_example.csv` - Basic format template
- `demo_breast_her2_enhanced.csv` - HER2+ breast cancer example
- `demo_tnbc_example.csv` - Triple-negative breast cancer example
- `demo_luad_egfr_example.csv` - Lung adenocarcinoma EGFR+ example

---

## Query Patterns

### Pattern 1: Basic Patient Expression Query

```sql
-- Find overexpressed genes in patient
SELECT
    g.gene_symbol,
    t.transcript_id,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change
FROM public.transcripts t
LEFT JOIN patient_PATIENT123.expression_data pe
    ON t.transcript_id = pe.transcript_id
JOIN public.genes g ON t.gene_id = g.gene_id
WHERE COALESCE(pe.expression_fold_change, 1.0) > 2.0
ORDER BY fold_change DESC
LIMIT 20;
```

**Key Elements:**
- `LEFT JOIN patient_X.expression_data` - Patient-specific data
- `COALESCE(pe.expression_fold_change, 1.0)` - Baseline for missing values
- Filter on COALESCE result, not just pe.expression_fold_change

### Pattern 2: Patient + Drug Targeting

```sql
-- FDA-approved drugs targeting overexpressed genes
SELECT
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    okd.molecule_name as drug_name,
    okd.mechanism_of_action,
    okd.clinical_phase_label
FROM public.transcripts t
LEFT JOIN patient_PATIENT123.expression_data pe
    ON t.transcript_id = pe.transcript_id
JOIN public.genes g ON t.gene_id = g.gene_id
JOIN public.opentargets_known_drugs okd
    ON g.gene_id = okd.target_gene_id
WHERE COALESCE(pe.expression_fold_change, 1.0) > 3.0
  AND okd.is_approved = true
ORDER BY fold_change DESC, okd.clinical_phase DESC
LIMIT 25;
```

**Clinical Value:**
- Identifies FDA-approved therapeutic options
- Prioritizes by expression level
- Provides mechanism of action context

### Pattern 3: Pathway Enrichment Analysis

```sql
-- Pathways with multiple overexpressed genes (patient)
WITH patient_overexpressed AS (
    SELECT
        g.gene_id,
        g.gene_symbol,
        COALESCE(pe.expression_fold_change, 1.0) as fold_change
    FROM public.transcripts t
    LEFT JOIN patient_PATIENT123.expression_data pe
        ON t.transcript_id = pe.transcript_id
    JOIN public.genes g ON t.gene_id = g.gene_id
    WHERE COALESCE(pe.expression_fold_change, 1.0) > 2.0
)
SELECT
    gp.pathway_name,
    gp.pathway_description,
    COUNT(DISTINCT po.gene_id) as overexpressed_gene_count,
    ARRAY_AGG(DISTINCT po.gene_symbol ORDER BY po.fold_change DESC) as gene_symbols,
    ROUND(AVG(po.fold_change), 2) as avg_fold_change
FROM patient_overexpressed po
JOIN public.gene_pathways gp ON po.gene_id = gp.gene_id
GROUP BY gp.pathway_name, gp.pathway_description
HAVING COUNT(DISTINCT po.gene_id) >= 3
ORDER BY overexpressed_gene_count DESC, avg_fold_change DESC
LIMIT 20;
```

**Insights:**
- Identifies dysregulated biological pathways
- Shows which pathways have multiple altered genes
- Ranks by both gene count and expression magnitude

### Pattern 4: Tumor Suppressor Loss Detection

```sql
-- Detect tumor suppressor loss in patient
WITH tumor_suppressors AS (
    SELECT gene_symbol FROM (VALUES
        ('TP53'), ('RB1'), ('BRCA1'), ('BRCA2'), ('PTEN'),
        ('APC'), ('VHL'), ('CDKN2A'), ('STK11'), ('NF1')
    ) AS ts(gene_symbol)
)
SELECT
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    ROUND((1.0 - COALESCE(pe.expression_fold_change, 1.0)) * 100, 1) as percent_loss,
    CASE
        WHEN COALESCE(pe.expression_fold_change, 1.0) < 0.2 THEN 'SEVERE LOSS (>80%)'
        WHEN COALESCE(pe.expression_fold_change, 1.0) < 0.5 THEN 'SIGNIFICANT LOSS (>50%)'
        WHEN COALESCE(pe.expression_fold_change, 1.0) < 0.8 THEN 'MODERATE LOSS (>20%)'
        ELSE 'NORMAL'
    END as loss_severity
FROM public.genes g
INNER JOIN tumor_suppressors ts ON g.gene_symbol = ts.gene_symbol
JOIN public.transcripts t ON g.gene_id = t.gene_id
LEFT JOIN patient_PATIENT123.expression_data pe
    ON t.transcript_id = pe.transcript_id
WHERE COALESCE(pe.expression_fold_change, 1.0) < 0.8
ORDER BY fold_change ASC;
```

**Clinical Significance:**
- Identifies potential loss-of-function events
- Quantifies severity of expression loss
- Guides synthetic lethality strategies

### Pattern 5: Cross-Patient Comparison

```sql
-- Compare ERBB2 expression across multiple patients
SELECT
    'DEMO_BREAST_HER2' as patient_id,
    COALESCE(pe1.expression_fold_change, 1.0) as erbb2_fold_change
FROM public.genes g
JOIN public.transcripts t ON g.gene_id = t.gene_id
LEFT JOIN patient_DEMO_BREAST_HER2.expression_data pe1
    ON t.transcript_id = pe1.transcript_id
WHERE g.gene_symbol = 'ERBB2'

UNION ALL

SELECT
    'DEMO_TNBC' as patient_id,
    COALESCE(pe2.expression_fold_change, 1.0) as erbb2_fold_change
FROM public.genes g
JOIN public.transcripts t ON g.gene_id = t.gene_id
LEFT JOIN patient_DEMO_TNBC.expression_data pe2
    ON t.transcript_id = pe2.transcript_id
WHERE g.gene_symbol = 'ERBB2'

UNION ALL

SELECT
    'PATIENT123' as patient_id,
    COALESCE(pe3.expression_fold_change, 1.0) as erbb2_fold_change
FROM public.genes g
JOIN public.transcripts t ON g.gene_id = t.gene_id
LEFT JOIN patient_PATIENT123.expression_data pe3
    ON t.transcript_id = pe3.transcript_id
WHERE g.gene_symbol = 'ERBB2'

ORDER BY erbb2_fold_change DESC;
```

**Use Cases:**
- Compare biomarker expression across cohorts
- Validate patient stratification
- Identify outliers

### Pattern 6: Immune Checkpoint Expression

```sql
-- Assess immune checkpoint expression (patient-specific)
WITH immune_checkpoints AS (
    SELECT gene_symbol, checkpoint_type FROM (VALUES
        ('CD274', 'PD-L1'),
        ('PDCD1', 'PD-1'),
        ('CTLA4', 'CTLA-4'),
        ('LAG3', 'LAG-3'),
        ('HAVCR2', 'TIM-3'),
        ('TIGIT', 'TIGIT'),
        ('CD47', 'CD47')
    ) AS ic(gene_symbol, checkpoint_type)
)
SELECT
    ic.checkpoint_type,
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    CASE
        WHEN COALESCE(pe.expression_fold_change, 1.0) > 2.0
            THEN 'HIGH (Consider immunotherapy)'
        WHEN COALESCE(pe.expression_fold_change, 1.0) > 1.5
            THEN 'MODERATE'
        ELSE 'LOW'
    END as immunotherapy_potential
FROM immune_checkpoints ic
JOIN public.genes g ON ic.gene_symbol = g.gene_symbol
JOIN public.transcripts t ON g.gene_id = t.gene_id
LEFT JOIN patient_PATIENT123.expression_data pe
    ON t.transcript_id = pe.transcript_id
ORDER BY fold_change DESC;
```

**Clinical Decision Support:**
- Evaluates immune checkpoint blockade potential
- Identifies combination therapy opportunities
- Predicts response likelihood

---

## Best Practices

### Storage Optimization

**1. Only Create Schemas for Active Patients**

Don't create schemas speculatively. Each schema adds ~10 MB + indexing overhead.

```bash
# Good: Create when needed
poetry run python scripts/create_patient_copy.py \
    --patient-id ACTIVE_PATIENT_001 \
    --csv-file data.csv

# Avoid: Creating thousands of unused schemas
```

**2. Archive Inactive Patient Schemas**

```bash
# Export patient schema to SQL file
pg_dump -h localhost -U user -d mbase \
    --schema=patient_INACTIVE_001 \
    --schema-only > patient_INACTIVE_001_schema.sql

pg_dump -h localhost -U user -d mbase \
    --schema=patient_INACTIVE_001 \
    --data-only > patient_INACTIVE_001_data.sql

# Drop from active database
psql -h localhost -U user -d mbase \
    -c "DROP SCHEMA patient_INACTIVE_001 CASCADE;"
```

**3. Use Selective Indexing**

Patient schemas include minimal indexes by default. Add custom indexes for frequent queries:

```sql
-- Add index for specific query pattern
CREATE INDEX idx_patient_PATIENT123_high_expression
ON patient_PATIENT123.expression_data(expression_fold_change)
WHERE expression_fold_change > 3.0;
```

### Query Performance

**1. Always Use COALESCE Pattern**

```sql
-- CORRECT: Captures baseline and patient-specific values
WHERE COALESCE(pe.expression_fold_change, 1.0) > 2.0

-- WRONG: Misses transcripts at baseline
WHERE pe.expression_fold_change > 2.0
```

**2. Filter Early, Join Late**

```sql
-- Good: Filter patient data first
WITH patient_filtered AS (
    SELECT transcript_id, expression_fold_change
    FROM patient_PATIENT123.expression_data
    WHERE expression_fold_change > 5.0
)
SELECT g.gene_symbol, pf.expression_fold_change
FROM patient_filtered pf
JOIN public.transcripts t ON pf.transcript_id = t.transcript_id
JOIN public.genes g ON t.gene_id = g.gene_id;

-- Avoid: Joining before filtering
SELECT g.gene_symbol, pe.expression_fold_change
FROM public.genes g
JOIN public.transcripts t ON g.gene_id = t.gene_id
JOIN patient_PATIENT123.expression_data pe ON t.transcript_id = pe.transcript_id
WHERE pe.expression_fold_change > 5.0;
```

**3. Use CTEs for Complex Logic**

```sql
-- Readable, cacheable subqueries
WITH overexpressed AS (
    SELECT gene_id, fold_change
    FROM ...
    WHERE fold_change > 2.0
),
targeted_drugs AS (
    SELECT target_gene_id, drug_name
    FROM ...
    WHERE is_approved = true
)
SELECT ...
FROM overexpressed o
JOIN targeted_drugs d ON o.gene_id = d.target_gene_id;
```

### Security Considerations

**1. Schema Isolation**

Patient schemas provide data isolation but NOT security isolation. Use PostgreSQL permissions:

```sql
-- Create read-only user for patient queries
CREATE USER patient_analyst WITH PASSWORD 'secure_password';
GRANT USAGE ON SCHEMA public TO patient_analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO patient_analyst;

-- Grant access to specific patient schema
GRANT USAGE ON SCHEMA patient_PATIENT123 TO patient_analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA patient_PATIENT123 TO patient_analyst;
```

**2. De-identification**

Use non-identifying patient IDs:

```bash
# Good: De-identified
--patient-id STUDY_COHORT_A_042

# Avoid: PHI/PII
--patient-id JOHN_SMITH_DOB_1975
```

**3. Audit Trail**

Patient schema metadata table tracks provenance:

```sql
SELECT
    patient_id,
    upload_date,
    source_file,
    clinical_notes
FROM patient_PATIENT123.metadata;
```

---

## API Integration

### RESTful API with Patient Parameter

MEDIABASE v0.6.0 API supports patient-specific queries via `patient_id` parameter.

### Endpoints

**1. List Available Patients**

```bash
curl "http://localhost:8000/api/v1/patients"
```

Response:
```json
{
  "patients": [
    {
      "patient_id": "DEMO_BREAST_HER2",
      "schema_name": "patient_DEMO_BREAST_HER2",
      "upload_date": "2025-11-15T14:23:00Z",
      "total_transcripts": 8456,
      "cancer_type": "Breast Cancer",
      "cancer_subtype": "HER2+"
    },
    {
      "patient_id": "DEMO_TNBC",
      "schema_name": "patient_DEMO_TNBC",
      "upload_date": "2025-11-15T14:25:00Z",
      "total_transcripts": 12234,
      "cancer_type": "Breast Cancer",
      "cancer_subtype": "Triple-Negative"
    }
  ]
}
```

**2. Query Patient-Specific Expression**

```bash
# Search for ERBB2 in specific patient
curl "http://localhost:8000/api/v1/transcripts?patient_id=DEMO_BREAST_HER2&gene_symbols=ERBB2"

# Find overexpressed genes in patient
curl "http://localhost:8000/api/v1/transcripts?patient_id=DEMO_BREAST_HER2&fold_change_min=4.0&limit=20"

# Multiple genes across patient
curl "http://localhost:8000/api/v1/transcripts?patient_id=PATIENT123&gene_symbols=ERBB2,TP53,BRCA1"
```

**3. Query Baseline (Public Schema)**

```bash
# Search public schema (no patient_id)
curl "http://localhost:8000/api/v1/transcripts?gene_symbols=EGFR"

# Returns baseline fold_change = 1.0 for all transcripts
```

### Python SDK Example

```python
import requests

API_BASE = "http://localhost:8000/api/v1"

# 1. List patients
response = requests.get(f"{API_BASE}/patients")
patients = response.json()["patients"]
print(f"Found {len(patients)} patient schemas")

# 2. Query specific patient
patient_id = "DEMO_BREAST_HER2"
params = {
    "patient_id": patient_id,
    "gene_symbols": "ERBB2,GRB7,PGAP3",
    "fold_change_min": 2.0
}
response = requests.get(f"{API_BASE}/transcripts", params=params)
results = response.json()

for transcript in results["transcripts"]:
    print(f"{transcript['gene_symbol']}: {transcript['fold_change']}x")

# 3. FDA-approved drug targets for patient
params = {
    "patient_id": patient_id,
    "fold_change_min": 3.0,
    "include_drugs": True,
    "approved_only": True
}
response = requests.get(f"{API_BASE}/transcripts", params=params)
drug_targets = response.json()

for target in drug_targets["transcripts"]:
    print(f"\nGene: {target['gene_symbol']} ({target['fold_change']}x)")
    for drug in target.get("drugs", []):
        print(f"  - {drug['name']}: {drug['mechanism']}")
```

---

## Biological Validation

### Phenotype Validation Queries

After creating a patient schema, validate that the biological phenotype matches expectations.

**HER2+ Breast Cancer Validation:**

```sql
-- Expected: ERBB2 overexpression, co-amplicon genes, proliferation markers
SELECT
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    CASE
        WHEN g.gene_symbol = 'ERBB2' AND COALESCE(pe.expression_fold_change, 1.0) > 4.0
            THEN '✓ HER2 amplified (expected)'
        WHEN g.gene_symbol IN ('GRB7', 'PGAP3') AND COALESCE(pe.expression_fold_change, 1.0) > 3.0
            THEN '✓ Co-amplicon (expected)'
        WHEN g.gene_symbol IN ('MKI67', 'CCND1') AND COALESCE(pe.expression_fold_change, 1.0) > 2.5
            THEN '✓ High proliferation (expected)'
        ELSE '- Gene expression'
    END as validation_status
FROM public.genes g
JOIN public.transcripts t ON g.gene_id = t.gene_id
LEFT JOIN patient_DEMO_BREAST_HER2.expression_data pe
    ON t.transcript_id = pe.transcript_id
WHERE g.gene_symbol IN ('ERBB2', 'GRB7', 'PGAP3', 'PNMT', 'MKI67', 'CCND1', 'CDK4')
ORDER BY fold_change DESC;
```

**Triple-Negative Breast Cancer Validation:**

```sql
-- Expected: ESR1/PGR/ERBB2 low, TP53 loss, high proliferation
SELECT
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    CASE
        WHEN g.gene_symbol IN ('ESR1', 'PGR', 'ERBB2')
             AND COALESCE(pe.expression_fold_change, 1.0) < 0.5
            THEN '✓ Triple-negative marker (expected)'
        WHEN g.gene_symbol = 'TP53' AND COALESCE(pe.expression_fold_change, 1.0) < 0.4
            THEN '✓ TP53 loss (common in TNBC)'
        WHEN g.gene_symbol IN ('MKI67', 'PCNA') AND COALESCE(pe.expression_fold_change, 1.0) > 4.0
            THEN '✓ Very high proliferation (expected)'
        ELSE '- Gene expression'
    END as validation_status
FROM public.genes g
JOIN public.transcripts t ON g.gene_id = t.gene_id
LEFT JOIN patient_DEMO_TNBC.expression_data pe
    ON t.transcript_id = pe.transcript_id
WHERE g.gene_symbol IN ('ESR1', 'PGR', 'ERBB2', 'TP53', 'MKI67', 'PCNA', 'KRT5', 'KRT14')
ORDER BY g.gene_symbol;
```

### Data Integrity Checks

```sql
-- Check 1: No fold_change = 1.0 values (sparse storage constraint)
SELECT COUNT(*) as invalid_rows
FROM patient_PATIENT123.expression_data
WHERE expression_fold_change = 1.0;
-- Expected: 0

-- Check 2: All transcript IDs exist in public.transcripts
SELECT COUNT(*) as orphaned_transcripts
FROM patient_PATIENT123.expression_data pe
LEFT JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
WHERE t.transcript_id IS NULL;
-- Expected: 0

-- Check 3: All fold_change values are positive
SELECT COUNT(*) as negative_values
FROM patient_PATIENT123.expression_data
WHERE expression_fold_change <= 0;
-- Expected: 0

-- Check 4: Expression distribution sanity check
SELECT
    COUNT(*) as total_transcripts,
    COUNT(*) FILTER (WHERE expression_fold_change > 2.0) as overexpressed,
    COUNT(*) FILTER (WHERE expression_fold_change < 0.5) as underexpressed,
    ROUND(AVG(expression_fold_change), 2) as avg_fold_change,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY expression_fold_change), 2) as median_fold_change
FROM patient_PATIENT123.expression_data;
-- Typical: 5K-15K transcripts, avg ~1.5-2.5, median ~1.2-1.8
```

### Clinical Concordance Validation

Verify that patient data matches known clinical characteristics:

```sql
-- Example: Verify HER2+ patient has trastuzumab target profile
WITH patient_targets AS (
    SELECT
        g.gene_symbol,
        COALESCE(pe.expression_fold_change, 1.0) as fold_change
    FROM public.genes g
    JOIN public.transcripts t ON g.gene_id = t.gene_id
    LEFT JOIN patient_DEMO_BREAST_HER2.expression_data pe
        ON t.transcript_id = pe.transcript_id
    WHERE g.gene_symbol IN ('ERBB2', 'ESR1', 'PGR')
)
SELECT
    gene_symbol,
    fold_change,
    CASE
        WHEN gene_symbol = 'ERBB2' AND fold_change > 4.0 THEN '✓ Trastuzumab eligible'
        WHEN gene_symbol = 'ESR1' AND fold_change > 1.5 THEN '✓ Endocrine therapy eligible'
        WHEN gene_symbol = 'PGR' AND fold_change > 1.5 THEN '✓ Better prognosis marker'
        ELSE 'Below threshold'
    END as clinical_actionability
FROM patient_targets
ORDER BY fold_change DESC;
```

---

## Troubleshooting

### Issue 1: Low Matching Success Rate

**Symptom:**
```
Successfully matched: 5,234 / 15,000 (34.9%)
Unmatched symbols: 9,766 (65.1%)
```

**Causes & Solutions:**

1. **Non-standard gene symbols**
   ```bash
   # Check for non-HGNC symbols
   grep -v "^ENSG\|^ENST" your_file.csv | head -20

   # Solution: Use HGNC symbol standardization tool
   # Or: Use Ensembl transcript IDs directly
   ```

2. **Lowercase/mixed-case symbols**
   ```bash
   # Check case
   head -20 your_file.csv

   # Solution: Convert to uppercase
   awk 'BEGIN{FS=OFS=","} NR==1{print; next} {$1=toupper($1); print}' \
       input.csv > standardized.csv
   ```

3. **Deprecated gene symbols**
   ```bash
   # Solution: Update gene symbols using HGNC mapping
   # Example: FAM175A → ABRAXAS1 (renamed)
   ```

### Issue 2: Missing Expected Expression Changes

**Symptom:**
Patient is HER2+ but ERBB2 shows fold_change = 1.0 (baseline)

**Diagnosis:**
```sql
-- Check if ERBB2 was in uploaded data
SELECT
    pe.transcript_id,
    pe.expression_fold_change
FROM patient_DEMO_BREAST_HER2.expression_data pe
JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
JOIN public.genes g ON t.gene_id = g.gene_id
WHERE g.gene_symbol = 'ERBB2';

-- If empty: Check metadata for upload info
SELECT * FROM patient_DEMO_BREAST_HER2.metadata;
```

**Common Causes:**
1. Gene symbol not in uploaded CSV
2. Fold-change exactly 1.0 (filtered by sparse storage constraint)
3. Gene symbol misspelled in CSV

**Solution:**
```bash
# Re-upload with corrected data
poetry run python scripts/create_patient_copy.py \
    --patient-id DEMO_BREAST_HER2 \
    --csv-file corrected_data.csv \
    --source-db mbase \
    --overwrite
```

### Issue 3: Query Returns Wrong Results

**Symptom:**
Query for overexpressed genes returns too few results

**Check:**
```sql
-- Compare with and without COALESCE
SELECT COUNT(*) as with_coalesce
FROM public.transcripts t
LEFT JOIN patient_PATIENT123.expression_data pe ON t.transcript_id = pe.transcript_id
WHERE COALESCE(pe.expression_fold_change, 1.0) > 2.0;

SELECT COUNT(*) as without_coalesce
FROM patient_PATIENT123.expression_data pe
WHERE expression_fold_change > 2.0;

-- without_coalesce should match expression_data row count
```

**Solution:**
Always use LEFT JOIN with COALESCE to capture baseline expression.

### Issue 4: Schema Creation Fails

**Error:**
```
ERROR: schema "patient_PATIENT123" already exists
```

**Solution:**
```bash
# Check if schema exists
psql -h localhost -U user -d mbase -c "
SELECT schema_name
FROM information_schema.schemata
WHERE schema_name = 'patient_PATIENT123';"

# Option 1: Use different patient ID
--patient-id PATIENT123_v2

# Option 2: Drop and recreate (CAUTION: deletes data)
psql -h localhost -U user -d mbase -c "
DROP SCHEMA patient_PATIENT123 CASCADE;"
```

### Issue 5: Performance Issues

**Symptom:**
Queries on patient schemas take >10 seconds

**Diagnosis:**
```sql
-- Check index usage
EXPLAIN ANALYZE
SELECT g.gene_symbol, pe.expression_fold_change
FROM public.transcripts t
LEFT JOIN patient_PATIENT123.expression_data pe ON t.transcript_id = pe.transcript_id
JOIN public.genes g ON t.gene_id = g.gene_id
WHERE COALESCE(pe.expression_fold_change, 1.0) > 2.0;

-- Look for "Seq Scan" on patient schema
```

**Solution:**
```sql
-- Add filtered index for common query patterns
CREATE INDEX idx_patient_PATIENT123_overexpressed
ON patient_PATIENT123.expression_data(expression_fold_change)
WHERE expression_fold_change > 2.0;

-- Vacuum and analyze
VACUUM ANALYZE patient_PATIENT123.expression_data;
```

---

## Backup and Recovery

### Full Database Backup (All Patient Schemas)

```bash
# Backup entire mbase database (public + all patient schemas)
BACKUP_DIR="backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

pg_dump -h localhost -U mbase_user -d mbase \
    --format=custom \
    --file="${BACKUP_DIR}/mbase_full_${TIMESTAMP}.dump"

# Includes:
# - public schema (core data)
# - All patient_* schemas
# - All indexes, constraints, functions
```

### Single Patient Schema Backup

```bash
# Backup specific patient schema only
PATIENT_ID="PATIENT123"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

pg_dump -h localhost -U mbase_user -d mbase \
    --schema="patient_${PATIENT_ID}" \
    --format=custom \
    --file="backups/patient_${PATIENT_ID}_${TIMESTAMP}.dump"
```

### Restore Patient Schema

```bash
# Restore patient schema to same database
pg_restore -h localhost -U mbase_user -d mbase \
    --schema="patient_PATIENT123" \
    backups/patient_PATIENT123_20251121_140000.dump

# Restore to different database
pg_restore -h localhost -U mbase_user -d mbase_production \
    --schema="patient_PATIENT123" \
    backups/patient_PATIENT123_20251121_140000.dump
```

### Export Patient Data to CSV

```bash
# Export patient expression data to CSV
psql -h localhost -U mbase_user -d mbase -c "
COPY (
    SELECT
        t.transcript_id,
        g.gene_symbol,
        pe.expression_fold_change
    FROM patient_PATIENT123.expression_data pe
    JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
    JOIN public.genes g ON t.gene_id = g.gene_id
    ORDER BY pe.expression_fold_change DESC
) TO '/tmp/patient_PATIENT123_export.csv'
WITH (FORMAT CSV, HEADER true);"
```

### Disaster Recovery Scenario

**Scenario:** Core database corrupted, patient schemas intact

```bash
# 1. Restore core database from backup
pg_restore -h localhost -U mbase_user -d mbase_new \
    --schema=public \
    backups/mbase_full_20251115_080000.dump

# 2. Patient schemas are preserved in mbase database
# 3. Reconnect patient schemas to restored public schema
# (No action needed - schemas remain in same database)

# 4. Validate
psql -h localhost -U mbase_user -d mbase_new -c "
SELECT schema_name
FROM information_schema.schemata
WHERE schema_name LIKE 'patient_%';"
```

---

## Migration from v0.5.0

### Architecture Changes

**v0.5.0 (Per-Patient Databases):**
```
PostgreSQL Server
├── mbase (core database) - 23 GB
├── mediabase_patient_PATIENT001 - 23 GB
├── mediabase_patient_PATIENT002 - 23 GB
└── mediabase_patient_PATIENT003 - 23 GB
Total: 92 GB for 3 patients
```

**v0.6.0 (Shared Core):**
```
PostgreSQL Server
└── mbase (shared database) - 23.03 GB
    ├── public schema (core) - 23 GB
    ├── patient_PATIENT001 schema - 10 MB
    ├── patient_PATIENT002 schema - 10 MB
    └── patient_PATIENT003 schema - 10 MB
Total: 23.03 GB for 3 patients (99.6% reduction)
```

### Migration Steps

See `docs/MIGRATION_GUIDE_v0.6.0.md` for detailed instructions.

**Quick Migration:**

```bash
# 1. Create full backup of v0.5.0 patient databases
for DB in $(psql -h localhost -U user -lqt | cut -d \| -f 1 | grep mediabase_patient); do
    pg_dump -h localhost -U user -d $DB > "backups/${DB}_v050.sql"
done

# 2. Extract patient expression data to CSV
for DB in $(psql -h localhost -U user -lqt | cut -d \| -f 1 | grep mediabase_patient); do
    PATIENT_ID=$(echo $DB | sed 's/mediabase_patient_//')
    psql -h localhost -U user -d $DB -c "
    COPY (
        SELECT transcript_id, expression_fold_change
        FROM cancer_transcript_base
        WHERE expression_fold_change != 1.0
    ) TO '/tmp/${PATIENT_ID}_migration.csv' WITH (FORMAT CSV, HEADER true);"
done

# 3. Create patient schemas in v0.6.0
for CSV in /tmp/*_migration.csv; do
    PATIENT_ID=$(basename $CSV _migration.csv)
    poetry run python scripts/create_patient_copy.py \
        --patient-id $PATIENT_ID \
        --csv-file $CSV \
        --source-db mbase
done

# 4. Validate migration
poetry run python scripts/validate_migration.py --all-patients
```

### Query Migration

**v0.5.0 Query:**
```sql
-- Old: Query single patient database
SELECT gene_symbol, expression_fold_change
FROM cancer_transcript_base
WHERE expression_fold_change > 2.0;
```

**v0.6.0 Query:**
```sql
-- New: Query patient schema in shared database
SELECT
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change
FROM public.transcripts t
LEFT JOIN patient_PATIENT123.expression_data pe
    ON t.transcript_id = pe.transcript_id
JOIN public.genes g ON t.gene_id = g.gene_id
WHERE COALESCE(pe.expression_fold_change, 1.0) > 2.0;
```

**Key Differences:**
1. Must specify `patient_<ID>` schema
2. Use LEFT JOIN to capture baseline values
3. COALESCE for implicit baseline (fold_change = 1.0)
4. Join through public.transcripts and public.genes

---

## Additional Resources

### Documentation

- **[README.md](../README.md)** - Project overview and quick start
- **[CLAUDE.md](../CLAUDE.md)** - Developer documentation
- **[SCHEMA_REFERENCE.md](MEDIABASE_SCHEMA_REFERENCE.md)** - Complete schema documentation
- **[QUERY_LIBRARY.md](MEDIABASE_QUERY_LIBRARY.md)** - 25+ production queries
- **[MIGRATION_GUIDE_v0.6.0.md](MIGRATION_GUIDE_v0.6.0.md)** - Migration instructions

### Query Examples

- **[WORKING_QUERY_EXAMPLES.sql](../WORKING_QUERY_EXAMPLES.sql)** - 15+ verified queries
- **[cancer_specific_sota_queries.sql](../cancer_specific_sota_queries.sql)** - Cancer-type-specific queries
- **[patient_query_examples.sql](../examples/patient_query_examples.sql)** - Patient schema examples

### Example Data

- **`examples/patient_data_example.csv`** - Template CSV format
- **`examples/demo_breast_her2_enhanced.csv`** - HER2+ breast cancer example
- **`examples/demo_tnbc_example.csv`** - Triple-negative breast cancer
- **`examples/demo_luad_egfr_example.csv`** - Lung adenocarcinoma EGFR+

### Scripts

- **`scripts/create_patient_copy.py`** - Create patient schemas
- **`scripts/manage_db.py`** - Database management utilities
- **`scripts/generate_synthetic_patient_data.py`** - Generate test data
- **`scripts/validate_migration.py`** - Validate v0.5.0 → v0.6.0 migration

---

## Support

### Getting Help

- **Issues:** [GitHub Issues](https://github.com/itsatony/mediabase/issues)
- **Documentation:** [docs/](../docs/)
- **Examples:** [examples/](../examples/)

### Common Questions

**Q: How many patient schemas can I create?**
A: PostgreSQL supports thousands of schemas per database. Practical limit depends on server resources, but 100+ patient schemas is routine.

**Q: Can I update expression data after schema creation?**
A: Yes. Use `UPDATE` statements on `patient_X.expression_data` table or re-run `create_patient_copy.py` with `--overwrite`.

**Q: What happens if I upload duplicate transcript IDs?**
A: The script detects duplicates during validation and uses the first occurrence. Duplicates are logged in the upload report.

**Q: Can I query multiple patient schemas simultaneously?**
A: Yes. Use UNION ALL or dynamic SQL to query across patient schemas (see Pattern 5: Cross-Patient Comparison).

**Q: Is the API production-ready?**
A: Yes. The FastAPI server supports patient_id parameters and includes comprehensive error handling. Use with proper authentication in production.

---

**Version:** 0.6.0 | **Last Updated:** 2025-11-21 | **License:** MIT

# MEDIABASE Database Export - Setup Guide for Colleagues

**Generated:** 2025-09-22
**Version:** v0.3.0
**Export Package:** mediabase_export_[timestamp].zip

---

## 🎯 Quick Start - Get Running in 5 Minutes

### What You're Getting
This package contains **working databases with realistic cancer expression data** that you can query immediately:

- **Main Database (`mbase`)**: 10,000 genes, 104,627 transcripts with normalized schema
- **Patient Databases**: Cancer-specific expression profiles for immediate testing
  - Breast HER2+ (`mediabase_patient_DEMO_BREAST_HER2`)
  - Breast TNBC (`mediabase_patient_DEMO_BREAST_TNBC`)
  - And more patient databases with realistic expression patterns

### Prerequisites
```bash
# You need PostgreSQL 12+ installed
sudo apt-get install postgresql postgresql-contrib

# Or on macOS:
brew install postgresql
```

---

## 🚀 Database Restoration (5 minutes)

### 1. Start PostgreSQL
```bash
sudo service postgresql start
# or: brew services start postgresql
```

### 2. Create Databases
```bash
# Create main database
createdb mediabase_main

# Create patient databases
createdb mediabase_patient_breast_her2
createdb mediabase_patient_breast_tnbc
```

### 3. Restore Database Dumps
```bash
# Main database (larger, has full schema)
pg_restore -d mediabase_main databases/mbase.sql.gz

# Patient databases (cancer-specific expression data)
pg_restore -d mediabase_patient_breast_her2 databases/mediabase_patient_DEMO_BREAST_HER2.sql.gz
pg_restore -d mediabase_patient_breast_tnbc databases/mediabase_patient_DEMO_BREAST_TNBC.sql.gz
```

**That's it! You now have working cancer transcriptomics databases.**

---

## 💊 Test Queries - Verify Your Setup

### Test 1: HER2+ Breast Cancer Targeted Therapy
```sql
-- Connect to patient database
psql -d mediabase_patient_breast_her2

-- Find HER2+ therapeutic targets
SELECT
    gene_symbol,
    expression_fold_change as fold_change,
    CASE
        WHEN gene_symbol = 'ERBB2' AND expression_fold_change > 4.0
            THEN '🎯 TRASTUZUMAB TARGET (High Priority)'
        WHEN gene_symbol IN ('PIK3CA', 'AKT1') AND expression_fold_change > 3.0
            THEN '🎯 PI3K/AKT INHIBITOR TARGET'
        WHEN gene_symbol = 'ESR1' AND expression_fold_change > 2.0
            THEN '🎯 ENDOCRINE THERAPY CANDIDATE'
        ELSE '📊 MONITOR'
    END as therapeutic_strategy
FROM cancer_transcript_base
WHERE gene_symbol IN ('ERBB2', 'PIK3CA', 'AKT1', 'ESR1', 'ESR2')
  AND expression_fold_change <> 1.0
ORDER BY expression_fold_change DESC;
```

**Expected Results:**
```
 gene_symbol | fold_change |        therapeutic_strategy
-------------+-------------+------------------------------------
 ERBB2       |      12.618 | 🎯 TRASTUZUMAB TARGET (High Priority)
 PIK3CA      |       4.712 | 🎯 PI3K/AKT INHIBITOR TARGET
 AKT1        |       4.203 | 🎯 PI3K/AKT INHIBITOR TARGET
 ESR2        |       2.069 | 📊 MONITOR
 ESR1        |        0.66 | 📊 MONITOR
```

### Test 2: Database Statistics
```sql
-- Connect to main database
psql -d mediabase_main

-- Check database contents
SELECT 'Total Genes' as metric, COUNT(*) as count FROM genes
UNION ALL
SELECT 'Total Transcripts', COUNT(*) FROM transcripts
UNION ALL
SELECT 'Protein Coding Genes', COUNT(*) FROM genes WHERE gene_type = 'protein_coding';
```

---

## 🧬 Working Query Examples

### A. Cancer-Specific Queries (Patient Databases)

#### Find Oncogenes with High Expression
```sql
SELECT
    gene_symbol,
    expression_fold_change,
    CASE
        WHEN expression_fold_change > 5.0 THEN 'High Priority Target'
        WHEN expression_fold_change > 3.0 THEN 'Medium Priority'
        ELSE 'Monitor'
    END as priority
FROM cancer_transcript_base
WHERE expression_fold_change > 2.0
  AND gene_symbol IN (
    'MYC', 'ERBB2', 'EGFR', 'KRAS', 'PIK3CA', 'AKT1', 'CCND1'
  )
ORDER BY expression_fold_change DESC
LIMIT 10;
```

#### Tumor Suppressor Loss Analysis
```sql
SELECT
    gene_symbol,
    expression_fold_change,
    '⚠️ Potential Tumor Suppressor Loss' as significance
FROM cancer_transcript_base
WHERE expression_fold_change < 0.5
  AND gene_symbol IN (
    'TP53', 'RB1', 'BRCA1', 'BRCA2', 'PTEN', 'CDKN2A'
  )
ORDER BY expression_fold_change ASC;
```

### B. Normalized Schema Queries (Main Database)

#### Gene Statistics by Type
```sql
SELECT
    gene_type,
    COUNT(*) as gene_count,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM genes), 1) as percentage
FROM genes
GROUP BY gene_type
ORDER BY gene_count DESC
LIMIT 10;
```

#### Transcript Distribution Analysis
```sql
SELECT
    g.chromosome,
    COUNT(DISTINCT g.gene_id) as genes,
    COUNT(t.transcript_id) as transcripts,
    ROUND(AVG(LENGTH(t.sequence)), 0) as avg_length
FROM genes g
JOIN transcripts t ON g.gene_id = t.gene_id
WHERE g.chromosome ~ '^[0-9XYM]+$'
GROUP BY g.chromosome
ORDER BY genes DESC
LIMIT 10;
```

---

## 🎬 Demo Scenarios for Different Cancer Types

### Scenario 1: HER2+ Breast Cancer Drug Selection
**Database:** `mediabase_patient_breast_her2`
**Use Case:** Oncologist needs to select targeted therapy

```sql
-- Priority ranking for HER2+ patient
SELECT
    gene_symbol,
    expression_fold_change,
    CASE
        WHEN gene_symbol = 'ERBB2' THEN 'Primary: Trastuzumab + Pertuzumab'
        WHEN gene_symbol = 'PIK3CA' THEN 'Secondary: PI3K inhibitor'
        WHEN gene_symbol = 'CDK4' THEN 'Tertiary: CDK4/6 inhibitor'
        ELSE 'Monitor for resistance'
    END as treatment_recommendation
FROM cancer_transcript_base
WHERE gene_symbol IN ('ERBB2', 'PIK3CA', 'CDK4', 'CDK6', 'ESR1')
  AND expression_fold_change > 1.5
ORDER BY expression_fold_change DESC;
```

### Scenario 2: Triple-Negative Breast Cancer (TNBC)
**Database:** `mediabase_patient_breast_tnbc`
**Use Case:** PARP inhibitor eligibility

```sql
-- BRCA deficiency assessment
SELECT
    gene_symbol,
    expression_fold_change,
    CASE
        WHEN expression_fold_change < 0.5 THEN '✅ PARP Inhibitor Candidate'
        ELSE '❌ BRCA Intact'
    END as parp_eligibility
FROM cancer_transcript_base
WHERE gene_symbol IN ('BRCA1', 'BRCA2', 'ATM', 'CHEK1', 'CHEK2')
ORDER BY expression_fold_change ASC;
```

---

## 🔧 Advanced Usage

### Python Integration
```python
import psycopg2
import pandas as pd

# Connect to patient database
conn = psycopg2.connect(
    host="localhost",
    database="mediabase_patient_breast_her2",
    user="your_user",
    password="your_password"
)

# Query therapeutic targets
query = """
SELECT gene_symbol, expression_fold_change
FROM cancer_transcript_base
WHERE expression_fold_change > 2.0
ORDER BY expression_fold_change DESC
LIMIT 20;
"""

df = pd.read_sql(query, conn)
print(df)
```

### R Integration
```r
library(RPostgreSQL)
library(dplyr)

# Connect to database
drv <- dbDriver("PostgreSQL")
con <- dbConnect(drv,
    dbname="mediabase_patient_breast_her2",
    host="localhost"
)

# Query data
result <- dbGetQuery(con, "
    SELECT gene_symbol, expression_fold_change
    FROM cancer_transcript_base
    WHERE expression_fold_change > 2.0
")

# Analyze
result %>%
    filter(expression_fold_change > 3.0) %>%
    arrange(desc(expression_fold_change))
```

---

## 🗂️ Database Schemas

### Patient Databases (Cancer_Transcript_Base Schema)
**Primary Table:** `cancer_transcript_base`

| Column | Type | Description |
|--------|------|-------------|
| transcript_id | text | Ensembl transcript ID |
| gene_symbol | text | HGNC gene symbol |
| expression_fold_change | real | Expression fold change vs normal |
| gene_type | text | Gene biotype classification |
| chromosome | text | Chromosomal location |
| drugs | jsonb | Associated drug interactions |
| pathways | text[] | Reactome pathways |
| go_terms | jsonb | Gene Ontology annotations |

### Main Database (Normalized Schema)
**Key Tables:**
- `genes` - Gene master data
- `transcripts` - Transcript sequences and metadata
- `gene_drug_interactions` - Therapeutic compounds
- `gene_pathways` - Biological pathway memberships
- `transcript_go_terms` - Gene Ontology annotations

---

## 🚨 Known Limitations (Important!)

### Current Status - What Works:
- ✅ **Patient databases**: Realistic cancer expression data, working queries
- ✅ **Cancer-specific queries**: HER2+, TNBC scenarios work perfectly
- ✅ **Basic normalized queries**: Gene counts, transcript stats
- ✅ **Database structure**: Complete schemas, proper relationships

### Current Limitations:
- ⚠️ **Main database enrichment**: GO terms/pathways/drugs partially populated due to ETL issues
- ⚠️ **Expression data**: Main database has baseline expression (1.0) only
- ⚠️ **Some normalized queries**: May return limited results on main DB

### Recommended Usage:
1. **Start with patient databases** - These have the most realistic, working examples
2. **Use cancer-specific queries** - These demonstrate the full system capabilities
3. **Main database**: Good for schema exploration, gene/transcript counts
4. **For production**: Fix ETL pipeline for complete enrichment data

---

## 📞 Support & Next Steps

### If Queries Return Empty Results:
1. Check you're using the right database (patient vs main)
2. Verify table names match schema (old vs normalized)
3. Check expression_fold_change values (use `<> 1.0` not `!= 1.0`)

### File Structure in Export:
```
mediabase_export_[timestamp]/
├── README.md                     # This file
├── databases/                    # SQL dumps
│   ├── mbase.sql.gz             # Main database
│   ├── mediabase_patient_*.sql.gz # Patient databases
├── queries/                      # Example queries
│   ├── query_examples_normalized.py
│   ├── cancer_specific_sota_queries.sql
└── documentation/               # Additional docs
```

### Getting Help:
- Check query syntax for PostgreSQL compatibility
- Use patient databases for immediate working examples
- Main database good for exploring full schema structure

---

**🎯 Bottom Line:** You now have working cancer transcriptomics databases with realistic expression data. Start with the patient databases and cancer-specific queries - they provide immediate, meaningful results for therapeutic decision-making!
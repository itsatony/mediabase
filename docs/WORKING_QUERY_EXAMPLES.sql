-- =====================================================================================
-- MEDIABASE WORKING QUERY EXAMPLES (v0.6.0 - Shared Core Architecture)
-- =====================================================================================
-- These queries work with the new v0.6.0 patient schema architecture:
-- - Single mbase database with public schema (core data)
-- - Patient-specific schemas: patient_<PATIENT_ID>
-- - Sparse storage: only expression_fold_change != 1.0 stored
--
-- Database: mbase (localhost:5435)
-- Patient Schemas: patient_synthetic_her2, patient_synthetic_tnbc, patient_synthetic_luad
--
-- Generated: 2025-11-20
-- Version: v0.6.0
-- Tested on: PostgreSQL 14+
-- =====================================================================================

-- =====================================================================================
-- SECTION 1: PATIENT-SPECIFIC QUERIES (v0.6.0 Schema Pattern)
-- =====================================================================================
-- These queries use the new patient schema pattern: patient_<PATIENT_ID>.expression_data
-- Pattern: SELECT ... FROM patient_<ID>.expression_data pe
--          JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
--          JOIN public.genes g ON t.gene_id = g.gene_id

-- -------------------------------------------------------------------------------------
-- 1.1 HER2+ BREAST CANCER TARGETED THERAPY SELECTION
-- -------------------------------------------------------------------------------------
-- Patient Schema: patient_synthetic_her2
-- Returns: Therapeutic targets with treatment recommendations

SELECT
    g.gene_symbol,
    pe.expression_fold_change as fold_change,
    CASE
        WHEN g.gene_symbol = 'ERBB2' AND pe.expression_fold_change > 4.0
            THEN '🎯 TRASTUZUMAB/PERTUZUMAB TARGET (High Priority)'
        WHEN g.gene_symbol IN ('PIK3CA', 'AKT1') AND pe.expression_fold_change > 3.0
            THEN '🎯 PI3K/AKT INHIBITOR TARGET'
        WHEN g.gene_symbol = 'ESR1' AND pe.expression_fold_change > 2.0
            THEN '🎯 ENDOCRINE THERAPY CANDIDATE'
        WHEN g.gene_symbol IN ('CDK4', 'CDK6', 'CCND1') AND pe.expression_fold_change > 2.0
            THEN '🎯 CDK4/6 INHIBITOR TARGET'
        WHEN g.gene_symbol IN ('PTEN', 'TP53') AND pe.expression_fold_change < 0.5
            THEN '⚠️ TUMOR SUPPRESSOR LOSS (High Risk)'
        ELSE '📊 MONITOR'
    END as her2_therapeutic_strategy
FROM patient_synthetic_her2.expression_data pe
JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
JOIN public.genes g ON t.gene_id = g.gene_id
WHERE g.gene_symbol IN (
    'ERBB2', 'PIK3CA', 'AKT1', 'ESR1', 'ESR2', 'PGR',
    'CDK4', 'CDK6', 'CCND1', 'PTEN', 'TP53', 'BRCA1', 'BRCA2'
)
ORDER BY
    CASE g.gene_symbol
        WHEN 'ERBB2' THEN 1
        WHEN 'PIK3CA' THEN 2
        WHEN 'AKT1' THEN 3
        ELSE 4
    END,
    pe.expression_fold_change DESC;

-- EXPECTED RESULTS:
-- gene_symbol | fold_change |               her2_therapeutic_strategy
-- -------------+-------------+--------------------------------------------------------
-- ERBB2       |      6.123  | 🎯 TRASTUZUMAB/PERTUZUMAB TARGET (High Priority)
-- PIK3CA      |      2.812  | 📊 MONITOR
-- AKT1        |      2.203  | 📊 MONITOR

-- -------------------------------------------------------------------------------------
-- 1.2 ONCOGENE OVEREXPRESSION ANALYSIS (UNIVERSAL PATTERN)
-- -------------------------------------------------------------------------------------
-- Works with any patient schema - just change schema name
-- Pattern demonstrates sparse storage with proper JOIN
-- Patient Schema: patient_synthetic_her2 (example)

SELECT
    g.gene_symbol,
    pe.expression_fold_change,
    CASE
        WHEN pe.expression_fold_change > 10.0 THEN '🔴 EXTREME OVEREXPRESSION'
        WHEN pe.expression_fold_change > 5.0 THEN '🟠 HIGH OVEREXPRESSION'
        WHEN pe.expression_fold_change > 3.0 THEN '🟡 MODERATE OVEREXPRESSION'
        WHEN pe.expression_fold_change > 2.0 THEN '🟢 MILD OVEREXPRESSION'
        ELSE '📊 BASELINE'
    END as expression_level
FROM patient_synthetic_her2.expression_data pe
JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
JOIN public.genes g ON t.gene_id = g.gene_id
WHERE pe.expression_fold_change > 2.0
  AND g.gene_symbol IN (
    'MYC', 'ERBB2', 'EGFR', 'KRAS', 'PIK3CA', 'AKT1', 'CCND1', 'CCNE1',
    'MDM2', 'BRAF', 'RAF1', 'SRC', 'ABL1', 'BCR', 'FLT3', 'KIT'
  )
ORDER BY pe.expression_fold_change DESC
LIMIT 15;

-- -------------------------------------------------------------------------------------
-- 1.3 TUMOR SUPPRESSOR LOSS ANALYSIS
-- -------------------------------------------------------------------------------------
-- Patient Schema: patient_synthetic_tnbc (example)
-- Returns: Downregulated tumor suppressors indicating aggressive disease

SELECT
    g.gene_symbol,
    pe.expression_fold_change,
    ROUND(((1.0 - pe.expression_fold_change) * 100)::NUMERIC, 1) as percent_loss,
    CASE
        WHEN pe.expression_fold_change < 0.2 THEN '🚨 SEVERE LOSS (>80%)'
        WHEN pe.expression_fold_change < 0.5 THEN '⚠️ SIGNIFICANT LOSS (>50%)'
        WHEN pe.expression_fold_change < 0.8 THEN '🟡 MODERATE LOSS (>20%)'
        ELSE '📊 MILD CHANGE'
    END as loss_severity
FROM patient_synthetic_tnbc.expression_data pe
JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
JOIN public.genes g ON t.gene_id = g.gene_id
WHERE pe.expression_fold_change < 0.8
  AND g.gene_symbol IN (
    'TP53', 'RB1', 'BRCA1', 'BRCA2', 'PTEN', 'CDKN2A', 'CDKN1A', 'CDKN1B',
    'APC', 'VHL', 'NF1', 'ATM', 'CHEK1', 'CHEK2'
  )
ORDER BY pe.expression_fold_change ASC;

-- -------------------------------------------------------------------------------------
-- 1.4 PARP INHIBITOR ELIGIBILITY (TNBC FOCUS)
-- -------------------------------------------------------------------------------------
-- Patient Schema: patient_synthetic_tnbc
-- Returns: BRCA deficiency markers for PARP inhibitor selection

SELECT
    g.gene_symbol,
    pe.expression_fold_change,
    CASE
        WHEN g.gene_symbol IN ('BRCA1', 'BRCA2') AND pe.expression_fold_change < 0.5
            THEN '✅ STRONG PARP INHIBITOR CANDIDATE'
        WHEN g.gene_symbol IN ('ATM', 'CHEK1', 'CHEK2', 'PALB2') AND pe.expression_fold_change < 0.6
            THEN '🟡 POSSIBLE PARP INHIBITOR CANDIDATE'
        WHEN g.gene_symbol IN ('BRCA1', 'BRCA2') AND pe.expression_fold_change > 0.8
            THEN '❌ BRCA LIKELY INTACT'
        ELSE '📊 INCONCLUSIVE'
    END as parp_eligibility,
    CASE
        WHEN pe.expression_fold_change < 0.5 THEN 'Olaparib, Talazoparib'
        WHEN pe.expression_fold_change < 0.6 THEN 'Consider clinical trial'
        ELSE 'Alternative therapy'
    END as treatment_recommendation
FROM patient_synthetic_tnbc.expression_data pe
JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
JOIN public.genes g ON t.gene_id = g.gene_id
WHERE g.gene_symbol IN ('BRCA1', 'BRCA2', 'ATM', 'CHEK1', 'CHEK2', 'PALB2', 'RAD51')
ORDER BY pe.expression_fold_change ASC;

-- -------------------------------------------------------------------------------------
-- 1.5 EGFR-MUTANT LUNG CANCER TARGETED THERAPY
-- -------------------------------------------------------------------------------------
-- Patient Schema: patient_synthetic_luad
-- Returns: EGFR inhibitor eligibility and pathway activation

SELECT
    g.gene_symbol,
    pe.expression_fold_change,
    CASE
        WHEN g.gene_symbol = 'EGFR' AND pe.expression_fold_change > 4.0
            THEN '🎯 OSIMERTINIB/ERLOTINIB TARGET (First-line)'
        WHEN g.gene_symbol IN ('AKT1', 'MAPK1', 'PIK3CA') AND pe.expression_fold_change > 3.0
            THEN '🟡 DOWNSTREAM PATHWAY ACTIVATION'
        WHEN g.gene_symbol = 'KRAS' AND pe.expression_fold_change > 2.0
            THEN '⚠️ KRAS ACTIVATION (Check mutual exclusivity)'
        WHEN g.gene_symbol IN ('TP53', 'STK11', 'KEAP1') AND pe.expression_fold_change < 0.6
            THEN '⚠️ TUMOR SUPPRESSOR LOSS'
        ELSE '📊 MONITOR'
    END as egfr_therapeutic_strategy
FROM patient_synthetic_luad.expression_data pe
JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
JOIN public.genes g ON t.gene_id = g.gene_id
WHERE g.gene_symbol IN (
    'EGFR', 'ERBB3', 'KRAS', 'BRAF', 'AKT1', 'MAPK1', 'PIK3CA',
    'STAT3', 'TP53', 'STK11', 'KEAP1'
)
ORDER BY
    CASE g.gene_symbol
        WHEN 'EGFR' THEN 1
        WHEN 'AKT1' THEN 2
        WHEN 'KRAS' THEN 3
        ELSE 4
    END,
    pe.expression_fold_change DESC;

-- -------------------------------------------------------------------------------------
-- 1.6 EXPRESSION DISTRIBUTION SUMMARY (PATIENT-LEVEL)
-- -------------------------------------------------------------------------------------
-- Patient Schema: patient_synthetic_her2 (example)
-- Returns: Overall expression change statistics for a single patient

SELECT
    'Highly Overexpressed (>5x)' as category,
    COUNT(*) as gene_count,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM patient_synthetic_her2.expression_data), 1) as percentage
FROM patient_synthetic_her2.expression_data pe
WHERE pe.expression_fold_change > 5.0

UNION ALL

SELECT
    'Moderately Overexpressed (2-5x)',
    COUNT(*),
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM patient_synthetic_her2.expression_data), 1)
FROM patient_synthetic_her2.expression_data pe
WHERE pe.expression_fold_change >= 2.0 AND pe.expression_fold_change <= 5.0

UNION ALL

SELECT
    'Underexpressed (<0.5x)',
    COUNT(*),
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM patient_synthetic_her2.expression_data), 1)
FROM patient_synthetic_her2.expression_data pe
WHERE pe.expression_fold_change < 0.5

UNION ALL

SELECT
    'Baseline (implicit, not stored)',
    (SELECT COUNT(*) FROM public.transcripts) - (SELECT COUNT(*) FROM patient_synthetic_her2.expression_data),
    ROUND(((SELECT COUNT(*) FROM public.transcripts) - (SELECT COUNT(*) FROM patient_synthetic_her2.expression_data)) * 100.0 / (SELECT COUNT(*) FROM public.transcripts), 1)

UNION ALL

SELECT
    'Total Changed Genes (stored)',
    COUNT(*),
    100.0
FROM patient_synthetic_her2.expression_data pe

ORDER BY gene_count DESC;

-- =====================================================================================
-- SECTION 2: CROSS-PATIENT COMPARISON QUERIES
-- =====================================================================================
-- These queries compare expression patterns across multiple patients

-- -------------------------------------------------------------------------------------
-- 2.1 COMPARE ERBB2 EXPRESSION ACROSS PATIENTS
-- -------------------------------------------------------------------------------------
-- Returns: ERBB2 fold-change for all 3 synthetic patients

SELECT
    'HER2+ Breast' as patient_type,
    'patient_synthetic_her2' as schema_name,
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change
FROM public.genes g
LEFT JOIN public.transcripts t ON g.gene_id = t.gene_id
LEFT JOIN patient_synthetic_her2.expression_data pe ON t.transcript_id = pe.transcript_id
WHERE g.gene_symbol = 'ERBB2'

UNION ALL

SELECT
    'TNBC',
    'patient_synthetic_tnbc',
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0)
FROM public.genes g
LEFT JOIN public.transcripts t ON g.gene_id = t.gene_id
LEFT JOIN patient_synthetic_tnbc.expression_data pe ON t.transcript_id = pe.transcript_id
WHERE g.gene_symbol = 'ERBB2'

UNION ALL

SELECT
    'Lung EGFR+',
    'patient_synthetic_luad',
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0)
FROM public.genes g
LEFT JOIN public.transcripts t ON g.gene_id = t.gene_id
LEFT JOIN patient_synthetic_luad.expression_data pe ON t.transcript_id = pe.transcript_id
WHERE g.gene_symbol = 'ERBB2'

ORDER BY fold_change DESC;

-- -------------------------------------------------------------------------------------
-- 2.2 COMPARE TOP 5 OVEREXPRESSED GENES PER PATIENT
-- -------------------------------------------------------------------------------------
-- Returns: Most overexpressed genes for each patient

-- HER2+ Patient
(
    SELECT
        'patient_synthetic_her2' as patient_schema,
        g.gene_symbol,
        pe.expression_fold_change
    FROM patient_synthetic_her2.expression_data pe
    JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
    JOIN public.genes g ON t.gene_id = g.gene_id
    ORDER BY pe.expression_fold_change DESC
    LIMIT 5
)

UNION ALL

-- TNBC Patient
(
    SELECT
        'patient_synthetic_tnbc',
        g.gene_symbol,
        pe.expression_fold_change
    FROM patient_synthetic_tnbc.expression_data pe
    JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
    JOIN public.genes g ON t.gene_id = g.gene_id
    ORDER BY pe.expression_fold_change DESC
    LIMIT 5
)

UNION ALL

-- Lung Cancer Patient
(
    SELECT
        'patient_synthetic_luad',
        g.gene_symbol,
        pe.expression_fold_change
    FROM patient_synthetic_luad.expression_data pe
    JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
    JOIN public.genes g ON t.gene_id = g.gene_id
    ORDER BY pe.expression_fold_change DESC
    LIMIT 5
)

ORDER BY patient_schema, expression_fold_change DESC;

-- -------------------------------------------------------------------------------------
-- 2.3 PATIENT METADATA COMPARISON
-- -------------------------------------------------------------------------------------
-- Returns: Summary of all patient metadata
-- Note: v0.6.0 metadata uses key/value structure

SELECT
    'patient_synthetic_her2' as schema_name,
    MAX(CASE WHEN key = 'patient_id' THEN value END) as patient_id,
    MAX(CASE WHEN key = 'cancer_type' THEN value END) as cancer_type,
    MAX(CASE WHEN key = 'cancer_subtype' THEN value END) as cancer_subtype,
    MAX(CASE WHEN key = 'upload_date' THEN value END) as upload_date,
    MAX(CASE WHEN key = 'data_source' THEN value END) as data_source,
    (SELECT COUNT(*) FROM patient_synthetic_her2.expression_data) as stored_values
FROM patient_synthetic_her2.metadata

UNION ALL

SELECT
    'patient_synthetic_tnbc',
    MAX(CASE WHEN key = 'patient_id' THEN value END),
    MAX(CASE WHEN key = 'cancer_type' THEN value END),
    MAX(CASE WHEN key = 'cancer_subtype' THEN value END),
    MAX(CASE WHEN key = 'upload_date' THEN value END),
    MAX(CASE WHEN key = 'data_source' THEN value END),
    (SELECT COUNT(*) FROM patient_synthetic_tnbc.expression_data)
FROM patient_synthetic_tnbc.metadata

UNION ALL

SELECT
    'patient_synthetic_luad',
    MAX(CASE WHEN key = 'patient_id' THEN value END),
    MAX(CASE WHEN key = 'cancer_type' THEN value END),
    MAX(CASE WHEN key = 'cancer_subtype' THEN value END),
    MAX(CASE WHEN key = 'upload_date' THEN value END),
    MAX(CASE WHEN key = 'data_source' THEN value END),
    (SELECT COUNT(*) FROM patient_synthetic_luad.expression_data)
FROM patient_synthetic_luad.metadata

ORDER BY cancer_type, cancer_subtype;

-- =====================================================================================
-- SECTION 3: MAIN DATABASE QUERIES (Public Schema)
-- =====================================================================================
-- These work on the core public schema tables (genes, transcripts, etc.)

-- -------------------------------------------------------------------------------------
-- 3.1 GENE STATISTICS BY BIOTYPE
-- -------------------------------------------------------------------------------------
-- Returns: Distribution of gene types in the public schema

SELECT
    gene_type,
    COUNT(*) as gene_count,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM public.genes), 1) as percentage
FROM public.genes
GROUP BY gene_type
ORDER BY gene_count DESC
LIMIT 15;

-- -------------------------------------------------------------------------------------
-- 3.2 CHROMOSOME DISTRIBUTION
-- -------------------------------------------------------------------------------------
-- Returns: Gene and transcript counts by chromosome

SELECT
    g.chromosome,
    COUNT(DISTINCT g.gene_id) as genes,
    COUNT(t.transcript_id) as transcripts
FROM public.genes g
JOIN public.transcripts t ON g.gene_id = t.gene_id
WHERE g.chromosome ~ '^chr[0-9XYM]+$'
GROUP BY g.chromosome
ORDER BY
    CASE
        WHEN g.chromosome ~ '^chr[0-9]+$' THEN CAST(SUBSTRING(g.chromosome FROM 4) AS INTEGER)
        WHEN g.chromosome = 'chrX' THEN 23
        WHEN g.chromosome = 'chrY' THEN 24
        WHEN g.chromosome = 'chrM' THEN 25
        ELSE 26
    END;

-- -------------------------------------------------------------------------------------
-- 3.3 GENE SYMBOL SEARCH
-- -------------------------------------------------------------------------------------
-- Returns: Find genes by symbol pattern

SELECT
    g.gene_symbol,
    g.gene_type,
    g.chromosome,
    COUNT(t.transcript_id) as transcript_count,
    STRING_AGG(t.transcript_id, ', ' ORDER BY t.transcript_id) as transcript_ids
FROM public.genes g
LEFT JOIN public.transcripts t ON g.gene_id = t.gene_id
WHERE g.gene_symbol ILIKE '%BRCA%'
GROUP BY g.gene_id, g.gene_symbol, g.gene_type, g.chromosome
ORDER BY g.gene_symbol;

-- -------------------------------------------------------------------------------------
-- 3.4 LIST ALL PATIENT SCHEMAS
-- -------------------------------------------------------------------------------------
-- Returns: All patient schemas in the database

SELECT
    schema_name,
    REPLACE(schema_name, 'patient_', '') as patient_id
FROM information_schema.schemata
WHERE schema_name LIKE 'patient_%'
ORDER BY schema_name;

-- =====================================================================================
-- SECTION 4: SPARSE STORAGE PATTERN EXAMPLES
-- =====================================================================================
-- Demonstrates how to query with sparse storage (baseline = 1.0 implicit)

-- -------------------------------------------------------------------------------------
-- 4.1 GET EXPRESSION FOR ALL GENES (INCLUDING BASELINE)
-- -------------------------------------------------------------------------------------
-- Pattern: COALESCE to provide default value of 1.0 for genes not in expression_data
-- Patient Schema: patient_synthetic_her2 (example)

SELECT
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    CASE
        WHEN pe.expression_fold_change IS NULL THEN 'Baseline (implicit)'
        ELSE 'Changed (stored)'
    END as storage_status
FROM public.genes g
JOIN public.transcripts t ON g.gene_id = t.gene_id
LEFT JOIN patient_synthetic_her2.expression_data pe ON t.transcript_id = pe.transcript_id
WHERE g.gene_symbol IN ('ERBB2', 'TP53', 'GAPDH', 'ACTB')
ORDER BY g.gene_symbol;

-- -------------------------------------------------------------------------------------
-- 4.2 COMPARE STORED VS TOTAL TRANSCRIPTS (SPARSE STORAGE EFFICIENCY)
-- -------------------------------------------------------------------------------------
-- Shows storage savings from sparse storage

SELECT
    'patient_synthetic_her2' as patient_schema,
    (SELECT COUNT(*) FROM public.transcripts) as total_transcripts_in_database,
    (SELECT COUNT(*) FROM patient_synthetic_her2.expression_data) as stored_expression_values,
    ROUND(
        (SELECT COUNT(*) FROM patient_synthetic_her2.expression_data) * 100.0 /
        (SELECT COUNT(*) FROM public.transcripts),
        2
    ) as storage_percentage,
    ROUND(
        100.0 - (
            (SELECT COUNT(*) FROM patient_synthetic_her2.expression_data) * 100.0 /
            (SELECT COUNT(*) FROM public.transcripts)
        ),
        2
    ) as storage_savings_percentage

UNION ALL

SELECT
    'patient_synthetic_tnbc',
    (SELECT COUNT(*) FROM public.transcripts),
    (SELECT COUNT(*) FROM patient_synthetic_tnbc.expression_data),
    ROUND(
        (SELECT COUNT(*) FROM patient_synthetic_tnbc.expression_data) * 100.0 /
        (SELECT COUNT(*) FROM public.transcripts),
        2
    ),
    ROUND(
        100.0 - (
            (SELECT COUNT(*) FROM patient_synthetic_tnbc.expression_data) * 100.0 /
            (SELECT COUNT(*) FROM public.transcripts)
        ),
        2
    )

UNION ALL

SELECT
    'patient_synthetic_luad',
    (SELECT COUNT(*) FROM public.transcripts),
    (SELECT COUNT(*) FROM patient_synthetic_luad.expression_data),
    ROUND(
        (SELECT COUNT(*) FROM patient_synthetic_luad.expression_data) * 100.0 /
        (SELECT COUNT(*) FROM public.transcripts),
        2
    ),
    ROUND(
        100.0 - (
            (SELECT COUNT(*) FROM patient_synthetic_luad.expression_data) * 100.0 /
            (SELECT COUNT(*) FROM public.transcripts)
        ),
        2
    );

-- =====================================================================================
-- SECTION 5: TROUBLESHOOTING AND VALIDATION QUERIES
-- =====================================================================================

-- -------------------------------------------------------------------------------------
-- 5.1 CHECK DATABASE ARCHITECTURE
-- -------------------------------------------------------------------------------------
-- Verify you're using v0.6.0 shared core architecture

SELECT
    CASE
        WHEN EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name LIKE 'patient_%')
             AND EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'genes')
        THEN 'v0.6.0 Shared Core Architecture ✅'
        WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'cancer_transcript_base')
        THEN 'Old Patient Database (pre-v0.6.0)'
        ELSE 'Unknown Schema'
    END as architecture_version;

-- -------------------------------------------------------------------------------------
-- 5.2 VALIDATE PATIENT SCHEMA STRUCTURE
-- -------------------------------------------------------------------------------------
-- Check that patient schema has required tables

SELECT
    schema_name,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = schema_name AND table_name = 'expression_data'
        ) THEN '✅ Has expression_data'
        ELSE '❌ Missing expression_data'
    END as expression_table,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = schema_name AND table_name = 'metadata'
        ) THEN '✅ Has metadata'
        ELSE '❌ Missing metadata'
    END as metadata_table
FROM information_schema.schemata
WHERE schema_name LIKE 'patient_%'
ORDER BY schema_name;

-- -------------------------------------------------------------------------------------
-- 5.3 VALIDATE SPARSE STORAGE CONSTRAINT
-- -------------------------------------------------------------------------------------
-- Verify no baseline (1.0) values are stored (should return 0 rows)

SELECT
    'patient_synthetic_her2' as patient_schema,
    COUNT(*) as invalid_baseline_rows
FROM patient_synthetic_her2.expression_data
WHERE expression_fold_change = 1.0

UNION ALL

SELECT
    'patient_synthetic_tnbc',
    COUNT(*)
FROM patient_synthetic_tnbc.expression_data
WHERE expression_fold_change = 1.0

UNION ALL

SELECT
    'patient_synthetic_luad',
    COUNT(*)
FROM patient_synthetic_luad.expression_data
WHERE expression_fold_change = 1.0;

-- Expected: All counts = 0 (sparse storage working correctly)

-- -------------------------------------------------------------------------------------
-- 5.4 VALIDATE JOIN INTEGRITY
-- -------------------------------------------------------------------------------------
-- Verify all patient expression data references valid transcripts

SELECT
    'patient_synthetic_her2' as patient_schema,
    COUNT(*) as orphaned_transcript_ids
FROM patient_synthetic_her2.expression_data pe
LEFT JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
WHERE t.transcript_id IS NULL

UNION ALL

SELECT
    'patient_synthetic_tnbc',
    COUNT(*)
FROM patient_synthetic_tnbc.expression_data pe
LEFT JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
WHERE t.transcript_id IS NULL

UNION ALL

SELECT
    'patient_synthetic_luad',
    COUNT(*)
FROM patient_synthetic_luad.expression_data pe
LEFT JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
WHERE t.transcript_id IS NULL;

-- Expected: All counts = 0 (perfect referential integrity)

-- -------------------------------------------------------------------------------------
-- 5.5 SAMPLE DATA PREVIEW
-- -------------------------------------------------------------------------------------
-- Quick look at patient expression data with gene symbols

SELECT
    g.gene_symbol,
    pe.expression_fold_change,
    CASE
        WHEN pe.expression_fold_change > 2.0 THEN 'Overexpressed'
        WHEN pe.expression_fold_change < 0.5 THEN 'Underexpressed'
        ELSE 'Near Baseline'
    END as expression_status
FROM patient_synthetic_her2.expression_data pe
JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
JOIN public.genes g ON t.gene_id = g.gene_id
ORDER BY ABS(pe.expression_fold_change - 1.0) DESC
LIMIT 10;

-- =====================================================================================
-- NOTES FOR USERS (v0.6.0 Architecture)
-- =====================================================================================
/*
QUICK REFERENCE - v0.6.0 SHARED CORE ARCHITECTURE:

1. Architecture Overview:
   - Single database: mbase
   - Public schema: genes, transcripts (shared core data)
   - Patient schemas: patient_<PATIENT_ID> with expression_data and metadata tables
   - Sparse storage: Only fold_change != 1.0 stored (99.99% storage savings)

2. Query Pattern:
   SELECT g.gene_symbol, pe.expression_fold_change
   FROM patient_<PATIENT_ID>.expression_data pe
   JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
   JOIN public.genes g ON t.gene_id = g.gene_id
   WHERE ...

3. Sparse Storage:
   - Stored: expression_fold_change != 1.0
   - Implicit baseline: 1.0 for all transcripts not in expression_data
   - Use COALESCE(pe.expression_fold_change, 1.0) to get all values

4. Available Patient Schemas:
   - patient_synthetic_her2: HER2+ Breast Cancer
   - patient_synthetic_tnbc: Triple-Negative Breast Cancer
   - patient_synthetic_luad: Lung Adenocarcinoma (EGFR-mutant)

5. Expression Values:
   - 1.0 = baseline expression (implicit, not stored)
   - >1.0 = overexpressed
   - <1.0 = underexpressed
   - Use <> 1.0 (not != 1.0) in PostgreSQL

6. Performance Tips:
   - Indexes exist on transcript_id for fast JOINs
   - Sparse storage = faster queries (less data to scan)
   - Use LIMIT for exploratory queries
   - Patient schemas are isolated (no cross-contamination)

7. Storage Efficiency:
   - v0.5.0: ~2.1GB per patient (full database copy)
   - v0.6.0: ~2KB per patient (sparse schema only)
   - Storage reduction: 99.99%

8. Migration from Old Queries:
   OLD (pre-v0.6.0):
     SELECT gene_symbol, expression_fold_change
     FROM cancer_transcript_base
     WHERE ...

   NEW (v0.6.0):
     SELECT g.gene_symbol, pe.expression_fold_change
     FROM patient_<ID>.expression_data pe
     JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
     JOIN public.genes g ON t.gene_id = g.gene_id
     WHERE ...

9. Cross-Patient Queries:
   - Use UNION ALL to combine results from multiple patient schemas
   - Public schema is shared across all patients
   - Each patient schema is independent

10. Validation:
    - Run Section 5 queries to validate architecture
    - Check sparse storage: no fold_change = 1.0 rows
    - Verify JOIN integrity: no orphaned transcript_ids

For comprehensive documentation, see:
- docs/PATIENT_DATABASE_GUIDE.md
- docs/MIGRATION_GUIDE_v0.6.0.md
- src/db/patient_schema_template.sql
*/

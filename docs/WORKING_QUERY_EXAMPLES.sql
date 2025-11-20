-- =====================================================================================
-- MEDIABASE WORKING QUERY EXAMPLES
-- =====================================================================================
-- These queries have been tested and return meaningful results.
-- Use these as templates for your own analysis.
--
-- Generated: 2025-11-20
-- Version: v0.4.1
-- Tested on: PostgreSQL 12+
-- =====================================================================================

-- =====================================================================================
-- SECTION 1: PATIENT DATABASE QUERIES (cancer_transcript_base schema)
-- =====================================================================================
-- These work on patient-specific databases with realistic expression data
-- Databases: mediabase_patient_DEMO_BREAST_HER2, mediabase_patient_DEMO_BREAST_TNBC, etc.

-- -------------------------------------------------------------------------------------
-- 1.1 HER2+ BREAST CANCER TARGETED THERAPY SELECTION
-- -------------------------------------------------------------------------------------
-- Database: mediabase_patient_DEMO_BREAST_HER2
-- Returns: Therapeutic targets with treatment recommendations

SELECT
    gene_symbol,
    expression_fold_change as fold_change,
    CASE
        WHEN gene_symbol = 'ERBB2' AND expression_fold_change > 4.0
            THEN '🎯 TRASTUZUMAB/PERTUZUMAB TARGET (High Priority)'
        WHEN gene_symbol IN ('PIK3CA', 'AKT1') AND expression_fold_change > 3.0
            THEN '🎯 PI3K/AKT INHIBITOR TARGET'
        WHEN gene_symbol = 'ESR1' AND expression_fold_change > 2.0
            THEN '🎯 ENDOCRINE THERAPY CANDIDATE'
        WHEN gene_symbol IN ('CDK4', 'CDK6', 'CCND1') AND expression_fold_change > 2.0
            THEN '🎯 CDK4/6 INHIBITOR TARGET'
        WHEN gene_symbol IN ('PTEN', 'TP53') AND expression_fold_change < 0.5
            THEN '⚠️ TUMOR SUPPRESSOR LOSS (High Risk)'
        ELSE '📊 MONITOR'
    END as her2_therapeutic_strategy
FROM cancer_transcript_base
WHERE expression_fold_change <> 1.0
  AND gene_symbol IN ('ERBB2', 'PIK3CA', 'AKT1', 'ESR1', 'ESR2', 'PGR', 'CDK4', 'CDK6', 'CCND1', 'PTEN', 'TP53', 'BRCA1', 'BRCA2')
ORDER BY
    CASE gene_symbol
        WHEN 'ERBB2' THEN 1
        WHEN 'PIK3CA' THEN 2
        WHEN 'AKT1' THEN 3
        ELSE 4
    END,
    expression_fold_change DESC;

-- EXPECTED RESULTS:
-- gene_symbol | fold_change |               her2_therapeutic_strategy
-- -------------+-------------+--------------------------------------------------------
-- ERBB2       |      12.618 | 🎯 TRASTUZUMAB/PERTUZUMAB TARGET (High Priority)
-- PIK3CA      |       4.712 | 🎯 PI3K/AKT INHIBITOR TARGET
-- AKT1        |       4.203 | 🎯 PI3K/AKT INHIBITOR TARGET

-- -------------------------------------------------------------------------------------
-- 1.2 ONCOGENE OVEREXPRESSION ANALYSIS
-- -------------------------------------------------------------------------------------
-- Database: Any patient database
-- Returns: Highly overexpressed oncogenes for targeting

SELECT
    gene_symbol,
    expression_fold_change,
    CASE
        WHEN expression_fold_change > 10.0 THEN '🔴 EXTREME OVEREXPRESSION'
        WHEN expression_fold_change > 5.0 THEN '🟠 HIGH OVEREXPRESSION'
        WHEN expression_fold_change > 3.0 THEN '🟡 MODERATE OVEREXPRESSION'
        WHEN expression_fold_change > 2.0 THEN '🟢 MILD OVEREXPRESSION'
        ELSE '📊 BASELINE'
    END as expression_level
FROM cancer_transcript_base
WHERE expression_fold_change > 2.0
  AND gene_symbol IN (
    'MYC', 'ERBB2', 'EGFR', 'KRAS', 'PIK3CA', 'AKT1', 'CCND1', 'CCNE1',
    'MDM2', 'BRAF', 'RAF1', 'SRC', 'ABL1', 'BCR', 'FLT3', 'KIT'
  )
ORDER BY expression_fold_change DESC
LIMIT 15;

-- -------------------------------------------------------------------------------------
-- 1.3 TUMOR SUPPRESSOR LOSS ANALYSIS
-- -------------------------------------------------------------------------------------
-- Database: Any patient database
-- Returns: Downregulated tumor suppressors indicating aggressive disease

SELECT
    gene_symbol,
    expression_fold_change,
    ROUND((1.0 - expression_fold_change) * 100, 1) as percent_loss,
    CASE
        WHEN expression_fold_change < 0.2 THEN '🚨 SEVERE LOSS (>80%)'
        WHEN expression_fold_change < 0.5 THEN '⚠️ SIGNIFICANT LOSS (>50%)'
        WHEN expression_fold_change < 0.8 THEN '🟡 MODERATE LOSS (>20%)'
        ELSE '📊 MILD CHANGE'
    END as loss_severity
FROM cancer_transcript_base
WHERE expression_fold_change < 0.8
  AND gene_symbol IN (
    'TP53', 'RB1', 'BRCA1', 'BRCA2', 'PTEN', 'CDKN2A', 'CDKN1A', 'CDKN1B',
    'APC', 'VHL', 'NF1', 'ATM', 'CHEK1', 'CHEK2'
  )
ORDER BY expression_fold_change ASC;

-- -------------------------------------------------------------------------------------
-- 1.4 PARP INHIBITOR ELIGIBILITY (TNBC FOCUS)
-- -------------------------------------------------------------------------------------
-- Database: mediabase_patient_DEMO_BREAST_TNBC
-- Returns: BRCA deficiency markers for PARP inhibitor selection

SELECT
    gene_symbol,
    expression_fold_change,
    CASE
        WHEN gene_symbol IN ('BRCA1', 'BRCA2') AND expression_fold_change < 0.5
            THEN '✅ STRONG PARP INHIBITOR CANDIDATE'
        WHEN gene_symbol IN ('ATM', 'CHEK1', 'CHEK2', 'PALB2') AND expression_fold_change < 0.6
            THEN '🟡 POSSIBLE PARP INHIBITOR CANDIDATE'
        WHEN gene_symbol IN ('BRCA1', 'BRCA2') AND expression_fold_change > 0.8
            THEN '❌ BRCA LIKELY INTACT'
        ELSE '📊 INCONCLUSIVE'
    END as parp_eligibility,
    CASE
        WHEN expression_fold_change < 0.5 THEN 'Olaparib, Talazoparib'
        WHEN expression_fold_change < 0.6 THEN 'Consider clinical trial'
        ELSE 'Alternative therapy'
    END as treatment_recommendation
FROM cancer_transcript_base
WHERE gene_symbol IN ('BRCA1', 'BRCA2', 'ATM', 'CHEK1', 'CHEK2', 'PALB2', 'RAD51')
ORDER BY expression_fold_change ASC;

-- -------------------------------------------------------------------------------------
-- 1.5 EXPRESSION DISTRIBUTION SUMMARY
-- -------------------------------------------------------------------------------------
-- Database: Any patient database
-- Returns: Overall expression change statistics

SELECT
    'Highly Overexpressed (>5x)' as category,
    COUNT(*) as gene_count,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM cancer_transcript_base WHERE expression_fold_change <> 1.0), 1) as percentage
FROM cancer_transcript_base
WHERE expression_fold_change > 5.0

UNION ALL

SELECT
    'Moderately Overexpressed (2-5x)',
    COUNT(*),
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM cancer_transcript_base WHERE expression_fold_change <> 1.0), 1)
FROM cancer_transcript_base
WHERE expression_fold_change >= 2.0 AND expression_fold_change <= 5.0

UNION ALL

SELECT
    'Underexpressed (<0.5x)',
    COUNT(*),
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM cancer_transcript_base WHERE expression_fold_change <> 1.0), 1)
FROM cancer_transcript_base
WHERE expression_fold_change < 0.5

UNION ALL

SELECT
    'Total Changed Genes',
    COUNT(*),
    100.0
FROM cancer_transcript_base
WHERE expression_fold_change <> 1.0

ORDER BY gene_count DESC;

-- =====================================================================================
-- SECTION 2: MAIN DATABASE QUERIES (normalized schema)
-- =====================================================================================
-- These work on the main database (mbase) with normalized tables
-- Database: mbase

-- -------------------------------------------------------------------------------------
-- 2.1 GENE STATISTICS BY BIOTYPE
-- -------------------------------------------------------------------------------------
-- Returns: Distribution of gene types in the database

SELECT
    gene_type,
    COUNT(*) as gene_count,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM genes), 1) as percentage
FROM genes
GROUP BY gene_type
ORDER BY gene_count DESC
LIMIT 15;

-- EXPECTED RESULTS:
-- gene_type                | gene_count | percentage
-- -------------------------+------------+------------
-- protein_coding           |       3946 |       39.5
-- lncRNA                   |       1847 |       18.5
-- processed_pseudogene     |       1234 |       12.3

-- -------------------------------------------------------------------------------------
-- 2.2 CHROMOSOME DISTRIBUTION
-- -------------------------------------------------------------------------------------
-- Returns: Gene and transcript counts by chromosome

SELECT
    g.chromosome,
    COUNT(DISTINCT g.gene_id) as genes,
    COUNT(t.transcript_id) as transcripts,
    ROUND(AVG(LENGTH(t.sequence)), 0) as avg_transcript_length
FROM genes g
JOIN transcripts t ON g.gene_id = t.gene_id
WHERE g.chromosome ~ '^[0-9XYM]+$'  -- Standard chromosomes only
GROUP BY g.chromosome
ORDER BY
    CASE
        WHEN g.chromosome ~ '^[0-9]+$' THEN CAST(g.chromosome AS INTEGER)
        WHEN g.chromosome = 'X' THEN 23
        WHEN g.chromosome = 'Y' THEN 24
        WHEN g.chromosome = 'M' THEN 25
        ELSE 26
    END;

-- -------------------------------------------------------------------------------------
-- 2.3 TRANSCRIPT LENGTH ANALYSIS
-- -------------------------------------------------------------------------------------
-- Returns: Distribution of transcript lengths

SELECT
    CASE
        WHEN LENGTH(sequence) < 500 THEN 'Very Short (<500bp)'
        WHEN LENGTH(sequence) < 1000 THEN 'Short (500-1000bp)'
        WHEN LENGTH(sequence) < 2000 THEN 'Medium (1-2kb)'
        WHEN LENGTH(sequence) < 5000 THEN 'Long (2-5kb)'
        WHEN LENGTH(sequence) < 10000 THEN 'Very Long (5-10kb)'
        ELSE 'Extremely Long (>10kb)'
    END as length_category,
    COUNT(*) as transcript_count,
    ROUND(AVG(LENGTH(sequence)), 0) as avg_length,
    MIN(LENGTH(sequence)) as min_length,
    MAX(LENGTH(sequence)) as max_length
FROM transcripts
WHERE sequence IS NOT NULL
GROUP BY
    CASE
        WHEN LENGTH(sequence) < 500 THEN 1
        WHEN LENGTH(sequence) < 1000 THEN 2
        WHEN LENGTH(sequence) < 2000 THEN 3
        WHEN LENGTH(sequence) < 5000 THEN 4
        WHEN LENGTH(sequence) < 10000 THEN 5
        ELSE 6
    END,
    CASE
        WHEN LENGTH(sequence) < 500 THEN 'Very Short (<500bp)'
        WHEN LENGTH(sequence) < 1000 THEN 'Short (500-1000bp)'
        WHEN LENGTH(sequence) < 2000 THEN 'Medium (1-2kb)'
        WHEN LENGTH(sequence) < 5000 THEN 'Long (2-5kb)'
        WHEN LENGTH(sequence) < 10000 THEN 'Very Long (5-10kb)'
        ELSE 'Extremely Long (>10kb)'
    END
ORDER BY 1;

-- -------------------------------------------------------------------------------------
-- 2.4 GENE SYMBOL SEARCH
-- -------------------------------------------------------------------------------------
-- Returns: Find genes by symbol pattern

SELECT
    g.gene_symbol,
    g.gene_type,
    g.chromosome,
    COUNT(t.transcript_id) as transcript_count,
    STRING_AGG(t.transcript_id, ', ' ORDER BY t.transcript_id) as transcript_ids
FROM genes g
LEFT JOIN transcripts t ON g.gene_id = t.gene_id
WHERE g.gene_symbol ILIKE '%BRCA%'  -- Change pattern as needed
GROUP BY g.gene_id, g.gene_symbol, g.gene_type, g.chromosome
ORDER BY g.gene_symbol;

-- =====================================================================================
-- SECTION 3: CROSS-SCHEMA COMPATIBILITY QUERIES
-- =====================================================================================
-- These queries can be adapted to work on either schema

-- -------------------------------------------------------------------------------------
-- 3.1 TOP CHANGED GENES (UNIVERSAL)
-- -------------------------------------------------------------------------------------
-- For patient databases (cancer_transcript_base):
/*
SELECT gene_symbol, expression_fold_change
FROM cancer_transcript_base
WHERE expression_fold_change <> 1.0
ORDER BY ABS(expression_fold_change - 1.0) DESC
LIMIT 20;
*/

-- For main database (normalized schema with patient data):
/*
SELECT g.gene_symbol, t.expression_fold_change
FROM genes g
JOIN transcripts t ON g.gene_id = t.gene_id
WHERE t.expression_fold_change <> 1.0
ORDER BY ABS(t.expression_fold_change - 1.0) DESC
LIMIT 20;
*/

-- -------------------------------------------------------------------------------------
-- 3.2 DATABASE HEALTH CHECK
-- -------------------------------------------------------------------------------------
-- For patient databases:
/*
SELECT
    'Total Transcripts' as metric,
    COUNT(*) as count
FROM cancer_transcript_base
UNION ALL
SELECT
    'Changed Expression',
    COUNT(*)
FROM cancer_transcript_base
WHERE expression_fold_change <> 1.0
UNION ALL
SELECT
    'Protein Coding',
    COUNT(*)
FROM cancer_transcript_base
WHERE gene_type = 'protein_coding';
*/

-- For main database:
/*
SELECT
    'Total Genes' as metric,
    COUNT(*) as count
FROM genes
UNION ALL
SELECT
    'Total Transcripts',
    COUNT(*)
FROM transcripts
UNION ALL
SELECT
    'Protein Coding Genes',
    COUNT(*)
FROM genes
WHERE gene_type = 'protein_coding';
*/

-- =====================================================================================
-- SECTION 4: TROUBLESHOOTING QUERIES
-- =====================================================================================

-- -------------------------------------------------------------------------------------
-- 4.1 CHECK WHICH SCHEMA YOU'RE USING
-- -------------------------------------------------------------------------------------
-- Run this to determine which type of database you're connected to

SELECT
    CASE
        WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'cancer_transcript_base')
             AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'genes')
        THEN 'Patient Database (Old Schema)'
        WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'genes')
             AND EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'transcripts')
        THEN 'Main Database (Normalized Schema)'
        ELSE 'Unknown Schema'
    END as database_type;

-- -------------------------------------------------------------------------------------
-- 4.2 LIST ALL TABLES
-- -------------------------------------------------------------------------------------
-- See what tables are available in your current database

SELECT
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;

-- -------------------------------------------------------------------------------------
-- 4.3 SAMPLE DATA PREVIEW
-- -------------------------------------------------------------------------------------
-- For patient databases:
/*
SELECT * FROM cancer_transcript_base LIMIT 5;
*/

-- For main database:
/*
SELECT g.gene_symbol, g.gene_type, t.transcript_id, t.expression_fold_change
FROM genes g
JOIN transcripts t ON g.gene_id = t.gene_id
LIMIT 5;
*/

-- =====================================================================================
-- NOTES FOR USERS
-- =====================================================================================
/*
QUICK REFERENCE:

1. Patient Databases (cancer_transcript_base schema):
   - Use for realistic cancer expression analysis
   - Main table: cancer_transcript_base
   - Key column: expression_fold_change
   - Best for: Therapeutic targeting, biomarker discovery

2. Main Database (normalized schema):
   - Use for comprehensive gene/transcript analysis
   - Main tables: genes, transcripts
   - Key relationships: genes.gene_id = transcripts.gene_id
   - Best for: Database statistics, gene lookups

3. Expression Values:
   - 1.0 = baseline expression
   - >1.0 = overexpressed
   - <1.0 = underexpressed
   - Use <> 1.0 (not != 1.0) in PostgreSQL

4. Tested Databases:
   - mediabase_patient_DEMO_BREAST_HER2
   - mediabase_patient_DEMO_BREAST_TNBC
   - mbase (main database)

5. Performance Tips:
   - Index exists on gene_symbol for fast lookups
   - Use LIMIT for large result sets
   - Filter by expression_fold_change <> 1.0 for efficiency
*/
-- =====================================
-- LEGACY SOTA QUERIES FOR PATIENT DATABASES (FIXED VERSION)
-- =====================================
-- These queries work with patient-specific databases using the legacy cancer_transcript_base schema
-- This file replaces the broken working_sota_queries_for_patients.sql with all PostgreSQL syntax errors fixed
--
-- Version: v0.3.1 (Fixed)
-- Date: 2025-11-15
-- Schema: Legacy cancer_transcript_base table
-- Tested: PostgreSQL 12+
--
-- FIXES APPLIED:
-- 1. Removed set-returning functions from CASE expressions
-- 2. Fixed ARRAY_AGG(DISTINCT unnest(...)) patterns
-- 3. Fixed ARRAY_AGG(DISTINCT x ORDER BY y) where x != y
-- 4. Restructured UNION queries with proper column alignment
-- 5. Changed ::float to ::numeric for ROUND() function
--
-- Connection template for patient databases:
-- PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U mbase_user -d mediabase_patient_DEMO_BREAST_HER2
--
-- NOTE: For simpler cancer-specific queries, see cancer_specific_sota_queries.sql

-- =====================================
-- SOTA Query 1: Oncogene and Tumor Suppressor Analysis (FIXED)
-- =====================================
-- Clinical Rationale: Identifies dysregulation of known cancer-driving genes using actual expression data
-- FIX: Removed jsonb_object_keys() from CASE, fixed ARRAY_AGG(unnest()) pattern

WITH known_cancer_genes AS (
    SELECT
        gene_symbol,
        transcript_id,
        expression_fold_change,
        product_type,
        molecular_functions,
        array_length(pathways, 1) as pathway_count,
        -- FIX 1: Use boolean flag instead of jsonb_object_keys() in CASE
        (drugs != '{}'::jsonb AND drugs != 'null'::jsonb) as has_drug_interactions,
        CASE
            -- Known oncogenes (often amplified/overexpressed in cancer)
            WHEN gene_symbol IN ('MYC', 'ERBB2', 'EGFR', 'KRAS', 'PIK3CA', 'AKT1', 'CCND1', 'MDM2', 'BRAF', 'NRAS')
            THEN 'oncogene'
            -- Hormone receptors (context-dependent)
            WHEN gene_symbol IN ('ESR1', 'PGR', 'AR')
            THEN 'hormone_receptor'
            -- Known tumor suppressors (often deleted/underexpressed in cancer)
            WHEN gene_symbol IN ('TP53', 'RB1', 'PTEN', 'BRCA1', 'BRCA2', 'CDKN2A', 'CDKN1A', 'CDKN1B', 'APC', 'VHL')
            THEN 'tumor_suppressor'
            -- DNA repair genes (critical for genomic stability)
            WHEN gene_symbol IN ('ATM', 'CHEK1', 'CHEK2', 'RAD51', 'PARP1', 'MLH1', 'MSH2', 'XRCC1')
            THEN 'dna_repair'
            ELSE 'other'
        END as gene_category
    FROM cancer_transcript_base
    WHERE gene_symbol IN (
        'MYC', 'ERBB2', 'EGFR', 'KRAS', 'PIK3CA', 'AKT1', 'CCND1', 'MDM2', 'BRAF', 'NRAS',
        'TP53', 'RB1', 'PTEN', 'BRCA1', 'BRCA2', 'CDKN2A', 'CDKN1A', 'CDKN1B', 'APC', 'VHL',
        'ATM', 'CHEK1', 'CHEK2', 'RAD51', 'PARP1', 'MLH1', 'MSH2', 'XRCC1',
        'ESR1', 'PGR', 'AR'
    )
    AND expression_fold_change IS NOT NULL
    AND expression_fold_change != 1.0  -- Only include genes with actual expression changes
),
gene_summary AS (
    SELECT
        gene_category,
        gene_symbol,
        COUNT(*) as transcript_count,
        -- Use actual expression data for clinical assessment
        MAX(expression_fold_change) as max_fold_change,
        AVG(expression_fold_change) as avg_fold_change,
        AVG(pathway_count) as avg_pathway_count,
        -- FIX 1: Use boolean flag instead of set-returning function
        COUNT(*) FILTER (WHERE has_drug_interactions) as druggable_transcripts,
        -- FIX 2: Fixed ARRAY_AGG(DISTINCT unnest()) pattern using subquery
        ARRAY(
            SELECT DISTINCT pt
            FROM known_cancer_genes k2, unnest(k2.product_type) pt
            WHERE k2.gene_symbol = known_cancer_genes.gene_symbol
              AND k2.gene_category = known_cancer_genes.gene_category
        ) as all_product_types
    FROM known_cancer_genes
    GROUP BY gene_category, gene_symbol
)
SELECT
    gene_category,
    gene_symbol,
    transcript_count,
    ROUND(max_fold_change::numeric, 2) as max_expression_fold,
    ROUND(avg_fold_change::numeric, 2) as avg_expression_fold,
    ROUND(avg_pathway_count::numeric, 1) as avg_pathways,
    druggable_transcripts,
    CASE
        -- Clinical interpretation based on ACTUAL expression data
        WHEN gene_category = 'oncogene' AND max_fold_change > 2.0 THEN '🔴 ACTIVATED ONCOGENE (Therapeutic Target)'
        WHEN gene_category = 'oncogene' AND max_fold_change < 0.7 THEN '🟢 SUPPRESSED ONCOGENE (Favorable)'
        WHEN gene_category = 'tumor_suppressor' AND max_fold_change < 0.5 THEN '🔴 SUPPRESSED TUMOR SUPPRESSOR (High Risk)'
        WHEN gene_category = 'tumor_suppressor' AND max_fold_change > 1.5 THEN '🟢 ACTIVE TUMOR SUPPRESSOR (Protective)'
        WHEN gene_category = 'dna_repair' AND max_fold_change < 0.7 THEN '🔴 IMPAIRED DNA REPAIR (PARP/Immunotherapy Candidate)'
        WHEN gene_category = 'hormone_receptor' AND max_fold_change > 2.0 THEN '🟡 HORMONE RECEPTOR ACTIVE (Endocrine Therapy)'
        WHEN gene_category = 'hormone_receptor' AND max_fold_change < 0.5 THEN '🔴 HORMONE RECEPTOR SUPPRESSED (Hormone-Independent)'
        ELSE '⚪ NORMAL EXPRESSION RANGE'
    END as clinical_significance,
    all_product_types as product_types,
    CASE
        WHEN druggable_transcripts > 0 THEN '💊 TARGETABLE (' || druggable_transcripts || ' variants with drugs)'
        ELSE '❌ No approved drug targets identified'
    END as therapeutic_options
FROM gene_summary
ORDER BY
    CASE gene_category
        WHEN 'oncogene' THEN 1
        WHEN 'tumor_suppressor' THEN 2
        WHEN 'dna_repair' THEN 3
        ELSE 4
    END,
    max_fold_change DESC;

-- =====================================
-- SOTA Query 2: Therapeutic Target Prioritization (FIXED)
-- =====================================
-- Clinical Rationale: Ranks targets by expression level + druggability + pathway involvement
-- FIX: Fixed array slicing syntax and ARRAY_AGG(unnest()) patterns

WITH druggable_targets AS (
    SELECT
        gene_symbol,
        transcript_id,
        expression_fold_change,
        array_length(pathways, 1) as pathway_count,
        product_type,
        molecular_functions,
        drugs,
        -- Enhanced priority score using REAL expression data
        CASE
            WHEN expression_fold_change > 4.0 THEN 4  -- Very high expression
            WHEN expression_fold_change > 2.5 THEN 3  -- High expression
            WHEN expression_fold_change > 1.5 THEN 2  -- Moderate overexpression
            WHEN expression_fold_change > 1.0 THEN 1  -- Mild overexpression
            ELSE 0
        END +
        CASE
            WHEN drugs != '{}'::jsonb AND drugs != 'null'::jsonb THEN 3  -- Has drug interactions
            ELSE 0
        END +
        CASE
            WHEN 'kinase' = ANY(product_type) THEN 3   -- Kinases highly druggable
            WHEN 'receptor' = ANY(product_type) THEN 2 -- Receptors druggable
            WHEN 'enzyme' = ANY(product_type) THEN 1   -- Enzymes moderately druggable
            ELSE 0
        END +
        CASE
            WHEN array_length(pathways, 1) > 20 THEN 2  -- High pathway involvement
            WHEN array_length(pathways, 1) > 10 THEN 1  -- Moderate pathway involvement
            ELSE 0
        END as priority_score
    FROM cancer_transcript_base
    WHERE expression_fold_change > 1.2  -- Only upregulated genes are targetable
        AND (drugs != '{}'::jsonb OR
             'kinase' = ANY(product_type) OR
             'receptor' = ANY(product_type) OR
             'enzyme' = ANY(product_type)
             OR array_length(pathways, 1) > 10)
),
target_prioritization AS (
    SELECT
        gene_symbol,
        COUNT(*) as transcript_variants,
        MAX(priority_score) as max_priority_score,
        MAX(expression_fold_change) as max_expression_fold,
        AVG(expression_fold_change) as avg_expression_fold,
        AVG(pathway_count) as avg_pathway_count,
        COUNT(*) FILTER (WHERE drugs != '{}'::jsonb AND drugs != 'null'::jsonb) as druggable_variants,
        -- FIX 2: Fixed ARRAY_AGG(DISTINCT unnest()) pattern
        ARRAY(
            SELECT DISTINCT pt
            FROM druggable_targets dt2, unnest(dt2.product_type) pt
            WHERE dt2.gene_symbol = druggable_targets.gene_symbol
        ) as product_types,
        -- FIX 2: Fixed molecular_functions aggregation and array slicing
        ARRAY(
            SELECT DISTINCT mf
            FROM druggable_targets dt2, unnest(dt2.molecular_functions) mf
            WHERE dt2.gene_symbol = druggable_targets.gene_symbol
            LIMIT 3
        ) as key_functions
    FROM druggable_targets
    GROUP BY gene_symbol
)
SELECT
    gene_symbol,
    transcript_variants,
    max_priority_score,
    ROUND(max_expression_fold::numeric, 2) as max_fold_change,
    ROUND(avg_expression_fold::numeric, 2) as avg_fold_change,
    ROUND(avg_pathway_count::numeric, 1) as avg_pathways,
    druggable_variants,
    product_types,
    -- FIX 2: Array slicing with proper parentheses
    (key_functions)[1:2] as top_functions,
    CASE
        WHEN max_priority_score >= 9 THEN '🎯 IMMEDIATE PRIORITY - Strong expression + druggable + pathways'
        WHEN max_priority_score >= 6 THEN '🔵 HIGH PRIORITY - Good expression + some druggability'
        WHEN max_priority_score >= 4 THEN '🟡 MEDIUM PRIORITY - Moderate expression or druggability'
        WHEN max_priority_score >= 2 THEN '⚪ LOW PRIORITY - Weak signals'
        ELSE 'MINIMAL PRIORITY'
    END as clinical_recommendation,
    CASE
        WHEN druggable_variants > 0 AND max_expression_fold > 3.0
        THEN '💊 HIGH-PRIORITY DRUG TARGET (Strong expression + drugs available)'
        WHEN druggable_variants > 0
        THEN '💊 DRUG TARGET (Multiple variants: ' || druggable_variants || '/' || transcript_variants || ')'
        WHEN max_expression_fold > 3.0
        THEN '🔬 RESEARCH TARGET (High expression, needs drug development)'
        ELSE '📊 PATHWAY TARGET (Consider pathway-level intervention)'
    END as therapeutic_strategy
FROM target_prioritization
WHERE max_priority_score >= 2  -- Only meaningful targets
ORDER BY max_priority_score DESC, max_expression_fold DESC
LIMIT 20;

-- =====================================
-- SOTA Query 3: Pathway-Based Therapeutic Strategy (FIXED)
-- =====================================
-- Clinical Rationale: Identifies dysregulated pathways using expression data for weighting
-- FIX: Removed DISTINCT from ARRAY_AGG when ORDER BY uses different column

WITH pathway_expression_analysis AS (
    SELECT
        unnest(pathways) as pathway_name,
        COUNT(*) as total_genes,
        COUNT(DISTINCT gene_symbol) as unique_genes,
        -- Expression-based metrics
        COUNT(*) FILTER (WHERE expression_fold_change > 2.0) as highly_upregulated,
        COUNT(*) FILTER (WHERE expression_fold_change > 1.5) as upregulated_genes,
        COUNT(*) FILTER (WHERE expression_fold_change < 0.7) as downregulated_genes,
        COUNT(*) FILTER (WHERE expression_fold_change < 0.5) as highly_downregulated,
        AVG(expression_fold_change) as avg_pathway_expression,
        COUNT(*) FILTER (WHERE drugs != '{}'::jsonb AND drugs != 'null'::jsonb) as druggable_genes,
        COUNT(*) FILTER (WHERE array_length(molecular_functions, 1) > 3) as functionally_diverse_genes,
        -- FIX 3: Removed DISTINCT to allow ORDER BY on different column
        ARRAY_AGG(gene_symbol ORDER BY expression_fold_change DESC) as involved_genes
    FROM cancer_transcript_base
    WHERE pathways IS NOT NULL
        AND array_length(pathways, 1) > 0
        AND expression_fold_change != 1.0  -- Only genes with expression changes
    GROUP BY pathway_name
    HAVING COUNT(*) >= 3  -- At least 3 genes with expression changes
),
pathway_scoring AS (
    SELECT *,
        CASE
            -- Pathway classification
            WHEN pathway_name ILIKE '%PI3K%' OR pathway_name ILIKE '%AKT%' OR pathway_name ILIKE '%mTOR%' THEN 'growth_survival'
            WHEN pathway_name ILIKE '%RAS%' OR pathway_name ILIKE '%MAPK%' OR pathway_name ILIKE '%ERK%' THEN 'proliferation'
            WHEN pathway_name ILIKE '%p53%' OR pathway_name ILIKE '%DNA repair%' OR pathway_name ILIKE '%checkpoint%' THEN 'genome_stability'
            WHEN pathway_name ILIKE '%apoptosis%' OR pathway_name ILIKE '%cell death%' THEN 'apoptosis'
            WHEN pathway_name ILIKE '%angiogenesis%' OR pathway_name ILIKE '%VEGF%' THEN 'angiogenesis'
            WHEN pathway_name ILIKE '%immune%' OR pathway_name ILIKE '%interferon%' THEN 'immune_response'
            WHEN pathway_name ILIKE '%metabolism%' OR pathway_name ILIKE '%glycolysis%' THEN 'metabolism'
            ELSE 'other'
        END as pathway_category,
        -- Expression-weighted dysregulation score
        (highly_upregulated * 3) +  -- Highly upregulated genes (most important)
        (upregulated_genes * 2) +   -- Moderately upregulated
        (highly_downregulated * 2) + -- Highly downregulated (loss of function)
        (downregulated_genes * 1) +  -- Moderately downregulated
        (druggable_genes * 3) +      -- Druggability bonus
        (functionally_diverse_genes * 1) as dysregulation_score,
        -- Expression pattern classification
        CASE
            WHEN highly_upregulated > 0 AND highly_downregulated > 0 THEN 'mixed_dysregulation'
            WHEN highly_upregulated > upregulated_genes/2 THEN 'activation_pattern'
            WHEN highly_downregulated > downregulated_genes/2 THEN 'suppression_pattern'
            ELSE 'moderate_changes'
        END as expression_pattern
    FROM pathway_expression_analysis
)
SELECT
    pathway_category,
    pathway_name,
    unique_genes,
    highly_upregulated,
    upregulated_genes,
    downregulated_genes,
    highly_downregulated,
    ROUND(avg_pathway_expression::numeric, 2) as avg_expression,
    druggable_genes,
    dysregulation_score,
    expression_pattern,
    CASE
        WHEN dysregulation_score > 20 THEN '🚨 CRITICAL PATHWAY - Immediate multi-target intervention'
        WHEN dysregulation_score > 12 THEN '🔴 HIGH PRIORITY - Major pathway dysregulation detected'
        WHEN dysregulation_score > 8 THEN '🟡 MODERATE PRIORITY - Significant pathway changes'
        WHEN dysregulation_score > 4 THEN '⚪ LOW PRIORITY - Minor pathway alterations'
        ELSE 'MINIMAL DYSREGULATION'
    END as intervention_priority,
    CASE
        WHEN expression_pattern = 'activation_pattern' AND druggable_genes > 2
        THEN '💊 PATHWAY INHIBITION - Multiple drug targets available for activated pathway'
        WHEN expression_pattern = 'suppression_pattern' AND pathway_category = 'tumor_suppressor'
        THEN '🧬 PATHWAY RESTORATION - Consider synthetic lethality or pathway bypass'
        WHEN expression_pattern = 'mixed_dysregulation'
        THEN '⚖️ COMPLEX TARGETING - Mixed signals require precision approach'
        WHEN druggable_genes > 0
        THEN '🎯 TARGETED THERAPY - Focus on druggable components'
        ELSE '🔬 RESEARCH NEEDED - Pathway disrupted but lacks drug targets'
    END as therapeutic_strategy,
    (involved_genes)[1:5] as top_dysregulated_genes  -- Show most dysregulated genes
FROM pathway_scoring
WHERE dysregulation_score > 4  -- Only pathways with meaningful dysregulation
ORDER BY dysregulation_score DESC, avg_pathway_expression DESC
LIMIT 15;

-- =====================================
-- SOTA Query 4: Patient-Specific Expression Pattern Analysis (FIXED)
-- =====================================
-- Clinical Rationale: Analyze overall expression patterns for personalized insights
-- FIX: Simplified UNION structure to avoid syntax errors

-- Query 4A: Summary Statistics
WITH expression_profile AS (
    SELECT
        -- Overall expression statistics
        COUNT(*) as total_genes_with_changes,
        COUNT(*) FILTER (WHERE expression_fold_change > 2.0) as highly_upregulated,
        COUNT(*) FILTER (WHERE expression_fold_change BETWEEN 1.5 AND 2.0) as moderately_upregulated,
        COUNT(*) FILTER (WHERE expression_fold_change BETWEEN 0.7 AND 1.5) as normal_expression,
        COUNT(*) FILTER (WHERE expression_fold_change BETWEEN 0.5 AND 0.7) as moderately_downregulated,
        COUNT(*) FILTER (WHERE expression_fold_change < 0.5) as highly_downregulated,

        -- Therapeutic categories
        COUNT(*) FILTER (WHERE drugs != '{}'::jsonb AND drugs != 'null'::jsonb AND expression_fold_change > 1.5) as upregulated_drug_targets,
        COUNT(*) FILTER (WHERE 'kinase' = ANY(product_type) AND expression_fold_change > 1.5) as upregulated_kinases,
        COUNT(*) FILTER (WHERE 'receptor' = ANY(product_type) AND expression_fold_change > 1.5) as upregulated_receptors,

        -- Expression statistics
        MAX(expression_fold_change) as max_upregulation,
        MIN(expression_fold_change) as max_downregulation,
        AVG(expression_fold_change) as mean_expression,
        percentile_cont(0.9) WITHIN GROUP (ORDER BY expression_fold_change) as ninetieth_percentile,
        percentile_cont(0.1) WITHIN GROUP (ORDER BY expression_fold_change) as tenth_percentile
    FROM cancer_transcript_base
    WHERE expression_fold_change != 1.0  -- Only genes with expression changes
)
SELECT
    'PATIENT EXPRESSION PROFILE SUMMARY' as metric_category,
    'Total Genes with Expression Changes' as metric_name,
    total_genes_with_changes::text as value
FROM expression_profile
UNION ALL
SELECT
    'DYSREGULATION LEVELS',
    '🔴 Highly Upregulated (>2.0x)',
    highly_upregulated::text
FROM expression_profile
UNION ALL
SELECT
    'DYSREGULATION LEVELS',
    '🟡 Moderately Upregulated (1.5-2.0x)',
    moderately_upregulated::text
FROM expression_profile
UNION ALL
SELECT
    'DYSREGULATION LEVELS',
    '🔵 Moderately Downregulated (0.5-0.7x)',
    moderately_downregulated::text
FROM expression_profile
UNION ALL
SELECT
    'DYSREGULATION LEVELS',
    '🔴 Highly Downregulated (<0.5x)',
    highly_downregulated::text
FROM expression_profile
UNION ALL
SELECT
    'THERAPEUTIC TARGETS',
    '💊 Upregulated Drug Targets',
    upregulated_drug_targets::text
FROM expression_profile
UNION ALL
SELECT
    'THERAPEUTIC TARGETS',
    '🎯 Upregulated Kinases',
    upregulated_kinases::text
FROM expression_profile
UNION ALL
SELECT
    'THERAPEUTIC TARGETS',
    '📡 Upregulated Receptors',
    upregulated_receptors::text
FROM expression_profile
UNION ALL
SELECT
    'EXPRESSION RANGE',
    'Maximum Upregulation',
    ROUND(max_upregulation::numeric, 2)::text || 'x'
FROM expression_profile
UNION ALL
SELECT
    'EXPRESSION RANGE',
    'Maximum Downregulation',
    ROUND(max_downregulation::numeric, 2)::text || 'x'
FROM expression_profile
ORDER BY metric_category, metric_name;

-- Query 4B: Top Expression Candidates
-- FIX 4: Separate query with clean UNION structure
WITH top_upregulated AS (
    SELECT
        'Most Upregulated' as category,
        gene_symbol,
        ROUND(expression_fold_change::numeric, 2) as fold_change,
        CASE
            WHEN drugs != '{}'::jsonb AND drugs != 'null'::jsonb THEN '💊 Druggable'
            ELSE '🔬 Research'
        END as druggability,
        array_length(pathways, 1) as pathway_count
    FROM cancer_transcript_base
    WHERE expression_fold_change > 3.0
    ORDER BY expression_fold_change DESC
    LIMIT 5
),
top_downregulated AS (
    SELECT
        'Most Downregulated' as category,
        gene_symbol,
        ROUND(expression_fold_change::numeric, 2) as fold_change,
        CASE
            WHEN gene_symbol IN ('TP53', 'BRCA1', 'BRCA2', 'PTEN', 'ATM') THEN '🚨 Tumor Suppressor Loss'
            WHEN drugs != '{}'::jsonb AND drugs != 'null'::jsonb THEN '💊 Restoration Target'
            ELSE '🔬 Research'
        END as druggability,
        array_length(pathways, 1) as pathway_count
    FROM cancer_transcript_base
    WHERE expression_fold_change < 0.3
    ORDER BY expression_fold_change ASC
    LIMIT 5
)
SELECT * FROM top_upregulated
UNION ALL
SELECT * FROM top_downregulated
ORDER BY category DESC, fold_change DESC;

-- =====================================
-- Quick Patient Database Validation Query (FIXED)
-- =====================================
-- Use this to quickly validate your patient database has expression data
-- FIX 5: Changed ::float to ::numeric for ROUND function

SELECT
    'Database Validation Results' as check_type,
    COUNT(*) as total_transcripts,
    COUNT(*) FILTER (WHERE expression_fold_change != 1.0) as transcripts_with_expression_data,
    -- FIX 5: Use ::numeric instead of ::float for ROUND
    ROUND((COUNT(*) FILTER (WHERE expression_fold_change != 1.0)::numeric / COUNT(*) * 100), 1) as percentage_with_data,
    ROUND(MIN(expression_fold_change)::numeric, 3) as min_expression,
    ROUND(MAX(expression_fold_change)::numeric, 3) as max_expression
FROM cancer_transcript_base;

-- =====================================
-- Connection Examples for All Demo Databases
-- =====================================
/*
-- Breast HER2-Positive Cancer:
PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U mbase_user -d mediabase_patient_DEMO_BREAST_HER2

-- Breast Triple-Negative Cancer:
PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U mbase_user -d mediabase_patient_DEMO_BREAST_TNBC

-- Lung EGFR-Mutant Adenocarcinoma:
PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U mbase_user -d mediabase_patient_DEMO_LUNG_EGFR

-- Colorectal MSI-High Cancer:
PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U mbase_user -d mediabase_patient_DEMO_COLORECTAL_MSI

-- Pancreatic Ductal Adenocarcinoma:
PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U mbase_user -d mediabase_patient_DEMO_PANCREATIC_PDAC

-- Comprehensive Pan-Cancer:
PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U mbase_user -d mediabase_patient_DEMO_COMPREHENSIVE
*/

-- =====================================
-- QUERY SUMMARY AND USAGE NOTES
-- =====================================
/*
FIXED ISSUES:
1. ✅ SOTA Query 1: Removed set-returning function jsonb_object_keys() from CASE
2. ✅ SOTA Query 2: Fixed ARRAY_AGG(DISTINCT unnest()) and array slicing syntax
3. ✅ SOTA Query 3: Removed DISTINCT from ARRAY_AGG to allow ORDER BY different column
4. ✅ SOTA Query 4: Restructured UNION queries with consistent column structure
5. ✅ Validation Query: Changed ::float to ::numeric for ROUND function

TESTED ON:
- PostgreSQL 12+
- Patient databases with cancer_transcript_base schema
- Demo databases: DEMO_BREAST_HER2, DEMO_BREAST_TNBC

ALTERNATIVE QUERY FILES:
- cancer_specific_sota_queries.sql - Simpler, cancer-specific queries (RECOMMENDED for most use cases)
- normalized_sota_queries_for_patients.sql - For normalized schema (requires migration)

For detailed documentation, see: docs/SOTA_QUERIES_GUIDE.md
*/

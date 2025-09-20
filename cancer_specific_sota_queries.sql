-- CANCER-SPECIFIC SOTA QUERY EXAMPLES
-- These queries are optimized for different cancer types using patient databases

-- =============================================================================
-- BREAST CANCER HER2+ SPECIFIC QUERIES
-- Database: mediabase_patient_DEMO_BREAST_HER2
-- =============================================================================

-- HER2+ Breast Cancer: Targeted Therapy Selection
SELECT
    gene_symbol,
    expression_fold_change as fold_change,
    CASE
        WHEN gene_symbol = 'ERBB2' AND expression_fold_change > 4.0 THEN '🎯 TRASTUZUMAB/PERTUZUMAB TARGET (High Priority)'
        WHEN gene_symbol IN ('PIK3CA', 'AKT1') AND expression_fold_change > 3.0 THEN '🎯 PI3K/AKT INHIBITOR TARGET'
        WHEN gene_symbol = 'ESR1' AND expression_fold_change > 2.0 THEN '🎯 ENDOCRINE THERAPY CANDIDATE'
        WHEN gene_symbol IN ('CDK4', 'CDK6', 'CCND1') AND expression_fold_change > 2.0 THEN '🎯 CDK4/6 INHIBITOR TARGET'
        WHEN gene_symbol IN ('PTEN', 'TP53') AND expression_fold_change < 0.5 THEN '⚠️ TUMOR SUPPRESSOR LOSS (High Risk)'
        ELSE '📊 MONITOR'
    END as her2_therapeutic_strategy,
    LENGTH(drugs::text) as drug_options_available
FROM cancer_transcript_base
WHERE expression_fold_change != 1.0
  AND gene_symbol IN ('ERBB2', 'PIK3CA', 'AKT1', 'ESR1', 'ESR2', 'PGR', 'CDK4', 'CDK6', 'CCND1', 'PTEN', 'TP53', 'BRCA1', 'BRCA2')
ORDER BY
    CASE gene_symbol
        WHEN 'ERBB2' THEN 1
        WHEN 'PIK3CA' THEN 2
        WHEN 'AKT1' THEN 3
        ELSE 4
    END,
    expression_fold_change DESC;

-- HER2+ Breast Cancer: Resistance Pathway Analysis
SELECT
    pathway,
    COUNT(*) as affected_genes,
    AVG(expression_fold_change) as avg_expression,
    STRING_AGG(
        gene_symbol || ' (' || ROUND(expression_fold_change::numeric, 2) || 'x)',
        ', '
        ORDER BY expression_fold_change DESC
    ) as key_resistance_genes,
    CASE
        WHEN pathway ILIKE '%PI3K%' OR pathway ILIKE '%AKT%' THEN '🔴 PI3K/AKT RESISTANCE PATHWAY'
        WHEN pathway ILIKE '%cell cycle%' OR pathway ILIKE '%CDK%' THEN '🟡 CELL CYCLE BYPASS'
        WHEN pathway ILIKE '%ERBB%' OR pathway ILIKE '%HER%' THEN '🔴 HER2 SIGNALING DYSREGULATION'
        WHEN pathway ILIKE '%apoptosis%' THEN '🟡 APOPTOSIS EVASION'
        ELSE '📊 OTHER PATHWAY'
    END as resistance_mechanism
FROM (
    SELECT
        unnest(pathways) as pathway,
        gene_symbol,
        expression_fold_change
    FROM cancer_transcript_base
    WHERE expression_fold_change > 2.0
      AND gene_symbol IN (
          SELECT DISTINCT gene_symbol
          FROM cancer_transcript_base
          WHERE LENGTH(drugs::text) > 1000  -- Genes with extensive drug interactions
      )
) pathway_resistance
GROUP BY pathway
HAVING COUNT(*) >= 2
ORDER BY AVG(expression_fold_change) DESC
LIMIT 10;

-- =============================================================================
-- BREAST CANCER TRIPLE-NEGATIVE (TNBC) SPECIFIC QUERIES
-- Database: mediabase_patient_DEMO_BREAST_TNBC
-- =============================================================================

-- TNBC: Immunotherapy and DNA Damage Response Targets
SELECT
    gene_symbol,
    expression_fold_change as fold_change,
    CASE
        WHEN gene_symbol IN ('BRCA1', 'BRCA2') AND expression_fold_change < 0.5 THEN '🎯 PARP INHIBITOR CANDIDATE (BRCA-deficient)'
        WHEN gene_symbol IN ('ATM', 'ATR', 'CHEK1', 'CHEK2') AND expression_fold_change < 0.6 THEN '🎯 DNA DAMAGE RESPONSE TARGET'
        WHEN gene_symbol IN ('PD1', 'PDL1', 'CTLA4') AND expression_fold_change > 1.5 THEN '🎯 IMMUNE CHECKPOINT TARGET'
        WHEN gene_symbol IN ('MYC', 'CCND1', 'CCNE1') AND expression_fold_change > 3.0 THEN '🔴 AGGRESSIVE PROLIFERATION SIGNATURE'
        WHEN gene_symbol IN ('TP53', 'RB1', 'CDKN2A') AND expression_fold_change < 0.5 THEN '⚠️ TUMOR SUPPRESSOR LOSS'
        ELSE '📊 MONITOR'
    END as tnbc_therapeutic_strategy,
    CASE WHEN LENGTH(drugs::text) > 100 THEN '💊 Druggable' ELSE '🔬 Research' END as target_status
FROM cancer_transcript_base
WHERE expression_fold_change != 1.0
  AND gene_symbol IN ('BRCA1', 'BRCA2', 'ATM', 'ATR', 'CHEK1', 'CHEK2', 'TP53', 'RB1', 'CDKN2A', 'MYC', 'CCND1', 'CCNE1')
ORDER BY
    CASE
        WHEN gene_symbol IN ('BRCA1', 'BRCA2') THEN 1
        WHEN gene_symbol = 'TP53' THEN 2
        ELSE 3
    END,
    ABS(expression_fold_change - 1.0) DESC;

-- =============================================================================
-- LUNG ADENOCARCINOMA EGFR-MUTANT SPECIFIC QUERIES
-- Database: mediabase_patient_DEMO_LUNG_EGFR
-- =============================================================================

-- EGFR-Mutant Lung Cancer: Targeted Therapy and Resistance
SELECT
    gene_symbol,
    expression_fold_change as fold_change,
    CASE
        WHEN gene_symbol = 'EGFR' AND expression_fold_change > 4.0 THEN '🎯 EGFR TKI PRIMARY TARGET (Gefitinib/Erlotinib/Osimertinib)'
        WHEN gene_symbol = 'MET' AND expression_fold_change > 3.0 THEN '🎯 MET INHIBITOR (Resistance Bypass)'
        WHEN gene_symbol IN ('ALK', 'ROS1', 'RET') AND expression_fold_change > 2.5 THEN '🎯 ALTERNATIVE RTK TARGET'
        WHEN gene_symbol = 'KRAS' AND expression_fold_change > 2.0 THEN '⚠️ KRAS-MEDIATED RESISTANCE RISK'
        WHEN gene_symbol IN ('PIK3CA', 'AKT1') AND expression_fold_change > 2.5 THEN '🎯 PI3K/AKT PATHWAY TARGET'
        WHEN gene_symbol = 'TP53' AND expression_fold_change < 0.5 THEN '⚠️ TP53 LOSS (Poor Prognosis)'
        ELSE '📊 MONITOR'
    END as egfr_lung_strategy,
    molecular_functions[1:3] as key_functions
FROM cancer_transcript_base
WHERE expression_fold_change != 1.0
  AND gene_symbol IN ('EGFR', 'MET', 'ALK', 'ROS1', 'RET', 'KRAS', 'PIK3CA', 'AKT1', 'TP53', 'STK11', 'CDKN2A')
ORDER BY
    CASE gene_symbol
        WHEN 'EGFR' THEN 1
        WHEN 'MET' THEN 2
        WHEN 'KRAS' THEN 3
        ELSE 4
    END,
    expression_fold_change DESC;

-- =============================================================================
-- COLORECTAL MSI-HIGH SPECIFIC QUERIES
-- Database: mediabase_patient_DEMO_COLORECTAL_MSI
-- =============================================================================

-- MSI-High Colorectal: Immunotherapy Prediction and Mismatch Repair
SELECT
    gene_symbol,
    expression_fold_change as fold_change,
    CASE
        WHEN gene_symbol IN ('MLH1', 'MSH2', 'MSH6', 'PMS2') AND expression_fold_change < 0.5 THEN '🎯 MSI-HIGH CONFIRMED (Immunotherapy Candidate)'
        WHEN gene_symbol IN ('CD8A', 'PDCD1', 'CD274', 'CTLA4') AND expression_fold_change > 1.8 THEN '🎯 IMMUNE ACTIVATION SIGNATURE'
        WHEN gene_symbol IN ('KRAS', 'PIK3CA', 'APC', 'TP53') AND expression_fold_change > 2.0 THEN '🔴 ONCOGENIC DRIVER ACTIVATION'
        WHEN gene_symbol = 'BRAF' AND expression_fold_change > 2.5 THEN '🎯 BRAF INHIBITOR TARGET (if V600E)'
        WHEN gene_symbol IN ('TGFBR2', 'ACVR2A') AND expression_fold_change < 0.6 THEN '⚠️ TGF-β PATHWAY DISRUPTION'
        ELSE '📊 MONITOR'
    END as msi_colorectal_strategy,
    CASE
        WHEN gene_symbol IN ('MLH1', 'MSH2', 'MSH6', 'PMS2') THEN 'Mismatch Repair'
        WHEN gene_symbol IN ('CD8A', 'PDCD1', 'CD274') THEN 'Immune Checkpoint'
        WHEN gene_symbol IN ('KRAS', 'PIK3CA', 'BRAF') THEN 'Oncogenic Driver'
        ELSE 'Other'
    END as gene_category
FROM cancer_transcript_base
WHERE expression_fold_change != 1.0
  AND gene_symbol IN ('MLH1', 'MSH2', 'MSH6', 'PMS2', 'CD8A', 'PDCD1', 'CD274', 'CTLA4', 'KRAS', 'PIK3CA', 'APC', 'TP53', 'BRAF', 'TGFBR2', 'ACVR2A')
ORDER BY
    CASE gene_category
        WHEN 'Mismatch Repair' THEN 1
        WHEN 'Immune Checkpoint' THEN 2
        WHEN 'Oncogenic Driver' THEN 3
        ELSE 4
    END,
    ABS(expression_fold_change - 1.0) DESC;

-- =============================================================================
-- PANCREATIC DUCTAL ADENOCARCINOMA (PDAC) SPECIFIC QUERIES
-- Database: mediabase_patient_DEMO_PANCREATIC_PDAC
-- =============================================================================

-- PDAC: Targeting the Challenging Tumor Microenvironment
SELECT
    gene_symbol,
    expression_fold_change as fold_change,
    CASE
        WHEN gene_symbol = 'KRAS' AND expression_fold_change > 3.0 THEN '🎯 KRAS G12C INHIBITOR CANDIDATE (if G12C mutation)'
        WHEN gene_symbol IN ('BRCA1', 'BRCA2', 'PALB2') AND expression_fold_change < 0.5 THEN '🎯 PARP INHIBITOR + PLATINUM THERAPY'
        WHEN gene_symbol = 'CDKN2A' AND expression_fold_change < 0.3 THEN '🎯 CDK4/6 INHIBITOR STRATEGY'
        WHEN gene_symbol IN ('SMAD4', 'TGFBR1', 'TGFBR2') AND expression_fold_change < 0.6 THEN '⚠️ TGF-β PATHWAY LOSS'
        WHEN gene_symbol IN ('MYC', 'CCND1') AND expression_fold_change > 4.0 THEN '🔴 AGGRESSIVE PROLIFERATION'
        WHEN gene_symbol = 'TP53' AND expression_fold_change < 0.4 THEN '⚠️ TP53 LOSS (Very Poor Prognosis)'
        ELSE '📊 MONITOR'
    END as pdac_therapeutic_strategy,
    pathways[1:2] as relevant_pathways
FROM cancer_transcript_base
WHERE expression_fold_change != 1.0
  AND gene_symbol IN ('KRAS', 'TP53', 'CDKN2A', 'SMAD4', 'BRCA1', 'BRCA2', 'PALB2', 'ATM', 'MYC', 'CCND1', 'TGFBR1', 'TGFBR2')
ORDER BY
    CASE gene_symbol
        WHEN 'KRAS' THEN 1
        WHEN 'TP53' THEN 2
        WHEN 'CDKN2A' THEN 3
        ELSE 4
    END,
    ABS(expression_fold_change - 1.0) DESC;

-- =============================================================================
-- COMPREHENSIVE PAN-CANCER ANALYSIS
-- Database: mediabase_patient_DEMO_COMPREHENSIVE
-- =============================================================================

-- Pan-Cancer: Universal Biomarkers and Therapeutic Targets
SELECT
    gene_symbol,
    expression_fold_change as fold_change,
    CASE
        WHEN gene_symbol IN ('TP53', 'RB1', 'APC', 'PTEN', 'BRCA1', 'BRCA2') AND expression_fold_change < 0.5
            THEN '🔴 UNIVERSAL TUMOR SUPPRESSOR LOSS'
        WHEN gene_symbol IN ('MYC', 'EGFR', 'ERBB2', 'KRAS', 'PIK3CA') AND expression_fold_change > 3.0
            THEN '🔴 UNIVERSAL ONCOGENE ACTIVATION'
        WHEN gene_symbol IN ('PDCD1', 'CD274', 'CTLA4', 'LAG3', 'TIGIT') AND expression_fold_change > 1.5
            THEN '🎯 UNIVERSAL IMMUNE CHECKPOINT TARGET'
        WHEN gene_symbol IN ('MLH1', 'MSH2', 'MSH6', 'PMS2') AND expression_fold_change < 0.5
            THEN '🎯 UNIVERSAL MSI/IMMUNOTHERAPY CANDIDATE'
        WHEN gene_symbol IN ('CDK4', 'CDK6', 'CCND1', 'CCNE1') AND expression_fold_change > 2.5
            THEN '🎯 UNIVERSAL CELL CYCLE TARGET'
        ELSE '📊 CANCER-TYPE SPECIFIC'
    END as pan_cancer_significance,
    CASE
        WHEN gene_symbol IN ('TP53', 'RB1', 'APC', 'PTEN', 'BRCA1', 'BRCA2') THEN 'Tumor Suppressor'
        WHEN gene_symbol IN ('MYC', 'EGFR', 'ERBB2', 'KRAS', 'PIK3CA') THEN 'Oncogene'
        WHEN gene_symbol IN ('PDCD1', 'CD274', 'CTLA4', 'LAG3', 'TIGIT') THEN 'Immune Checkpoint'
        WHEN gene_symbol IN ('MLH1', 'MSH2', 'MSH6', 'PMS2') THEN 'DNA Repair'
        WHEN gene_symbol IN ('CDK4', 'CDK6', 'CCND1', 'CCNE1') THEN 'Cell Cycle'
        ELSE 'Other'
    END as gene_class,
    LENGTH(drugs::text) as therapeutic_options
FROM cancer_transcript_base
WHERE expression_fold_change != 1.0
  AND gene_symbol IN (
      'TP53', 'RB1', 'APC', 'PTEN', 'BRCA1', 'BRCA2',  -- Tumor suppressors
      'MYC', 'EGFR', 'ERBB2', 'KRAS', 'PIK3CA',        -- Oncogenes
      'PDCD1', 'CD274', 'CTLA4', 'LAG3', 'TIGIT',      -- Immune checkpoints
      'MLH1', 'MSH2', 'MSH6', 'PMS2',                  -- DNA repair
      'CDK4', 'CDK6', 'CCND1', 'CCNE1'                 -- Cell cycle
  )
ORDER BY
    gene_class,
    ABS(expression_fold_change - 1.0) DESC;

-- =============================================================================
-- USAGE INSTRUCTIONS
-- =============================================================================

/*
To use these cancer-specific queries:

1. Connect to the appropriate patient database:
   \c mediabase_patient_DEMO_BREAST_HER2
   \c mediabase_patient_DEMO_BREAST_TNBC
   \c mediabase_patient_DEMO_LUNG_EGFR
   \c mediabase_patient_DEMO_COLORECTAL_MSI
   \c mediabase_patient_DEMO_PANCREATIC_PDAC
   \c mediabase_patient_DEMO_COMPREHENSIVE

2. Run the corresponding cancer-specific query section

3. Interpret results based on clinical context:
   🔴 = High priority therapeutic targets or risk factors
   🎯 = Specific drug targets with available therapies
   🟡 = Moderate priority or monitoring required
   ⚠️ = Warning signs or poor prognostic factors
   📊 = Standard monitoring or research interest
   💊 = Druggable targets
   🔬 = Research targets

4. Cross-reference with patient's mutation profile, staging, and treatment history
*/
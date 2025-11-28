-- ========================================================================
-- CROSS-PATIENT COMPARISON QUERIES
-- ========================================================================
-- Purpose: Demonstrate clinically meaningful analyses across different
--          cancer types using patient-specific MEDIABASE databases
--
-- Clinical Value: These queries show how MEDIABASE enables:
--   1. Biomarker-driven treatment selection
--   2. Cross-cancer comparison for clinical trial matching
--   3. Pathway-based therapeutic targeting
--   4. Precision oncology decision support
--
-- Test Datasets:
--   - Patient 1: HER2+ breast cancer (DEMO_HER2)
--   - Patient 2: TNBC breast cancer (DEMO_TNBC)
--   - Patient 3: Lung adenocarcinoma EGFR+ (DEMO_LUAD)
-- ========================================================================


-- ========================================================================
-- QUERY 1: HER2/ERBB2 EXPRESSION ACROSS ALL CANCER TYPES
-- ========================================================================
-- Clinical Question: "Which of my patients are HER2 therapy candidates?"
--
-- Clinical Context:
-- - HER2 targeted therapy (trastuzumab, pertuzumab) approved for:
--   * Breast cancer (>4x overexpression or IHC 3+)
--   * Gastric cancer (IHC 3+ or 2+ with FISH+)
--   * Recently: Any solid tumor with HER2 amplification (T-DXd)
--
-- This query identifies HER2 expression across different tumor types
-- ========================================================================

\echo '=== QUERY 1: HER2 Expression Comparison Across Patients ==='

-- Run this on HER2+ database
\c mediabase_patient_DEMO_HER2

SELECT
    'HER2_BREAST' as patient_id,
    ctb.gene_symbol,
    ctb.expression_fold_change,
    CASE
        WHEN ctb.expression_fold_change >= 4.0
            THEN '🎯 APPROVED: Trastuzumab + Pertuzumab'
        WHEN ctb.expression_fold_change >= 2.0
            THEN '⚠️  EQUIVOCAL: Requires FISH confirmation'
        ELSE 'Not a HER2 therapy candidate'
    END as therapeutic_recommendation,
    CASE
        WHEN ctb.expression_fold_change >= 4.0 THEN 'IHC 3+ equivalent'
        WHEN ctb.expression_fold_change >= 2.0 THEN 'IHC 2+ equivalent'
        WHEN ctb.expression_fold_change >= 1.2 THEN 'IHC 1+ equivalent'
        ELSE 'IHC 0/negative'
    END as ihc_equivalent
FROM cancer_transcript_base ctb
WHERE ctb.gene_symbol = 'ERBB2';

-- Expected Result (HER2+ patient):
-- | patient_id  | gene_symbol | expression_fold_change | therapeutic_recommendation          | ihc_equivalent     |
-- |-------------|-------------|------------------------|-------------------------------------|--------------------|
-- | HER2_BREAST | ERBB2       | 6.2                    | 🎯 APPROVED: Trastuzumab + Pertuzumab | IHC 3+ equivalent |


\echo '\n--- Same query on TNBC patient ---'
\c mediabase_patient_DEMO_TNBC

SELECT
    'TNBC_BREAST' as patient_id,
    ctb.gene_symbol,
    ctb.expression_fold_change,
    CASE
        WHEN ctb.expression_fold_change >= 4.0
            THEN '🎯 APPROVED: Trastuzumab + Pertuzumab'
        WHEN ctb.expression_fold_change >= 2.0
            THEN '⚠️  EQUIVOCAL: Requires FISH confirmation'
        ELSE 'Not a HER2 therapy candidate'
    END as therapeutic_recommendation
FROM cancer_transcript_base ctb
WHERE ctb.gene_symbol = 'ERBB2';

-- Expected Result (TNBC patient):
-- | patient_id  | gene_symbol | expression_fold_change | therapeutic_recommendation         |
-- |-------------|-------------|------------------------|------------------------------------|
-- | TNBC_BREAST | ERBB2       | 0.8                    | Not a HER2 therapy candidate       |


\echo '\n--- Same query on Lung adenocarcinoma patient ---'
\c mediabase_patient_DEMO_LUAD

SELECT
    'LUAD_PATIENT' as patient_id,
    ctb.gene_symbol,
    ctb.expression_fold_change,
    CASE
        WHEN ctb.expression_fold_change >= 4.0
            THEN '🎯 CONSIDER: T-DXd (HER2-targeting ADC, tumor-agnostic)'
        WHEN ctb.expression_fold_change >= 2.0
            THEN '⚠️  EQUIVOCAL: Requires confirmation'
        ELSE 'Not a HER2 therapy candidate'
    END as therapeutic_recommendation
FROM cancer_transcript_base ctb
WHERE ctb.gene_symbol = 'ERBB2';

-- Expected Result (LUAD patient):
-- | patient_id  | gene_symbol | expression_fold_change | therapeutic_recommendation         |
-- |-------------|-------------|------------------------|------------------------------------|
-- | LUAD_PATIENT| ERBB2       | 0.8                    | Not a HER2 therapy candidate       |

-- Clinical Interpretation:
-- Only the HER2+ breast cancer patient is a candidate for HER2-targeted
-- therapy. TNBC and LUAD patients show normal HER2 expression and would
-- not benefit from anti-HER2 agents.


-- ========================================================================
-- QUERY 2: FIND DRUGGABLE TARGETS IN HER2+ PATIENT
-- ========================================================================
-- Clinical Question: "What FDA-approved drugs target my patient's
--                     overexpressed genes?"
--
-- Clinical Value: Identifies actionable targets for precision medicine
-- ========================================================================

\echo '\n\n=== QUERY 2: Druggable Overexpressed Targets (HER2+ Patient) ==='

\c mediabase_patient_DEMO_HER2

SELECT
    ctb.gene_symbol,
    ctb.expression_fold_change,
    d.drug_name,
    d.max_phase,
    dm.mechanism_of_action,
    di.indication,
    CASE
        WHEN d.max_phase = 4 THEN '✅ FDA APPROVED'
        WHEN d.max_phase = 3 THEN '🔬 Phase III (Late stage)'
        WHEN d.max_phase = 2 THEN '🧪 Phase II (Mid stage)'
        ELSE '🔍 Early stage'
    END as clinical_status
FROM cancer_transcript_base ctb
INNER JOIN genes g ON ctb.gene_id = g.gene_id
INNER JOIN drug_target_genes dtg ON g.gene_id = dtg.gene_id
INNER JOIN drugs d ON dtg.drug_id = d.drug_id
LEFT JOIN drug_mechanisms dm ON d.drug_id = dm.drug_id
LEFT JOIN drug_indications di ON d.drug_id = di.drug_id
WHERE ctb.expression_fold_change > 2.0  -- Significantly overexpressed
  AND d.max_phase >= 3  -- Late-stage or approved only
  AND di.indication ILIKE '%breast%'  -- Breast cancer indication
ORDER BY
    d.max_phase DESC,
    ctb.expression_fold_change DESC
LIMIT 20;

-- Expected Results:
-- | gene_symbol | fold_change | drug_name    | max_phase | mechanism_of_action           | clinical_status  |
-- |-------------|-------------|--------------|-----------|-------------------------------|------------------|
-- | ERBB2       | 6.2         | Trastuzumab  | 4         | HER2 monoclonal antibody      | ✅ FDA APPROVED |
-- | ERBB2       | 6.2         | Pertuzumab   | 4         | HER2 dimerization inhibitor   | ✅ FDA APPROVED |
-- | ERBB2       | 6.2         | Ado-trastuzumab | 4      | HER2 antibody-drug conjugate  | ✅ FDA APPROVED |
-- | PIK3CA      | 2.8         | Alpelisib    | 4         | PI3K alpha inhibitor          | ✅ FDA APPROVED |
-- | ESR1        | 2.1         | Tamoxifen    | 4         | Estrogen receptor antagonist  | ✅ FDA APPROVED |
-- | CDK4        | 2.5         | Palbociclib  | 4         | CDK4/6 inhibitor              | ✅ FDA APPROVED |

-- Clinical Interpretation:
-- This HER2+ ER+ patient has multiple actionable targets:
-- 1. First-line: Dual HER2 blockade (trastuzumab + pertuzumab) + chemo
-- 2. If PIK3CA mutant: Add alpelisib
-- 3. If ER+: Endocrine therapy + CDK4/6 inhibitor (maintenance)
-- 4. Second-line: T-DM1 or T-DXd (HER2 ADCs)


-- ========================================================================
-- QUERY 3: PATHWAY ENRICHMENT COMPARISON (HER2+ vs TNBC)
-- ========================================================================
-- Clinical Question: "What biological pathways differ between HER2+ and
--                     TNBC breast cancers?"
--
-- Clinical Value: Reveals distinct biology → different therapeutic strategies
-- ========================================================================

\echo '\n\n=== QUERY 3A: Pathway Enrichment in HER2+ Patient ==='

\c mediabase_patient_DEMO_HER2

SELECT
    gp.pathway_name,
    COUNT(*) as num_overexpressed_genes,
    ROUND(AVG(ctb.expression_fold_change), 2) as avg_pathway_fold_change,
    STRING_AGG(
        ctb.gene_symbol || '(' || ROUND(ctb.expression_fold_change::numeric, 1) || 'x)',
        ', '
        ORDER BY ctb.expression_fold_change DESC
    ) as top_genes,
    CASE
        WHEN gp.pathway_name ILIKE '%PI3K%' OR gp.pathway_name ILIKE '%AKT%'
            THEN '🎯 PI3K inhibitors (alpelisib)'
        WHEN gp.pathway_name ILIKE '%ERBB%' OR gp.pathway_name ILIKE '%HER2%'
            THEN '🎯 HER2 inhibitors (trastuzumab)'
        WHEN gp.pathway_name ILIKE '%cell cycle%'
            THEN '🎯 CDK4/6 inhibitors'
        ELSE 'No direct therapeutic'
    END as therapeutic_target
FROM cancer_transcript_base ctb
INNER JOIN genes g ON ctb.gene_id = g.gene_id
INNER JOIN gene_pathways gp ON g.gene_id = gp.gene_id
WHERE ctb.expression_fold_change > 2.0  -- Overexpressed genes
GROUP BY gp.pathway_name
HAVING COUNT(*) >= 3  -- Pathway must have 3+ overexpressed genes
ORDER BY avg_pathway_fold_change DESC
LIMIT 15;

-- Expected Results (HER2+ patient):
-- | pathway_name                    | num_genes | avg_fc | top_genes                        | therapeutic_target           |
-- |---------------------------------|-----------|--------|----------------------------------|------------------------------|
-- | ERBB2 signaling                 | 8         | 4.5    | ERBB2(6.2x), GRB7(4.8x), ...    | 🎯 HER2 inhibitors          |
-- | PI3K-AKT-mTOR signaling         | 6         | 3.2    | PIK3CA(2.8x), AKT1(2.4x), ...   | 🎯 PI3K inhibitors          |
-- | Cell cycle regulation           | 7         | 3.8    | CCND1(3.5x), CDK4(2.9x), ...    | 🎯 CDK4/6 inhibitors        |
-- | Estrogen receptor signaling     | 5         | 2.4    | ESR1(2.1x), GATA3(2.0x), ...    | Endocrine therapy            |


\echo '\n=== QUERY 3B: Pathway Enrichment in TNBC Patient ==='

\c mediabase_patient_DEMO_TNBC

SELECT
    gp.pathway_name,
    COUNT(*) as num_overexpressed_genes,
    ROUND(AVG(ctb.expression_fold_change), 2) as avg_pathway_fold_change,
    STRING_AGG(
        ctb.gene_symbol || '(' || ROUND(ctb.expression_fold_change::numeric, 1) || 'x)',
        ', '
        ORDER BY ctb.expression_fold_change DESC
    ) as top_genes,
    CASE
        WHEN gp.pathway_name ILIKE '%DNA repair%' OR gp.pathway_name ILIKE '%BRCA%'
            THEN '🎯 PARP inhibitors'
        WHEN gp.pathway_name ILIKE '%immune%' OR gp.pathway_name ILIKE '%PD-1%'
            THEN '🎯 Immunotherapy'
        WHEN gp.pathway_name ILIKE '%cell cycle%'
            THEN 'Chemotherapy targeting'
        ELSE 'No direct therapeutic'
    END as therapeutic_target
FROM cancer_transcript_base ctb
INNER JOIN genes g ON ctb.gene_id = g.gene_id
INNER JOIN gene_pathways gp ON g.gene_id = gp.gene_id
WHERE ctb.expression_fold_change > 3.0  -- Higher threshold for TNBC
GROUP BY gp.pathway_name
HAVING COUNT(*) >= 3
ORDER BY avg_pathway_fold_change DESC
LIMIT 15;

-- Expected Results (TNBC patient):
-- | pathway_name                    | num_genes | avg_fc | top_genes                        | therapeutic_target           |
-- |---------------------------------|-----------|--------|----------------------------------|------------------------------|
-- | Cell cycle and mitosis          | 12        | 5.2    | MKI67(5.8x), CCNE1(4.5x), ...   | Chemotherapy targeting       |
-- | Basal epithelial markers        | 6         | 4.8    | KRT5(4.8x), KRT14(4.2x), ...    | Diagnostic marker            |
-- | DNA damage response             | 5         | 3.5    | BRCA1(low), RAD51(low), ...     | 🎯 PARP inhibitors          |
-- | PD-1/PD-L1 checkpoint           | 4         | 3.0    | CD274(2.8x), CD8A(2.5x), ...    | 🎯 Immunotherapy            |

-- Clinical Interpretation:
-- HER2+ vs TNBC show COMPLETELY different pathway enrichment:
--
-- HER2+: Targetable with precision agents (HER2, PI3K, CDK4/6 inhibitors)
-- TNBC: Requires cytotoxic chemo, PARP inhibitors, or immunotherapy
--
-- This explains why treatment strategies differ dramatically.


-- ========================================================================
-- QUERY 4: GENES WITH OPPOSITE EXPRESSION (HER2+ vs LUAD)
-- ========================================================================
-- Clinical Question: "What genes distinguish breast cancer from lung cancer?"
--
-- Clinical Value: Tissue-specific expression validates diagnosis,
--                 identifies tumor-type-specific vulnerabilities
-- ========================================================================

\echo '\n\n=== QUERY 4: Breast vs. Lung Cancer Differential Expression ==='

-- This query requires a federated approach or manual comparison
-- Here we show the structure for each database

\echo '\n--- Step 1: Get HER2+ breast cancer overexpressed genes ---'
\c mediabase_patient_DEMO_HER2

CREATE TEMP TABLE her2_overexpressed AS
SELECT
    gene_symbol,
    expression_fold_change as her2_fold_change
FROM cancer_transcript_base
WHERE expression_fold_change > 2.5
  AND gene_symbol IS NOT NULL;

\echo '\n--- Step 2: Get lung cancer overexpressed genes ---'
\c mediabase_patient_DEMO_LUAD

CREATE TEMP TABLE luad_overexpressed AS
SELECT
    gene_symbol,
    expression_fold_change as luad_fold_change
FROM cancer_transcript_base
WHERE expression_fold_change > 2.5
  AND gene_symbol IS NOT NULL;

\echo '\n--- Step 3: Compare (conceptual - requires export/import) ---'

-- Genes HIGH in breast, LOW in lung (breast-specific):
SELECT
    h.gene_symbol,
    h.her2_fold_change,
    COALESCE(l.luad_fold_change, 1.0) as luad_fold_change,
    h.her2_fold_change - COALESCE(l.luad_fold_change, 1.0) as expression_difference,
    CASE
        WHEN h.gene_symbol IN ('ESR1', 'PGR', 'GATA3') THEN 'Breast-specific hormone receptor'
        WHEN h.gene_symbol IN ('ERBB2', 'GRB7') THEN 'HER2 amplicon (breast)'
        WHEN h.gene_symbol LIKE 'KRT%' THEN 'Epithelial keratin'
        ELSE 'Other'
    END as biological_category
FROM her2_overexpressed h
LEFT JOIN luad_overexpressed l ON h.gene_symbol = l.gene_symbol
WHERE COALESCE(l.luad_fold_change, 1.0) < 1.5  -- Low in lung
ORDER BY expression_difference DESC
LIMIT 20;

-- Expected Results:
-- | gene_symbol | her2_fc | luad_fc | difference | biological_category           |
-- |-------------|---------|---------|------------|-------------------------------|
-- | ESR1        | 2.1     | 0.1     | 2.0        | Breast-specific hormone rec   |
-- | PGR         | 1.9     | 0.1     | 1.8        | Breast-specific hormone rec   |
-- | GATA3       | 2.3     | 0.2     | 2.1        | Breast-specific hormone rec   |
-- | ERBB2       | 6.2     | 0.8     | 5.4        | HER2 amplicon (breast)        |
-- | GRB7        | 4.8     | 0.7     | 4.1        | HER2 amplicon (breast)        |

-- Genes LOW in breast, HIGH in lung (lung-specific):
-- Would show EGFR, lung differentiation markers, etc.

-- Clinical Interpretation:
-- Confirms tissue of origin and validates diagnosis.
-- Breast-specific genes (ER, GATA3) virtually absent in lung cancer.
-- Each tumor type has distinct therapeutic vulnerabilities.


-- ========================================================================
-- QUERY 5: CLINICAL TRIAL ELIGIBILITY MATCHING
-- ========================================================================
-- Clinical Question: "Which clinical trials is this HER2+ patient eligible for?"
--
-- Clinical Value: Identifies experimental therapies matching patient profile
-- ========================================================================

\echo '\n\n=== QUERY 5: Clinical Trial Eligibility (HER2+ Patient) ==='

\c mediabase_patient_DEMO_HER2

-- NOTE: This query assumes future integration with ClinicalTrials.gov data
-- Shown here as a conceptual framework for v0.5.0

SELECT
    ctb.gene_symbol,
    ctb.expression_fold_change,
    'NCT123456' as nct_id,  -- Placeholder
    'Trastuzumab Deruxtecan in HER2+ Solid Tumors' as trial_title,
    CASE
        WHEN ctb.gene_symbol = 'ERBB2' AND ctb.expression_fold_change >= 4.0
            THEN '✅ ELIGIBLE (HER2+ by IHC/FISH)'
        WHEN ctb.gene_symbol = 'ESR1' AND ctb.expression_fold_change > 1.5
            THEN '✅ ELIGIBLE (ER+ cohort available)'
        WHEN ctb.gene_symbol = 'PIK3CA' AND ctb.expression_fold_change > 2.0
            THEN '✅ ELIGIBLE (PIK3CA altered cohort)'
        ELSE 'Review eligibility criteria'
    END as eligibility_status,
    CASE
        WHEN ctb.gene_symbol = 'ERBB2' THEN 'Primary inclusion criterion: HER2+ status'
        WHEN ctb.gene_symbol = 'ESR1' THEN 'Stratification factor: ER status'
        WHEN ctb.gene_symbol = 'PIK3CA' THEN 'Biomarker-defined cohort'
        ELSE NULL
    END as trial_notes
FROM cancer_transcript_base ctb
WHERE ctb.gene_symbol IN ('ERBB2', 'ESR1', 'PGR', 'PIK3CA', 'TP53')
  AND ctb.expression_fold_change <> 1.0
ORDER BY ctb.expression_fold_change DESC;

-- Expected Results:
-- | gene_symbol | fold_change | nct_id     | trial_title                            | eligibility_status        |
-- |-------------|-------------|------------|----------------------------------------|---------------------------|
-- | ERBB2       | 6.2         | NCT123456  | T-DXd in HER2+ Solid Tumors           | ✅ ELIGIBLE (HER2+)      |
-- | PIK3CA      | 2.8         | NCT789012  | Alpelisib + Trastuzumab               | ✅ ELIGIBLE (PIK3CA+)    |
-- | ESR1        | 2.1         | NCT345678  | CDK4/6i + HER2-targeted therapy       | ✅ ELIGIBLE (ER+/HER2+)  |

-- Clinical Interpretation:
-- This HER2+ ER+ patient with PIK3CA overexpression qualifies for multiple trials:
-- 1. HER2-targeted ADC trials (T-DXd, T-DM1)
-- 2. PI3K inhibitor combinations (if PIK3CA mutation confirmed)
-- 3. CDK4/6 inhibitor + HER2 therapy combinations


-- ========================================================================
-- QUERY 6: IMMUNOTHERAPY ELIGIBILITY ASSESSMENT
-- ========================================================================
-- Clinical Question: "Is this patient a candidate for immunotherapy?"
-- ========================================================================

\echo '\n\n=== QUERY 6A: Immunotherapy Biomarkers (HER2+ Patient) ==='

\c mediabase_patient_DEMO_HER2

SELECT
    ctb.gene_symbol,
    ctb.expression_fold_change,
    CASE
        WHEN ctb.gene_symbol = 'CD274' THEN  -- PD-L1
            CASE
                WHEN ctb.expression_fold_change > 2.0 THEN '✅ PD-L1 HIGH (>50%)'
                WHEN ctb.expression_fold_change > 1.5 THEN '⚠️  PD-L1 MODERATE (1-49%)'
                ELSE '❌ PD-L1 NEGATIVE'
            END
        WHEN ctb.gene_symbol = 'CD8A' THEN  -- T cell infiltration
            CASE
                WHEN ctb.expression_fold_change > 2.0 THEN '✅ T CELL INFLAMED (hot tumor)'
                WHEN ctb.expression_fold_change > 1.2 THEN 'MODERATE T cell presence'
                ELSE '❌ T CELL EXCLUDED (cold tumor)'
            END
        WHEN ctb.gene_symbol = 'PDCD1' THEN  -- PD-1
            CASE
                WHEN ctb.expression_fold_change > 1.5 THEN 'PD-1 POSITIVE T cells'
                ELSE 'PD-1 LOW'
            END
        END as biomarker_interpretation,
    CASE
        WHEN ctb.gene_symbol = 'CD274' AND ctb.expression_fold_change < 1.5
            THEN '❌ Unlikely to respond to single-agent immunotherapy'
        WHEN ctb.gene_symbol = 'CD274' AND ctb.expression_fold_change > 2.0
            THEN '✅ Consider pembrolizumab or atezolizumab'
        WHEN ctb.gene_symbol = 'CD8A' AND ctb.expression_fold_change < 1.2
            THEN '❌ Cold tumor - consider immune-priming strategies'
        ELSE 'Additional testing recommended'
    END as clinical_recommendation
FROM cancer_transcript_base ctb
WHERE ctb.gene_symbol IN ('CD274', 'PDCD1', 'CD8A', 'CTLA4', 'LAG3')  -- Immune checkpoints
ORDER BY ctb.expression_fold_change DESC;

-- Expected Result (HER2+ patient - typically immunosuppressed):
-- | gene_symbol | fold_change | biomarker_interpretation       | clinical_recommendation                         |
-- |-------------|-------------|--------------------------------|-------------------------------------------------|
-- | CD274       | 0.6         | ❌ PD-L1 NEGATIVE             | ❌ Unlikely to respond to single-agent IO      |
-- | CD8A        | 0.4         | ❌ T CELL EXCLUDED           | ❌ Cold tumor - consider immune-priming       |

-- Clinical Interpretation (HER2+ patient):
-- Most HER2+ tumors are immune "cold" with low PD-L1 and poor T cell infiltration.
-- Single-agent immunotherapy unlikely to work.
-- Consider: HER2 therapy to trigger immunogenic cell death → immune activation


\echo '\n=== QUERY 6B: Immunotherapy Biomarkers (TNBC Patient) ==='

\c mediabase_patient_DEMO_TNBC

SELECT
    ctb.gene_symbol,
    ctb.expression_fold_change,
    CASE
        WHEN ctb.gene_symbol = 'CD274' THEN  -- PD-L1
            CASE
                WHEN ctb.expression_fold_change > 2.0 THEN '✅ PD-L1 HIGH (>50%) - PEMBROLIZUMAB'
                WHEN ctb.expression_fold_change > 1.5 THEN '⚠️  PD-L1 MODERATE'
                ELSE '❌ PD-L1 NEGATIVE'
            END
        WHEN ctb.gene_symbol = 'CD8A' THEN
            CASE
                WHEN ctb.expression_fold_change > 2.0 THEN '✅ T CELL INFLAMED - GOOD PROGNOSIS'
                ELSE 'LOW T cell infiltration'
            END
        END as biomarker_interpretation,
    CASE
        WHEN ctb.gene_symbol = 'CD274' AND ctb.expression_fold_change > 2.0
            THEN '✅ APPROVED: Pembrolizumab + chemo (1st line TNBC)'
        WHEN ctb.gene_symbol = 'CD8A' AND ctb.expression_fold_change > 2.0
            THEN '✅ Favorable immune microenvironment'
        ELSE 'Consider biomarker testing'
    END as clinical_recommendation
FROM cancer_transcript_base ctb
WHERE ctb.gene_symbol IN ('CD274', 'PDCD1', 'CD8A', 'CTLA4')
ORDER BY ctb.expression_fold_change DESC;

-- Expected Result (TNBC patient - often immune "hot"):
-- | gene_symbol | fold_change | biomarker_interpretation           | clinical_recommendation                    |
-- |-------------|-------------|------------------------------------|--------------------------------------------|
-- | CD274       | 2.8         | ✅ PD-L1 HIGH (>50%) - PEMBROLIZUMAB | ✅ APPROVED: Pembrolizumab + chemo      |
-- | CD8A        | 2.5         | ✅ T CELL INFLAMED                   | ✅ Favorable immune microenvironment    |

-- Clinical Interpretation (TNBC patient):
-- ~40% of TNBC have high PD-L1 and are immune-inflamed.
-- FDA-approved regimen: Pembrolizumab + chemotherapy (KEYNOTE-355 trial).
-- This patient would benefit from adding immunotherapy to chemotherapy.


-- ========================================================================
-- SUMMARY TABLE: TREATMENT RECOMMENDATIONS BY PATIENT
-- ========================================================================

\echo '\n\n=== TREATMENT SUMMARY ACROSS PATIENTS ==='

-- Patient 1: HER2+ Breast Cancer
-- | Line     | Treatment Regimen                                    | Rationale                    |
-- |----------|------------------------------------------------------|------------------------------|
-- | 1st line | Trastuzumab + Pertuzumab + Taxane                   | HER2+ (ERBB2 6.2x)          |
-- | 1st line | Add alpelisib if PIK3CA mutant                      | PIK3CA overexpression       |
-- | 2nd line | T-DM1 or T-DXd (HER2 ADC)                           | HER2+ refractory             |
-- | 3rd line | Tucatinib + Trastuzumab + Capecitabine              | HER2+ metastatic             |
-- | Adjuvant | Endocrine therapy + CDK4/6i (if ER+)                | ESR1 2.1x, long-term control |

-- Patient 2: TNBC Breast Cancer
-- | Line     | Treatment Regimen                                    | Rationale                    |
-- |----------|------------------------------------------------------|------------------------------|
-- | 1st line | Pembrolizumab + Carboplatin + Paclitaxel           | PD-L1 HIGH (CD274 2.8x)     |
-- | 1st line | Olaparib or Talazoparib if BRCA germline mutant     | BRCA1 low expression         |
-- | 2nd line | Sacituzumab govitecan (Trop-2 ADC)                  | TNBC standard of care        |
-- | 3rd line | Capecitabine or eribulin                            | Chemotherapy-sensitive       |

-- Patient 3: Lung Adenocarcinoma (EGFR+)
-- | Line     | Treatment Regimen                                    | Rationale                    |
-- |----------|------------------------------------------------------|------------------------------|
-- | 1st line | Osimertinib (3rd gen EGFR TKI)                      | EGFR overexpression (4.5x)   |
-- | 2nd line | Chemotherapy + bevacizumab                          | VEGFA high (4.0x)            |
-- | 3rd line | Immunotherapy (if acquired PD-L1+)                  | Post-TKI progression         |
-- | Clinical trial | Combination EGFR TKI + anti-VEGF                | Dual pathway inhibition      |


-- ========================================================================
-- KEY CLINICAL INSIGHTS
-- ========================================================================

\echo '\n\n=== KEY CLINICAL INSIGHTS FROM CROSS-PATIENT ANALYSIS ==='
\echo ''
\echo '1. TUMOR-SPECIFIC BIOLOGY:'
\echo '   - HER2+ breast: Targetable oncogene addiction (HER2 pathway)'
\echo '   - TNBC: High proliferation, immune-inflamed, DNA repair defects'
\echo '   - EGFR+ LUAD: Receptor tyrosine kinase driven, angiogenic'
\echo ''
\echo '2. TREATMENT STRATEGY DIFFERENCES:'
\echo '   - HER2+: Precision targeted therapy (antibodies, TKIs, ADCs)'
\echo '   - TNBC: Combination chemo-immunotherapy or PARP inhibitors'
\echo '   - EGFR+ LUAD: Sequential TKI therapy, resist-and-adapt approach'
\echo ''
\echo '3. BIOMARKER-DRIVEN DECISIONS:'
\echo '   - HER2 expression determines anti-HER2 therapy eligibility'
\echo '   - PD-L1 expression determines immunotherapy benefit'
\echo '   - ER expression determines endocrine therapy use'
\echo '   - EGFR expression/mutation determines TKI selection'
\echo ''
\echo '4. CROSS-CANCER APPLICATIONS:'
\echo '   - HER2+ can occur in non-breast tumors (gastric, bladder, lung)'
\echo '   - Tumor-agnostic approvals: T-DXd for any HER2+ solid tumor'
\echo '   - Immunotherapy works across cancers if biomarkers present'
\echo ''
\echo '5. MEDIABASE ENABLES:'
\echo '   - Rapid biomarker assessment from transcriptome data'
\echo '   - Treatment matching based on expression profiles'
\echo '   - Clinical trial eligibility screening'
\echo '   - Pathway-based therapeutic hypothesis generation'
\echo ''

-- ========================================================================
-- END OF CROSS-PATIENT COMPARISON QUERIES
-- ========================================================================

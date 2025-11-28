/*******************************************************************************
 * TRIPLE-NEGATIVE BREAST CANCER (TNBC) QUERY GUIDE
 * MEDIABASE v0.6.0
 *
 * Clinical Context:
 * ----------------
 * TNBC represents 15-20% of breast cancers and is defined by:
 * - Absence of ER, PR, and HER2 expression (triple-negative)
 * - Enrichment for basal-like molecular subtype
 * - High proliferation rates and early metastatic potential
 * - Limited targeted therapy options (chemotherapy remains backbone)
 * - High frequency of TP53 mutations (~80%)
 * - Potential for immunotherapy and PARP inhibitors
 *
 * This guide provides SQL queries to:
 * 1. Confirm triple-negative status (ER-, PR-, HER2-)
 * 2. Assess PARP inhibitor eligibility (BRCA1/2 deficiency)
 * 3. Evaluate immune checkpoint inhibitor eligibility (PD-L1 status)
 * 4. Identify targetable genomic alterations (PI3K, AKT, EGFR)
 * 5. Find supporting scientific publications
 *
 * References:
 * ----------
 * - Foulkes et al. N Engl J Med 2010 (TNBC molecular characterization)
 * - Robson et al. N Engl J Med 2017 (Olaparib in BRCA-mutant breast cancer)
 * - Schmid et al. N Engl J Med 2018 (IMpassion130 - Atezolizumab in TNBC)
 * - Cortes et al. N Engl J Med 2020 (Sacituzumab govitecan approval)
 ******************************************************************************/

-- Set patient schema name (MODIFY THIS)
\set PATIENT_SCHEMA 'patient_synthetic_tnbc'

\echo '====================================================================='
\echo 'TRIPLE-NEGATIVE BREAST CANCER (TNBC) THERAPEUTIC ANALYSIS'
\echo '====================================================================='
\echo ''

/*******************************************************************************
 * QUERY 1: Confirm Triple-Negative Status
 *
 * Purpose:
 * --------
 * - Verify absence of ER (ESR1), PR (PGR), and HER2 (ERBB2)
 * - Confirm basal-like markers (KRT5, KRT14, KRT17, EGFR)
 *
 * Clinical Interpretation:
 * -----------------------
 * - ESR1 <0.5x AND PGR <0.5x AND ERBB2 <2.0x: Triple-negative confirmed
 * - KRT5, KRT14, KRT17 overexpression: Basal-like subtype
 * - EGFR overexpression common in TNBC (not therapeutic target)
 ******************************************************************************/

\echo '---------------------------------------------------------------------'
\echo 'Query 1: Triple-Negative Status Confirmation'
\echo '---------------------------------------------------------------------'

SELECT
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    CASE
        WHEN g.gene_symbol IN ('ESR1', 'PGR') AND COALESCE(pe.expression_fold_change, 1.0) < 0.5
            THEN '✓ NEGATIVE (Triple-Negative Confirmed)'
        WHEN g.gene_symbol = 'ERBB2' AND COALESCE(pe.expression_fold_change, 1.0) < 2.0
            THEN '✓ HER2 NEGATIVE (Triple-Negative Confirmed)'
        WHEN g.gene_symbol IN ('KRT5', 'KRT14', 'KRT17') AND COALESCE(pe.expression_fold_change, 1.0) > 3.0
            THEN '✓ BASAL MARKER POSITIVE (Basal-like subtype)'
        WHEN g.gene_symbol = 'EGFR' AND COALESCE(pe.expression_fold_change, 1.0) > 3.0
            THEN '📊 BASAL EGFR EXPRESSION (Common in TNBC, not targetable)'
        WHEN g.gene_symbol IN ('ESR1', 'PGR', 'ERBB2') AND COALESCE(pe.expression_fold_change, 1.0) >= 2.0
            THEN '⚠️  POSITIVE - NOT TNBC'
        ELSE '📊 Monitor'
    END as tnbc_classification
FROM public.genes g
LEFT JOIN patient_synthetic_tnbc.expression_data pe
    ON g.gene_id = pe.gene_id
WHERE g.gene_symbol IN (
    'ESR1', 'PGR', 'ERBB2',  -- Triple-negative markers
    'KRT5', 'KRT14', 'KRT17',  -- Basal markers
    'EGFR'  -- Basal EGFR
)
ORDER BY COALESCE(pe.expression_fold_change, 1.0) DESC;

\echo ''

/*******************************************************************************
 * QUERY 2: PARP Inhibitor Eligibility Assessment
 *
 * Purpose:
 * --------
 * - Assess BRCA1/BRCA2 and DNA repair pathway status
 * - BRCA1/2 deficiency → synthetic lethality with PARP inhibition
 * - ~20% of TNBC have germline or somatic BRCA1/2 mutations
 *
 * Clinical Decision Support:
 * -------------------------
 * FDA-approved PARP inhibitors for BRCA-mutant breast cancer:
 * - Olaparib (Lynparza): First-line for metastatic BRCA-mutant HER2- breast cancer
 * - Talazoparib (Talzenna): First-line for metastatic BRCA-mutant HER2- breast cancer
 *
 * Interpretation:
 * --------------
 * - BRCA1 <0.5x OR BRCA2 <0.5x: PARP inhibitor eligible (confirm germline testing)
 * - RAD51 <0.5x: HR deficiency marker → potential PARP sensitivity
 * - High MKI67: Aggressive disease → early PARP inhibitor consideration
 ******************************************************************************/

\echo '---------------------------------------------------------------------'
\echo 'Query 2: PARP Inhibitor Eligibility (BRCA1/2 Deficiency)'
\echo '---------------------------------------------------------------------'

SELECT
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    CASE
        WHEN g.gene_symbol IN ('BRCA1', 'BRCA2') AND COALESCE(pe.expression_fold_change, 1.0) < 0.5
            THEN '🎯 PARP INHIBITOR ELIGIBLE (Olaparib, Talazoparib)'
        WHEN g.gene_symbol = 'RAD51' AND COALESCE(pe.expression_fold_change, 1.0) < 0.5
            THEN '🟡 HR DEFICIENCY MARKER (potential PARP sensitivity)'
        WHEN g.gene_symbol = 'PALB2' AND COALESCE(pe.expression_fold_change, 1.0) < 0.5
            THEN '🟡 PALB2 DEFICIENCY (PARP inhibitor eligible)'
        WHEN g.gene_symbol IN ('BRCA1', 'BRCA2', 'RAD51', 'PALB2')
            THEN '📊 NORMAL EXPRESSION (PARP inhibitor not indicated)'
        ELSE '📊 Monitor'
    END as parp_eligibility,
    'Confirm with germline testing' as recommendation
FROM public.genes g
LEFT JOIN patient_synthetic_tnbc.expression_data pe
    ON g.gene_id = pe.gene_id
WHERE g.gene_symbol IN (
    'BRCA1', 'BRCA2',  -- Main PARP targets
    'RAD51', 'PALB2',  -- HR deficiency markers
    'ATM', 'CHEK2'     -- Additional DDR genes
)
ORDER BY COALESCE(pe.expression_fold_change, 1.0) ASC;

\echo ''

/*******************************************************************************
 * QUERY 3: Immune Checkpoint Inhibitor Eligibility
 *
 * Purpose:
 * --------
 * - Assess PD-L1 (CD274) expression for pembrolizumab eligibility
 * - Evaluate immune infiltration markers (CD8A, PDCD1)
 * - TNBC has higher immune infiltration than ER+ breast cancer
 *
 * Clinical Context:
 * ----------------
 * FDA-approved immunotherapy for TNBC:
 * - Pembrolizumab (Keytruda) + chemotherapy: First-line for PD-L1+ metastatic TNBC
 * - Atezolizumab (Tecentriq) + nab-paclitaxel: First-line for PD-L1+ metastatic TNBC
 *
 * PD-L1 Scoring:
 * -------------
 * - CPS ≥10 (Combined Positive Score): Strong pembrolizumab benefit
 * - CPS 1-9: Moderate benefit
 * - CPS <1: Limited benefit (chemotherapy alone)
 ******************************************************************************/

\echo '---------------------------------------------------------------------'
\echo 'Query 3: Immune Checkpoint Inhibitor Eligibility'
\echo '---------------------------------------------------------------------'

SELECT
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    CASE
        WHEN g.gene_symbol = 'CD274' AND COALESCE(pe.expression_fold_change, 1.0) > 3.0
            THEN '🎯 PD-L1 HIGH → PEMBROLIZUMAB + CHEMOTHERAPY (First-line)'
        WHEN g.gene_symbol = 'CD274' AND COALESCE(pe.expression_fold_change, 1.0) BETWEEN 1.5 AND 3.0
            THEN '🟡 PD-L1 MODERATE → Consider pembrolizumab'
        WHEN g.gene_symbol = 'CD274' AND COALESCE(pe.expression_fold_change, 1.0) < 1.5
            THEN '📊 PD-L1 LOW → Chemotherapy alone preferred'
        WHEN g.gene_symbol = 'CD8A' AND COALESCE(pe.expression_fold_change, 1.0) > 2.0
            THEN '✓ T CELL INFILTRATION (Immune-active tumor)'
        WHEN g.gene_symbol = 'PDCD1' AND COALESCE(pe.expression_fold_change, 1.0) > 1.5
            THEN '✓ PD-1 EXPRESSION (Immune checkpoint activated)'
        ELSE '📊 Monitor'
    END as immunotherapy_strategy
FROM public.genes g
LEFT JOIN patient_synthetic_tnbc.expression_data pe
    ON g.gene_id = pe.gene_id
WHERE g.gene_symbol IN (
    'CD274',  -- PD-L1
    'PDCD1',  -- PD-1
    'CD8A',   -- T cell marker
    'CTLA4',  -- Alternative checkpoint
    'LAG3'    -- Emerging checkpoint
)
ORDER BY COALESCE(pe.expression_fold_change, 1.0) DESC;

\echo ''

/*******************************************************************************
 * QUERY 4: Targetable Genomic Alterations (Emerging Therapies)
 *
 * Purpose:
 * --------
 * - Identify potentially targetable pathways in TNBC
 * - PI3K/AKT pathway activation (~10% of TNBC)
 * - AKT1 mutations (~3% of TNBC)
 * - Androgen receptor expression (LAR subtype, ~10-15% of TNBC)
 *
 * Emerging Targeted Therapies:
 * ---------------------------
 * - Capivasertib (AKT inhibitor): Phase III CAPItello-291 trial
 * - Alpelisib (PI3K inhibitor): Clinical trials in PIK3CA-mutant TNBC
 * - Enzalutamide (AR antagonist): Clinical trials in AR+ TNBC
 * - Sacituzumab govitecan (Trodelvy): FDA-approved ADC for metastatic TNBC
 ******************************************************************************/

\echo '---------------------------------------------------------------------'
\echo 'Query 4: Targetable Genomic Alterations (Clinical Trials)'
\echo '---------------------------------------------------------------------'

SELECT
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    CASE
        WHEN g.gene_symbol = 'PIK3CA' AND COALESCE(pe.expression_fold_change, 1.0) > 3.0
            THEN '🎯 PI3K INHIBITOR TARGET (Alpelisib - Clinical Trial)'
        WHEN g.gene_symbol = 'AKT1' AND COALESCE(pe.expression_fold_change, 1.0) > 3.0
            THEN '🎯 AKT INHIBITOR TARGET (Capivasertib - Clinical Trial)'
        WHEN g.gene_symbol = 'AR' AND COALESCE(pe.expression_fold_change, 1.0) > 2.0
            THEN '🎯 LAR SUBTYPE → ENZALUTAMIDE (Clinical Trial)'
        WHEN g.gene_symbol = 'TROP2' AND COALESCE(pe.expression_fold_change, 1.0) > 2.0
            THEN '🎯 TROP2+ → SACITUZUMAB GOVITECAN (FDA-Approved ADC)'
        WHEN g.gene_symbol IN ('CDK1', 'CCNE1') AND COALESCE(pe.expression_fold_change, 1.0) > 4.0
            THEN '📊 HIGH PROLIFERATION → Dose-dense chemotherapy'
        ELSE '📊 Monitor'
    END as therapeutic_opportunity
FROM public.genes g
LEFT JOIN patient_synthetic_tnbc.expression_data pe
    ON g.gene_id = pe.gene_id
WHERE g.gene_symbol IN (
    'PIK3CA', 'AKT1', 'AKT2', 'MTOR',  -- PI3K/AKT pathway
    'AR',  -- Androgen receptor (LAR subtype)
    'TROP2',  -- Sacituzumab govitecan target
    'CDK1', 'CCNE1', 'MKI67'  -- Proliferation markers
)
ORDER BY COALESCE(pe.expression_fold_change, 1.0) DESC;

\echo ''

/*******************************************************************************
 * QUERY 5: Comprehensive Treatment Recommendation Summary
 *
 * Purpose:
 * --------
 * - Integrate all findings into prioritized treatment options
 * - Consider TNBC subtype (Basal-like, LAR, Mesenchymal, Immunogenic)
 ******************************************************************************/

\echo '---------------------------------------------------------------------'
\echo 'Query 5: Comprehensive TNBC Treatment Recommendations'
\echo '---------------------------------------------------------------------'

WITH patient_profile AS (
    SELECT
        MAX(CASE WHEN g.gene_symbol = 'CD274' THEN COALESCE(pe.expression_fold_change, 1.0) END) as pdl1_fc,
        MAX(CASE WHEN g.gene_symbol = 'BRCA1' THEN COALESCE(pe.expression_fold_change, 1.0) END) as brca1_fc,
        MAX(CASE WHEN g.gene_symbol = 'PIK3CA' THEN COALESCE(pe.expression_fold_change, 1.0) END) as pik3ca_fc,
        MAX(CASE WHEN g.gene_symbol = 'AR' THEN COALESCE(pe.expression_fold_change, 1.0) END) as ar_fc
    FROM public.genes g
    LEFT JOIN patient_synthetic_tnbc.expression_data pe
        ON g.gene_id = pe.gene_id
    WHERE g.gene_symbol IN ('CD274', 'BRCA1', 'PIK3CA', 'AR')
)
SELECT
    CASE
        WHEN pp.brca1_fc < 0.5
            THEN '1. PARP INHIBITOR (Olaparib/Talazoparib) - FDA Approved'
        WHEN pp.pdl1_fc > 2.0
            THEN '1. PEMBROLIZUMAB + CHEMOTHERAPY (PD-L1 positive) - FDA Approved'
        WHEN pp.ar_fc > 2.0
            THEN '1. ENZALUTAMIDE + CHEMOTHERAPY (LAR subtype) - Clinical Trial'
        ELSE '1. CHEMOTHERAPY (Anthracycline + Taxane) - Standard of Care'
    END as first_line_recommendation,
    CASE
        WHEN pp.brca1_fc >= 0.5 AND pp.pdl1_fc > 2.0
            THEN '2. PEMBROLIZUMAB + CHEMOTHERAPY (Immune-active TNBC)'
        WHEN pp.pik3ca_fc > 3.0
            THEN '2. ALPELISIB + CHEMOTHERAPY (PIK3CA-mutant) - Clinical Trial'
        ELSE '2. SACITUZUMAB GOVITECAN (Trodelvy) - FDA Approved for metastatic'
    END as second_line_recommendation,
    CASE
        WHEN pp.brca1_fc < 0.5 OR pp.pdl1_fc > 2.0
            THEN 'FDA Approved'
        ELSE 'Clinical Trial / Standard Chemotherapy'
    END as evidence_level
FROM patient_profile pp;

\echo ''

/*******************************************************************************
 * QUERY 6: Find Supporting Publications
 ******************************************************************************/

\echo '---------------------------------------------------------------------'
\echo 'Query 6: Supporting Publications (TNBC Research)'
\echo '---------------------------------------------------------------------'

SELECT
    g.gene_symbol,
    gp.pmid,
    gp.mention_count,
    pm.publication_year,
    LEFT(pm.abstract, 200) || '...' as abstract_preview
FROM public.genes g
INNER JOIN public.gene_publications gp
    ON g.gene_id = gp.gene_id
LEFT JOIN public.pubmed_metadata pm
    ON gp.pmid = pm.pmid
WHERE g.gene_symbol IN ('BRCA1', 'CD274', 'PIK3CA', 'AR', 'TROP2')
  AND pm.publication_year >= 2019
ORDER BY gp.mention_count DESC, pm.publication_year DESC
LIMIT 10;

\echo ''
\echo '====================================================================='
\echo 'ANALYSIS COMPLETE'
\echo ''
\echo 'Next Steps:'
\echo '1. Confirm triple-negative status (ER-, PR-, HER2-)'
\echo '2. Consider germline BRCA testing if BRCA1/2 underexpressed'
\echo '3. Assess PD-L1 status for immunotherapy eligibility'
\echo '4. Discuss clinical trial options for targeted therapies'
\echo '5. Consider neoadjuvant chemotherapy for early-stage disease'
\echo ''
\echo 'Key Clinical Trials:'
\echo '- KEYNOTE-355 (Pembrolizumab + chemotherapy)'
\echo '- OlympiAD (Olaparib in BRCA-mutant breast cancer)'
\echo '- CAPItello-291 (Capivasertib in AKT-pathway altered TNBC)'
\echo '====================================================================='

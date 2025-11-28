/*******************************************************************************
 * COLORECTAL CANCER (CRC) QUERY GUIDE
 * MEDIABASE v0.6.0
 *
 * Clinical Context:
 * ----------------
 * Colorectal cancer treatment is highly stratified by molecular features:
 * - KRAS/NRAS/BRAF mutation status (anti-EGFR therapy eligibility)
 * - MSI-H/dMMR status (immunotherapy response predictor)
 * - HER2 amplification (~5% of CRC, emerging target)
 * - Left vs. right-sided primary (prognostic and predictive)
 *
 * This guide provides SQL queries to:
 * 1. Assess KRAS/BRAF status for anti-EGFR therapy eligibility
 * 2. Evaluate MSI-H/dMMR markers for immunotherapy
 * 3. Identify VEGF pathway activation for bevacizumab
 * 4. Assess HER2 amplification status (emerging target)
 * 5. Find supporting scientific publications
 *
 * FDA-Approved Targeted Therapies:
 * -------------------------------
 * **Anti-EGFR** (RAS/BRAF wild-type only):
 * - Cetuximab (Erbitux): First-line + chemotherapy (left-sided preferred)
 * - Panitumumab (Vectibix): First-line + chemotherapy (left-sided preferred)
 *
 * **Anti-VEGF**:
 * - Bevacizumab (Avastin): First-line + chemotherapy (all subtypes)
 * - Ramucirumab (Cyramza): Second-line + FOLFIRI
 *
 * **BRAF V600E mutant**:
 * - Encorafenib + Cetuximab (+/- Binimetinib): FDA-approved for BRAF V600E
 *
 * **MSI-H/dMMR**:
 * - Pembrolizumab (Keytruda): First-line monotherapy
 * - Nivolumab (Opdivo): Second-line monotherapy or + Ipilimumab
 *
 * References:
 * ----------
 * - Douillard et al. N Engl J Med 2013 (Panitumumab + FOLFOX4)
 * - Van Cutsem et al. N Engl J Med 2009 (Cetuximab + chemotherapy)
 * - Le et al. N Engl J Med 2015 (PD-1 blockade in MSI-H CRC)
 * - Kopetz et al. N Engl J Med 2019 (Encorafenib + Cetuximab in BRAF V600E)
 ******************************************************************************/

-- Set patient schema name (MODIFY THIS - replace with your patient schema)
-- \set PATIENT_SCHEMA 'patient_YOUR_CRC_PATIENT_ID'

\echo '====================================================================='
\echo 'COLORECTAL CANCER THERAPEUTIC ANALYSIS'
\echo '====================================================================='
\echo ''

/*******************************************************************************
 * QUERY 1: KRAS/BRAF Mutation Status (Anti-EGFR Therapy Eligibility)
 *
 * Purpose:
 * --------
 * - Assess KRAS, NRAS, BRAF expression as surrogate for mutation status
 * - Determine anti-EGFR therapy (cetuximab, panitumumab) eligibility
 * - CRITICAL: RNA expression is NOT definitive for mutation status
 *
 * Clinical Interpretation:
 * -----------------------
 * **Anti-EGFR Therapy Requirements:**
 * - KRAS wild-type (codons 12, 13, 61, 117, 146)
 * - NRAS wild-type (codons 12, 13, 61)
 * - BRAF wild-type (codon 600)
 * - Left-sided primary (better response than right-sided)
 *
 * **IMPORTANT**: MUST confirm wild-type status by DNA sequencing!
 * RNA overexpression does NOT indicate mutation.
 *
 * **If BRAF V600E mutant**: Use Encorafenib + Cetuximab (FDA-approved)
 ******************************************************************************/

\echo '---------------------------------------------------------------------'
\echo 'Query 1: KRAS/BRAF Status for Anti-EGFR Therapy Eligibility'
\echo '---------------------------------------------------------------------'
\echo 'NOTE: This query uses public schema (no patient-specific data)'
\echo 'Modify to include patient expression data if available'
\echo ''

-- This query shows genes relevant to anti-EGFR therapy from public schema
-- Oncologists should substitute with their patient schema

SELECT
    g.gene_symbol,
    '1.0' as baseline_fold_change,  -- Placeholder: replace with patient data
    CASE
        WHEN g.gene_symbol = 'EGFR'
            THEN '🎯 EGFR TARGET - Requires KRAS/NRAS/BRAF wild-type confirmation'
        WHEN g.gene_symbol IN ('KRAS', 'NRAS')
            THEN '⚠️  RAS GENES - Mutation EXCLUDES anti-EGFR therapy (DNA sequencing required)'
        WHEN g.gene_symbol = 'BRAF'
            THEN '⚠️  BRAF - If V600E mutant, use ENCORAFENIB + CETUXIMAB'
        ELSE '📊 Monitor'
    END as clinical_interpretation
FROM public.genes g
WHERE g.gene_symbol IN ('EGFR', 'KRAS', 'NRAS', 'BRAF', 'MAP2K1')
ORDER BY g.gene_symbol;

\echo ''
\echo '⚠️  CRITICAL: Confirm RAS/BRAF mutation status by DNA sequencing!'
\echo ''

-- Example patient-specific query (if you have patient data):
-- UNCOMMENT AND MODIFY THE PATIENT SCHEMA NAME
/*
SELECT
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    CASE
        WHEN g.gene_symbol IN ('KRAS', 'NRAS', 'BRAF') AND COALESCE(pe.expression_fold_change, 1.0) > 2.0
            THEN '⚠️  HIGH EXPRESSION - Confirm mutation by DNA sequencing'
        WHEN g.gene_symbol = 'EGFR' AND COALESCE(pe.expression_fold_change, 1.0) > 2.0
            THEN '🎯 EGFR HIGH - Consider anti-EGFR IF RAS/BRAF wild-type'
        ELSE '📊 Baseline expression'
    END as interpretation
FROM public.genes g
LEFT JOIN patient_YOUR_CRC_PATIENT_ID.expression_data pe
    ON g.gene_id = pe.gene_id
WHERE g.gene_symbol IN ('EGFR', 'KRAS', 'NRAS', 'BRAF')
ORDER BY COALESCE(pe.expression_fold_change, 1.0) DESC;
*/

\echo '---------------------------------------------------------------------'
\echo 'Query 2: FDA-Approved Anti-EGFR Therapies (RAS/BRAF WT only)'
\echo '---------------------------------------------------------------------'

SELECT
    otd.molecule_name as drug_name,
    otd.mechanism_of_action,
    otd.is_approved,
    CASE
        WHEN otd.molecule_name IN ('CETUXIMAB', 'PANITUMUMAB')
            THEN 'Anti-EGFR mAb - Requires RAS/BRAF WT'
        WHEN otd.molecule_name = 'ENCORAFENIB'
            THEN 'BRAF inhibitor - For BRAF V600E mutant + Cetuximab'
        ELSE 'Check mechanism'
    END as therapy_notes,
    STRING_AGG(DISTINCT di.indication, ' | ' ORDER BY di.indication) as indications
FROM public.genes g
INNER JOIN public.opentargets_known_drugs otd
    ON g.gene_id = otd.target_gene_id
LEFT JOIN public.drug_indications di
    ON otd.molecule_chembl_id = di.molecule_chembl_id
WHERE g.gene_symbol IN ('EGFR', 'BRAF')
  AND otd.is_approved = true
  AND otd.molecule_name IN ('CETUXIMAB', 'PANITUMUMAB', 'ENCORAFENIB', 'BINIMETINIB')
GROUP BY otd.molecule_name, otd.mechanism_of_action, otd.is_approved
ORDER BY
    CASE
        WHEN otd.molecule_name IN ('CETUXIMAB', 'PANITUMUMAB') THEN 1
        ELSE 2
    END,
    otd.molecule_name;

\echo ''

/*******************************************************************************
 * QUERY 3: MSI-H/dMMR Status Assessment (Immunotherapy Eligibility)
 *
 * Purpose:
 * --------
 * - Assess mismatch repair (MMR) gene expression
 * - MSI-H/dMMR status predicts excellent pembrolizumab response
 * - ~15% of colon cancers are MSI-H (mostly right-sided, proximal)
 *
 * Clinical Context:
 * ----------------
 * **MSI-H/dMMR Definition:**
 * - Loss of MLH1, MSH2, MSH6, or PMS2 protein expression (IHC)
 * - OR high microsatellite instability (PCR-based assay)
 *
 * **Immunotherapy Options (FDA-Approved):**
 * - Pembrolizumab: First-line monotherapy (superior to chemotherapy)
 * - Nivolumab: Second-line monotherapy
 * - Nivolumab + Ipilimumab: Higher response rate, more toxicity
 *
 * **NOTE**: RNA underexpression correlates with but does NOT confirm dMMR
 * Confirm by IHC (MLH1/MSH2/MSH6/PMS2) or PCR (MSI testing)
 ******************************************************************************/

\echo '---------------------------------------------------------------------'
\echo 'Query 3: MSI-H/dMMR Markers (Immunotherapy Eligibility)'
\echo '---------------------------------------------------------------------'
\echo 'NOTE: This query uses public schema (no patient-specific data)'
\echo ''

-- This query shows MMR genes from public schema
SELECT
    g.gene_symbol,
    '1.0' as baseline_fold_change,  -- Placeholder: replace with patient data
    CASE
        WHEN g.gene_symbol IN ('MLH1', 'MSH2', 'MSH6', 'PMS2')
            THEN '🎯 MMR GENE - Loss predicts MSI-H/dMMR → PEMBROLIZUMAB eligible'
        WHEN g.gene_symbol IN ('CD274', 'PDCD1')
            THEN '📊 Immune checkpoint genes (PD-L1, PD-1)'
        ELSE '📊 Monitor'
    END as msi_h_interpretation
FROM public.genes g
WHERE g.gene_symbol IN ('MLH1', 'MSH2', 'MSH6', 'PMS2', 'CD274', 'PDCD1', 'CD8A')
ORDER BY g.gene_symbol;

\echo ''
\echo '⚠️  IMPORTANT: Confirm MSI-H/dMMR by IHC or PCR testing!'
\echo 'RNA underexpression is suggestive but NOT definitive'
\echo ''

-- Example patient-specific query:
/*
SELECT
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    CASE
        WHEN g.gene_symbol IN ('MLH1', 'MSH2', 'MSH6', 'PMS2')
             AND COALESCE(pe.expression_fold_change, 1.0) < 0.5
            THEN '🎯 MMR LOSS → Likely MSI-H/dMMR → PEMBROLIZUMAB first-line'
        WHEN g.gene_symbol = 'CD274' AND COALESCE(pe.expression_fold_change, 1.0) > 2.0
            THEN '✓ PD-L1 HIGH (supports immunotherapy)'
        ELSE '📊 Monitor'
    END as immunotherapy_eligibility
FROM public.genes g
LEFT JOIN patient_YOUR_CRC_PATIENT_ID.expression_data pe
    ON g.gene_id = pe.gene_id
WHERE g.gene_symbol IN ('MLH1', 'MSH2', 'MSH6', 'PMS2', 'CD274', 'PDCD1')
ORDER BY COALESCE(pe.expression_fold_change, 1.0) ASC;
*/

\echo ''

/*******************************************************************************
 * QUERY 4: VEGF Pathway & Anti-Angiogenic Therapy
 *
 * Purpose:
 * --------
 * - Assess VEGF pathway activation
 * - Bevacizumab (first-line) and ramucirumab (second-line) eligibility
 * - Angiogenesis is critical for CRC growth and metastasis
 *
 * Clinical Context:
 * ----------------
 * **Bevacizumab (Avastin)**:
 * - First-line: FOLFOX/FOLFIRI + Bevacizumab (standard of care)
 * - Works in all molecular subtypes (RAS mutant, RAS WT, MSI-H, MSS)
 * - Continuation beyond progression recommended (CAIRO3, AIO 0207)
 *
 * **Ramucirumab (Cyramza)**:
 * - Second-line: FOLFIRI + Ramucirumab (RAISE trial)
 * - VEGFR2-targeted antibody (different from bevacizumab mechanism)
 ******************************************************************************/

\echo '---------------------------------------------------------------------'
\echo 'Query 4: VEGF Pathway Activation & Anti-Angiogenic Therapies'
\echo '---------------------------------------------------------------------'

SELECT
    g.gene_symbol,
    '1.0' as baseline_fold_change,  -- Placeholder
    CASE
        WHEN g.gene_symbol = 'VEGFA'
            THEN '🎯 VEGF-A - Target for BEVACIZUMAB (all CRC subtypes)'
        WHEN g.gene_symbol = 'KDR'
            THEN '🎯 VEGFR2 - Target for RAMUCIRUMAB (second-line)'
        WHEN g.gene_symbol IN ('FLT1', 'FLT4')
            THEN '📊 Alternative VEGF receptors'
        ELSE '📊 Monitor'
    END as angiogenesis_interpretation
FROM public.genes g
WHERE g.gene_symbol IN ('VEGFA', 'VEGFB', 'VEGFC', 'KDR', 'FLT1', 'FLT4', 'ANGPT2')
ORDER BY g.gene_symbol;

\echo ''

-- Query for FDA-approved anti-VEGF therapies
SELECT
    otd.molecule_name as drug_name,
    otd.mechanism_of_action,
    STRING_AGG(DISTINCT di.indication, ' | ' ORDER BY di.indication) as indications
FROM public.genes g
INNER JOIN public.opentargets_known_drugs otd
    ON g.gene_id = otd.target_gene_id
LEFT JOIN public.drug_indications di
    ON otd.molecule_chembl_id = di.molecule_chembl_id
WHERE g.gene_symbol IN ('VEGFA', 'KDR')
  AND otd.is_approved = true
  AND otd.molecule_name IN ('BEVACIZUMAB', 'RAMUCIRUMAB')
GROUP BY otd.molecule_name, otd.mechanism_of_action
ORDER BY otd.molecule_name;

\echo ''

/*******************************************************************************
 * QUERY 5: HER2 Amplification (Emerging Target in CRC)
 *
 * Purpose:
 * --------
 * - Assess HER2 (ERBB2) amplification status
 * - ~5% of CRC have HER2 amplification (enriched in RAS/BRAF WT)
 * - Emerging target with trastuzumab + pertuzumab combinations
 *
 * Clinical Context:
 * ----------------
 * **HER2-Targeted Therapy in CRC:**
 * - Trastuzumab + Pertuzumab: Phase II trials show ~30% response rate
 * - Trastuzumab deruxtecan (T-DXd): Clinical trials ongoing
 * - Tucatinib + Trastuzumab: MOUNTAINEER trial (HER2+ CRC)
 *
 * **Testing Requirements:**
 * - IHC 3+ or IHC 2+ with FISH amplification (HER2:CEP17 ratio ≥2.0)
 * - Consider testing in RAS/BRAF WT, anti-EGFR refractory patients
 ******************************************************************************/

\echo '---------------------------------------------------------------------'
\echo 'Query 5: HER2 Amplification Status (Emerging CRC Target)'
\echo '---------------------------------------------------------------------'

SELECT
    g.gene_symbol,
    '1.0' as baseline_fold_change,  -- Placeholder
    CASE
        WHEN g.gene_symbol = 'ERBB2'
            THEN '🎯 HER2 - If amplified (IHC 3+ or FISH+), consider TRASTUZUMAB + PERTUZUMAB'
        WHEN g.gene_symbol = 'ERBB3'
            THEN '📊 HER3 - Co-receptor, influences HER2 signaling'
        ELSE '📊 Monitor'
    END as her2_interpretation
FROM public.genes g
WHERE g.gene_symbol IN ('ERBB2', 'ERBB3', 'GRB7')
ORDER BY g.gene_symbol;

\echo ''
\echo '⚠️  NOTE: HER2 amplification occurs in ~5% of CRC'
\echo 'Test by IHC/FISH in RAS/BRAF WT, anti-EGFR refractory patients'
\echo ''

/*
-- Example patient-specific query:
SELECT
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    CASE
        WHEN g.gene_symbol = 'ERBB2' AND COALESCE(pe.expression_fold_change, 1.0) > 4.0
            THEN '🎯 HER2 HIGH - Confirm amplification by IHC/FISH → Consider TRASTUZUMAB'
        WHEN g.gene_symbol = 'ERBB2' AND COALESCE(pe.expression_fold_change, 1.0) BETWEEN 2.0 AND 4.0
            THEN '🟡 HER2 MODERATE - Consider IHC/FISH testing'
        ELSE '📊 Baseline'
    END as her2_therapy_recommendation
FROM public.genes g
LEFT JOIN patient_YOUR_CRC_PATIENT_ID.expression_data pe
    ON g.gene_id = pe.gene_id
WHERE g.gene_symbol IN ('ERBB2', 'ERBB3', 'GRB7')
ORDER BY COALESCE(pe.expression_fold_change, 1.0) DESC;
*/

\echo ''

/*******************************************************************************
 * QUERY 6: Comprehensive CRC Treatment Algorithm
 *
 * Purpose:
 * --------
 * - Integrate molecular findings into treatment decision tree
 * - Prioritize based on FDA-approved therapies and NCCN guidelines
 ******************************************************************************/

\echo '---------------------------------------------------------------------'
\echo 'Query 6: CRC Treatment Algorithm Summary'
\echo '---------------------------------------------------------------------'
\echo ''
\echo 'FIRST-LINE TREATMENT DECISION TREE:'
\echo '------------------------------------'
\echo '1. MSI-H/dMMR (15% of CRC, mostly right-sided):'
\echo '   → PEMBROLIZUMAB monotherapy (FDA-approved first-line)'
\echo '   → Superior to chemotherapy (KEYNOTE-177 trial)'
\echo ''
\echo '2. RAS/BRAF Wild-Type + Left-Sided Primary (~20% of CRC):'
\echo '   → FOLFOX or FOLFIRI + CETUXIMAB or PANITUMUMAB'
\echo '   → Anti-EGFR therapy improves OS in left-sided tumors'
\echo ''
\echo '3. BRAF V600E Mutant (~10% of CRC):'
\echo '   → ENCORAFENIB + CETUXIMAB (+/- BINIMETINIB)'
\echo '   → FDA-approved for BRAF V600E after prior therapy'
\echo ''
\echo '4. RAS Mutant or Right-Sided Primary (~60% of CRC):'
\echo '   → FOLFOX or FOLFIRI + BEVACIZUMAB'
\echo '   → Anti-VEGF therapy is standard for all subtypes'
\echo ''
\echo '5. HER2 Amplified + RAS/BRAF WT (~2-3% of CRC):'
\echo '   → TRASTUZUMAB + PERTUZUMAB (clinical trial or off-label)'
\echo '   → Consider after anti-EGFR failure'
\echo ''
\echo 'SECOND-LINE TREATMENT OPTIONS:'
\echo '-------------------------------'
\echo '- MSI-H/dMMR: NIVOLUMAB +/- IPILIMUMAB'
\echo '- RAS/BRAF WT: Switch anti-EGFR if used bevacizumab first-line'
\echo '- All others: FOLFIRI + RAMUCIRUMAB (VEGFR2 inhibitor)'
\echo '- Regorafenib or TAS-102 for later lines'
\echo ''
\echo '====================================================================='

\echo ''

/*******************************************************************************
 * QUERY 7: Find Supporting Publications (CRC Targeted Therapy)
 ******************************************************************************/

\echo '---------------------------------------------------------------------'
\echo 'Query 7: Supporting Publications (CRC Molecular Targets)'
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
WHERE g.gene_symbol IN ('KRAS', 'BRAF', 'EGFR', 'VEGFA', 'MLH1', 'ERBB2')
  AND pm.publication_year >= 2019
  AND (pm.abstract ILIKE '%colorectal%' OR pm.abstract ILIKE '%colon cancer%')
ORDER BY gp.mention_count DESC, pm.publication_year DESC
LIMIT 10;

\echo ''
\echo '====================================================================='
\echo 'ANALYSIS COMPLETE'
\echo ''
\echo 'CRITICAL NEXT STEPS FOR CRC:'
\echo '1. ⚠️  DNA sequencing for RAS/BRAF mutation status (REQUIRED)'
\echo '2. ⚠️  MSI-H/dMMR testing (IHC for MLH1/MSH2/MSH6/PMS2 or PCR)'
\echo '3. Consider HER2 testing if RAS/BRAF WT and anti-EGFR refractory'
\echo '4. Determine primary tumor location (left vs. right-sided)'
\echo '5. Review NCCN guidelines for latest treatment algorithms'
\echo ''
\echo 'Key Clinical Trials:'
\echo '- KEYNOTE-177 (Pembrolizumab in MSI-H/dMMR first-line)'
\echo '- BEACON (Encorafenib + Cetuximab in BRAF V600E)'
\echo '- MOUNTAINEER (Tucatinib + Trastuzumab in HER2+ CRC)'
\echo '- RAISE (Ramucirumab + FOLFIRI second-line)'
\echo '====================================================================='

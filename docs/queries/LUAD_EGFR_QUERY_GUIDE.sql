/*******************************************************************************
 * LUNG ADENOCARCINOMA (EGFR-MUTANT) QUERY GUIDE
 * MEDIABASE v0.6.0
 *
 * Clinical Context:
 * ----------------
 * EGFR-mutant lung adenocarcinoma represents ~15% of lung cancers in Western
 * populations and ~50% in East Asian populations. Characterized by:
 * - EGFR activating mutations (Exon 19 deletions, L858R most common)
 * - Excellent response to EGFR tyrosine kinase inhibitors (TKIs)
 * - Never/light smokers, adenocarcinoma histology
 * - Resistance mechanisms: T790M mutation, MET amplification, HER3 activation
 *
 * This guide provides SQL queries to:
 * 1. Confirm EGFR overexpression and downstream pathway activation
 * 2. Identify FDA-approved EGFR TKIs (1st, 2nd, 3rd generation)
 * 3. Assess resistance mechanisms (MET, HER3, bypass pathways)
 * 4. Evaluate combination therapy opportunities
 * 5. Find supporting scientific publications
 *
 * References:
 * ----------
 * - Lynch et al. N Engl J Med 2004 (EGFR mutations and gefitinib response)
 * - Mok et al. N Engl J Med 2009 (Gef itinib vs carboplatin-paclitaxel)
 * - Soria et al. N Engl J Med 2018 (Osimertinib first-line FLAURA trial)
 * - Ramalingam et al. N Engl J Med 2020 (Osimertinib adjuvant ADAURA trial)
 ******************************************************************************/

-- Set patient schema name (MODIFY THIS)
\set PATIENT_SCHEMA 'patient_synthetic_luad'

\echo '====================================================================='
\echo 'EGFR-MUTANT LUNG ADENOCARCINOMA THERAPEUTIC ANALYSIS'
\echo '====================================================================='
\echo ''

/*******************************************************************************
 * QUERY 1: EGFR Pathway Activation Assessment
 *
 * Purpose:
 * --------
 * - Verify EGFR overexpression (transcriptional surrogate for mutation)
 * - Assess downstream MAPK and PI3K/AKT pathway activation
 * - Evaluate co-receptor activation (ERBB3/HER3)
 *
 * Clinical Interpretation:
 * -----------------------
 * - EGFR >3.0x: Strong signal for EGFR pathway activation
 * - MAPK1/ERK2, AKT1 >2.0x: Downstream pathway activation
 * - ERBB3 >2.0x: HER3 co-receptor activation (resistance mechanism)
 *
 * NOTE: RNA expression is a surrogate for EGFR mutation status.
 * Confirm EGFR mutation by DNA sequencing (Exon 19 del, L858R).
 ******************************************************************************/

\echo '---------------------------------------------------------------------'
\echo 'Query 1: EGFR Pathway Activation & Downstream Signaling'
\echo '---------------------------------------------------------------------'

SELECT
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    CASE
        WHEN g.gene_symbol = 'EGFR' AND COALESCE(pe.expression_fold_change, 1.0) > 3.0
            THEN '🎯 EGFR HIGH → OSIMERTINIB (1st-line, 3rd-gen TKI)'
        WHEN g.gene_symbol = 'EGFR' AND COALESCE(pe.expression_fold_change, 1.0) BETWEEN 2.0 AND 3.0
            THEN '🟡 EGFR MODERATE → Confirm mutation status'
        WHEN g.gene_symbol = 'MAPK1' AND COALESCE(pe.expression_fold_change, 1.0) > 2.0
            THEN '✓ MAPK/ERK PATHWAY ACTIVE (downstream of EGFR)'
        WHEN g.gene_symbol IN ('AKT1', 'PIK3CA') AND COALESCE(pe.expression_fold_change, 1.0) > 2.5
            THEN '✓ PI3K/AKT PATHWAY ACTIVE (downstream of EGFR)'
        WHEN g.gene_symbol = 'ERBB3' AND COALESCE(pe.expression_fold_change, 1.0) > 2.0
            THEN '⚠️  HER3 ACTIVATION (potential resistance mechanism)'
        WHEN g.gene_symbol = 'STAT3' AND COALESCE(pe.expression_fold_change, 1.0) > 2.5
            THEN '📊 STAT3 ACTIVATION (EGFR downstream target)'
        ELSE '📊 Monitor'
    END as pathway_interpretation
FROM public.genes g
LEFT JOIN patient_synthetic_luad.expression_data pe
    ON g.gene_id = pe.gene_id
WHERE g.gene_symbol IN (
    'EGFR',  -- Primary target
    'ERBB3',  -- HER3 co-receptor
    'MAPK1',  -- ERK2 (MAPK pathway)
    'AKT1', 'PIK3CA', 'MTOR',  -- PI3K/AKT pathway
    'STAT3'  -- STAT pathway
)
ORDER BY COALESCE(pe.expression_fold_change, 1.0) DESC;

\echo ''

/*******************************************************************************
 * QUERY 2: FDA-Approved EGFR TKIs (1st, 2nd, 3rd Generation)
 *
 * Purpose:
 * --------
 * - List all FDA-approved EGFR tyrosine kinase inhibitors
 * - Distinguish by generation and T790M resistance coverage
 *
 * Clinical Decision Support:
 * -------------------------
 * **First-Line Treatment:**
 * - Osimertinib (3rd-gen): Preferred first-line (FLAURA trial)
 *   - Superior PFS and OS vs 1st/2nd-gen TKIs
 *   - CNS penetration excellent
 *   - Active against T790M
 *
 * **Alternative First-Line:**
 * - Erlotinib, Gefitinib (1st-gen): Effective but higher risk T790M resistance
 * - Afatinib, Dacomitinib (2nd-gen): Irreversible, broader HER family coverage
 *
 * **Second-Line (T790M resistance):**
 * - Osimertinib: FDA-approved for T790M-positive progression
 *
 * **After Osimertinib Resistance:**
 * - Chemotherapy + immunotherapy
 * - Clinical trials (e.g., EGFR/MET bispecific antibodies)
 ******************************************************************************/

\echo '---------------------------------------------------------------------'
\echo 'Query 2: FDA-Approved EGFR TKIs (All Generations)'
\echo '---------------------------------------------------------------------'

SELECT
    otd.molecule_name as drug_name,
    otd.mechanism_of_action,
    otd.max_phase as clinical_phase,
    otd.is_approved,
    CASE
        WHEN otd.molecule_name = 'OSIMERTINIB' THEN '3rd-gen (T790M active) - PREFERRED 1st-line'
        WHEN otd.molecule_name IN ('AFATINIB', 'DACOMITINIB') THEN '2nd-gen (irreversible)'
        WHEN otd.molecule_name IN ('ERLOTINIB', 'GEFITINIB') THEN '1st-gen (reversible)'
        ELSE 'Check mechanism'
    END as tki_generation,
    STRING_AGG(DISTINCT di.indication, ' | ' ORDER BY di.indication) as indications
FROM public.genes g
INNER JOIN public.opentargets_known_drugs otd
    ON g.gene_id = otd.target_gene_id
LEFT JOIN public.drug_indications di
    ON otd.molecule_chembl_id = di.molecule_chembl_id
WHERE g.gene_symbol = 'EGFR'
  AND otd.is_approved = true
  AND (di.indication ILIKE '%lung cancer%' OR di.indication IS NULL)
GROUP BY otd.molecule_name, otd.mechanism_of_action, otd.max_phase, otd.is_approved
ORDER BY
    CASE
        WHEN otd.molecule_name = 'OSIMERTINIB' THEN 1
        WHEN otd.molecule_name IN ('AFATINIB', 'DACOMITINIB') THEN 2
        ELSE 3
    END,
    otd.molecule_name;

\echo ''

/*******************************************************************************
 * QUERY 3: Resistance Mechanisms Assessment
 *
 * Purpose:
 * --------
 * - Assess known EGFR TKI resistance mechanisms
 * - MET amplification (~5-20% of resistance)
 * - HER3 (ERBB3) bypass signaling (~5% of resistance)
 * - Loss of tumor suppressors (STK11/LKB1, KEAP1)
 *
 * Clinical Interpretation:
 * -----------------------
 * - MET >3.0x: MET amplification → Consider capmatinib, tepotinib (MET inhibitors)
 * - ERBB3 >2.5x: HER3 activation → Clinical trials (HER3-targeted therapies)
 * - BRAF >2.0x: BRAF activation → Consider dabrafenib + trametinib
 * - STK11 <0.5x, KEAP1 <0.5x: Poor prognosis, immunotherapy resistance
 ******************************************************************************/

\echo '---------------------------------------------------------------------'
\echo 'Query 3: EGFR TKI Resistance Mechanisms'
\echo '---------------------------------------------------------------------'

SELECT
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    CASE
        WHEN g.gene_symbol = 'MET' AND COALESCE(pe.expression_fold_change, 1.0) > 3.0
            THEN '🎯 MET AMPLIFICATION → CAPMATINIB/TEPOTINIB (MET inhibitor)'
        WHEN g.gene_symbol = 'ERBB3' AND COALESCE(pe.expression_fold_change, 1.0) > 2.5
            THEN '🟡 HER3 BYPASS → Clinical trials (HER3-targeted therapy)'
        WHEN g.gene_symbol = 'BRAF' AND COALESCE(pe.expression_fold_change, 1.0) > 2.0
            THEN '🟡 BRAF ACTIVATION → Consider DABRAFENIB + TRAMETINIB'
        WHEN g.gene_symbol = 'KRAS' AND COALESCE(pe.expression_fold_change, 1.0) > 2.0
            THEN '⚠️  KRAS ACTIVATION (unusual in EGFR-mutant, recheck diagnosis)'
        WHEN g.gene_symbol IN ('STK11', 'KEAP1') AND COALESCE(pe.expression_fold_change, 1.0) < 0.5
            THEN '⚠️  TUMOR SUPPRESSOR LOSS → Poor prognosis, immunotherapy resistance'
        WHEN g.gene_symbol = 'TP53' AND COALESCE(pe.expression_fold_change, 1.0) < 0.5
            THEN '📊 TP53 LOSS (common in EGFR-mutant LUAD)'
        ELSE '📊 Monitor'
    END as resistance_interpretation
FROM public.genes g
LEFT JOIN patient_synthetic_luad.expression_data pe
    ON g.gene_id = pe.gene_id
WHERE g.gene_symbol IN (
    'MET',  -- MET amplification
    'ERBB3',  -- HER3 bypass
    'BRAF', 'KRAS',  -- Alternative pathway activation
    'STK11', 'KEAP1', 'TP53'  -- Tumor suppressors
)
ORDER BY COALESCE(pe.expression_fold_change, 1.0) DESC;

\echo ''

/*******************************************************************************
 * QUERY 4: Angiogenesis and Immune Checkpoint Status
 *
 * Purpose:
 * --------
 * - Assess VEGF pathway activation for anti-angiogenic therapy
 * - Evaluate PD-L1 expression for immunotherapy eligibility
 * - EGFR-mutant tumors typically have low PD-L1 and TMB
 *
 * Clinical Context:
 * ----------------
 * Combination strategies:
 * - Ramucirumab (VEGFR2 antibody) + Erlotinib: FDA-approved 1st-line
 * - Bevacizumab + Erlotinib: Phase III trial showed PFS benefit
 * - Immunotherapy: Generally NOT effective in EGFR-mutant (low TMB/PD-L1)
 *   Exception: After TKI resistance with high PD-L1 (≥50%)
 ******************************************************************************/

\echo '---------------------------------------------------------------------'
\echo 'Query 4: Angiogenesis & Immune Checkpoint Status'
\echo '---------------------------------------------------------------------'

SELECT
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    CASE
        WHEN g.gene_symbol = 'VEGFA' AND COALESCE(pe.expression_fold_change, 1.0) > 3.0
            THEN '🎯 VEGF HIGH → RAMUCIRUMAB + ERLOTINIB (FDA-approved)'
        WHEN g.gene_symbol = 'KDR' AND COALESCE(pe.expression_fold_change, 1.0) > 2.0
            THEN '✓ VEGFR2 EXPRESSION (angiogenesis active)'
        WHEN g.gene_symbol IN ('FGF2', 'ANGPT2') AND COALESCE(pe.expression_fold_change, 1.0) > 2.5
            THEN '✓ ANGIOGENIC FACTORS ELEVATED'
        WHEN g.gene_symbol = 'CD274' AND COALESCE(pe.expression_fold_change, 1.0) > 2.0
            THEN '🟡 PD-L1 MODERATE → Consider immunotherapy AFTER TKI failure'
        WHEN g.gene_symbol = 'CD274' AND COALESCE(pe.expression_fold_change, 1.0) < 1.5
            THEN '❌ PD-L1 LOW (typical in EGFR-mutant) → Immunotherapy not recommended'
        ELSE '📊 Monitor'
    END as therapy_interpretation
FROM public.genes g
LEFT JOIN patient_synthetic_luad.expression_data pe
    ON g.gene_id = pe.gene_id
WHERE g.gene_symbol IN (
    'VEGFA',  -- VEGF
    'KDR',  -- VEGFR2
    'FGF2', 'ANGPT2',  -- Angiogenic factors
    'CD274', 'PDCD1'  -- Immune checkpoints
)
ORDER BY COALESCE(pe.expression_fold_change, 1.0) DESC;

\echo ''

/*******************************************************************************
 * QUERY 5: Comprehensive Treatment Recommendation Summary
 *
 * Purpose:
 * --------
 * - Integrate all findings into actionable first, second, third-line recommendations
 * - Prioritize based on FDA-approved therapies and clinical trial evidence
 ******************************************************************************/

\echo '---------------------------------------------------------------------'
\echo 'Query 5: Comprehensive EGFR-Mutant LUAD Treatment Recommendations'
\echo '---------------------------------------------------------------------'

WITH patient_profile AS (
    SELECT
        MAX(CASE WHEN g.gene_symbol = 'EGFR' THEN COALESCE(pe.expression_fold_change, 1.0) END) as egfr_fc,
        MAX(CASE WHEN g.gene_symbol = 'MET' THEN COALESCE(pe.expression_fold_change, 1.0) END) as met_fc,
        MAX(CASE WHEN g.gene_symbol = 'VEGFA' THEN COALESCE(pe.expression_fold_change, 1.0) END) as vegfa_fc,
        MAX(CASE WHEN g.gene_symbol = 'CD274' THEN COALESCE(pe.expression_fold_change, 1.0) END) as pdl1_fc
    FROM public.genes g
    LEFT JOIN patient_synthetic_luad.expression_data pe
        ON g.gene_id = pe.gene_id
    WHERE g.gene_symbol IN ('EGFR', 'MET', 'VEGFA', 'CD274')
)
SELECT
    CASE
        WHEN pp.egfr_fc > 3.0 AND pp.vegfa_fc > 3.0
            THEN '1. OSIMERTINIB + RAMUCIRUMAB (EGFR + VEGF dual targeting)'
        WHEN pp.egfr_fc > 3.0
            THEN '1. OSIMERTINIB (3rd-gen EGFR TKI, first-line standard)'
        ELSE '1. Confirm EGFR mutation status by DNA sequencing'
    END as first_line_recommendation,
    CASE
        WHEN pp.met_fc > 3.0
            THEN '2. After osimertinib progression: CAPMATINIB (MET inhibitor) + EGFR TKI'
        WHEN pp.pdl1_fc > 2.0
            THEN '2. After osimertinib progression: PEMBROLIZUMAB + CHEMOTHERAPY'
        ELSE '2. After osimertinib progression: Platinum-based chemotherapy'
    END as second_line_recommendation,
    '3. After progression: DOCETAXEL or Clinical Trial' as third_line_recommendation,
    CASE
        WHEN pp.egfr_fc > 3.0 THEN 'FDA Approved (FLAURA trial)'
        ELSE 'Confirm EGFR mutation required'
    END as evidence_level
FROM patient_profile pp;

\echo ''

/*******************************************************************************
 * QUERY 6: Find Supporting Publications (EGFR-Mutant LUAD Research)
 ******************************************************************************/

\echo '---------------------------------------------------------------------'
\echo 'Query 6: Supporting Publications (EGFR-Mutant LUAD)'
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
WHERE g.gene_symbol IN ('EGFR', 'MET', 'ERBB3', 'VEGFA', 'STK11')
  AND pm.publication_year >= 2019
ORDER BY gp.mention_count DESC, pm.publication_year DESC
LIMIT 10;

\echo ''
\echo '====================================================================='
\echo 'ANALYSIS COMPLETE'
\echo ''
\echo 'Next Steps:'
\echo '1. CONFIRM EGFR mutation by DNA sequencing (Exon 19 del, L858R, etc.)'
\echo '2. Start osimertinib 80mg daily (first-line standard)'
\echo '3. Brain MRI at baseline (CNS metastases common in EGFR-mutant)'
\echo '4. Monitor for resistance with liquid biopsy (ctDNA for T790M)'
\echo '5. Consider adjuvant osimertinib if stage IB-IIIA after resection'
\echo ''
\echo 'Key Clinical Trials:'
\echo '- FLAURA (Osimertinib vs gefitinib/erlotinib first-line)'
\echo '- ADAURA (Osimertinib adjuvant after resection)'
\echo '- RELAY (Ramucirumab + erlotinib first-line)'
\echo '- MARIPOSA (Amivantamab + lazertinib vs osimertinib)'
\echo '====================================================================='

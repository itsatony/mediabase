/*******************************************************************************
 * HER2+ BREAST CANCER QUERY GUIDE
 * MEDIABASE v0.6.0
 *
 * Clinical Context:
 * ----------------
 * HER2+ (ERBB2-amplified) breast cancer represents 15-20% of invasive breast
 * cancers and is characterized by:
 * - ERBB2 gene amplification (chromosome 17q12 amplicon)
 * - High proliferation rates
 * - Historically aggressive disease
 * - Excellent response to anti-HER2 targeted therapies
 *
 * This guide provides SQL queries to:
 * 1. Confirm HER2 amplification and co-amplified genes
 * 2. Identify FDA-approved targeted therapies
 * 3. Assess PI3K/AKT pathway activation (common resistance mechanism)
 * 4. Evaluate CDK4/6 inhibitor eligibility
 * 5. Find supporting scientific publications
 *
 * Prerequisites:
 * -------------
 * - Patient RNA-seq data uploaded to patient-specific schema
 * - Schema name format: patient_<PATIENT_ID>
 * - Replace 'patient_synthetic_her2' with your actual patient schema name
 *
 * References:
 * ----------
 * - Perou et al. Nature 2000 (breast cancer molecular subtypes)
 * - Slamon et al. N Engl J Med 2001 (trastuzumab efficacy)
 * - Swain et al. N Engl J Med 2015 (pertuzumab benefit)
 * - Krop et al. Lancet Oncol 2017 (T-DM1 mechanism)
 ******************************************************************************/

-- Set patient schema name (MODIFY THIS)
\set PATIENT_SCHEMA 'patient_synthetic_her2'

\echo '====================================================================='
\echo 'HER2+ BREAST CANCER THERAPEUTIC ANALYSIS'
\echo '====================================================================='
\echo ''

/*******************************************************************************
 * QUERY 1: Confirm HER2 Amplification and Identify Co-Amplified Genes
 *
 * Purpose:
 * --------
 * - Verify ERBB2 overexpression (diagnostic threshold: >4-fold)
 * - Identify co-amplified genes in 17q12 amplicon (GRB7, PGAP3, PNMT)
 * - These genes serve as positive controls for amplification event
 *
 * Clinical Interpretation:
 * -----------------------
 * - ERBB2 fold-change >4.0: HER2+ confirmed → anti-HER2 therapy eligible
 * - ERBB2 fold-change 2.0-4.0: Equivocal → consider IHC/FISH confirmation
 * - ERBB2 fold-change <2.0: HER2-negative
 * - GRB7, PGAP3, PNMT: Expected co-amplification (validate amplicon event)
 ******************************************************************************/

\echo '---------------------------------------------------------------------'
\echo 'Query 1: HER2 Amplification Status & Co-Amplified Genes'
\echo '---------------------------------------------------------------------'

SELECT
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    CASE
        WHEN g.gene_symbol = 'ERBB2' AND COALESCE(pe.expression_fold_change, 1.0) > 4.0
            THEN '🎯 HER2+ CONFIRMED - Anti-HER2 Therapy Eligible'
        WHEN g.gene_symbol = 'ERBB2' AND COALESCE(pe.expression_fold_change, 1.0) BETWEEN 2.0 AND 4.0
            THEN '⚠️  HER2 EQUIVOCAL - Consider IHC/FISH Confirmation'
        WHEN g.gene_symbol = 'ERBB2'
            THEN '❌ HER2 Negative'
        WHEN g.gene_symbol IN ('GRB7', 'PGAP3', 'PNMT') AND COALESCE(pe.expression_fold_change, 1.0) > 2.0
            THEN '✓ Co-amplified (17q12 amplicon validation)'
        ELSE '📊 Monitor'
    END as clinical_interpretation
FROM public.genes g
LEFT JOIN patient_synthetic_her2.expression_data pe
    ON g.gene_id = pe.gene_id
WHERE g.gene_symbol IN ('ERBB2', 'GRB7', 'PGAP3', 'PNMT', 'ERBB3')
ORDER BY COALESCE(pe.expression_fold_change, 1.0) DESC;

\echo ''

/*******************************************************************************
 * QUERY 2: FDA-Approved Anti-HER2 Targeted Therapies
 *
 * Purpose:
 * --------
 * - List all FDA-approved drugs targeting HER2/ERBB2
 * - Include mechanism of action and clinical trial phase
 *
 * Clinical Decision Support:
 * -------------------------
 * First-line options (metastatic):
 * - Trastuzumab + Pertuzumab + Chemotherapy (CLEOPATRA regimen)
 * - T-DM1 (Trastuzumab emtansine) for 2nd line
 * - Trastuzumab deruxtecan (T-DXd) for 3rd line
 *
 * Adjuvant setting:
 * - Trastuzumab (1 year) +/- Pertuzumab
 * - Neratinib (extended adjuvant if high-risk)
 ******************************************************************************/

\echo '---------------------------------------------------------------------'
\echo 'Query 2: FDA-Approved Anti-HER2 Targeted Therapies'
\echo '---------------------------------------------------------------------'

SELECT
    otd.molecule_name as drug_name,
    otd.mechanism_of_action,
    otd.max_phase as clinical_phase,
    otd.is_approved,
    STRING_AGG(DISTINCT di.indication, ' | ' ORDER BY di.indication) as indications
FROM public.genes g
INNER JOIN public.opentargets_known_drugs otd
    ON g.gene_id = otd.target_gene_id
LEFT JOIN public.drug_indications di
    ON otd.molecule_chembl_id = di.molecule_chembl_id
WHERE g.gene_symbol = 'ERBB2'
  AND otd.is_approved = true
  AND (di.indication ILIKE '%breast cancer%' OR di.indication IS NULL)
GROUP BY otd.molecule_name, otd.mechanism_of_action, otd.max_phase, otd.is_approved
ORDER BY otd.molecule_name;

\echo ''

/*******************************************************************************
 * QUERY 3: PI3K/AKT/mTOR Pathway Activation Assessment
 *
 * Purpose:
 * --------
 * - Assess PI3K/AKT pathway activation (major resistance mechanism)
 * - ~40% of HER2+ tumors have PIK3CA mutations → pathway hyperactivation
 * - High pathway activation → consider PI3K/mTOR inhibitor combination
 *
 * Clinical Interpretation:
 * -----------------------
 * - PIK3CA >3.0x + AKT1 >2.0x: Strong pathway activation
 *   → Consider Alpelisib (PI3K inhibitor) + anti-HER2 therapy
 * - PTEN <0.5x (loss): Alternative resistance mechanism
 *   → mTOR inhibitors (Everolimus) may be beneficial
 ******************************************************************************/

\echo '---------------------------------------------------------------------'
\echo 'Query 3: PI3K/AKT/mTOR Pathway Activation (Resistance Mechanism)'
\echo '---------------------------------------------------------------------'

SELECT
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    CASE
        WHEN g.gene_symbol = 'PIK3CA' AND COALESCE(pe.expression_fold_change, 1.0) > 3.0
            THEN '🎯 PI3K INHIBITOR TARGET (Alpelisib)'
        WHEN g.gene_symbol = 'AKT1' AND COALESCE(pe.expression_fold_change, 1.0) > 2.0
            THEN '🟡 AKT ACTIVATION (downstream of PI3K)'
        WHEN g.gene_symbol = 'MTOR' AND COALESCE(pe.expression_fold_change, 1.0) > 2.0
            THEN '🟡 mTOR ACTIVATION (consider Everolimus)'
        WHEN g.gene_symbol = 'PTEN' AND COALESCE(pe.expression_fold_change, 1.0) < 0.5
            THEN '⚠️  PTEN LOSS (mTOR pathway activated)'
        ELSE '📊 Monitor'
    END as therapeutic_strategy
FROM public.genes g
LEFT JOIN patient_synthetic_her2.expression_data pe
    ON g.gene_id = pe.gene_id
WHERE g.gene_symbol IN ('PIK3CA', 'AKT1', 'AKT2', 'MTOR', 'PTEN', 'TSC1', 'TSC2')
ORDER BY COALESCE(pe.expression_fold_change, 1.0) DESC;

\echo ''

/*******************************************************************************
 * QUERY 4: CDK4/6 Inhibitor Eligibility (Hormone Receptor Positive)
 *
 * Purpose:
 * --------
 * - Assess ER/PR status and cell cycle pathway activation
 * - If ER+ and CDK4/6 pathway active → eligible for CDK4/6 inhibitor + anti-HER2
 *
 * Clinical Context:
 * ----------------
 * - ~50% of HER2+ tumors are also ER+ (HER2+/HR+)
 * - MonarcHER trial: Abemaciclib + Trastuzumab improved PFS in HER2+/HR+ disease
 * - CCND1 amplification and CDK4 overexpression predict CDK4/6 inhibitor benefit
 *
 * Interpretation:
 * --------------
 * - ESR1 >2.0x AND (CCND1 >3.0x OR CDK4 >2.0x)
 *   → Strong candidate for CDK4/6 inhibitor combination (Palbociclib, Abemaciclib)
 ******************************************************************************/

\echo '---------------------------------------------------------------------'
\echo 'Query 4: CDK4/6 Inhibitor Eligibility Assessment'
\echo '---------------------------------------------------------------------'

SELECT
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    CASE
        WHEN g.gene_symbol = 'ESR1' AND COALESCE(pe.expression_fold_change, 1.0) > 2.0
            THEN '✓ ER POSITIVE (hormone receptor positive)'
        WHEN g.gene_symbol = 'PGR' AND COALESCE(pe.expression_fold_change, 1.0) > 2.0
            THEN '✓ PR POSITIVE (hormone receptor positive)'
        WHEN g.gene_symbol = 'CCND1' AND COALESCE(pe.expression_fold_change, 1.0) > 3.0
            THEN '🎯 CDK4/6 INHIBITOR TARGET (Palbociclib, Abemaciclib)'
        WHEN g.gene_symbol = 'CDK4' AND COALESCE(pe.expression_fold_change, 1.0) > 2.0
            THEN '🎯 CDK4/6 INHIBITOR TARGET'
        WHEN g.gene_symbol IN ('ESR1', 'PGR') AND COALESCE(pe.expression_fold_change, 1.0) < 0.5
            THEN '❌ HORMONE RECEPTOR NEGATIVE'
        ELSE '📊 Monitor'
    END as therapeutic_interpretation
FROM public.genes g
LEFT JOIN patient_synthetic_her2.expression_data pe
    ON g.gene_id = pe.gene_id
WHERE g.gene_symbol IN ('ESR1', 'PGR', 'CCND1', 'CDK4', 'CDK6', 'RB1')
ORDER BY COALESCE(pe.expression_fold_change, 1.0) DESC;

\echo ''

/*******************************************************************************
 * QUERY 5: Comprehensive Treatment Recommendation Summary
 *
 * Purpose:
 * --------
 * - Integrate all findings into actionable treatment recommendations
 * - Prioritize therapies based on expression levels and approved indications
 *
 * Output:
 * -------
 * - Ranked list of therapeutic strategies
 * - Evidence level (FDA-approved, clinical trial, preclinical)
 * - Combination therapy opportunities
 ******************************************************************************/

\echo '---------------------------------------------------------------------'
\echo 'Query 5: Comprehensive Treatment Recommendation Summary'
\echo '---------------------------------------------------------------------'

WITH patient_profile AS (
    SELECT
        MAX(CASE WHEN g.gene_symbol = 'ERBB2' THEN COALESCE(pe.expression_fold_change, 1.0) END) as erbb2_fc,
        MAX(CASE WHEN g.gene_symbol = 'PIK3CA' THEN COALESCE(pe.expression_fold_change, 1.0) END) as pik3ca_fc,
        MAX(CASE WHEN g.gene_symbol = 'ESR1' THEN COALESCE(pe.expression_fold_change, 1.0) END) as esr1_fc,
        MAX(CASE WHEN g.gene_symbol = 'CCND1' THEN COALESCE(pe.expression_fold_change, 1.0) END) as ccnd1_fc
    FROM public.genes g
    LEFT JOIN patient_synthetic_her2.expression_data pe
        ON g.gene_id = pe.gene_id
    WHERE g.gene_symbol IN ('ERBB2', 'PIK3CA', 'ESR1', 'CCND1')
)
SELECT
    CASE
        WHEN pp.erbb2_fc > 4.0 AND pp.esr1_fc > 2.0 AND pp.ccnd1_fc > 3.0
            THEN '1. TRASTUZUMAB + PERTUZUMAB + PALBOCICLIB (HER2+/HR+, CCND1 amplified)'
        WHEN pp.erbb2_fc > 4.0 AND pp.pik3ca_fc > 3.0
            THEN '1. TRASTUZUMAB + PERTUZUMAB + ALPELISIB (HER2+, PIK3CA activated)'
        WHEN pp.erbb2_fc > 4.0 AND pp.esr1_fc > 2.0
            THEN '1. TRASTUZUMAB + PERTUZUMAB + ENDOCRINE THERAPY (HER2+/HR+)'
        WHEN pp.erbb2_fc > 4.0
            THEN '1. TRASTUZUMAB + PERTUZUMAB + CHEMOTHERAPY (Standard HER2+)'
        ELSE 'HER2 not amplified - Consider alternative subtypes'
    END as first_line_recommendation,
    CASE
        WHEN pp.erbb2_fc > 4.0 THEN '2. T-DM1 (Trastuzumab emtansine) for 2nd line'
        ELSE NULL
    END as second_line_recommendation,
    CASE
        WHEN pp.erbb2_fc > 4.0 THEN '3. T-DXd (Trastuzumab deruxtecan) for 3rd line'
        ELSE NULL
    END as third_line_recommendation,
    'FDA Approved' as evidence_level
FROM patient_profile pp;

\echo ''

/*******************************************************************************
 * QUERY 6: Find Supporting Publications (PubMed Evidence)
 *
 * Purpose:
 * --------
 * - Retrieve publications linking ERBB2 and key resistance genes
 * - Provide literature evidence for treatment recommendations
 * - Identify recent clinical trials and mechanistic studies
 *
 * Usage:
 * ------
 * - Review top 10 publications for clinical context
 * - Look for recent (last 5 years) papers on resistance mechanisms
 * - Search for combination therapy trials in your patient's profile
 ******************************************************************************/

\echo '---------------------------------------------------------------------'
\echo 'Query 6: Supporting Publications (PubMed Evidence)'
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
WHERE g.gene_symbol IN ('ERBB2', 'PIK3CA', 'ESR1', 'CCND1')
  AND pm.publication_year >= 2019  -- Last 5 years
ORDER BY gp.mention_count DESC, pm.publication_year DESC
LIMIT 10;

\echo ''
\echo '====================================================================='
\echo 'ANALYSIS COMPLETE'
\echo ''
\echo 'Next Steps:'
\echo '1. Review HER2 amplification status (Query 1)'
\echo '2. Confirm anti-HER2 therapy eligibility'
\echo '3. Assess resistance mechanisms (PI3K/AKT, CDK4/6)'
\echo '4. Discuss findings with medical oncology team'
\echo '5. Consider enrollment in relevant clinical trials'
\echo ''
\echo 'For additional queries, see:'
\echo '- docs/WORKING_QUERY_EXAMPLES.sql (comprehensive query library)'
\echo '- docs/SOTA_QUERIES_GUIDE.md (detailed methodology)'
\echo '====================================================================='

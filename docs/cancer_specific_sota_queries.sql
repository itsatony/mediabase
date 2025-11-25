-- ============================================================================
-- CANCER-SPECIFIC STATE-OF-THE-ART QUERIES FOR PATIENT DATABASES
-- ============================================================================
-- Version: v0.6.0.2 (PMID Evidence Integration)
-- Purpose: Cancer-type-specific therapeutic queries for clinical decision support
--
-- Architecture: v0.6.0 Shared Core
--   - Single database (mbase) with public schema (core transcriptome data)
--   - Patient-specific schemas: patient_<PATIENT_ID>
--   - Sparse storage: Only expression_fold_change != 1.0 stored
--
-- v0.6.0.2 Enhancements:
--   - PMID evidence integration via gene_publications table (47M+ gene-publication links)
--   - Publication count and evidence level for all therapeutic targets
--   - Evidence tiers: Extensively studied (100K+), Well-studied (10K+), Moderate (1K+), Limited (<1K)
--
-- Usage: Connect to mbase database, queries automatically reference correct schemas
--
-- Query Pattern (v0.6.0):
--   FROM patient_<ID>.expression_data pe
--   JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
--   JOIN public.genes g ON t.gene_id = g.gene_id
--
-- Included Cancer Types:
--   1. HER2+ Breast Cancer (ERBB2 amplification)
--   2. Triple-Negative Breast Cancer (TNBC)
--   3. Lung Adenocarcinoma EGFR-mutant (LUAD-EGFR+)
--   4. MSI-High Colorectal Cancer (CRC-MSI)
--   5. KRAS-mutant Pancreatic Adenocarcinoma (PDAC)
--
-- Each query section includes:
--   - Therapeutic target identification
--   - Pathway dysregulation analysis
--   - Drug recommendation priorities
--   - Biomarker assessment
-- ============================================================================


-- ============================================================================
-- SECTION 1: HER2+ BREAST CANCER QUERIES
-- ============================================================================
-- Clinical Context: ERBB2 amplification drives oncogenic signaling
-- Standard of Care: Trastuzumab + Pertuzumab + Taxane
-- Resistance mechanisms: PI3K/AKT activation, HER2 mutations

-- ----------------------------------------------------------------------------
-- Query 1.1: HER2+ Therapeutic Target Stratification (v0.6.0.2 PMID Evidence)
-- ----------------------------------------------------------------------------
-- Purpose: Identify primary HER2 amplification and co-amplified genes with publication evidence
-- Clinical Value: Confirms HER2 target and identifies potential co-targeting opportunities

SELECT
    g.gene_symbol,
    g.gene_name,
    pe.expression_fold_change,
    g.chromosome,
    COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
    CASE
        WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
        ELSE 'Limited publications'
    END as evidence_level,
    CASE
        WHEN g.gene_symbol = 'ERBB2' AND pe.expression_fold_change >= 5.0
            THEN '🎯 PRIMARY TARGET: Trastuzumab + Pertuzumab (High Priority)'
        WHEN g.gene_symbol = 'ERBB2' AND pe.expression_fold_change >= 3.0
            THEN '🎯 PRIMARY TARGET: Trastuzumab (Standard)'
        WHEN g.gene_symbol IN ('GRB7', 'PGAP3', 'PNMT', 'STARD3')
             AND pe.expression_fold_change > 3.0
            THEN '📍 HER2 Amplicon Co-amplification (17q12)'
        WHEN g.gene_symbol = 'CDK12' AND pe.expression_fold_change > 3.0
            THEN '📍 CDK12 Co-amplification (Potential synthetic lethality)'
    END as therapeutic_priority
FROM patient_synthetic_her2.expression_data pe
JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
JOIN public.genes g ON t.gene_id = g.gene_id
LEFT JOIN public.gene_publications gp ON g.gene_id = gp.gene_id
WHERE
    (g.gene_symbol IN ('ERBB2', 'GRB7', 'PGAP3', 'PNMT', 'STARD3', 'CDK12')
    OR (g.chromosome = '17' AND pe.expression_fold_change > 3.0))
GROUP BY g.gene_symbol, g.gene_name, pe.expression_fold_change, g.chromosome
ORDER BY publication_count DESC, pe.expression_fold_change DESC
LIMIT 20;

-- Expected Results:
-- - ERBB2: 5-8 fold overexpression → Trastuzumab + Pertuzumab
-- - GRB7: 3-5 fold (co-amplified) → Confirms 17q12 amplicon
-- - CDK12: If >3 fold → Consider PARP inhibitor combination


-- ----------------------------------------------------------------------------
-- Query 1.2: HER2+ Resistance Pathway Analysis (PI3K/AKT/mTOR) (v0.6.0.2 PMID Evidence)
-- ----------------------------------------------------------------------------
-- Purpose: Identify PI3K pathway activation (common trastuzumab resistance mechanism) with evidence
-- Clinical Value: Guides addition of PI3K/mTOR inhibitors

SELECT
    g.gene_symbol,
    g.gene_name,
    pe.expression_fold_change,
    COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
    CASE
        WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
        ELSE 'Limited publications'
    END as evidence_level,
    CASE
        WHEN g.gene_symbol = 'PIK3CA' AND pe.expression_fold_change > 2.5
            THEN '🔴 RESISTANCE RISK: Consider Alpelisib (PI3K inhibitor)'
        WHEN g.gene_symbol = 'AKT1' AND pe.expression_fold_change > 2.5
            THEN '🔴 RESISTANCE RISK: AKT pathway activation'
        WHEN g.gene_symbol = 'MTOR' AND pe.expression_fold_change > 2.0
            THEN '🔴 RESISTANCE RISK: Consider Everolimus (mTOR inhibitor)'
        WHEN g.gene_symbol = 'PTEN' AND pe.expression_fold_change < 0.5
            THEN '🔴 RESISTANCE RISK: PTEN loss → PI3K activation'
        ELSE 'Monitor'
    END as resistance_mechanism,
    CASE
        WHEN g.gene_symbol IN ('PIK3CA', 'AKT1', 'AKT2', 'AKT3')
             AND pe.expression_fold_change > 2.5
            THEN 'Alpelisib + Trastuzumab combination'
        WHEN g.gene_symbol = 'MTOR' AND pe.expression_fold_change > 2.0
            THEN 'Everolimus + Trastuzumab combination'
        WHEN g.gene_symbol = 'PTEN' AND pe.expression_fold_change < 0.5
            THEN 'PI3K inhibitor recommended due to PTEN loss'
    END as drug_recommendation
FROM patient_synthetic_her2.expression_data pe
JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
JOIN public.genes g ON t.gene_id = g.gene_id
LEFT JOIN public.gene_publications gp ON g.gene_id = gp.gene_id
WHERE g.gene_symbol IN (
    'PIK3CA', 'PIK3CB', 'PIK3CD', 'PIK3CG',
    'AKT1', 'AKT2', 'AKT3',
    'MTOR', 'RICTOR', 'RAPTOR',
    'PTEN', 'TSC1', 'TSC2'
)
GROUP BY g.gene_symbol, g.gene_name, pe.expression_fold_change
ORDER BY publication_count DESC, pe.expression_fold_change DESC;

-- Expected Results:
-- - PIK3CA >2.5x → 40% of HER2+ have PIK3CA mutations/activation
-- - PTEN <0.5x → PTEN loss predicts trastuzumab resistance
-- - Recommendation: Add alpelisib or everolimus to trastuzumab


-- ----------------------------------------------------------------------------
-- Query 1.3: HER2+ Endocrine Therapy Eligibility (ER/PR Status) (v0.6.0.2 PMID Evidence)
-- ----------------------------------------------------------------------------
-- Purpose: Assess ER/PR expression to determine hormone therapy eligibility with evidence
-- Clinical Value: ~50% of HER2+ are also ER+ (dual therapy candidates)

SELECT
    g.gene_symbol,
    pe.expression_fold_change,
    COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
    CASE
        WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
        ELSE 'Limited publications'
    END as evidence_level,
    CASE
        WHEN g.gene_symbol = 'ESR1' AND pe.expression_fold_change >= 2.0
            THEN '✅ ER-POSITIVE: Add Endocrine Therapy (Letrozole/Tamoxifen)'
        WHEN g.gene_symbol = 'ESR1' AND pe.expression_fold_change < 0.5
            THEN '❌ ER-NEGATIVE: HER2-targeted therapy only'
        WHEN g.gene_symbol = 'PGR' AND pe.expression_fold_change >= 1.5
            THEN '✅ PR-POSITIVE: Favorable prognosis'
        WHEN g.gene_symbol = 'PGR' AND pe.expression_fold_change < 0.5
            THEN '⚠️ PR-NEGATIVE: Monitor closely'
    END as hormone_receptor_status,
    CASE
        WHEN g.gene_symbol = 'ESR1' AND pe.expression_fold_change >= 2.0
            THEN 'Trastuzumab + Pertuzumab + Aromatase Inhibitor (e.g., Letrozole)'
        WHEN g.gene_symbol = 'ESR1' AND pe.expression_fold_change < 0.5
            THEN 'Trastuzumab + Pertuzumab + Chemotherapy (Taxane)'
    END as treatment_regimen
FROM patient_synthetic_her2.expression_data pe
JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
JOIN public.genes g ON t.gene_id = g.gene_id
LEFT JOIN public.gene_publications gp ON g.gene_id = gp.gene_id
WHERE g.gene_symbol IN ('ESR1', 'PGR', 'GATA3', 'FOXA1')
GROUP BY g.gene_symbol, pe.expression_fold_change
ORDER BY g.gene_symbol;

-- Expected Results:
-- - ESR1 ≥2.0 → ER+/HER2+ (50% of cases) → Dual HER2 + endocrine therapy
-- - ESR1 <0.5 → ER-/HER2+ → HER2-targeted + chemotherapy only


-- ============================================================================
-- SECTION 2: TRIPLE-NEGATIVE BREAST CANCER (TNBC) QUERIES
-- ============================================================================
-- Clinical Context: ER-, PR-, HER2- (no targeted therapy)
-- Standard of Care: Chemotherapy (anthracyclines + taxanes)
-- Key Targets: PARP (if BRCA1/2 deficient), PD-L1 (if immune-hot)

-- ----------------------------------------------------------------------------
-- Query 2.1: TNBC Molecular Subtype Classification
-- ----------------------------------------------------------------------------
-- Purpose: Confirm triple-negative status and identify basal-like markers
-- Clinical Value: Rule out potential targeted therapy eligibility

SELECT
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    CASE
        WHEN g.gene_symbol = 'ESR1' AND COALESCE(pe.expression_fold_change, 1.0) < 0.3
            THEN '✅ ER-NEGATIVE: Confirmed TNBC'
        WHEN g.gene_symbol = 'PGR' AND COALESCE(pe.expression_fold_change, 1.0) < 0.3
            THEN '✅ PR-NEGATIVE: Confirmed TNBC'
        WHEN g.gene_symbol = 'ERBB2' AND COALESCE(pe.expression_fold_change, 1.0) < 1.0
            THEN '✅ HER2-NEGATIVE: Confirmed TNBC'
        WHEN g.gene_symbol IN ('KRT5', 'KRT14', 'KRT17')
             AND COALESCE(pe.expression_fold_change, 1.0) > 3.0
            THEN '📍 BASAL-LIKE MARKER: Aggressive subtype'
        WHEN g.gene_symbol = 'EGFR' AND COALESCE(pe.expression_fold_change, 1.0) > 2.5
            THEN '📍 EGFR-POSITIVE (basal): No EGFR inhibitors effective in TNBC'
    END as tnbc_classification
FROM public.genes g
JOIN public.transcripts t ON g.gene_id = t.gene_id
LEFT JOIN patient_synthetic_tnbc.expression_data pe ON t.transcript_id = pe.transcript_id
WHERE g.gene_symbol IN (
    'ESR1', 'PGR', 'ERBB2',  -- Triple-negative confirmation
    'KRT5', 'KRT14', 'KRT17', 'EGFR',  -- Basal-like markers
    'AR'  -- Androgen receptor (LAR subtype)
)
ORDER BY g.gene_symbol;

-- Expected Results:
-- - ESR1, PGR, ERBB2: All <0.5x → Confirms TNBC
-- - KRT5/14/17 >3x → Basal-like subtype (80% of TNBC)
-- - EGFR >2.5x → Basal phenotype (EGFR inhibitors NOT effective)


-- ----------------------------------------------------------------------------
-- Query 2.2: TNBC PARP Inhibitor Eligibility (BRCA1/2 Assessment) (v0.6.0.2 PMID Evidence)
-- ----------------------------------------------------------------------------
-- Purpose: Identify DNA repair deficiency → PARP inhibitor candidacy with evidence
-- Clinical Value: Olaparib/Talazoparib approved for germline BRCA1/2-mutant TNBC

SELECT
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
    CASE
        WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
        ELSE 'Limited publications'
    END as evidence_level,
    CASE
        WHEN g.gene_symbol = 'BRCA1' AND COALESCE(pe.expression_fold_change, 1.0) < 0.5
            THEN '🎯 BRCA1 DEFICIENCY: PARP inhibitor (Olaparib/Talazoparib) HIGH PRIORITY'
        WHEN g.gene_symbol = 'BRCA2' AND COALESCE(pe.expression_fold_change, 1.0) < 0.5
            THEN '🎯 BRCA2 DEFICIENCY: PARP inhibitor (Olaparib/Talazoparib) HIGH PRIORITY'
        WHEN g.gene_symbol IN ('RAD51', 'RAD51C', 'PALB2', 'FANCF')
             AND COALESCE(pe.expression_fold_change, 1.0) < 0.6
            THEN '⚠️ HOMOLOGOUS RECOMBINATION DEFICIENCY: Consider PARP inhibitor'
        WHEN g.gene_symbol = 'TP53' AND COALESCE(pe.expression_fold_change, 1.0) < 0.4
            THEN '📍 TP53 LOSS: Genomic instability (common in TNBC)'
    END as dna_repair_status,
    CASE
        WHEN g.gene_symbol IN ('BRCA1', 'BRCA2')
             AND COALESCE(pe.expression_fold_change, 1.0) < 0.5
            THEN 'Olaparib 300mg BID or Talazoparib 1mg daily (FDA approved)'
        WHEN g.gene_symbol IN ('RAD51', 'PALB2', 'ATM')
             AND COALESCE(pe.expression_fold_change, 1.0) < 0.6
            THEN 'PARP inhibitor clinical trial (HRD signature positive)'
    END as drug_recommendation
FROM public.genes g
JOIN public.transcripts t ON g.gene_id = t.gene_id
LEFT JOIN patient_synthetic_tnbc.expression_data pe ON t.transcript_id = pe.transcript_id
LEFT JOIN public.gene_publications gp ON g.gene_id = gp.gene_id
WHERE g.gene_symbol IN (
    'BRCA1', 'BRCA2', 'PALB2',
    'RAD51', 'RAD51C', 'RAD51D',
    'FANCA', 'FANCF', 'ATM', 'ATR',
    'TP53', 'CHEK2'
)
GROUP BY g.gene_symbol, pe.expression_fold_change
ORDER BY COALESCE(pe.expression_fold_change, 1.0) ASC;

-- Expected Results:
-- - BRCA1 <0.5x → 15-20% of TNBC → Olaparib/Talazoparib eligibility
-- - RAD51 <0.6x → HRD signature → PARP inhibitor clinical trial
-- - TP53 <0.4x → 80% of TNBC (genomic instability)


-- ----------------------------------------------------------------------------
-- Query 2.3: TNBC Immunotherapy Eligibility (PD-L1/Immune Infiltration) (v0.6.0.2 PMID Evidence)
-- ----------------------------------------------------------------------------
-- Purpose: Assess tumor immune microenvironment for checkpoint inhibitor therapy with evidence
-- Clinical Value: Pembrolizumab approved for PD-L1+ TNBC (CPS ≥10)

SELECT
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
    CASE
        WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
        ELSE 'Limited publications'
    END as evidence_level,
    CASE
        WHEN g.gene_symbol = 'CD274' AND COALESCE(pe.expression_fold_change, 1.0) >= 2.0
            THEN '🎯 PD-L1 HIGH: Pembrolizumab + Chemotherapy (FDA approved)'
        WHEN g.gene_symbol = 'CD274' AND COALESCE(pe.expression_fold_change, 1.0) >= 1.5
            THEN '⚠️ PD-L1 POSITIVE: Consider Pembrolizumab combination'
        WHEN g.gene_symbol = 'CD8A' AND COALESCE(pe.expression_fold_change, 1.0) >= 2.5
            THEN '✅ HIGH T-CELL INFILTRATION: Immune-hot tumor'
        WHEN g.gene_symbol IN ('PDCD1', 'CTLA4')
             AND COALESCE(pe.expression_fold_change, 1.0) >= 1.8
            THEN '📍 IMMUNE CHECKPOINT EXPRESSION: Favorable for immunotherapy'
        WHEN g.gene_symbol = 'CD274' AND COALESCE(pe.expression_fold_change, 1.0) < 1.2
            THEN '❌ PD-L1 LOW: Immunotherapy unlikely to benefit'
    END as immunotherapy_status,
    CASE
        WHEN g.gene_symbol = 'CD274' AND COALESCE(pe.expression_fold_change, 1.0) >= 2.0
            THEN 'Pembrolizumab 200mg Q3W + Carboplatin/Paclitaxel (KEYNOTE-355 regimen)'
        WHEN g.gene_symbol = 'CD8A' AND COALESCE(pe.expression_fold_change, 1.0) >= 2.5
            THEN 'Checkpoint inhibitor combination (clinical trial)'
    END as drug_recommendation
FROM public.genes g
JOIN public.transcripts t ON g.gene_id = t.gene_id
LEFT JOIN patient_synthetic_tnbc.expression_data pe ON t.transcript_id = pe.transcript_id
LEFT JOIN public.gene_publications gp ON g.gene_id = gp.gene_id
WHERE g.gene_symbol IN (
    'CD274',  -- PD-L1
    'PDCD1',  -- PD-1
    'CD8A', 'CD8B',  -- T-cell markers
    'CTLA4', 'LAG3', 'TIM3',  -- Immune checkpoints
    'IFNG', 'GZMB'  -- Immune activation
)
GROUP BY g.gene_symbol, pe.expression_fold_change
ORDER BY publication_count DESC, COALESCE(pe.expression_fold_change, 1.0) DESC;

-- Expected Results:
-- - CD274 ≥2.0x → PD-L1+ (40% of TNBC) → Pembrolizumab + chemo
-- - CD8A ≥2.5x → Immune-hot (20% of TNBC) → Better immunotherapy response
-- - CD274 <1.2x → Immune-cold → Chemotherapy only


-- ============================================================================
-- SECTION 3: LUNG ADENOCARCINOMA EGFR-MUTANT (LUAD-EGFR+) QUERIES
-- ============================================================================
-- Clinical Context: EGFR-activating mutations (exon 19 del, L858R)
-- Standard of Care: Osimertinib (3rd-gen EGFR TKI)
-- Resistance: T790M (osimertinib), MET amplification, BRAF mutations

-- ----------------------------------------------------------------------------
-- Query 3.1: EGFR-Mutant LUAD Primary Target Confirmation (v0.6.0.2 PMID Evidence)
-- ----------------------------------------------------------------------------
-- Purpose: Confirm EGFR pathway activation and identify mutation signature with evidence
-- Clinical Value: Validates EGFR TKI therapy (osimertinib first-line)

SELECT
    g.gene_symbol,
    g.gene_name,
    pe.expression_fold_change,
    COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
    CASE
        WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
        ELSE 'Limited publications'
    END as evidence_level,
    CASE
        WHEN g.gene_symbol = 'EGFR' AND pe.expression_fold_change >= 4.0
            THEN '🎯 PRIMARY TARGET: Osimertinib 80mg daily (first-line)'
        WHEN g.gene_symbol = 'EGFR' AND pe.expression_fold_change >= 2.5
            THEN '🎯 EGFR ACTIVATION: Confirm mutation status (exon 19del/L858R)'
        WHEN g.gene_symbol IN ('ERBB2', 'ERBB3') AND pe.expression_fold_change > 2.5
            THEN '📍 HETERODIMERIZATION PARTNERS: EGFR signaling active'
        WHEN g.gene_symbol = 'KRAS' AND pe.expression_fold_change < 1.5
            THEN '✅ KRAS LOW: Mutually exclusive with EGFR (expected)'
    END as egfr_target_status,
    'Osimertinib 80mg PO daily (FLAURA trial: 18.9mo median PFS)' as first_line_therapy
FROM patient_synthetic_luad.expression_data pe
JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
JOIN public.genes g ON t.gene_id = g.gene_id
LEFT JOIN public.gene_publications gp ON g.gene_id = gp.gene_id
WHERE g.gene_symbol IN (
    'EGFR', 'ERBB2', 'ERBB3', 'ERBB4',
    'KRAS', 'BRAF', 'ALK', 'ROS1'  -- Exclusionary markers
)
GROUP BY g.gene_symbol, g.gene_name, pe.expression_fold_change
ORDER BY publication_count DESC, pe.expression_fold_change DESC;

-- Expected Results:
-- - EGFR ≥4.0x → Confirms EGFR-driven tumor → Osimertinib
-- - KRAS <1.5x → Mutually exclusive (correct EGFR classification)
-- - ERBB3 >2.5x → Heterodimerization partner (signaling active)


-- ----------------------------------------------------------------------------
-- Query 3.2: EGFR TKI Resistance Mechanism Surveillance (v0.6.0.2 PMID Evidence)
-- ----------------------------------------------------------------------------
-- Purpose: Identify resistance pathways (MET, BRAF, PIK3CA, EMT) with evidence
-- Clinical Value: Guides salvage therapy or combination strategies

SELECT
    g.gene_symbol,
    pe.expression_fold_change,
    COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
    CASE
        WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
        ELSE 'Limited publications'
    END as evidence_level,
    CASE
        WHEN g.gene_symbol = 'MET' AND pe.expression_fold_change >= 3.0
            THEN '🔴 MET AMPLIFICATION: Add Crizotinib or Capmatinib (MET inhibitor)'
        WHEN g.gene_symbol = 'BRAF' AND pe.expression_fold_change >= 2.5
            THEN '🔴 BRAF ACTIVATION: Consider BRAF inhibitor (dabrafenib)'
        WHEN g.gene_symbol = 'PIK3CA' AND pe.expression_fold_change >= 2.5
            THEN '🔴 PI3K PATHWAY ACTIVATION: Resistance to EGFR TKI'
        WHEN g.gene_symbol = 'VIM' AND pe.expression_fold_change >= 3.0
            THEN '🔴 EMT SIGNATURE: Vimentin high → EGFR TKI resistance'
        WHEN g.gene_symbol = 'CDH1' AND pe.expression_fold_change < 0.5
            THEN '🔴 E-CADHERIN LOSS: EMT → Poor TKI response'
    END as resistance_mechanism,
    CASE
        WHEN g.gene_symbol = 'MET' AND pe.expression_fold_change >= 3.0
            THEN 'Osimertinib + Crizotinib combination (clinical trial)'
        WHEN g.gene_symbol = 'BRAF' AND pe.expression_fold_change >= 2.5
            THEN 'Dabrafenib + Trametinib (BRAF + MEK inhibition)'
        WHEN g.gene_symbol = 'VIM' AND pe.expression_fold_change >= 3.0
            THEN 'Switch to chemotherapy (EMT reduces TKI efficacy)'
    END as salvage_therapy
FROM patient_synthetic_luad.expression_data pe
JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
JOIN public.genes g ON t.gene_id = g.gene_id
LEFT JOIN public.gene_publications gp ON g.gene_id = gp.gene_id
WHERE g.gene_symbol IN (
    'MET', 'BRAF', 'PIK3CA', 'AKT1',
    'VIM', 'CDH1', 'CDH2',  -- EMT markers
    'AXL', 'TWIST1'  -- EMT transcription factors
)
GROUP BY g.gene_symbol, pe.expression_fold_change
ORDER BY publication_count DESC, pe.expression_fold_change DESC;

-- Expected Results:
-- - MET ≥3.0x → MET amplification (10-15% of TKI resistance) → Add crizotinib
-- - VIM ≥3.0x + CDH1 <0.5x → EMT phenotype → Switch to chemotherapy
-- - BRAF ≥2.5x → BRAF activation (rare) → BRAF/MEK inhibitor combination


-- ----------------------------------------------------------------------------
-- Query 3.3: EGFR-Mutant Angiogenesis Pathway (Bevacizumab Combination) (v0.6.0.2 PMID Evidence)
-- ----------------------------------------------------------------------------
-- Purpose: Assess VEGF pathway activation for anti-angiogenic combination with evidence
-- Clinical Value: Osimertinib + Bevacizumab improves PFS (NEJ026, ARTEMIS-CTONG1509)

SELECT
    g.gene_symbol,
    pe.expression_fold_change,
    COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
    CASE
        WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
        ELSE 'Limited publications'
    END as evidence_level,
    CASE
        WHEN g.gene_symbol = 'VEGFA' AND pe.expression_fold_change >= 3.5
            THEN '🎯 HIGH VEGFA: Add Bevacizumab to Osimertinib (NEJ026 trial)'
        WHEN g.gene_symbol IN ('ANGPT2', 'FGF2') AND pe.expression_fold_change >= 2.5
            THEN '📍 ANGIOGENESIS ACTIVE: Bevacizumab combination likely beneficial'
        WHEN g.gene_symbol = 'VEGFA' AND pe.expression_fold_change < 2.0
            THEN '✅ LOW VEGFA: Osimertinib monotherapy sufficient'
    END as angiogenesis_status,
    CASE
        WHEN g.gene_symbol = 'VEGFA' AND pe.expression_fold_change >= 3.5
            THEN 'Osimertinib 80mg daily + Bevacizumab 15mg/kg Q3W'
    END as combination_therapy
FROM patient_synthetic_luad.expression_data pe
JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
JOIN public.genes g ON t.gene_id = g.gene_id
LEFT JOIN public.gene_publications gp ON g.gene_id = gp.gene_id
WHERE g.gene_symbol IN (
    'VEGFA', 'VEGFB', 'VEGFC',
    'KDR',  -- VEGFR2
    'ANGPT1', 'ANGPT2',
    'FGF2', 'PDGFB'
)
GROUP BY g.gene_symbol, pe.expression_fold_change
ORDER BY publication_count DESC, pe.expression_fold_change DESC;

-- Expected Results:
-- - VEGFA ≥3.5x → High angiogenesis (50% of EGFR+ LUAD)
-- - Recommendation: Osimertinib + Bevacizumab (17.5mo vs 10.2mo PFS in NEJ026)


-- ============================================================================
-- SECTION 4: MSI-HIGH COLORECTAL CANCER (CRC-MSI) QUERIES
-- ============================================================================
-- Clinical Context: Mismatch repair deficiency (dMMR) → Microsatellite instability
-- Standard of Care: Pembrolizumab or Nivolumab (immune checkpoint inhibitors)
-- Biomarker: MSI-H/dMMR status, high tumor mutational burden (TMB)

-- ----------------------------------------------------------------------------
-- Query 4.1: MSI-H CRC Mismatch Repair Deficiency Signature (v0.6.0.2 PMID Evidence)
-- ----------------------------------------------------------------------------
-- Purpose: Identify MMR gene loss and immune infiltration with evidence
-- Clinical Value: Confirms immunotherapy eligibility (pembrolizumab FDA approved)

SELECT
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
    CASE
        WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
        ELSE 'Limited publications'
    END as evidence_level,
    CASE
        WHEN g.gene_symbol IN ('MLH1', 'MSH2', 'MSH6', 'PMS2')
             AND COALESCE(pe.expression_fold_change, 1.0) < 0.4
            THEN '🎯 MMR DEFICIENCY: Pembrolizumab 200mg Q3W or Nivolumab 240mg Q2W'
        WHEN g.gene_symbol = 'CD274' AND COALESCE(pe.expression_fold_change, 1.0) >= 2.5
            THEN '✅ PD-L1 HIGH: Favorable for immunotherapy (expected in MSI-H)'
        WHEN g.gene_symbol IN ('CD8A', 'CD8B')
             AND COALESCE(pe.expression_fold_change, 1.0) >= 3.0
            THEN '✅ HIGH T-CELL INFILTRATION: Immune-hot tumor (MSI-H hallmark)'
        WHEN g.gene_symbol IN ('IFNG', 'GZMB')
             AND COALESCE(pe.expression_fold_change, 1.0) >= 2.5
            THEN '✅ IMMUNE ACTIVATION: Good immunotherapy response expected'
    END as msi_immunotherapy_status,
    'Pembrolizumab 200mg Q3W (KEYNOTE-177: 16.5mo vs 8.2mo median PFS)' as first_line_therapy
FROM public.genes g
JOIN public.transcripts t ON g.gene_id = t.gene_id
LEFT JOIN patient_synthetic_her2.expression_data pe ON t.transcript_id = pe.transcript_id
LEFT JOIN public.gene_publications gp ON g.gene_id = gp.gene_id
WHERE g.gene_symbol IN (
    'MLH1', 'MSH2', 'MSH6', 'PMS2',  -- MMR genes
    'CD274', 'PDCD1',  -- PD-L1/PD-1
    'CD8A', 'CD8B', 'CD4',  -- T-cell markers
    'IFNG', 'GZMB', 'PRF1',  -- Cytotoxic markers
    'CTLA4', 'LAG3'  -- Alternative checkpoints
)
GROUP BY g.gene_symbol, pe.expression_fold_change
ORDER BY g.gene_symbol;

-- Expected Results:
-- - MLH1/MSH2 <0.4x → dMMR/MSI-H (15% of CRC) → Pembrolizumab first-line
-- - CD8A/CD274 ≥2.5x → Immune-hot (hallmark of MSI-H)
-- - KEYNOTE-177: 83% response rate in MSI-H CRC with pembrolizumab


-- ----------------------------------------------------------------------------
-- Query 4.2: MSI-H CRC WNT/β-Catenin Pathway Analysis
-- ----------------------------------------------------------------------------
-- Purpose: Assess WNT pathway mutations (common in CRC, affects immune response)
-- Clinical Value: CTNNB1 activation may reduce immunotherapy efficacy

SELECT
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    CASE
        WHEN g.gene_symbol IN ('CTNNB1', 'TCF7L2')
             AND COALESCE(pe.expression_fold_change, 1.0) >= 2.5
            THEN '⚠️ WNT PATHWAY ACTIVATION: May reduce immunotherapy efficacy'
        WHEN g.gene_symbol IN ('APC', 'AXIN2')
             AND COALESCE(pe.expression_fold_change, 1.0) < 0.5
            THEN '📍 TUMOR SUPPRESSOR LOSS: WNT pathway deregulation (common CRC)'
        WHEN g.gene_symbol = 'MYC' AND COALESCE(pe.expression_fold_change, 1.0) >= 3.0
            THEN '📍 MYC AMPLIFICATION: Aggressive phenotype'
    END as wnt_pathway_status
FROM public.genes g
JOIN public.transcripts t ON g.gene_id = t.gene_id
LEFT JOIN patient_synthetic_her2.expression_data pe ON t.transcript_id = pe.transcript_id
WHERE g.gene_symbol IN (
    'APC', 'CTNNB1', 'AXIN1', 'AXIN2',
    'TCF7L2', 'LEF1',
    'MYC', 'CCND1'
)
ORDER BY COALESCE(pe.expression_fold_change, 1.0) DESC;


-- ============================================================================
-- SECTION 5: KRAS-MUTANT PANCREATIC ADENOCARCINOMA (PDAC) QUERIES
-- ============================================================================
-- Clinical Context: KRAS G12C/G12D/G12V mutations (90% of PDAC)
-- Standard of Care: FOLFIRINOX or Gemcitabine/nab-Paclitaxel
-- Emerging: KRAS G12C inhibitors (sotorasib, adagrasib)

-- ----------------------------------------------------------------------------
-- Query 5.1: PDAC KRAS Pathway Activation and Targeting (v0.6.0.2 PMID Evidence)
-- ----------------------------------------------------------------------------
-- Purpose: Identify KRAS and downstream effector activation with evidence
-- Clinical Value: KRAS G12C inhibitor eligibility (if G12C mutation confirmed)

SELECT
    g.gene_symbol,
    pe.expression_fold_change,
    COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
    CASE
        WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
        ELSE 'Limited publications'
    END as evidence_level,
    CASE
        WHEN g.gene_symbol = 'KRAS' AND pe.expression_fold_change >= 3.0
            THEN '🎯 KRAS HIGH: Confirm G12C mutation for sotorasib/adagrasib eligibility'
        WHEN g.gene_symbol IN ('MAPK1', 'MAPK3') AND pe.expression_fold_change >= 2.5
            THEN '📍 MAPK PATHWAY ACTIVATION: Downstream KRAS effector'
        WHEN g.gene_symbol = 'MYC' AND pe.expression_fold_change >= 3.5
            THEN '📍 MYC AMPLIFICATION: KRAS-driven proliferation'
        WHEN g.gene_symbol = 'TP53' AND pe.expression_fold_change < 0.3
            THEN '📍 TP53 LOSS: Common co-mutation with KRAS in PDAC (90%)'
    END as kras_pathway_status,
    CASE
        WHEN g.gene_symbol = 'KRAS' AND pe.expression_fold_change >= 3.0
            THEN 'If KRAS G12C: Sotorasib 960mg daily (CodeBreaK 100 trial)'
        ELSE 'FOLFIRINOX or Gem/Abraxane (no KRAS-targeted therapy yet)'
    END as treatment_recommendation
FROM patient_synthetic_luad.expression_data pe
JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
JOIN public.genes g ON t.gene_id = g.gene_id
LEFT JOIN public.gene_publications gp ON g.gene_id = gp.gene_id
WHERE g.gene_symbol IN (
    'KRAS', 'NRAS', 'HRAS',
    'MAPK1', 'MAPK3',  -- ERK1/2
    'MAP2K1', 'MAP2K2',  -- MEK1/2
    'RAF1', 'BRAF',
    'MYC', 'TP53'
)
GROUP BY g.gene_symbol, pe.expression_fold_change
ORDER BY publication_count DESC, pe.expression_fold_change DESC;

-- Expected Results:
-- - KRAS ≥3.0x → KRAS-driven PDAC (90% have KRAS mutation)
-- - If G12C mutation: Sotorasib (12% response rate in PDAC, lower than NSCLC)
-- - TP53 <0.3x → Co-mutation in 75% of PDAC


-- ----------------------------------------------------------------------------
-- Query 5.2: PDAC DNA Damage Response and Synthetic Lethality (v0.6.0.2 PMID Evidence)
-- ----------------------------------------------------------------------------
-- Purpose: Identify ATM/BRCA2 deficiency → PARP inhibitor or platinum sensitivity with evidence
-- Clinical Value: 5-10% of PDAC have germline BRCA1/2 → Olaparib maintenance

SELECT
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
    CASE
        WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
        ELSE 'Limited publications'
    END as evidence_level,
    CASE
        WHEN g.gene_symbol IN ('BRCA1', 'BRCA2')
             AND COALESCE(pe.expression_fold_change, 1.0) < 0.5
            THEN '🎯 BRCA DEFICIENCY: Olaparib maintenance (POLO trial)'
        WHEN g.gene_symbol = 'ATM' AND COALESCE(pe.expression_fold_change, 1.0) < 0.5
            THEN '📍 ATM LOSS: Platinum-sensitive, consider PARP inhibitor'
        WHEN g.gene_symbol IN ('PALB2', 'RAD51')
             AND COALESCE(pe.expression_fold_change, 1.0) < 0.6
            THEN '📍 HRD SIGNATURE: Platinum-based chemotherapy'
    END as ddr_deficiency_status,
    CASE
        WHEN g.gene_symbol IN ('BRCA1', 'BRCA2')
             AND COALESCE(pe.expression_fold_change, 1.0) < 0.5
            THEN 'Platinum-based induction → Olaparib 300mg BID maintenance (POLO: 7.4mo vs 3.8mo PFS)'
    END as treatment_recommendation
FROM public.genes g
JOIN public.transcripts t ON g.gene_id = t.gene_id
LEFT JOIN patient_synthetic_luad.expression_data pe ON t.transcript_id = pe.transcript_id
LEFT JOIN public.gene_publications gp ON g.gene_id = gp.gene_id
WHERE g.gene_symbol IN (
    'BRCA1', 'BRCA2', 'PALB2',
    'ATM', 'ATR', 'CHEK1', 'CHEK2',
    'RAD51', 'RAD51C',
    'FANCA', 'FANCF'
)
GROUP BY g.gene_symbol, pe.expression_fold_change
ORDER BY COALESCE(pe.expression_fold_change, 1.0) ASC;

-- Expected Results:
-- - BRCA2 <0.5x → 5-7% of PDAC → Olaparib maintenance after platinum
-- - ATM <0.5x → ATM mutations in 5% of PDAC → Platinum-sensitive
-- - POLO trial: Olaparib maintenance doubled PFS (7.4mo vs 3.8mo)


-- ============================================================================
-- USAGE INSTRUCTIONS
-- ============================================================================

/*
To use these queries:

1. Connect to the mbase database:
   psql -h localhost -p 5435 -U mbase_user -d mbase

2. Replace patient schema name in queries:
   - patient_synthetic_her2 → patient_<YOUR_PATIENT_ID>
   - patient_synthetic_tnbc → patient_<YOUR_PATIENT_ID>
   - patient_synthetic_luad → patient_<YOUR_PATIENT_ID>

3. Example:
   For patient "PATIENT123" with HER2+ breast cancer:

   -- Change this:
   FROM patient_synthetic_her2.expression_data pe

   -- To this:
   FROM patient_patient123.expression_data pe

4. Run query sections relevant to your patient's cancer type:
   - Section 1: HER2+ Breast Cancer
   - Section 2: Triple-Negative Breast Cancer (TNBC)
   - Section 3: Lung Adenocarcinoma EGFR-mutant
   - Section 4: MSI-High Colorectal Cancer
   - Section 5: KRAS-mutant Pancreatic Adenocarcinoma

5. Interpret results in clinical context:
   - 🎯 = Primary therapeutic target (FDA-approved or guideline-recommended)
   - 📍 = Biomarker or pathway finding (clinical relevance)
   - ✅ = Positive/favorable finding
   - ❌ = Negative/unfavorable finding
   - 🔴 = Resistance mechanism or adverse feature
   - ⚠️ = Caution/monitor

IMPORTANT NOTES:
- These queries are for research and clinical decision support only
- Always confirm molecular findings with clinical-grade genomic testing
- Drug recommendations should be reviewed by oncology team
- Fold-change thresholds are approximations based on literature
- Consider patient's performance status, comorbidities, and preferences
*/


-- ============================================================================
-- CLINICAL TRIAL MATCHING QUERIES (BONUS)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Cross-Cancer Actionable Target Summary (v0.6.0.2 PMID Evidence)
-- ----------------------------------------------------------------------------
-- Purpose: Identify all potential therapeutic targets across cancer types with evidence
-- Clinical Value: Quick overview of druggable alterations for trial matching

SELECT
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
    CASE
        WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
        ELSE 'Limited publications'
    END as evidence_level,
    CASE
        WHEN g.gene_symbol IN ('ERBB2', 'EGFR', 'MET', 'ALK', 'ROS1', 'RET', 'NTRK1', 'NTRK2', 'NTRK3')
             AND COALESCE(pe.expression_fold_change, 1.0) >= 3.0
            THEN '🎯 ACTIONABLE TARGET: FDA-approved targeted therapy available'
        WHEN g.gene_symbol IN ('BRCA1', 'BRCA2', 'ATM', 'PALB2')
             AND COALESCE(pe.expression_fold_change, 1.0) < 0.5
            THEN '🎯 DDR DEFICIENCY: PARP inhibitor eligible'
        WHEN g.gene_symbol = 'CD274' AND COALESCE(pe.expression_fold_change, 1.0) >= 2.0
            THEN '🎯 PD-L1 HIGH: Checkpoint inhibitor eligible'
        WHEN g.gene_symbol IN ('PIK3CA', 'AKT1', 'MTOR', 'PTEN')
             AND COALESCE(pe.expression_fold_change, 1.0) != 1.0
            THEN '📍 PI3K/AKT PATHWAY: Clinical trial targets'
        WHEN g.gene_symbol IN ('KRAS', 'BRAF', 'MAP2K1')
             AND COALESCE(pe.expression_fold_change, 1.0) >= 2.5
            THEN '📍 MAPK PATHWAY: Emerging targets'
    END as actionable_target_class,
    CASE
        WHEN g.gene_symbol = 'ERBB2' AND COALESCE(pe.expression_fold_change, 1.0) >= 3.0
            THEN 'Trastuzumab, Pertuzumab, Trastuzumab-deruxtecan, Tucatinib'
        WHEN g.gene_symbol = 'EGFR' AND COALESCE(pe.expression_fold_change, 1.0) >= 3.0
            THEN 'Osimertinib, Erlotinib, Afatinib'
        WHEN g.gene_symbol = 'MET' AND COALESCE(pe.expression_fold_change, 1.0) >= 3.0
            THEN 'Crizotinib, Capmatinib, Tepotinib'
        WHEN g.gene_symbol = 'CD274' AND COALESCE(pe.expression_fold_change, 1.0) >= 2.0
            THEN 'Pembrolizumab, Nivolumab, Atezolizumab'
        WHEN g.gene_symbol IN ('BRCA1', 'BRCA2') AND COALESCE(pe.expression_fold_change, 1.0) < 0.5
            THEN 'Olaparib, Talazoparib, Rucaparib'
    END as available_drugs
FROM public.genes g
JOIN public.transcripts t ON g.gene_id = t.gene_id
LEFT JOIN patient_synthetic_her2.expression_data pe ON t.transcript_id = pe.transcript_id
LEFT JOIN public.gene_publications gp ON g.gene_id = gp.gene_id
WHERE g.gene_symbol IN (
    -- Receptor tyrosine kinases
    'ERBB2', 'EGFR', 'MET', 'ALK', 'ROS1', 'RET',
    'NTRK1', 'NTRK2', 'NTRK3', 'FGFR1', 'FGFR2', 'FGFR3',
    -- PI3K/AKT pathway
    'PIK3CA', 'AKT1', 'MTOR', 'PTEN',
    -- MAPK pathway
    'KRAS', 'NRAS', 'BRAF', 'MAP2K1',
    -- DNA repair
    'BRCA1', 'BRCA2', 'ATM', 'PALB2',
    -- Immune checkpoints
    'CD274', 'PDCD1', 'CTLA4'
)
AND (
    COALESCE(pe.expression_fold_change, 1.0) >= 2.5
    OR COALESCE(pe.expression_fold_change, 1.0) < 0.6
)
GROUP BY g.gene_symbol, pe.expression_fold_change
ORDER BY
    publication_count DESC,
    CASE
        WHEN COALESCE(pe.expression_fold_change, 1.0) >= 3.0 THEN 1
        WHEN COALESCE(pe.expression_fold_change, 1.0) < 0.5 THEN 2
        ELSE 3
    END,
    COALESCE(pe.expression_fold_change, 1.0) DESC;

-- ============================================================================
-- END OF CANCER-SPECIFIC QUERIES
-- ============================================================================

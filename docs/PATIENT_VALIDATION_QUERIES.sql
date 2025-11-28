-- ============================================================================
-- MEDIABASE Patient Schema Biological Validation Queries (v0.6.0)
-- ============================================================================
-- Version: 0.6.0
-- Status: PRODUCTION READY
-- Purpose: Validate patient-specific schemas in shared core architecture
--
-- Architecture: v0.6.0 Shared Core
-- - Single database (mbase) with public schema + patient schemas
-- - Patient schemas: patient_<ID> containing expression_data + metadata
-- - Sparse storage: Only expression_fold_change != 1.0 stored
-- - Query pattern: LEFT JOIN with COALESCE for baseline values
--
-- Usage: Replace ${PATIENT_ID} with actual patient identifier
-- Example: patient_DEMO_BREAST_HER2, patient_TNBC_001, patient_LUAD_EGFR
--
-- For implementation details, see:
--   - docs/PATIENT_DATABASE_GUIDE.md (Section: Biological Validation)
--   - WORKING_QUERY_EXAMPLES.sql (v0.6.0 query patterns)
--   - src/db/patient_schema_template.sql (Schema structure)
-- ============================================================================

-- ============================================================================
-- SECTION A: DATA INTEGRITY CHECKS
-- ============================================================================
-- Purpose: Validate schema structure and data consistency
-- Run these first to ensure data quality before biological analysis

-- ----------------------------------------------------------------------------
-- A1: Sparse Storage Violation Check
-- ----------------------------------------------------------------------------
-- Purpose: Verify sparse storage constraint (no fold_change = 1.0)
-- Expected: 0 rows (constraint should prevent this)

SELECT
    'A1: Sparse Storage Violation' as check_name,
    COUNT(*) as violation_count,
    CASE
        WHEN COUNT(*) = 0 THEN '✓ PASS'
        ELSE '✗ FAIL - Constraint not enforced'
    END as status
FROM patient_${PATIENT_ID}.expression_data
WHERE expression_fold_change = 1.0;

-- Expected Output:
-- check_name                    | violation_count | status
-- ------------------------------|-----------------|-------
-- A1: Sparse Storage Violation  | 0               | ✓ PASS

-- ----------------------------------------------------------------------------
-- A2: Orphaned Transcript Check
-- ----------------------------------------------------------------------------
-- Purpose: Verify all transcript_ids exist in public.transcripts
-- Expected: 0 orphaned transcripts

SELECT
    'A2: Orphaned Transcripts' as check_name,
    COUNT(*) as orphaned_count,
    CASE
        WHEN COUNT(*) = 0 THEN '✓ PASS'
        ELSE '✗ FAIL - Invalid transcript_ids present'
    END as status
FROM patient_${PATIENT_ID}.expression_data pe
LEFT JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
WHERE t.transcript_id IS NULL;

-- Expected Output:
-- check_name              | orphaned_count | status
-- ------------------------|----------------|-------
-- A2: Orphaned Transcripts| 0              | ✓ PASS

-- ----------------------------------------------------------------------------
-- A3: Negative Fold-Change Check
-- ----------------------------------------------------------------------------
-- Purpose: Verify all fold changes are positive
-- Expected: 0 negative values (constraint should prevent this)

SELECT
    'A3: Negative Fold Changes' as check_name,
    COUNT(*) as negative_count,
    CASE
        WHEN COUNT(*) = 0 THEN '✓ PASS'
        ELSE '✗ FAIL - Negative values present'
    END as status
FROM patient_${PATIENT_ID}.expression_data
WHERE expression_fold_change <= 0;

-- Expected Output:
-- check_name                 | negative_count | status
-- ---------------------------|----------------|-------
-- A3: Negative Fold Changes  | 0              | ✓ PASS

-- ----------------------------------------------------------------------------
-- A4: Expression Distribution Statistics
-- ----------------------------------------------------------------------------
-- Purpose: Overall expression profile statistics
-- Expected: Reasonable distribution with biological range

SELECT
    'A4: Expression Statistics' as check_name,
    COUNT(*) as total_expressed_transcripts,
    ROUND(AVG(expression_fold_change)::numeric, 2) as mean_fold_change,
    ROUND(percentile_cont(0.5) WITHIN GROUP (ORDER BY expression_fold_change)::numeric, 2) as median_fold_change,
    ROUND(MIN(expression_fold_change)::numeric, 4) as min_fold_change,
    ROUND(MAX(expression_fold_change)::numeric, 2) as max_fold_change,
    COUNT(CASE WHEN expression_fold_change > 2.0 THEN 1 END) as overexpressed_count,
    COUNT(CASE WHEN expression_fold_change < 0.5 THEN 1 END) as underexpressed_count
FROM patient_${PATIENT_ID}.expression_data;

-- Expected Output (example for HER2+ breast cancer):
-- check_name              | total | mean | median | min    | max   | over | under
-- ------------------------|-------|------|--------|--------|-------|------|------
-- A4: Expression Stats    | 450   | 1.85 | 1.32   | 0.0523 | 8.42  | 125  | 78

-- ----------------------------------------------------------------------------
-- A5: Metadata Completeness Check
-- ----------------------------------------------------------------------------
-- Purpose: Verify patient metadata is populated
-- Expected: 1 row with key fields populated

SELECT
    'A5: Metadata Completeness' as check_name,
    COUNT(*) as metadata_rows,
    SUM(CASE WHEN patient_id IS NOT NULL THEN 1 ELSE 0 END) as has_patient_id,
    SUM(CASE WHEN cancer_type IS NOT NULL THEN 1 ELSE 0 END) as has_cancer_type,
    SUM(CASE WHEN matching_success_rate IS NOT NULL THEN 1 ELSE 0 END) as has_success_rate,
    CASE
        WHEN COUNT(*) = 1 AND MIN(patient_id) IS NOT NULL THEN '✓ PASS'
        ELSE '✗ FAIL - Metadata incomplete'
    END as status
FROM patient_${PATIENT_ID}.metadata;

-- Expected Output:
-- check_name                | metadata_rows | has_patient_id | has_cancer_type | has_success_rate | status
-- --------------------------|---------------|----------------|-----------------|------------------|-------
-- A5: Metadata Completeness| 1             | 1              | 1               | 1                | ✓ PASS


-- ============================================================================
-- SECTION B: PHENOTYPE VALIDATION
-- ============================================================================
-- Purpose: Validate cancer-specific molecular signatures
-- Compare patient expression to known cancer phenotypes

-- ----------------------------------------------------------------------------
-- B1: HER2+ Breast Cancer Signature Validation
-- ----------------------------------------------------------------------------
-- Purpose: Verify HER2+ signature (ERBB2 amplification, ER/PR variable)
-- Expected: ERBB2 > 4.0, GRB7 > 3.0, high proliferation

SELECT
    'B1: HER2+ Signature' as check_name,
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    CASE
        WHEN g.gene_symbol = 'ERBB2' AND COALESCE(pe.expression_fold_change, 1.0) > 4.0
            THEN '✓ PASS - Strong HER2 amplification'
        WHEN g.gene_symbol = 'ERBB2' AND COALESCE(pe.expression_fold_change, 1.0) BETWEEN 2.0 AND 4.0
            THEN '~ BORDERLINE - Moderate HER2'
        WHEN g.gene_symbol = 'ERBB2'
            THEN '✗ FAIL - HER2 not amplified'
        WHEN g.gene_symbol = 'GRB7' AND COALESCE(pe.expression_fold_change, 1.0) > 3.0
            THEN '✓ PASS - Co-amplified with HER2'
        WHEN g.gene_symbol IN ('MKI67', 'CCND1') AND COALESCE(pe.expression_fold_change, 1.0) > 2.5
            THEN '✓ PASS - High proliferation'
        WHEN g.gene_symbol IN ('ESR1', 'PGR')
            THEN 'INFO - ER/PR status (can be positive or negative in HER2+)'
        ELSE 'INFO - Supporting marker'
    END as validation_status
FROM public.transcripts t
LEFT JOIN patient_${PATIENT_ID}.expression_data pe ON t.transcript_id = pe.transcript_id
JOIN public.genes g ON t.gene_id = g.gene_id
WHERE g.gene_symbol IN ('ERBB2', 'GRB7', 'PGAP3', 'MKI67', 'CCND1', 'ESR1', 'PGR')
ORDER BY
    CASE g.gene_symbol
        WHEN 'ERBB2' THEN 1
        WHEN 'GRB7' THEN 2
        ELSE 3
    END,
    fold_change DESC;

-- Expected Output (for HER2+ patient):
-- check_name        | gene_symbol | fold_change | validation_status
-- ------------------|-------------|-------------|------------------
-- B1: HER2+ Signature| ERBB2      | 6.24        | ✓ PASS - Strong HER2 amplification
-- B1: HER2+ Signature| GRB7       | 4.18        | ✓ PASS - Co-amplified with HER2
-- B1: HER2+ Signature| MKI67      | 3.52        | ✓ PASS - High proliferation

-- ----------------------------------------------------------------------------
-- B2: Triple-Negative Breast Cancer (TNBC) Signature Validation
-- ----------------------------------------------------------------------------
-- Purpose: Verify TNBC signature (ER-/PR-/HER2-, basal markers high)
-- Expected: ESR1/PGR/ERBB2 low, KRT5/KRT14/EGFR high, TP53 often low

SELECT
    'B2: TNBC Signature' as check_name,
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    CASE
        WHEN g.gene_symbol IN ('ESR1', 'PGR') AND COALESCE(pe.expression_fold_change, 1.0) < 0.5
            THEN '✓ PASS - ER/PR negative'
        WHEN g.gene_symbol = 'ERBB2' AND COALESCE(pe.expression_fold_change, 1.0) < 1.5
            THEN '✓ PASS - HER2 negative'
        WHEN g.gene_symbol IN ('KRT5', 'KRT14', 'KRT17') AND COALESCE(pe.expression_fold_change, 1.0) > 3.0
            THEN '✓ PASS - Basal-like markers'
        WHEN g.gene_symbol = 'EGFR' AND COALESCE(pe.expression_fold_change, 1.0) > 2.5
            THEN '✓ PASS - Basal EGFR expression'
        WHEN g.gene_symbol = 'MKI67' AND COALESCE(pe.expression_fold_change, 1.0) > 4.0
            THEN '✓ PASS - Very high proliferation'
        WHEN g.gene_symbol = 'TP53' AND COALESCE(pe.expression_fold_change, 1.0) < 0.5
            THEN 'INFO - TP53 loss (common in TNBC)'
        ELSE 'INFO - Supporting marker'
    END as validation_status
FROM public.transcripts t
LEFT JOIN patient_${PATIENT_ID}.expression_data pe ON t.transcript_id = pe.transcript_id
JOIN public.genes g ON t.gene_id = g.gene_id
WHERE g.gene_symbol IN ('ESR1', 'PGR', 'ERBB2', 'KRT5', 'KRT14', 'KRT17', 'EGFR', 'MKI67', 'TP53', 'BRCA1')
ORDER BY
    CASE
        WHEN g.gene_symbol IN ('ESR1', 'PGR', 'ERBB2') THEN 1
        WHEN g.gene_symbol IN ('KRT5', 'KRT14', 'EGFR') THEN 2
        ELSE 3
    END,
    fold_change DESC;

-- Expected Output (for TNBC patient):
-- check_name        | gene_symbol | fold_change | validation_status
-- ------------------|-------------|-------------|------------------
-- B2: TNBC Signature| ESR1        | 0.18        | ✓ PASS - ER/PR negative
-- B2: TNBC Signature| PGR         | 0.22        | ✓ PASS - ER/PR negative
-- B2: TNBC Signature| ERBB2       | 0.85        | ✓ PASS - HER2 negative
-- B2: TNBC Signature| KRT5        | 4.38        | ✓ PASS - Basal-like markers
-- B2: TNBC Signature| MKI67       | 5.72        | ✓ PASS - Very high proliferation

-- ----------------------------------------------------------------------------
-- B3: Lung Adenocarcinoma EGFR-Mutant Signature Validation
-- ----------------------------------------------------------------------------
-- Purpose: Verify EGFR+ signature (EGFR high, KRAS normal, lung markers low)
-- Expected: EGFR > 3.5, surfactant proteins low, angiogenesis high

SELECT
    'B3: LUAD EGFR+ Signature' as check_name,
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    CASE
        WHEN g.gene_symbol = 'EGFR' AND COALESCE(pe.expression_fold_change, 1.0) > 3.5
            THEN '✓ PASS - EGFR activation'
        WHEN g.gene_symbol = 'KRAS' AND COALESCE(pe.expression_fold_change, 1.0) BETWEEN 0.8 AND 1.5
            THEN '✓ PASS - KRAS wild-type (mutually exclusive with EGFR)'
        WHEN g.gene_symbol IN ('SFTPA1', 'SFTPB', 'SFTPC') AND COALESCE(pe.expression_fold_change, 1.0) < 0.4
            THEN '✓ PASS - Loss of lung differentiation'
        WHEN g.gene_symbol IN ('VEGFA', 'ANGPT2') AND COALESCE(pe.expression_fold_change, 1.0) > 3.0
            THEN '✓ PASS - Angiogenesis activation'
        WHEN g.gene_symbol IN ('AKT1', 'MAPK1', 'STAT3') AND COALESCE(pe.expression_fold_change, 1.0) > 2.0
            THEN 'INFO - Downstream EGFR signaling'
        ELSE 'INFO - Supporting marker'
    END as validation_status
FROM public.transcripts t
LEFT JOIN patient_${PATIENT_ID}.expression_data pe ON t.transcript_id = pe.transcript_id
JOIN public.genes g ON t.gene_id = g.gene_id
WHERE g.gene_symbol IN ('EGFR', 'ERBB3', 'KRAS', 'BRAF', 'SFTPA1', 'SFTPB', 'SFTPC',
                        'VEGFA', 'ANGPT2', 'AKT1', 'MAPK1', 'STAT3', 'MKI67')
ORDER BY
    CASE g.gene_symbol
        WHEN 'EGFR' THEN 1
        WHEN 'KRAS' THEN 2
        ELSE 3
    END,
    fold_change DESC;

-- Expected Output (for EGFR+ LUAD patient):
-- check_name              | gene_symbol | fold_change | validation_status
-- ------------------------|-------------|-------------|------------------
-- B3: LUAD EGFR+ Signature| EGFR        | 4.82        | ✓ PASS - EGFR activation
-- B3: LUAD EGFR+ Signature| KRAS        | 1.15        | ✓ PASS - KRAS wild-type
-- B3: LUAD EGFR+ Signature| VEGFA       | 3.95        | ✓ PASS - Angiogenesis activation


-- ============================================================================
-- SECTION C: CLINICAL CONCORDANCE CHECKS
-- ============================================================================
-- Purpose: Validate clinically relevant biomarkers and therapeutic targets

-- ----------------------------------------------------------------------------
-- C1: Tumor Suppressor Loss Detection
-- ----------------------------------------------------------------------------
-- Purpose: Identify loss of key tumor suppressors
-- Expected: Variable depending on cancer type (TP53 often lost)

SELECT
    'C1: Tumor Suppressor Loss' as check_name,
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    ROUND((1.0 - COALESCE(pe.expression_fold_change, 1.0)) * 100, 1) as percent_loss,
    CASE
        WHEN COALESCE(pe.expression_fold_change, 1.0) < 0.2 THEN '🚨 SEVERE LOSS (>80%)'
        WHEN COALESCE(pe.expression_fold_change, 1.0) < 0.5 THEN '⚠️  SIGNIFICANT LOSS (>50%)'
        WHEN COALESCE(pe.expression_fold_change, 1.0) < 0.8 THEN 'ℹ️  MODERATE LOSS (>20%)'
        ELSE '✓ INTACT'
    END as loss_severity,
    CASE g.gene_symbol
        WHEN 'TP53' THEN 'Guardian of genome - loss common in many cancers'
        WHEN 'PTEN' THEN 'PI3K pathway regulator - loss activates growth signaling'
        WHEN 'RB1' THEN 'Cell cycle checkpoint - loss allows uncontrolled proliferation'
        WHEN 'BRCA1' THEN 'DNA repair - loss causes genomic instability'
        WHEN 'BRCA2' THEN 'DNA repair - loss causes genomic instability'
        WHEN 'STK11' THEN 'LKB1 - metabolic/growth regulator, often lost in lung cancer'
        WHEN 'CDKN2A' THEN 'p16 - cell cycle inhibitor, commonly deleted'
        WHEN 'APC' THEN 'Wnt pathway - loss common in colorectal cancer'
    END as clinical_significance
FROM public.transcripts t
LEFT JOIN patient_${PATIENT_ID}.expression_data pe ON t.transcript_id = pe.transcript_id
JOIN public.genes g ON t.gene_id = g.gene_id
WHERE g.gene_symbol IN ('TP53', 'PTEN', 'RB1', 'BRCA1', 'BRCA2', 'STK11', 'CDKN2A', 'APC')
  AND COALESCE(pe.expression_fold_change, 1.0) < 0.8
ORDER BY fold_change ASC;

-- Expected Output (example):
-- check_name             | gene_symbol | fold_change | percent_loss | loss_severity      | clinical_significance
-- -----------------------|-------------|-------------|--------------|--------------------|-----------------------
-- C1: Tumor Suppressor   | TP53        | 0.28        | 72.0         | ⚠️  SIGNIFICANT    | Guardian of genome...
-- C1: Tumor Suppressor   | PTEN        | 0.42        | 58.0         | ⚠️  SIGNIFICANT    | PI3K pathway regulator...

-- ----------------------------------------------------------------------------
-- C2: Immune Checkpoint Expression Analysis
-- ----------------------------------------------------------------------------
-- Purpose: Assess immunotherapy biomarkers (PD-L1, PD-1, CTLA-4)
-- Expected: Variable - high PD-L1 suggests potential immunotherapy benefit

SELECT
    'C2: Immune Checkpoints' as check_name,
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    CASE
        WHEN g.gene_symbol = 'CD274' AND COALESCE(pe.expression_fold_change, 1.0) > 2.0
            THEN '🎯 HIGH PD-L1 - Consider immunotherapy'
        WHEN g.gene_symbol = 'CD274' AND COALESCE(pe.expression_fold_change, 1.0) > 1.5
            THEN '~ MODERATE PD-L1 - May respond to immunotherapy'
        WHEN g.gene_symbol = 'CD274'
            THEN 'ℹ️  LOW PD-L1 - Limited immunotherapy benefit expected'
        WHEN g.gene_symbol = 'PDCD1' AND COALESCE(pe.expression_fold_change, 1.0) > 1.5
            THEN 'INFO - Elevated PD-1 (T cell exhaustion marker)'
        WHEN g.gene_symbol = 'CTLA4' AND COALESCE(pe.expression_fold_change, 1.0) > 1.5
            THEN 'INFO - Elevated CTLA-4 (consider dual checkpoint blockade)'
        WHEN g.gene_symbol IN ('CD8A', 'CD8B') AND COALESCE(pe.expression_fold_change, 1.0) > 2.0
            THEN '✓ HIGH T CELL INFILTRATION - Favorable for immunotherapy'
        ELSE 'INFO - Supporting marker'
    END as immunotherapy_relevance,
    CASE g.gene_symbol
        WHEN 'CD274' THEN 'PD-L1: Primary immunotherapy biomarker'
        WHEN 'PDCD1' THEN 'PD-1: T cell checkpoint receptor'
        WHEN 'CTLA4' THEN 'CTLA-4: Alternative checkpoint target'
        WHEN 'CD8A' THEN 'CD8A: Cytotoxic T cell marker'
        WHEN 'CD8B' THEN 'CD8B: Cytotoxic T cell marker'
        WHEN 'LAG3' THEN 'LAG-3: Emerging checkpoint target'
    END as biomarker_description
FROM public.transcripts t
LEFT JOIN patient_${PATIENT_ID}.expression_data pe ON t.transcript_id = pe.transcript_id
JOIN public.genes g ON t.gene_id = g.gene_id
WHERE g.gene_symbol IN ('CD274', 'PDCD1', 'CTLA4', 'CD8A', 'CD8B', 'LAG3')
ORDER BY
    CASE g.gene_symbol
        WHEN 'CD274' THEN 1
        WHEN 'CD8A' THEN 2
        ELSE 3
    END,
    fold_change DESC;

-- Expected Output (example for immunotherapy-eligible patient):
-- check_name           | gene_symbol | fold_change | immunotherapy_relevance              | biomarker_description
-- ---------------------|-------------|-------------|--------------------------------------|----------------------
-- C2: Immune Checkpoints| CD274      | 2.45        | 🎯 HIGH PD-L1 - Consider immunotherapy| PD-L1: Primary...
-- C2: Immune Checkpoints| CD8A       | 2.82        | ✓ HIGH T CELL INFILTRATION           | CD8A: Cytotoxic...

-- ----------------------------------------------------------------------------
-- C3: Oncogene Amplification Detection
-- ----------------------------------------------------------------------------
-- Purpose: Identify targetable oncogene overexpression
-- Expected: Variable - high expression suggests potential drug targets

SELECT
    'C3: Oncogene Amplification' as check_name,
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    CASE
        WHEN COALESCE(pe.expression_fold_change, 1.0) > 5.0 THEN '🎯 STRONG AMPLIFICATION'
        WHEN COALESCE(pe.expression_fold_change, 1.0) > 3.0 THEN '🎯 MODERATE AMPLIFICATION'
        WHEN COALESCE(pe.expression_fold_change, 1.0) > 2.0 THEN 'ℹ️  MILD OVEREXPRESSION'
        ELSE '✓ NORMAL'
    END as amplification_status,
    CASE g.gene_symbol
        WHEN 'ERBB2' THEN 'HER2: Trastuzumab, Pertuzumab, T-DM1'
        WHEN 'EGFR' THEN 'EGFR: Erlotinib, Gefitinib, Osimertinib'
        WHEN 'MET' THEN 'MET: Crizotinib, Capmatinib'
        WHEN 'ALK' THEN 'ALK: Alectinib, Ceritinib, Lorlatinib'
        WHEN 'RET' THEN 'RET: Selpercatinib, Pralsetinib'
        WHEN 'BRAF' THEN 'BRAF: Vemurafenib, Dabrafenib (if V600E mutant)'
        WHEN 'KIT' THEN 'KIT: Imatinib, Sunitinib'
        WHEN 'PDGFRA' THEN 'PDGFRA: Imatinib'
        WHEN 'FGFR1' THEN 'FGFR1: Erdafitinib, Pemigatinib'
        WHEN 'FGFR2' THEN 'FGFR2: Erdafitinib, Pemigatinib'
    END as targeted_therapies
FROM public.transcripts t
LEFT JOIN patient_${PATIENT_ID}.expression_data pe ON t.transcript_id = pe.transcript_id
JOIN public.genes g ON t.gene_id = g.gene_id
WHERE g.gene_symbol IN ('ERBB2', 'EGFR', 'MET', 'ALK', 'RET', 'BRAF', 'KIT', 'PDGFRA', 'FGFR1', 'FGFR2')
  AND COALESCE(pe.expression_fold_change, 1.0) > 2.0
ORDER BY fold_change DESC;

-- Expected Output (example for HER2+ patient):
-- check_name              | gene_symbol | fold_change | amplification_status    | targeted_therapies
-- ------------------------|-------------|-------------|-------------------------|-------------------
-- C3: Oncogene Amplification| ERBB2     | 6.24        | 🎯 STRONG AMPLIFICATION | HER2: Trastuzumab...
-- C3: Oncogene Amplification| EGFR      | 3.45        | 🎯 MODERATE AMPLIFICATION| EGFR: Erlotinib...


-- ============================================================================
-- SECTION D: STATISTICAL VALIDATION
-- ============================================================================
-- Purpose: Statistical analysis of expression distributions

-- ----------------------------------------------------------------------------
-- D1: Expression Range Distribution
-- ----------------------------------------------------------------------------
-- Purpose: Categorize transcripts by expression level
-- Expected: Most transcripts near baseline, tails represent dysregulation

SELECT
    'D1: Expression Distribution' as check_name,
    expression_category,
    transcript_count,
    ROUND(percentage, 1) as percentage,
    REPEAT('█', LEAST(ROUND(percentage)::int, 50)) as visualization
FROM (
    SELECT
        CASE
            WHEN expression_fold_change >= 5.0 THEN '≥5.0x (Strong overexpression)'
            WHEN expression_fold_change >= 3.0 THEN '3.0-5.0x (Moderate overexpression)'
            WHEN expression_fold_change >= 2.0 THEN '2.0-3.0x (Mild overexpression)'
            WHEN expression_fold_change >= 1.5 THEN '1.5-2.0x (Slight overexpression)'
            WHEN expression_fold_change > 0.67 THEN '0.67-1.5x (Near baseline - sparse)'
            WHEN expression_fold_change > 0.5 THEN '0.5-0.67x (Slight underexpression)'
            WHEN expression_fold_change > 0.33 THEN '0.33-0.5x (Moderate underexpression)'
            ELSE '≤0.33x (Severe underexpression)'
        END as expression_category,
        COUNT(*) as transcript_count,
        COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () as percentage
    FROM patient_${PATIENT_ID}.expression_data
    GROUP BY 1
) dist
ORDER BY
    CASE expression_category
        WHEN '≥5.0x (Strong overexpression)' THEN 1
        WHEN '3.0-5.0x (Moderate overexpression)' THEN 2
        WHEN '2.0-3.0x (Mild overexpression)' THEN 3
        WHEN '1.5-2.0x (Slight overexpression)' THEN 4
        WHEN '0.67-1.5x (Near baseline - sparse)' THEN 5
        WHEN '0.5-0.67x (Slight underexpression)' THEN 6
        WHEN '0.33-0.5x (Moderate underexpression)' THEN 7
        ELSE 8
    END;

-- Expected Output (example):
-- check_name            | expression_category              | transcript_count | percentage | visualization
-- ----------------------|----------------------------------|------------------|------------|------------------
-- D1: Expression Dist.  | ≥5.0x (Strong overexpression)    | 18               | 4.0        | ████
-- D1: Expression Dist.  | 3.0-5.0x (Moderate overexp.)     | 42               | 9.3        | █████████
-- D1: Expression Dist.  | 2.0-3.0x (Mild overexpression)   | 65               | 14.4       | ██████████████

-- ----------------------------------------------------------------------------
-- D2: Top Dysregulated Genes Summary
-- ----------------------------------------------------------------------------
-- Purpose: Identify most extreme expression changes
-- Expected: Cancer driver genes in top overexpressed/underexpressed

SELECT
    'D2: Top Dysregulated Genes' as check_name,
    regulation_type,
    gene_symbol,
    fold_change,
    deviation_from_baseline
FROM (
    -- Top 10 overexpressed
    SELECT
        'Overexpressed' as regulation_type,
        g.gene_symbol,
        ROUND(pe.expression_fold_change::numeric, 2) as fold_change,
        ROUND((pe.expression_fold_change - 1.0)::numeric, 2) as deviation_from_baseline,
        ROW_NUMBER() OVER (ORDER BY pe.expression_fold_change DESC) as rank
    FROM patient_${PATIENT_ID}.expression_data pe
    JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
    JOIN public.genes g ON t.gene_id = g.gene_id
    WHERE pe.expression_fold_change > 1.0
    ORDER BY pe.expression_fold_change DESC
    LIMIT 10

    UNION ALL

    -- Top 10 underexpressed
    SELECT
        'Underexpressed' as regulation_type,
        g.gene_symbol,
        ROUND(pe.expression_fold_change::numeric, 4) as fold_change,
        ROUND((pe.expression_fold_change - 1.0)::numeric, 4) as deviation_from_baseline,
        ROW_NUMBER() OVER (ORDER BY pe.expression_fold_change ASC) as rank
    FROM patient_${PATIENT_ID}.expression_data pe
    JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
    JOIN public.genes g ON t.gene_id = g.gene_id
    WHERE pe.expression_fold_change < 1.0
    ORDER BY pe.expression_fold_change ASC
    LIMIT 10
) top_genes
ORDER BY
    CASE regulation_type WHEN 'Overexpressed' THEN 1 ELSE 2 END,
    ABS(deviation_from_baseline) DESC;

-- Expected Output (example for HER2+ patient):
-- check_name            | regulation_type | gene_symbol | fold_change | deviation_from_baseline
-- ----------------------|-----------------|-------------|-------------|------------------------
-- D2: Top Dysregulated  | Overexpressed   | ERBB2       | 6.24        | 5.24
-- D2: Top Dysregulated  | Overexpressed   | GRB7        | 4.18        | 3.18
-- D2: Top Dysregulated  | Underexpressed  | ESR1        | 0.0523      | -0.9477

-- ----------------------------------------------------------------------------
-- D3: Gene Expression Quartile Analysis
-- ----------------------------------------------------------------------------
-- Purpose: Quartile-based statistical summary
-- Expected: Identify outliers and validate biological range

SELECT
    'D3: Quartile Analysis' as check_name,
    ROUND(MIN(expression_fold_change)::numeric, 4) as minimum,
    ROUND(percentile_cont(0.25) WITHIN GROUP (ORDER BY expression_fold_change)::numeric, 2) as q1_25th_percentile,
    ROUND(percentile_cont(0.5) WITHIN GROUP (ORDER BY expression_fold_change)::numeric, 2) as q2_median,
    ROUND(percentile_cont(0.75) WITHIN GROUP (ORDER BY expression_fold_change)::numeric, 2) as q3_75th_percentile,
    ROUND(MAX(expression_fold_change)::numeric, 2) as maximum,
    ROUND((percentile_cont(0.75) WITHIN GROUP (ORDER BY expression_fold_change) -
           percentile_cont(0.25) WITHIN GROUP (ORDER BY expression_fold_change))::numeric, 2) as iqr_interquartile_range,
    COUNT(*) as total_transcripts
FROM patient_${PATIENT_ID}.expression_data;

-- Expected Output (example):
-- check_name          | minimum | q1    | q2     | q3    | maximum | iqr   | total_transcripts
-- --------------------|---------|-------|--------|-------|---------|-------|------------------
-- D3: Quartile Anal.  | 0.0523  | 0.78  | 1.32   | 2.45  | 8.42    | 1.67  | 450


-- ============================================================================
-- SECTION E: CROSS-PATIENT VALIDATION
-- ============================================================================
-- Purpose: Compare expression patterns across multiple patient schemas
-- Note: Replace ${PATIENT_ID_1}, ${PATIENT_ID_2}, ${PATIENT_ID_3} with actual IDs

-- ----------------------------------------------------------------------------
-- E1: Cross-Patient Expression Correlation
-- ----------------------------------------------------------------------------
-- Purpose: Compare expression of key biomarkers across patients
-- Expected: Patients with same cancer type show similar signatures

SELECT
    'E1: Cross-Patient Comparison' as check_name,
    g.gene_symbol,
    COALESCE(p1.expression_fold_change, 1.0) as patient_1_fc,
    COALESCE(p2.expression_fold_change, 1.0) as patient_2_fc,
    COALESCE(p3.expression_fold_change, 1.0) as patient_3_fc,
    CASE
        WHEN ABS(COALESCE(p1.expression_fold_change, 1.0) - COALESCE(p2.expression_fold_change, 1.0)) < 1.0
         AND ABS(COALESCE(p1.expression_fold_change, 1.0) - COALESCE(p3.expression_fold_change, 1.0)) < 1.0
            THEN '✓ CONCORDANT - Similar expression across patients'
        WHEN GREATEST(COALESCE(p1.expression_fold_change, 1.0), COALESCE(p2.expression_fold_change, 1.0), COALESCE(p3.expression_fold_change, 1.0)) > 2.0
            THEN 'VARIABLE - Check patient-specific factors'
        ELSE 'DIVERGENT - Different molecular subtypes possible'
    END as concordance_status
FROM public.genes g
JOIN public.transcripts t ON g.gene_id = t.gene_id
LEFT JOIN patient_${PATIENT_ID_1}.expression_data p1 ON t.transcript_id = p1.transcript_id
LEFT JOIN patient_${PATIENT_ID_2}.expression_data p2 ON t.transcript_id = p2.transcript_id
LEFT JOIN patient_${PATIENT_ID_3}.expression_data p3 ON t.transcript_id = p3.transcript_id
WHERE g.gene_symbol IN ('ERBB2', 'ESR1', 'PGR', 'MKI67', 'TP53', 'EGFR')
ORDER BY g.gene_symbol;

-- Expected Output (example for 3 HER2+ patients):
-- check_name               | gene_symbol | patient_1_fc | patient_2_fc | patient_3_fc | concordance_status
-- -------------------------|-------------|--------------|--------------|--------------|--------------------
-- E1: Cross-Patient Comp.  | ERBB2       | 6.24         | 5.87         | 6.45         | ✓ CONCORDANT
-- E1: Cross-Patient Comp.  | ESR1        | 2.15         | 0.35         | 1.82         | VARIABLE

-- ----------------------------------------------------------------------------
-- E2: Patient Cohort Summary Statistics
-- ----------------------------------------------------------------------------
-- Purpose: Statistical summary across all patient schemas
-- Expected: Population-level expression statistics

-- Note: This query requires dynamic SQL or manual listing of all patient schemas
-- Example for 3 patients:

WITH patient_stats AS (
    SELECT
        '${PATIENT_ID_1}' as patient_id,
        COUNT(*) as expressed_transcripts,
        ROUND(AVG(expression_fold_change)::numeric, 2) as mean_fc,
        ROUND(percentile_cont(0.5) WITHIN GROUP (ORDER BY expression_fold_change)::numeric, 2) as median_fc,
        COUNT(CASE WHEN expression_fold_change > 2.0 THEN 1 END) as overexpressed,
        COUNT(CASE WHEN expression_fold_change < 0.5 THEN 1 END) as underexpressed
    FROM patient_${PATIENT_ID_1}.expression_data

    UNION ALL

    SELECT
        '${PATIENT_ID_2}' as patient_id,
        COUNT(*),
        ROUND(AVG(expression_fold_change)::numeric, 2),
        ROUND(percentile_cont(0.5) WITHIN GROUP (ORDER BY expression_fold_change)::numeric, 2),
        COUNT(CASE WHEN expression_fold_change > 2.0 THEN 1 END),
        COUNT(CASE WHEN expression_fold_change < 0.5 THEN 1 END)
    FROM patient_${PATIENT_ID_2}.expression_data

    UNION ALL

    SELECT
        '${PATIENT_ID_3}' as patient_id,
        COUNT(*),
        ROUND(AVG(expression_fold_change)::numeric, 2),
        ROUND(percentile_cont(0.5) WITHIN GROUP (ORDER BY expression_fold_change)::numeric, 2),
        COUNT(CASE WHEN expression_fold_change > 2.0 THEN 1 END),
        COUNT(CASE WHEN expression_fold_change < 0.5 THEN 1 END)
    FROM patient_${PATIENT_ID_3}.expression_data
)
SELECT
    'E2: Patient Cohort Summary' as check_name,
    patient_id,
    expressed_transcripts,
    mean_fc,
    median_fc,
    overexpressed,
    underexpressed
FROM patient_stats
ORDER BY patient_id;

-- Expected Output (example for 3 patients):
-- check_name               | patient_id        | expressed_transcripts | mean_fc | median_fc | overexpressed | underexpressed
-- -------------------------|-------------------|----------------------|---------|-----------|---------------|----------------
-- E2: Patient Cohort Summ. | DEMO_BREAST_HER2  | 450                  | 1.85    | 1.32      | 125           | 78
-- E2: Patient Cohort Summ. | DEMO_TNBC         | 523                  | 2.12    | 1.45      | 187           | 92
-- E2: Patient Cohort Summ. | DEMO_LUAD_EGFR    | 412                  | 1.76    | 1.28      | 98            | 65


-- ============================================================================
-- SECTION F: COMPREHENSIVE VALIDATION SUMMARY
-- ============================================================================
-- Purpose: Executive summary of all validation checks

-- ----------------------------------------------------------------------------
-- F1: Validation Summary Report
-- ----------------------------------------------------------------------------
-- Purpose: Single-query summary of patient data quality
-- Expected: All checks pass with biologically meaningful values

WITH integrity_checks AS (
    SELECT
        COUNT(CASE WHEN expression_fold_change = 1.0 THEN 1 END) as sparse_violations,
        COUNT(CASE WHEN expression_fold_change <= 0 THEN 1 END) as negative_values,
        COUNT(*) as total_expressed,
        ROUND(AVG(expression_fold_change)::numeric, 2) as mean_fc,
        COUNT(CASE WHEN expression_fold_change > 2.0 THEN 1 END) as overexpressed,
        COUNT(CASE WHEN expression_fold_change < 0.5 THEN 1 END) as underexpressed
    FROM patient_${PATIENT_ID}.expression_data
),
metadata_check AS (
    SELECT
        COUNT(*) as metadata_rows,
        COUNT(patient_id) as has_patient_id,
        COUNT(cancer_type) as has_cancer_type
    FROM patient_${PATIENT_ID}.metadata
),
orphan_check AS (
    SELECT COUNT(*) as orphaned_transcripts
    FROM patient_${PATIENT_ID}.expression_data pe
    LEFT JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
    WHERE t.transcript_id IS NULL
)
SELECT
    'F1: Validation Summary' as report_name,
    'Data Integrity' as category,
    CASE
        WHEN ic.sparse_violations = 0
         AND ic.negative_values = 0
         AND oc.orphaned_transcripts = 0
            THEN '✓ PASS'
        ELSE '✗ FAIL'
    END as status,
    json_build_object(
        'total_expressed_transcripts', ic.total_expressed,
        'mean_fold_change', ic.mean_fc,
        'overexpressed_count', ic.overexpressed,
        'underexpressed_count', ic.underexpressed,
        'sparse_violations', ic.sparse_violations,
        'negative_values', ic.negative_values,
        'orphaned_transcripts', oc.orphaned_transcripts,
        'metadata_complete', (mc.metadata_rows = 1 AND mc.has_patient_id = 1)
    ) as validation_details
FROM integrity_checks ic
CROSS JOIN metadata_check mc
CROSS JOIN orphan_check oc;

-- Expected Output:
-- report_name           | category         | status  | validation_details
-- ----------------------|------------------|---------|-------------------
-- F1: Validation Summ.  | Data Integrity   | ✓ PASS  | {"total_expressed_transcripts": 450, ...}


-- ============================================================================
-- USAGE NOTES
-- ============================================================================
--
-- 1. Replace ${PATIENT_ID} with actual patient identifier before running
--    Example: patient_DEMO_BREAST_HER2 → replace with DEMO_BREAST_HER2
--
-- 2. Run queries sequentially: Start with Section A (integrity) before
--    biological validation (Sections B-C)
--
-- 3. Interpretation:
--    - ✓ PASS: Expected behavior, validation successful
--    - ~ BORDERLINE: May require clinical context for interpretation
--    - ✗ FAIL: Data quality issue or unexpected phenotype
--    - INFO: Supporting information, no pass/fail determination
--
-- 4. For cross-patient queries (Section E), create multiple patient schemas
--    first using scripts/create_patient_copy.py
--
-- 5. Cancer-specific signatures (Section B):
--    - Only relevant phenotype queries will return meaningful results
--    - Run B1 for HER2+ patients, B2 for TNBC, B3 for EGFR+ LUAD
--
-- 6. Clinical relevance prioritization:
--    - Section C: Most clinically actionable (therapeutic targets)
--    - Section B: Phenotype confirmation
--    - Section D: Statistical QC
--    - Section A: Technical validation
--
-- 7. For automated validation pipelines, extract status fields and
--    fail builds on any '✗ FAIL' results from Section A
--
-- ============================================================================
-- END OF VALIDATION QUERIES
-- ============================================================================

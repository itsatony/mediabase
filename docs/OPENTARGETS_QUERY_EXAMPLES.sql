-- ============================================================================
-- Open Targets Query Examples for LLM-Assisted Clinical Oncology
-- ============================================================================
-- These queries demonstrate common patterns for oncologist queries translated
-- to SQL by LLMs. All queries are designed to be clear, performant, and
-- clinically interpretable.
--
-- Database: MEDIABASE with Open Targets integration
-- Version: 0.4.0
-- Date: 2025-11-16
-- ============================================================================

-- ----------------------------------------------------------------------------
-- EXAMPLE 1: Find Approved Drugs for Overexpressed Genes
-- ----------------------------------------------------------------------------
-- Clinical Question: "Which overexpressed genes in my patient have approved
-- drug treatments?"
--
-- This is the most common actionability query - identifies immediate
-- therapeutic options based on patient transcriptome.

SELECT
    gt.gene_symbol,
    gt.gene_name,
    gt.cancer_fold as expression_fold_change,

    -- Disease context
    od.disease_name as cancer_type,
    oga.overall_score as evidence_strength,
    oga.somatic_mutation_score as cancer_mutation_evidence,

    -- Drug information
    okd.molecule_name as drug_name,
    okd.molecule_type as drug_type,
    okd.mechanism_of_action,
    okd.action_type,
    okd.approval_year,

    -- Clinical trial reference
    okd.clinical_trial_ids[1] as primary_trial_id

FROM gene_transcript gt
JOIN opentargets_gene_disease_associations oga ON gt.gene_id = oga.gene_id
JOIN opentargets_diseases od ON oga.disease_id = od.disease_id
JOIN opentargets_known_drugs okd ON gt.gene_id = okd.target_gene_id
    AND oga.disease_id = okd.disease_id

WHERE
    -- Patient has overexpression
    gt.cancer_fold > 2.0

    -- Cancer-specific associations
    AND od.is_cancer = true

    -- Moderate to strong evidence
    AND oga.overall_score >= 0.5

    -- FDA/EMA approved drugs only
    AND okd.is_approved = true

ORDER BY
    gt.cancer_fold DESC,
    oga.overall_score DESC,
    okd.approval_year DESC

LIMIT 50;

-- Expected output: Prioritized list of druggable overexpressed genes
-- Interpretation: Higher fold change + higher evidence score = stronger recommendation


-- ----------------------------------------------------------------------------
-- EXAMPLE 2: Novel Target Discovery - Druggable but Untargeted
-- ----------------------------------------------------------------------------
-- Clinical Question: "Are there highly overexpressed genes that are druggable
-- but don't have approved therapies yet?"
--
-- Use case: Identifying potential clinical trial candidates or novel
-- therapeutic targets for further investigation.

SELECT
    gt.gene_symbol,
    gt.gene_name,
    gt.cancer_fold as expression_fold_change,

    -- Evidence for cancer involvement
    oga.overall_score as cancer_association,
    oga.somatic_mutation_score as known_cancer_gene_score,
    od.disease_name,

    -- Druggability assessment
    ott.tractability_summary,
    ott.sm_clinical_precedence as has_sm_precedent,
    ott.ab_clinical_precedence as has_ab_precedent,

    -- Investigational drugs (if any)
    COUNT(DISTINCT okd.drug_id) FILTER (
        WHERE okd.clinical_phase BETWEEN 1 AND 3
    ) as drugs_in_trials,
    STRING_AGG(
        DISTINCT okd.molecule_name,
        ', '
    ) FILTER (
        WHERE okd.clinical_phase BETWEEN 1 AND 3
    ) as investigational_drugs

FROM gene_transcript gt
JOIN opentargets_gene_disease_associations oga ON gt.gene_id = oga.gene_id
JOIN opentargets_diseases od ON oga.disease_id = od.disease_id
JOIN opentargets_target_tractability ott ON gt.gene_id = ott.gene_id
LEFT JOIN opentargets_known_drugs okd ON gt.gene_id = okd.target_gene_id

WHERE
    -- Highly overexpressed
    gt.cancer_fold > 3.0

    -- Cancer-relevant
    AND od.is_cancer = true
    AND oga.overall_score >= 0.6

    -- Druggable (either small molecule or antibody)
    AND (
        ott.sm_clinical_precedence = true
        OR ott.ab_clinical_precedence = true
        OR ott.sm_predicted_tractable = true
        OR ott.ab_predicted_tractable = true
    )

    -- NO approved drugs for this target
    AND NOT EXISTS (
        SELECT 1
        FROM opentargets_known_drugs okd_approved
        WHERE okd_approved.target_gene_id = gt.gene_id
            AND okd_approved.is_approved = true
    )

GROUP BY
    gt.gene_id, gt.gene_symbol, gt.gene_name, gt.cancer_fold,
    oga.overall_score, oga.somatic_mutation_score, od.disease_name,
    ott.tractability_summary, ott.sm_clinical_precedence, ott.ab_clinical_precedence

ORDER BY
    gt.cancer_fold DESC,
    oga.overall_score DESC

LIMIT 30;

-- Expected output: Novel therapeutic targets worth investigating
-- Interpretation: High expression + druggable + no approved drugs = opportunity


-- ----------------------------------------------------------------------------
-- EXAMPLE 3: Comprehensive Gene Prioritization with Evidence Breakdown
-- ----------------------------------------------------------------------------
-- Clinical Question: "Rank all overexpressed genes by cancer relevance,
-- showing the evidence basis"
--
-- Use case: Comprehensive tumor profiling report showing multiple evidence
-- sources for each gene.

SELECT
    gt.gene_symbol,
    gt.gene_name,
    gt.cancer_fold,

    -- Disease associations
    STRING_AGG(DISTINCT od.disease_name, '; ') as associated_cancers,
    COUNT(DISTINCT od.disease_id) as cancer_type_count,

    -- Evidence breakdown (multiple sources)
    MAX(oga.overall_score) as max_overall_evidence,
    MAX(oga.somatic_mutation_score) as somatic_mutation_evidence,
    MAX(oga.known_drug_score) as drug_target_evidence,
    MAX(oga.literature_score) as literature_evidence,
    MAX(oga.rna_expression_score) as expression_evidence,

    -- Actionability metrics
    COUNT(DISTINCT okd.drug_id) FILTER (
        WHERE okd.is_approved = true
    ) as approved_drugs,
    COUNT(DISTINCT okd.drug_id) FILTER (
        WHERE okd.clinical_phase >= 2
    ) as clinical_drugs,

    -- Tractability flags
    BOOL_OR(ott.sm_clinical_precedence) as small_molecule_druggable,
    BOOL_OR(ott.ab_clinical_precedence) as antibody_druggable,

    -- Composite priority score (weighted combination)
    (
        -- Expression weight (normalize to 0-1 scale, cap at 10-fold)
        LEAST(gt.cancer_fold / 10.0, 1.0) * 0.3 +

        -- Evidence weight
        MAX(oga.overall_score) * 0.4 +

        -- Actionability weight (drugs available)
        CASE
            WHEN COUNT(DISTINCT okd.drug_id) FILTER (WHERE okd.is_approved = true) > 0
            THEN 0.3
            WHEN COUNT(DISTINCT okd.drug_id) FILTER (WHERE okd.clinical_phase >= 2) > 0
            THEN 0.2
            WHEN BOOL_OR(ott.sm_clinical_precedence OR ott.ab_clinical_precedence)
            THEN 0.1
            ELSE 0.0
        END
    ) as clinical_priority_score

FROM gene_transcript gt
LEFT JOIN opentargets_gene_disease_associations oga ON gt.gene_id = oga.gene_id
LEFT JOIN opentargets_diseases od ON oga.disease_id = od.disease_id
    AND od.is_cancer = true
LEFT JOIN opentargets_target_tractability ott ON gt.gene_id = ott.gene_id
LEFT JOIN opentargets_known_drugs okd ON gt.gene_id = okd.target_gene_id
    AND okd.disease_id = oga.disease_id

WHERE
    -- At least moderately overexpressed
    gt.cancer_fold > 1.5

    -- Has some cancer association evidence OR has drug/tractability info
    AND (
        oga.overall_score >= 0.4
        OR EXISTS (
            SELECT 1 FROM opentargets_known_drugs okd2
            WHERE okd2.target_gene_id = gt.gene_id
        )
        OR EXISTS (
            SELECT 1 FROM opentargets_target_tractability ott2
            WHERE ott2.gene_id = gt.gene_id
        )
    )

GROUP BY
    gt.gene_id, gt.gene_symbol, gt.gene_name, gt.cancer_fold

HAVING
    -- Must have at least some evidence
    MAX(oga.overall_score) IS NOT NULL
    OR COUNT(DISTINCT okd.drug_id) > 0

ORDER BY
    clinical_priority_score DESC,
    gt.cancer_fold DESC

LIMIT 100;

-- Expected output: Comprehensive ranked list for clinical discussion
-- Interpretation: Priority score combines expression, evidence, and actionability


-- ----------------------------------------------------------------------------
-- EXAMPLE 4: Drug Repurposing Opportunities
-- ----------------------------------------------------------------------------
-- Clinical Question: "Are there approved drugs for related cancers that might
-- work for my patient's overexpressed genes?"
--
-- Use case: Identifying off-label or repurposing opportunities from other
-- cancer indications.

SELECT
    gt.gene_symbol,
    gt.cancer_fold as patient_expression,

    -- Drug approved for DIFFERENT cancer
    okd.molecule_name,
    okd.mechanism_of_action,
    od.disease_name as approved_for_cancer,

    -- Evidence for patient's specific context
    oga.overall_score as gene_cancer_evidence,
    oga.somatic_mutation_score,

    -- Related cancer overlap
    ARRAY_AGG(DISTINCT od2.disease_name) as other_relevant_cancers

FROM gene_transcript gt
JOIN opentargets_known_drugs okd ON gt.gene_id = okd.target_gene_id
JOIN opentargets_diseases od ON okd.disease_id = od.disease_id
JOIN opentargets_gene_disease_associations oga ON gt.gene_id = oga.gene_id
JOIN opentargets_diseases od2 ON oga.disease_id = od2.disease_id

WHERE
    gt.cancer_fold > 2.0
    AND okd.is_approved = true
    AND od.is_cancer = true
    AND od2.is_cancer = true
    AND oga.overall_score >= 0.5

    -- Drug approved for at least one cancer indication
    AND od.disease_name ILIKE ANY(ARRAY[
        '%carcinoma%',
        '%leukemia%',
        '%lymphoma%',
        '%melanoma%',
        '%sarcoma%',
        '%myeloma%'
    ])

GROUP BY
    gt.gene_id, gt.gene_symbol, gt.cancer_fold,
    okd.drug_id, okd.molecule_name, okd.mechanism_of_action,
    od.disease_name, oga.overall_score, oga.somatic_mutation_score

ORDER BY
    gt.cancer_fold DESC,
    oga.overall_score DESC

LIMIT 40;

-- Expected output: Repurposing candidates with cross-cancer evidence
-- Interpretation: Consider drugs approved for one cancer but targeting relevant genes


-- ----------------------------------------------------------------------------
-- EXAMPLE 5: Cancer Gene Census Check
-- ----------------------------------------------------------------------------
-- Clinical Question: "Which of my patient's overexpressed genes are
-- well-established cancer genes?"
--
-- Use case: Quick triage to identify known cancer drivers vs novel findings.

SELECT
    gt.gene_symbol,
    gt.gene_name,
    gt.cancer_fold,

    -- Strong somatic mutation evidence indicates established cancer gene
    oga.somatic_mutation_score as cancer_gene_score,
    oga.overall_score as total_evidence,

    -- Count of cancer types associated
    COUNT(DISTINCT od.disease_id) as cancer_types_count,
    STRING_AGG(DISTINCT od.disease_name, '; ') as cancer_types,

    -- Classification
    CASE
        WHEN oga.somatic_mutation_score >= 0.8 THEN 'Well-established cancer gene'
        WHEN oga.somatic_mutation_score >= 0.5 THEN 'Known cancer association'
        WHEN oga.somatic_mutation_score >= 0.3 THEN 'Emerging cancer association'
        ELSE 'Limited cancer-specific evidence'
    END as cancer_gene_classification

FROM gene_transcript gt
JOIN opentargets_gene_disease_associations oga ON gt.gene_id = oga.gene_id
JOIN opentargets_diseases od ON oga.disease_id = od.disease_id

WHERE
    gt.cancer_fold > 1.5
    AND od.is_cancer = true

    -- Focus on genes with somatic mutation evidence
    AND oga.somatic_mutation_score IS NOT NULL

GROUP BY
    gt.gene_id, gt.gene_symbol, gt.gene_name, gt.cancer_fold,
    oga.somatic_mutation_score, oga.overall_score

ORDER BY
    oga.somatic_mutation_score DESC,
    gt.cancer_fold DESC

LIMIT 50;

-- Expected output: Established cancer genes ranked by evidence
-- Interpretation: High somatic_mutation_score = well-known cancer driver


-- ----------------------------------------------------------------------------
-- EXAMPLE 6: Pathway-Informed Drug Discovery
-- ----------------------------------------------------------------------------
-- Clinical Question: "Show me overexpressed genes grouped by pathway, with
-- available drugs"
--
-- Use case: Understanding coordinated dysregulation and pathway-targeted
-- therapy options.

SELECT
    p.pathway_name,
    p.pathway_source,
    COUNT(DISTINCT gt.gene_id) as overexpressed_genes_in_pathway,

    -- Representative genes
    STRING_AGG(
        DISTINCT gt.gene_symbol,
        ', '
        ORDER BY gt.cancer_fold DESC
    ) as top_genes,

    -- Average expression change
    AVG(gt.cancer_fold) as avg_fold_change,
    MAX(gt.cancer_fold) as max_fold_change,

    -- Pathway-level evidence
    AVG(oga.overall_score) as avg_cancer_association,

    -- Druggability of pathway
    COUNT(DISTINCT okd.drug_id) FILTER (
        WHERE okd.is_approved = true
    ) as approved_drugs_in_pathway,
    STRING_AGG(
        DISTINCT okd.molecule_name,
        ', '
    ) FILTER (
        WHERE okd.is_approved = true
    ) as available_drugs

FROM pathway p
JOIN gene_pathway gp ON p.pathway_id = gp.pathway_id
JOIN gene_transcript gt ON gp.gene_id = gt.gene_id
LEFT JOIN opentargets_gene_disease_associations oga ON gt.gene_id = oga.gene_id
LEFT JOIN opentargets_diseases od ON oga.disease_id = od.disease_id
    AND od.is_cancer = true
LEFT JOIN opentargets_known_drugs okd ON gt.gene_id = okd.target_gene_id

WHERE
    gt.cancer_fold > 2.0
    AND p.pathway_source = 'REACTOME'

GROUP BY
    p.pathway_id, p.pathway_name, p.pathway_source

HAVING
    -- Pathways with multiple overexpressed genes
    COUNT(DISTINCT gt.gene_id) >= 3

ORDER BY
    COUNT(DISTINCT okd.drug_id) FILTER (WHERE okd.is_approved = true) DESC,
    AVG(gt.cancer_fold) DESC

LIMIT 30;

-- Expected output: Dysregulated pathways with therapeutic options
-- Interpretation: Pathways with multiple hits + drugs = coordinated intervention opportunity


-- ----------------------------------------------------------------------------
-- EXAMPLE 7: Clinical Trial Matching
-- ----------------------------------------------------------------------------
-- Clinical Question: "Find active clinical trials for drugs targeting my
-- patient's overexpressed genes"
--
-- Use case: Identifying trial enrollment opportunities for patients with
-- specific molecular profiles.

SELECT
    gt.gene_symbol,
    gt.cancer_fold,

    okd.molecule_name,
    okd.molecule_type,
    okd.mechanism_of_action,
    okd.clinical_phase,
    okd.clinical_status,

    od.disease_name as cancer_indication,
    oga.overall_score as evidence_strength,

    -- Clinical trial IDs for further research
    okd.clinical_trial_ids,
    ARRAY_LENGTH(okd.clinical_trial_ids, 1) as trial_count

FROM gene_transcript gt
JOIN opentargets_known_drugs okd ON gt.gene_id = okd.target_gene_id
JOIN opentargets_diseases od ON okd.disease_id = od.disease_id
JOIN opentargets_gene_disease_associations oga ON gt.gene_id = oga.gene_id
    AND oga.disease_id = od.disease_id

WHERE
    -- Overexpressed targets
    gt.cancer_fold > 2.0

    -- Cancer indications
    AND od.is_cancer = true

    -- Phase II or III trials (late-stage, more likely recruiting)
    AND okd.clinical_phase BETWEEN 2 AND 3

    -- Active or recruiting trials
    AND okd.clinical_status IN ('Recruiting', 'Active, not recruiting', 'Active')

    -- Has trial IDs
    AND okd.clinical_trial_ids IS NOT NULL
    AND ARRAY_LENGTH(okd.clinical_trial_ids, 1) > 0

    -- Reasonable evidence
    AND oga.overall_score >= 0.5

ORDER BY
    okd.clinical_phase DESC,
    gt.cancer_fold DESC,
    trial_count DESC

LIMIT 50;

-- Expected output: Clinical trial opportunities matched to patient profile
-- Interpretation: Use clinical_trial_ids to look up details on ClinicalTrials.gov


-- ----------------------------------------------------------------------------
-- EXAMPLE 8: Multi-Target Drug Analysis
-- ----------------------------------------------------------------------------
-- Clinical Question: "Are there drugs that target multiple overexpressed
-- genes simultaneously?"
--
-- Use case: Identifying combination therapy opportunities or drugs with
-- multi-target mechanisms.

WITH patient_overexpressed_genes AS (
    SELECT gene_id, gene_symbol, cancer_fold
    FROM gene_transcript
    WHERE cancer_fold > 2.0
),
drug_target_counts AS (
    SELECT
        okd.molecule_chembl_id,
        okd.molecule_name,
        okd.molecule_type,
        okd.is_approved,
        okd.clinical_phase,
        COUNT(DISTINCT pog.gene_id) as matching_targets,
        ARRAY_AGG(DISTINCT pog.gene_symbol ORDER BY pog.cancer_fold DESC) as target_genes,
        AVG(pog.cancer_fold) as avg_target_expression,
        MAX(pog.cancer_fold) as max_target_expression
    FROM opentargets_known_drugs okd
    JOIN patient_overexpressed_genes pog ON okd.target_gene_id = pog.gene_id
    WHERE okd.clinical_phase >= 2  -- At least phase 2
    GROUP BY
        okd.molecule_chembl_id, okd.molecule_name,
        okd.molecule_type, okd.is_approved, okd.clinical_phase
    HAVING COUNT(DISTINCT pog.gene_id) >= 2  -- Multi-target
)
SELECT
    molecule_name,
    molecule_type,
    CASE
        WHEN is_approved THEN 'Approved'
        ELSE 'Phase ' || clinical_phase::TEXT
    END as drug_status,
    matching_targets as targets_hit,
    target_genes,
    ROUND(avg_target_expression::numeric, 2) as avg_expression_fold,
    ROUND(max_target_expression::numeric, 2) as max_expression_fold
FROM drug_target_counts
ORDER BY
    matching_targets DESC,
    is_approved DESC,
    clinical_phase DESC,
    avg_target_expression DESC
LIMIT 20;

-- Expected output: Drugs with broad coverage of patient's molecular profile
-- Interpretation: Multi-target drugs may provide better efficacy or reduce resistance


-- ----------------------------------------------------------------------------
-- EXAMPLE 9: Gene Summary for Clinical Report
-- ----------------------------------------------------------------------------
-- Clinical Question: "Give me a comprehensive clinical summary for gene EGFR
-- in this patient"
--
-- Use case: Deep dive into a specific gene of interest for detailed reporting.

WITH gene_of_interest AS (
    SELECT gene_id, gene_symbol, cancer_fold
    FROM gene_transcript
    WHERE gene_symbol = 'EGFR'  -- Can be parameterized
)
SELECT
    -- Gene basics
    'GENE INFORMATION' as section,
    goi.gene_symbol,
    gt.gene_name,
    goi.cancer_fold as patient_expression_fold,

    -- Clinical summary from Open Targets
    JSONB_BUILD_OBJECT(
        'cancer_associations', (
            SELECT JSONB_AGG(
                JSONB_BUILD_OBJECT(
                    'cancer_type', od.disease_name,
                    'evidence_score', oga.overall_score,
                    'somatic_mutation_score', oga.somatic_mutation_score,
                    'known_drug_score', oga.known_drug_score
                )
            )
            FROM opentargets_gene_disease_associations oga
            JOIN opentargets_diseases od ON oga.disease_id = od.disease_id
            WHERE oga.gene_id = goi.gene_id
                AND od.is_cancer = true
                AND oga.overall_score >= 0.5
            ORDER BY oga.overall_score DESC
            LIMIT 10
        ),
        'approved_drugs', (
            SELECT JSONB_AGG(
                JSONB_BUILD_OBJECT(
                    'drug_name', okd.molecule_name,
                    'mechanism', okd.mechanism_of_action,
                    'action_type', okd.action_type,
                    'approval_year', okd.approval_year,
                    'indication', od.disease_name
                )
            )
            FROM opentargets_known_drugs okd
            JOIN opentargets_diseases od ON okd.disease_id = od.disease_id
            WHERE okd.target_gene_id = goi.gene_id
                AND okd.is_approved = true
            ORDER BY okd.approval_year DESC
        ),
        'druggability', (
            SELECT JSONB_BUILD_OBJECT(
                'tractability_summary', ott.tractability_summary,
                'small_molecule_clinical_precedence', ott.sm_clinical_precedence,
                'antibody_clinical_precedence', ott.ab_clinical_precedence
            )
            FROM opentargets_target_tractability ott
            WHERE ott.gene_id = goi.gene_id
        )
    ) as clinical_data

FROM gene_of_interest goi
JOIN gene_transcript gt ON goi.gene_id = gt.gene_id;

-- Expected output: Structured JSON with all relevant clinical information
-- Interpretation: Use for detailed gene-specific clinical reports


-- ----------------------------------------------------------------------------
-- EXAMPLE 10: Using the Materialized View for Fast Queries
-- ----------------------------------------------------------------------------
-- Clinical Question: "Show me the top clinically relevant overexpressed genes"
--
-- Use case: Quick patient summary using pre-aggregated data for performance.
-- Note: Requires gene_clinical_summary materialized view from migration 006

SELECT
    gene_symbol,
    gene_name,
    cancer_fold as expression_fold,

    -- Pre-computed cancer associations
    cancer_association_count as cancer_types,
    max_cancer_association_score as best_evidence,
    max_somatic_mutation_score as cancer_gene_score,

    -- Pre-computed druggability
    CASE
        WHEN approved_drug_count > 0 THEN 'Approved drugs available'
        WHEN clinical_stage_drug_count > 0 THEN 'Clinical-stage drugs available'
        WHEN small_molecule_tractable OR antibody_tractable THEN 'Druggable target'
        ELSE 'Limited druggability'
    END as actionability_summary,

    approved_drug_count as approved_drugs,
    clinical_stage_drug_count as investigational_drugs,

    tractability_summary

FROM gene_clinical_summary

WHERE
    cancer_fold > 2.0
    AND (
        max_cancer_association_score >= 0.6
        OR approved_drug_count > 0
    )

ORDER BY
    -- Prioritize approved drugs, then evidence, then expression
    approved_drug_count DESC,
    max_cancer_association_score DESC,
    cancer_fold DESC

LIMIT 30;

-- Expected output: Fast, pre-aggregated clinical gene summary
-- Interpretation: Use materialized view for dashboard-style queries
-- Note: Refresh view after data updates with: REFRESH MATERIALIZED VIEW CONCURRENTLY gene_clinical_summary


-- ============================================================================
-- Query Performance Tips for LLM Generation
-- ============================================================================

-- 1. Always filter on indexed columns first:
--    - cancer_fold for expression thresholds
--    - is_cancer for cancer disease filtering
--    - overall_score for evidence thresholds
--    - is_approved for drug filtering

-- 2. Use appropriate indexes:
--    - All indexes are created in migration 006
--    - Check with: \d+ table_name in psql

-- 3. For complex analytics, use the materialized view:
--    - gene_clinical_summary is pre-aggregated
--    - Much faster than joining 5-6 tables
--    - Refresh after data updates

-- 4. Common LLM query patterns to optimize:
--    - "overexpressed genes" → WHERE cancer_fold > threshold
--    - "approved drugs" → WHERE is_approved = true
--    - "cancer" → WHERE is_cancer = true
--    - "strong evidence" → WHERE overall_score >= 0.7

-- 5. Limit result sets for interactive queries:
--    - Use LIMIT for top-N results
--    - Use pagination for large result sets
--    - Consider aggregation for summaries

-- ============================================================================
-- End of Query Examples
-- ============================================================================

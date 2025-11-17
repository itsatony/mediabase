-- Migration 006: Open Targets Platform Integration
-- Description: Add tables for disease-gene associations, known drugs, and tractability
-- Dependencies: gene_transcript, gene_id_map
-- Version: 0.4.0
-- Date: 2025-11-16

-- ============================================================================
-- DISEASES TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS opentargets_diseases (
    disease_id TEXT PRIMARY KEY,
    disease_name TEXT NOT NULL,
    disease_description TEXT,
    therapeutic_areas TEXT[],
    ontology_source TEXT,
    is_cancer BOOLEAN DEFAULT false,
    parent_disease_ids TEXT[],
    metadata JSONB,
    ot_version TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE opentargets_diseases IS
'Disease ontology from Open Targets Platform. Contains cancer classifications and hierarchies for disease-gene associations. Use disease_id to join with associations.';

COMMENT ON COLUMN opentargets_diseases.disease_id IS
'EFO, MONDO, or other ontology identifier (e.g., EFO_0000616 for neoplasm). Colons replaced with underscores for PostgreSQL compatibility.';

COMMENT ON COLUMN opentargets_diseases.disease_name IS
'Human-readable disease name as it appears in ontology (e.g., "breast carcinoma", "acute myeloid leukemia")';

COMMENT ON COLUMN opentargets_diseases.therapeutic_areas IS
'Array of therapeutic area classifications (e.g., ["neoplasm", "genetic disorder"]). Use for broad disease categorization.';

COMMENT ON COLUMN opentargets_diseases.is_cancer IS
'Boolean flag: true if disease is classified under neoplasm/cancer therapeutic areas. Use this for filtering cancer-specific associations.';

COMMENT ON COLUMN opentargets_diseases.parent_disease_ids IS
'Array of parent disease IDs in ontology hierarchy (e.g., breast cancer -> carcinoma -> neoplasm). Use for disease relationship queries.';

COMMENT ON COLUMN opentargets_diseases.ot_version IS
'Open Targets Platform release version (format: YY.MM, e.g., "24.09"). Track data provenance for updates.';

-- ============================================================================
-- GENE-DISEASE ASSOCIATIONS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS opentargets_gene_disease_associations (
    association_id SERIAL PRIMARY KEY,
    gene_id TEXT NOT NULL,
    disease_id TEXT NOT NULL REFERENCES opentargets_diseases(disease_id),
    overall_score NUMERIC(5,4) NOT NULL CHECK (overall_score >= 0 AND overall_score <= 1),

    -- Evidence scores by datatype (all 0-1 scale)
    genetic_association_score NUMERIC(5,4),
    somatic_mutation_score NUMERIC(5,4),
    known_drug_score NUMERIC(5,4),
    literature_score NUMERIC(5,4),
    rna_expression_score NUMERIC(5,4),
    pathways_systems_biology_score NUMERIC(5,4),
    animal_model_score NUMERIC(5,4),

    -- Association metadata
    is_direct BOOLEAN DEFAULT true,
    evidence_count INTEGER,
    datasource_count INTEGER,

    -- Tractability flags (from association data)
    tractability_clinical_precedence BOOLEAN,
    tractability_discovery_precedence BOOLEAN,

    metadata JSONB,
    ot_version TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(gene_id, disease_id, ot_version)
);

COMMENT ON TABLE opentargets_gene_disease_associations IS
'Gene-disease associations from Open Targets with evidence scores. Overall_score ≥0.5 indicates moderate evidence, ≥0.7 strong evidence, ≥0.85 very strong evidence. Join with gene_transcript on gene_id and opentargets_diseases on disease_id for clinical queries.';

COMMENT ON COLUMN opentargets_gene_disease_associations.gene_id IS
'Gene identifier matching gene_transcript.gene_id. Use for joining with patient expression data.';

COMMENT ON COLUMN opentargets_gene_disease_associations.overall_score IS
'Combined evidence score from 0-1 representing strength of gene-disease association. Thresholds: ≥0.5 moderate, ≥0.7 strong, ≥0.85 very strong evidence. Higher scores indicate more established associations.';

COMMENT ON COLUMN opentargets_gene_disease_associations.genetic_association_score IS
'Evidence from genetic association studies (GWAS, rare variant burden tests). Higher scores indicate genetic predisposition evidence.';

COMMENT ON COLUMN opentargets_gene_disease_associations.somatic_mutation_score IS
'Cancer somatic mutation evidence (Cancer Gene Census, COSMIC, IntOGen, tumor suppressor/oncogene databases). Higher scores indicate well-established cancer genes. Most relevant for oncology queries.';

COMMENT ON COLUMN opentargets_gene_disease_associations.known_drug_score IS
'Evidence from approved or clinical-phase drugs targeting this gene for this disease. Higher scores indicate actionable targets with existing therapeutic options.';

COMMENT ON COLUMN opentargets_gene_disease_associations.literature_score IS
'Evidence from biomedical literature (PubMed co-mentions, text mining). Indicates published research on gene-disease relationship.';

COMMENT ON COLUMN opentargets_gene_disease_associations.rna_expression_score IS
'Evidence from differential gene expression studies (tumor vs normal, disease vs control). Higher scores indicate consistent expression changes.';

COMMENT ON COLUMN opentargets_gene_disease_associations.pathways_systems_biology_score IS
'Evidence from pathway and systems biology databases (Reactome, KEGG). Indicates mechanistic connections.';

COMMENT ON COLUMN opentargets_gene_disease_associations.is_direct IS
'True for direct gene-disease associations, false for indirect (e.g., pathway-mediated). Direct associations are higher confidence.';

COMMENT ON COLUMN opentargets_gene_disease_associations.evidence_count IS
'Total number of evidence strings supporting this association. More evidence typically indicates stronger support.';

-- ============================================================================
-- KNOWN DRUGS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS opentargets_known_drugs (
    drug_id SERIAL PRIMARY KEY,
    molecule_chembl_id TEXT,
    molecule_name TEXT NOT NULL,
    molecule_type TEXT,

    target_gene_id TEXT,
    disease_id TEXT REFERENCES opentargets_diseases(disease_id),

    -- Clinical development status
    clinical_phase NUMERIC(3,1) CHECK (clinical_phase >= 0 AND clinical_phase <= 4),
    clinical_phase_label TEXT,
    clinical_status TEXT,

    -- Mechanism of action
    mechanism_of_action TEXT,
    action_type TEXT,

    -- Drug classification
    drug_type TEXT,
    is_approved BOOLEAN,
    approval_year INTEGER,

    -- Clinical trial references
    clinical_trial_ids TEXT[],

    metadata JSONB,
    ot_version TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE opentargets_known_drugs IS
'Approved and clinical-stage drugs with target and disease associations from Open Targets. Clinical_phase=4 indicates approved drugs. Use for identifying actionable drug-target-disease combinations for patient treatment recommendations.';

COMMENT ON COLUMN opentargets_known_drugs.molecule_chembl_id IS
'ChEMBL identifier for cross-referencing with ChEMBL database (format: CHEMBL####). NULL for drugs not in ChEMBL.';

COMMENT ON COLUMN opentargets_known_drugs.molecule_name IS
'Drug name (generic or brand). Use for display and search.';

COMMENT ON COLUMN opentargets_known_drugs.molecule_type IS
'Drug modality type: "Small molecule", "Antibody", "Protein", "Oligonucleotide", "Enzyme", "Other". Informs therapeutic approach.';

COMMENT ON COLUMN opentargets_known_drugs.target_gene_id IS
'Gene target identifier matching gene_transcript.gene_id. Use for finding drugs targeting specific genes. NULL for drugs with non-gene targets.';

COMMENT ON COLUMN opentargets_known_drugs.clinical_phase IS
'Clinical development phase: 0=preclinical, 1=Phase I safety, 2=Phase II efficacy, 3=Phase III confirmatory, 4=approved/marketed. NULL for withdrawn/terminated. Higher phases indicate more advanced development.';

COMMENT ON COLUMN opentargets_known_drugs.clinical_phase_label IS
'Human-readable phase label: "Preclinical", "Phase I", "Phase II", "Phase III", "Approved". Use for display.';

COMMENT ON COLUMN opentargets_known_drugs.clinical_status IS
'Current clinical trial status: "Recruiting", "Active", "Completed", "Terminated", "Withdrawn", "Approved". Indicates active development.';

COMMENT ON COLUMN opentargets_known_drugs.mechanism_of_action IS
'Description of how the drug works (e.g., "EGFR tyrosine kinase inhibitor", "PD-1 checkpoint inhibitor"). Use for mechanistic understanding.';

COMMENT ON COLUMN opentargets_known_drugs.action_type IS
'Molecular action type: "inhibitor", "antagonist", "agonist", "activator", "modulator", "antibody". Indicates direction of effect.';

COMMENT ON COLUMN opentargets_known_drugs.is_approved IS
'True if drug is approved for ANY indication (may differ from disease_id in this row). Use to prioritize drugs with regulatory approval.';

COMMENT ON COLUMN opentargets_known_drugs.approval_year IS
'Year of first regulatory approval (FDA, EMA, or other). NULL for non-approved drugs.';

COMMENT ON COLUMN opentargets_known_drugs.clinical_trial_ids IS
'Array of clinical trial identifiers (typically ClinicalTrials.gov NCT numbers). Use for finding trial details.';

-- ============================================================================
-- TARGET TRACTABILITY TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS opentargets_target_tractability (
    gene_id TEXT PRIMARY KEY,

    -- Small molecule tractability
    sm_clinical_precedence BOOLEAN,
    sm_discovery_precedence BOOLEAN,
    sm_predicted_tractable BOOLEAN,
    sm_top_bucket TEXT,

    -- Antibody tractability
    ab_clinical_precedence BOOLEAN,
    ab_predicted_tractable BOOLEAN,
    ab_top_bucket TEXT,

    -- Other modalities
    other_modality_tractable BOOLEAN,

    tractability_summary TEXT,

    metadata JSONB,
    ot_version TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE opentargets_target_tractability IS
'Druggability assessment for gene targets from Open Targets. Indicates likelihood of successful drug development. Clinical_precedence means drugs already exist for this target or related family members. Use to assess feasibility of targeting overexpressed genes.';

COMMENT ON COLUMN opentargets_target_tractability.gene_id IS
'Gene identifier matching gene_transcript.gene_id. Use for joining with expression and association data.';

COMMENT ON COLUMN opentargets_target_tractability.sm_clinical_precedence IS
'True if small molecule drugs exist for this target or closely related family members. Strong indicator of druggability.';

COMMENT ON COLUMN opentargets_target_tractability.sm_discovery_precedence IS
'True if target has structural or functional features associated with successful small molecule drug discovery (e.g., defined binding pocket).';

COMMENT ON COLUMN opentargets_target_tractability.sm_predicted_tractable IS
'True if computational models predict this target is amenable to small molecule drug development.';

COMMENT ON COLUMN opentargets_target_tractability.sm_top_bucket IS
'Highest small molecule tractability category achieved. Categories ordered by confidence: Clinical Precedence > Discovery Precedence > Predicted Tractable.';

COMMENT ON COLUMN opentargets_target_tractability.ab_clinical_precedence IS
'True if antibody drugs exist for this target or closely related family members. Indicates antibody drug feasibility.';

COMMENT ON COLUMN opentargets_target_tractability.ab_predicted_tractable IS
'True if target has features suitable for antibody-based therapy (e.g., extracellular location, membrane protein).';

COMMENT ON COLUMN opentargets_target_tractability.tractability_summary IS
'Human-readable summary of tractability assessment (e.g., "Small molecule: Clinical precedence; Antibody: Predicted tractable"). Use for display.';

-- ============================================================================
-- METADATA TRACKING TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS opentargets_metadata (
    version TEXT PRIMARY KEY,
    release_date DATE,
    loaded_date TIMESTAMP DEFAULT NOW(),
    record_counts JSONB,
    validation_results JSONB,
    notes TEXT
);

COMMENT ON TABLE opentargets_metadata IS
'Tracks Open Targets Platform data versions and ETL run metadata. Use to verify data currency and track updates.';

COMMENT ON COLUMN opentargets_metadata.version IS
'Open Targets Platform release version (format: YY.MM, e.g., "24.09"). Corresponds to ot_version in data tables.';

COMMENT ON COLUMN opentargets_metadata.record_counts IS
'JSON object with record counts by table (e.g., {"diseases": 15000, "associations": 120000}). Use for validation.';

COMMENT ON COLUMN opentargets_metadata.validation_results IS
'JSON object with data quality metrics from ETL run. Use for monitoring data integrity.';

-- ============================================================================
-- INDEXES FOR QUERY PERFORMANCE
-- ============================================================================

-- Disease lookups (full-text search on names)
CREATE INDEX IF NOT EXISTS idx_ot_diseases_name
    ON opentargets_diseases USING gin(to_tsvector('english', disease_name));

-- Filter for cancer diseases (most common query)
CREATE INDEX IF NOT EXISTS idx_ot_diseases_cancer
    ON opentargets_diseases(is_cancer) WHERE is_cancer = true;

-- Therapeutic area filtering
CREATE INDEX IF NOT EXISTS idx_ot_diseases_therapeutic_areas
    ON opentargets_diseases USING gin(therapeutic_areas);

-- Association queries by gene (most common join)
CREATE INDEX IF NOT EXISTS idx_ot_assoc_gene
    ON opentargets_gene_disease_associations(gene_id);

-- Association queries by disease
CREATE INDEX IF NOT EXISTS idx_ot_assoc_disease
    ON opentargets_gene_disease_associations(disease_id);

-- High-score associations (filtering threshold)
CREATE INDEX IF NOT EXISTS idx_ot_assoc_score
    ON opentargets_gene_disease_associations(overall_score DESC);

-- Combined gene + score (common pattern: gene with strong evidence)
CREATE INDEX IF NOT EXISTS idx_ot_assoc_gene_score
    ON opentargets_gene_disease_associations(gene_id, overall_score DESC);

-- Cancer genes with at least moderate evidence (filtered index)
CREATE INDEX IF NOT EXISTS idx_ot_assoc_cancer_genes
    ON opentargets_gene_disease_associations(gene_id, overall_score)
    WHERE overall_score >= 0.5;

-- Somatic mutation evidence (cancer-specific)
CREATE INDEX IF NOT EXISTS idx_ot_assoc_somatic
    ON opentargets_gene_disease_associations(somatic_mutation_score DESC)
    WHERE somatic_mutation_score IS NOT NULL;

-- Drug queries by target gene (most common: find drugs for gene)
CREATE INDEX IF NOT EXISTS idx_ot_drugs_target
    ON opentargets_known_drugs(target_gene_id)
    WHERE target_gene_id IS NOT NULL;

-- Drug queries by disease
CREATE INDEX IF NOT EXISTS idx_ot_drugs_disease
    ON opentargets_known_drugs(disease_id);

-- Approved drugs (high priority for clinical queries)
CREATE INDEX IF NOT EXISTS idx_ot_drugs_approved
    ON opentargets_known_drugs(is_approved, clinical_phase)
    WHERE is_approved = true;

-- Clinical phase filtering (common: phase >= 2)
CREATE INDEX IF NOT EXISTS idx_ot_drugs_phase
    ON opentargets_known_drugs(clinical_phase DESC)
    WHERE clinical_phase IS NOT NULL;

-- ChEMBL cross-reference
CREATE INDEX IF NOT EXISTS idx_ot_drugs_chembl
    ON opentargets_known_drugs(molecule_chembl_id)
    WHERE molecule_chembl_id IS NOT NULL;

-- Full-text search on drug names
CREATE INDEX IF NOT EXISTS idx_ot_drugs_name
    ON opentargets_known_drugs USING gin(to_tsvector('english', molecule_name));

-- Tractability for small molecule discovery
CREATE INDEX IF NOT EXISTS idx_ot_tract_sm
    ON opentargets_target_tractability(gene_id)
    WHERE sm_clinical_precedence = true OR sm_predicted_tractable = true;

-- Tractability for antibody discovery
CREATE INDEX IF NOT EXISTS idx_ot_tract_ab
    ON opentargets_target_tractability(gene_id)
    WHERE ab_clinical_precedence = true OR ab_predicted_tractable = true;

-- ============================================================================
-- MATERIALIZED VIEW: COMPREHENSIVE GENE SUMMARY
-- ============================================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS gene_clinical_summary AS
SELECT
    gt.gene_id,
    gt.gene_symbol,
    gt.gene_name,
    gt.gene_type,
    gt.cancer_fold,  -- Patient-specific expression

    -- Open Targets disease associations
    COUNT(DISTINCT oga.disease_id) FILTER (WHERE od.is_cancer = true)
        as cancer_association_count,
    MAX(oga.overall_score) FILTER (WHERE od.is_cancer = true)
        as max_cancer_association_score,
    MAX(oga.somatic_mutation_score) FILTER (WHERE od.is_cancer = true)
        as max_somatic_mutation_score,

    -- Druggability (from tractability table)
    COALESCE(ott.sm_clinical_precedence, false) as small_molecule_tractable,
    COALESCE(ott.ab_clinical_precedence, false) as antibody_tractable,
    ott.tractability_summary,

    -- Known drugs (actionability)
    COUNT(DISTINCT okd.drug_id) FILTER (WHERE okd.is_approved = true)
        as approved_drug_count,
    COUNT(DISTINCT okd.drug_id) FILTER (WHERE okd.clinical_phase >= 2)
        as clinical_stage_drug_count,

    -- Existing MEDIABASE annotations (for completeness)
    COUNT(DISTINCT gp.product_id) as product_count,
    COUNT(DISTINCT ggo.go_id) as go_term_count,
    COUNT(DISTINCT gpa.pathway_id) as pathway_count,

    -- Update tracking
    MAX(oga.ot_version) as ot_version,
    NOW() as summary_created_at

FROM gene_transcript gt
LEFT JOIN opentargets_gene_disease_associations oga ON gt.gene_id = oga.gene_id
LEFT JOIN opentargets_diseases od ON oga.disease_id = od.disease_id
LEFT JOIN opentargets_target_tractability ott ON gt.gene_id = ott.gene_id
LEFT JOIN opentargets_known_drugs okd ON gt.gene_id = okd.target_gene_id
    AND okd.disease_id = oga.disease_id
LEFT JOIN gene_product gp ON gt.gene_id = gp.gene_id
LEFT JOIN gene_go ggo ON gt.gene_id = ggo.gene_id
LEFT JOIN gene_pathway gpa ON gt.gene_id = gpa.gene_id

GROUP BY
    gt.gene_id, gt.gene_symbol, gt.gene_name, gt.gene_type, gt.cancer_fold,
    ott.sm_clinical_precedence, ott.ab_clinical_precedence, ott.tractability_summary;

COMMENT ON MATERIALIZED VIEW gene_clinical_summary IS
'Comprehensive gene summary combining patient-specific expression, Open Targets disease associations, druggability, known drugs, and existing MEDIABASE annotations. Refresh after data updates using: REFRESH MATERIALIZED VIEW CONCURRENTLY gene_clinical_summary. Use for high-level gene prioritization queries in LLM context.';

-- Index the materialized view for common access patterns
CREATE UNIQUE INDEX IF NOT EXISTS idx_gene_clinical_summary_gene_id
    ON gene_clinical_summary(gene_id);

CREATE INDEX IF NOT EXISTS idx_gene_clinical_summary_symbol
    ON gene_clinical_summary(gene_symbol);

CREATE INDEX IF NOT EXISTS idx_gene_clinical_summary_cancer_fold
    ON gene_clinical_summary(cancer_fold DESC)
    WHERE cancer_fold IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_gene_clinical_summary_druggable
    ON gene_clinical_summary(approved_drug_count DESC, max_cancer_association_score DESC)
    WHERE approved_drug_count > 0;

CREATE INDEX IF NOT EXISTS idx_gene_clinical_summary_high_evidence
    ON gene_clinical_summary(max_cancer_association_score DESC, cancer_fold DESC)
    WHERE max_cancer_association_score >= 0.7;

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Function to refresh summary view
CREATE OR REPLACE FUNCTION refresh_gene_clinical_summary()
RETURNS VOID AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY gene_clinical_summary;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION refresh_gene_clinical_summary() IS
'Refresh the gene_clinical_summary materialized view. Call after updating Open Targets data or patient expression values. Uses CONCURRENTLY to avoid locking.';

-- ============================================================================
-- VERSION TRACKING
-- ============================================================================

-- Insert schema version
INSERT INTO schema_version (version, description, applied_at)
VALUES (
    '0.4.0',
    'Open Targets Platform integration: diseases, associations, drugs, tractability',
    NOW()
)
ON CONFLICT (version) DO NOTHING;

-- Update schema to v0.3.0 with enhanced pathway and drug interaction support
-- This migration removes legacy table dependencies and adds biomedically-sound enhancements

-- =============================================================================
-- PART 1: PATHWAY ENHANCEMENTS (gene_pathways table)
-- =============================================================================

-- Add pathway hierarchy and evidence fields
ALTER TABLE gene_pathways
ADD COLUMN IF NOT EXISTS parent_pathway_id VARCHAR(100),
ADD COLUMN IF NOT EXISTS pathway_level INTEGER DEFAULT 1,
ADD COLUMN IF NOT EXISTS pathway_category VARCHAR(200),
ADD COLUMN IF NOT EXISTS evidence_code VARCHAR(10) DEFAULT 'IEA',
ADD COLUMN IF NOT EXISTS confidence_score DECIMAL(3,2) DEFAULT 0.80,
ADD COLUMN IF NOT EXISTS gene_role VARCHAR(100),
ADD COLUMN IF NOT EXISTS pmids TEXT[];

-- Add helpful comments for documentation
COMMENT ON COLUMN gene_pathways.parent_pathway_id IS 'Parent pathway ID for hierarchical pathway organization';
COMMENT ON COLUMN gene_pathways.pathway_level IS 'Hierarchy level: 1=top-level, 2=sub-pathway, 3=detailed';
COMMENT ON COLUMN gene_pathways.pathway_category IS 'High-level category (metabolism, signaling, etc.)';
COMMENT ON COLUMN gene_pathways.evidence_code IS 'GO/ECO evidence code (IEA, IDA, IMP, TAS, etc.)';
COMMENT ON COLUMN gene_pathways.confidence_score IS 'Data quality score 0.0-1.0';
COMMENT ON COLUMN gene_pathways.gene_role IS 'Gene role in pathway (member, regulator, target, etc.)';
COMMENT ON COLUMN gene_pathways.pmids IS 'PubMed IDs supporting pathway annotation';

-- Create indexes for pathway queries
CREATE INDEX IF NOT EXISTS idx_gene_pathways_parent ON gene_pathways(parent_pathway_id);
CREATE INDEX IF NOT EXISTS idx_gene_pathways_level ON gene_pathways(pathway_level);
CREATE INDEX IF NOT EXISTS idx_gene_pathways_category ON gene_pathways(pathway_category);
CREATE INDEX IF NOT EXISTS idx_gene_pathways_evidence ON gene_pathways(evidence_code);
CREATE INDEX IF NOT EXISTS idx_gene_pathways_confidence ON gene_pathways(confidence_score);
CREATE INDEX IF NOT EXISTS idx_gene_pathways_role ON gene_pathways(gene_role);

-- Create GIN index for array-based PMID queries
CREATE INDEX IF NOT EXISTS idx_gene_pathways_pmids ON gene_pathways USING GIN(pmids);

-- =============================================================================
-- PART 2: DRUG INTERACTION ENHANCEMENTS (gene_drug_interactions table)
-- =============================================================================

-- Add clinical and pharmacological fields
ALTER TABLE gene_drug_interactions
ADD COLUMN IF NOT EXISTS drug_chembl_id VARCHAR(50),
ADD COLUMN IF NOT EXISTS drugbank_id VARCHAR(20),
ADD COLUMN IF NOT EXISTS clinical_phase VARCHAR(50),
ADD COLUMN IF NOT EXISTS approval_status VARCHAR(50),
ADD COLUMN IF NOT EXISTS activity_value DECIMAL(10,4),
ADD COLUMN IF NOT EXISTS activity_unit VARCHAR(20),
ADD COLUMN IF NOT EXISTS activity_type VARCHAR(50),
ADD COLUMN IF NOT EXISTS drug_class VARCHAR(200),
ADD COLUMN IF NOT EXISTS drug_type VARCHAR(50),
ADD COLUMN IF NOT EXISTS evidence_strength INTEGER DEFAULT 1,
ADD COLUMN IF NOT EXISTS pmids TEXT[];

-- Add helpful comments for documentation
COMMENT ON COLUMN gene_drug_interactions.drug_chembl_id IS 'ChEMBL database identifier for cross-referencing';
COMMENT ON COLUMN gene_drug_interactions.drugbank_id IS 'DrugBank database identifier';
COMMENT ON COLUMN gene_drug_interactions.clinical_phase IS 'Clinical development phase (Preclinical, Phase I/II/III, Approved, Withdrawn)';
COMMENT ON COLUMN gene_drug_interactions.approval_status IS 'Regulatory approval status';
COMMENT ON COLUMN gene_drug_interactions.activity_value IS 'Pharmacological activity value (IC50, Ki, Kd, EC50)';
COMMENT ON COLUMN gene_drug_interactions.activity_unit IS 'Unit of measurement (nM, uM, etc.)';
COMMENT ON COLUMN gene_drug_interactions.activity_type IS 'Type of activity metric (IC50, Ki, Kd, EC50, etc.)';
COMMENT ON COLUMN gene_drug_interactions.drug_class IS 'Therapeutic drug classification';
COMMENT ON COLUMN gene_drug_interactions.drug_type IS 'Drug type (small_molecule, antibody, protein, etc.)';
COMMENT ON COLUMN gene_drug_interactions.evidence_strength IS 'Evidence quality score 1-5 (1=low, 5=high)';
COMMENT ON COLUMN gene_drug_interactions.pmids IS 'PubMed IDs supporting drug interaction';

-- Migrate existing single PMID to array format
UPDATE gene_drug_interactions
SET pmids = ARRAY[pmid]::TEXT[]
WHERE pmid IS NOT NULL
  AND pmid != ''
  AND pmids IS NULL;

-- Create indexes for drug interaction queries
CREATE INDEX IF NOT EXISTS idx_gene_drug_chembl ON gene_drug_interactions(drug_chembl_id);
CREATE INDEX IF NOT EXISTS idx_gene_drug_drugbank ON gene_drug_interactions(drugbank_id);
CREATE INDEX IF NOT EXISTS idx_gene_drug_clinical_phase ON gene_drug_interactions(clinical_phase);
CREATE INDEX IF NOT EXISTS idx_gene_drug_approval ON gene_drug_interactions(approval_status);
CREATE INDEX IF NOT EXISTS idx_gene_drug_activity_type ON gene_drug_interactions(activity_type);
CREATE INDEX IF NOT EXISTS idx_gene_drug_class ON gene_drug_interactions(drug_class);
CREATE INDEX IF NOT EXISTS idx_gene_drug_type ON gene_drug_interactions(drug_type);
CREATE INDEX IF NOT EXISTS idx_gene_drug_evidence_strength ON gene_drug_interactions(evidence_strength);

-- Create GIN index for array-based PMID queries
CREATE INDEX IF NOT EXISTS idx_gene_drug_pmids ON gene_drug_interactions USING GIN(pmids);

-- Create composite index for filtering by clinical relevance
CREATE INDEX IF NOT EXISTS idx_gene_drug_clinical_relevance
ON gene_drug_interactions(clinical_phase, approval_status, evidence_strength);

-- =============================================================================
-- PART 3: MATERIALIZED VIEWS FOR PERFORMANCE
-- =============================================================================

-- Drop existing views if they exist (for clean migration)
DROP MATERIALIZED VIEW IF EXISTS pathway_gene_counts CASCADE;
DROP MATERIALIZED VIEW IF EXISTS pathway_druggability CASCADE;
DROP MATERIALIZED VIEW IF EXISTS drug_gene_summary CASCADE;

-- Create pathway gene counts view for enrichment analysis
CREATE MATERIALIZED VIEW pathway_gene_counts AS
SELECT
    gp.pathway_id,
    gp.pathway_name,
    gp.pathway_source,
    gp.pathway_category,
    gp.parent_pathway_id,
    gp.pathway_level,
    COUNT(DISTINCT gp.gene_id) as gene_count,
    array_agg(DISTINCT gp.gene_id) as gene_members,
    array_agg(DISTINCT g.gene_symbol) FILTER (WHERE g.gene_symbol IS NOT NULL) as gene_symbols,
    AVG(gp.confidence_score) as avg_confidence,
    COUNT(*) FILTER (WHERE gp.evidence_code IN ('IDA', 'IMP', 'IPI', 'IGI', 'IEP')) as experimental_evidence_count,
    COUNT(*) FILTER (WHERE gp.evidence_code = 'IEA') as computational_evidence_count,
    array_agg(DISTINCT gp.evidence_code) as evidence_codes,
    MAX(gp.created_at) as last_updated
FROM gene_pathways gp
LEFT JOIN genes g ON gp.gene_id = g.gene_id
GROUP BY
    gp.pathway_id,
    gp.pathway_name,
    gp.pathway_source,
    gp.pathway_category,
    gp.parent_pathway_id,
    gp.pathway_level;

-- Create indexes on materialized view
CREATE UNIQUE INDEX idx_pathway_counts_id ON pathway_gene_counts(pathway_id, pathway_source);
CREATE INDEX idx_pathway_counts_gene_count ON pathway_gene_counts(gene_count);
CREATE INDEX idx_pathway_counts_category ON pathway_gene_counts(pathway_category);
CREATE INDEX idx_pathway_counts_level ON pathway_gene_counts(pathway_level);
CREATE INDEX idx_pathway_counts_confidence ON pathway_gene_counts(avg_confidence);
CREATE INDEX idx_pathway_counts_members ON pathway_gene_counts USING GIN(gene_members);
CREATE INDEX idx_pathway_counts_symbols ON pathway_gene_counts USING GIN(gene_symbols);

-- Create pathway druggability view
CREATE MATERIALIZED VIEW pathway_druggability AS
SELECT
    gp.pathway_id,
    gp.pathway_name,
    gp.pathway_source,
    gp.pathway_category,
    COUNT(DISTINCT gp.gene_id) as total_genes,
    COUNT(DISTINCT gdi.gene_id) as druggable_genes,
    ROUND(
        (COUNT(DISTINCT gdi.gene_id)::DECIMAL / NULLIF(COUNT(DISTINCT gp.gene_id), 0) * 100),
        2
    ) as druggability_percentage,
    COUNT(DISTINCT gdi.drug_name) as unique_drugs,
    array_agg(DISTINCT gdi.drug_name) FILTER (WHERE gdi.clinical_phase IN ('Approved', 'Phase III')) as approved_drugs,
    array_agg(DISTINCT gdi.drug_class) FILTER (WHERE gdi.drug_class IS NOT NULL) as drug_classes,
    AVG(gdi.evidence_strength) FILTER (WHERE gdi.evidence_strength IS NOT NULL) as avg_evidence_strength,
    AVG(gp.confidence_score) as avg_pathway_confidence,
    MAX(gp.created_at) as last_updated
FROM gene_pathways gp
LEFT JOIN gene_drug_interactions gdi ON gp.gene_id = gdi.gene_id
GROUP BY
    gp.pathway_id,
    gp.pathway_name,
    gp.pathway_source,
    gp.pathway_category;

-- Create indexes on druggability view
CREATE UNIQUE INDEX idx_pathway_drug_id ON pathway_druggability(pathway_id, pathway_source);
CREATE INDEX idx_pathway_drug_percentage ON pathway_druggability(druggability_percentage);
CREATE INDEX idx_pathway_drug_category ON pathway_druggability(pathway_category);
CREATE INDEX idx_pathway_drug_approved ON pathway_druggability USING GIN(approved_drugs);

-- Create drug gene summary view
CREATE MATERIALIZED VIEW drug_gene_summary AS
SELECT
    gdi.drug_name,
    gdi.drug_id,
    gdi.drug_chembl_id,
    gdi.drugbank_id,
    gdi.drug_class,
    gdi.drug_type,
    gdi.clinical_phase,
    gdi.approval_status,
    COUNT(DISTINCT gdi.gene_id) as target_gene_count,
    array_agg(DISTINCT g.gene_symbol) FILTER (WHERE g.gene_symbol IS NOT NULL) as target_genes,
    array_agg(DISTINCT gdi.interaction_type) as interaction_types,
    AVG(gdi.evidence_strength) as avg_evidence_strength,
    COUNT(*) FILTER (WHERE gdi.evidence_strength >= 4) as high_confidence_interactions,
    array_agg(DISTINCT gp.pathway_name) FILTER (WHERE gp.pathway_name IS NOT NULL) as affected_pathways,
    COUNT(DISTINCT gp.pathway_id) as pathway_count,
    MAX(gdi.created_at) as last_updated
FROM gene_drug_interactions gdi
LEFT JOIN genes g ON gdi.gene_id = g.gene_id
LEFT JOIN gene_pathways gp ON gdi.gene_id = gp.gene_id
GROUP BY
    gdi.drug_name,
    gdi.drug_id,
    gdi.drug_chembl_id,
    gdi.drugbank_id,
    gdi.drug_class,
    gdi.drug_type,
    gdi.clinical_phase,
    gdi.approval_status;

-- Create indexes on drug summary view
CREATE UNIQUE INDEX idx_drug_summary_name ON drug_gene_summary(drug_name);
CREATE INDEX idx_drug_summary_chembl ON drug_gene_summary(drug_chembl_id);
CREATE INDEX idx_drug_summary_drugbank ON drug_gene_summary(drugbank_id);
CREATE INDEX idx_drug_summary_class ON drug_gene_summary(drug_class);
CREATE INDEX idx_drug_summary_phase ON drug_gene_summary(clinical_phase);
CREATE INDEX idx_drug_summary_target_count ON drug_gene_summary(target_gene_count);
CREATE INDEX idx_drug_summary_genes ON drug_gene_summary USING GIN(target_genes);
CREATE INDEX idx_drug_summary_pathways ON drug_gene_summary USING GIN(affected_pathways);

-- =============================================================================
-- PART 4: UTILITY FUNCTIONS
-- =============================================================================

-- Function to refresh all materialized views
CREATE OR REPLACE FUNCTION refresh_pathway_drug_views()
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    REFRESH MATERIALIZED VIEW pathway_gene_counts;
    REFRESH MATERIALIZED VIEW pathway_druggability;
    REFRESH MATERIALIZED VIEW drug_gene_summary;
    RAISE NOTICE 'Refreshed pathway and drug materialized views';
END;
$$;

-- Function to get pathway druggability details
CREATE OR REPLACE FUNCTION get_pathway_druggability(pathway_name_filter TEXT)
RETURNS TABLE(
    pathway_name TEXT,
    total_genes BIGINT,
    druggable_genes BIGINT,
    druggability_pct NUMERIC,
    unique_drugs BIGINT,
    approved_drugs TEXT[],
    drug_classes TEXT[]
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        pd.pathway_name::TEXT,
        pd.total_genes,
        pd.druggable_genes,
        pd.druggability_percentage,
        pd.unique_drugs,
        pd.approved_drugs,
        pd.drug_classes
    FROM pathway_druggability pd
    WHERE pd.pathway_name ILIKE '%' || pathway_name_filter || '%'
    ORDER BY pd.druggability_percentage DESC NULLS LAST;
END;
$$;

-- Function to find drugs for a specific gene with clinical relevance
CREATE OR REPLACE FUNCTION get_clinically_relevant_drugs(gene_symbol_filter TEXT)
RETURNS TABLE(
    drug_name VARCHAR,
    drug_class VARCHAR,
    clinical_phase VARCHAR,
    approval_status VARCHAR,
    interaction_type VARCHAR,
    activity_value DECIMAL,
    activity_unit VARCHAR,
    evidence_strength INTEGER,
    pmid_count INTEGER
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        gdi.drug_name,
        gdi.drug_class,
        gdi.clinical_phase,
        gdi.approval_status,
        gdi.interaction_type,
        gdi.activity_value,
        gdi.activity_unit,
        gdi.evidence_strength,
        COALESCE(array_length(gdi.pmids, 1), 0) as pmid_count
    FROM gene_drug_interactions gdi
    INNER JOIN genes g ON gdi.gene_id = g.gene_id
    WHERE g.gene_symbol = gene_symbol_filter
      AND gdi.evidence_strength >= 2
    ORDER BY
        CASE gdi.clinical_phase
            WHEN 'Approved' THEN 1
            WHEN 'Phase III' THEN 2
            WHEN 'Phase II' THEN 3
            WHEN 'Phase I' THEN 4
            ELSE 5
        END,
        gdi.evidence_strength DESC,
        gdi.activity_value ASC NULLS LAST;
END;
$$;

-- =============================================================================
-- PART 5: DATA QUALITY VIEWS
-- =============================================================================

-- Create view for pathway annotation coverage
CREATE OR REPLACE VIEW pathway_annotation_coverage AS
SELECT
    COUNT(DISTINCT g.gene_id) as total_genes,
    COUNT(DISTINCT gp.gene_id) as genes_with_pathways,
    ROUND(
        (COUNT(DISTINCT gp.gene_id)::DECIMAL / NULLIF(COUNT(DISTINCT g.gene_id), 0) * 100),
        2
    ) as pathway_coverage_percentage,
    COUNT(DISTINCT gp.pathway_id) as unique_pathways,
    COUNT(*) as total_pathway_annotations,
    AVG(gp.confidence_score) as avg_confidence_score
FROM genes g
LEFT JOIN gene_pathways gp ON g.gene_id = gp.gene_id;

-- Create view for drug interaction coverage
CREATE OR REPLACE VIEW drug_interaction_coverage AS
SELECT
    COUNT(DISTINCT g.gene_id) as total_genes,
    COUNT(DISTINCT gdi.gene_id) as genes_with_drugs,
    ROUND(
        (COUNT(DISTINCT gdi.gene_id)::DECIMAL / NULLIF(COUNT(DISTINCT g.gene_id), 0) * 100),
        2
    ) as drug_coverage_percentage,
    COUNT(DISTINCT gdi.drug_name) as unique_drugs,
    COUNT(*) as total_drug_interactions,
    AVG(gdi.evidence_strength) as avg_evidence_strength,
    COUNT(*) FILTER (WHERE gdi.clinical_phase IN ('Approved', 'Phase III')) as clinical_stage_interactions,
    COUNT(*) FILTER (WHERE gdi.evidence_strength >= 4) as high_confidence_interactions
FROM genes g
LEFT JOIN gene_drug_interactions gdi ON g.gene_id = gdi.gene_id;

-- =============================================================================
-- PART 6: SCHEMA VERSION TRACKING
-- =============================================================================

-- Ensure schema_version table exists
CREATE TABLE IF NOT EXISTS schema_version (
    id SERIAL PRIMARY KEY,
    version_name VARCHAR(20) UNIQUE NOT NULL,
    description TEXT,
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Insert schema version record
INSERT INTO schema_version (version_name, description)
VALUES (
    'v0.3.0',
    'Enhanced pathway hierarchy and drug interaction schema with clinical/pharmacological fields'
)
ON CONFLICT (version_name) DO UPDATE
SET
    applied_at = CURRENT_TIMESTAMP,
    description = EXCLUDED.description;

-- Add final comment
COMMENT ON TABLE gene_pathways IS 'Enhanced pathway annotations with hierarchy, evidence codes, and PMID arrays (v0.3.0)';
COMMENT ON TABLE gene_drug_interactions IS 'Enhanced drug interactions with clinical phase, pharmacology, and cross-database IDs (v0.3.0)';

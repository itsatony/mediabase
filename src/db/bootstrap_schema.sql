-- ============================================================================
-- MEDIABASE v0.3.0 Complete Bootstrap Schema
-- Single-step database initialization (replaces incremental migrations)
-- ============================================================================
--
-- This script creates the complete MEDIABASE database schema including:
-- - Normalized core tables (genes, transcripts, cross-references)
-- - Relationship tables (pathways, drugs, GO terms, annotations)
-- - Legacy tables (cancer_transcript_base for backwards compatibility)
-- - All indexes for performance
-- - Views and materialized views for analytics
-- - Functions for data management
--
-- Usage:
--   psql -h localhost -p 5435 -U mbase_user -d mbase -f bootstrap_schema.sql
--
-- Author: Claude Code
-- Date: 2025-01-16
-- Version: 0.3.0
-- ============================================================================

-- ============================================================================
-- PART 1: Clean Slate - Drop Everything
-- ============================================================================

DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO PUBLIC;

-- ============================================================================
-- PART 2: Core Infrastructure
-- ============================================================================

-- Custom type for publication references
DO $$
BEGIN
    CREATE TYPE publication_reference AS (
        pmid text,
        evidence_type text,
        source_db text,
        title text,
        abstract text,
        year integer,
        journal text,
        authors text[],
        citation_count integer,
        doi text,
        url text
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

COMMENT ON TYPE publication_reference IS 'Structured type for storing publication metadata from PubMed and other sources';

-- Schema version tracking table
CREATE TABLE schema_version (
    version_name VARCHAR(20) PRIMARY KEY,
    description TEXT,
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE schema_version IS 'Tracks database schema versions and migration history';

-- ============================================================================
-- PART 3: Normalized Core Tables (Primary Data Storage)
-- ============================================================================

-- -----------------------------------------------------------------------------
-- genes: Primary gene table with core metadata
-- -----------------------------------------------------------------------------
CREATE TABLE genes (
    gene_id VARCHAR(50) PRIMARY KEY,  -- Ensembl gene ID (e.g., ENSG00000141510)
    gene_symbol VARCHAR(100) NOT NULL,
    gene_name VARCHAR(200),
    gene_type VARCHAR(100),  -- protein_coding, lncRNA, miRNA, etc.
    chromosome VARCHAR(10),
    start_position INTEGER,
    end_position INTEGER,
    strand INTEGER,  -- 1 or -1
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE genes IS 'Core gene table storing unique genes with metadata from GENCODE';
COMMENT ON COLUMN genes.gene_id IS 'Ensembl gene ID (primary identifier)';
COMMENT ON COLUMN genes.gene_symbol IS 'HGNC gene symbol (e.g., TP53, BRCA1)';
COMMENT ON COLUMN genes.gene_type IS 'Gene biotype from GENCODE (protein_coding, lncRNA, etc.)';
COMMENT ON COLUMN genes.strand IS 'Genomic strand: 1 for forward, -1 for reverse';

CREATE INDEX idx_genes_symbol ON genes(gene_symbol);
CREATE INDEX idx_genes_type ON genes(gene_type);
CREATE INDEX idx_genes_chromosome ON genes(chromosome);
CREATE INDEX idx_genes_position ON genes(chromosome, start_position, end_position);
CREATE INDEX idx_genes_created ON genes(created_at);

-- -----------------------------------------------------------------------------
-- transcripts: Transcript isoforms linked to genes
-- -----------------------------------------------------------------------------
CREATE TABLE transcripts (
    transcript_id VARCHAR(50) PRIMARY KEY,  -- Ensembl transcript ID (e.g., ENST00000269305)
    gene_id VARCHAR(50) NOT NULL REFERENCES genes(gene_id) ON DELETE CASCADE,
    transcript_name VARCHAR(200),
    transcript_type VARCHAR(100),
    transcript_support_level INTEGER DEFAULT 1,  -- 1-5, lower is better
    expression_fold_change FLOAT DEFAULT 1.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE transcripts IS 'Transcript isoforms with expression data';
COMMENT ON COLUMN transcripts.transcript_support_level IS 'TSL from GENCODE: 1 (best) to 5 (worst)';
COMMENT ON COLUMN transcripts.expression_fold_change IS 'Patient-specific expression fold change (default 1.0)';

CREATE INDEX idx_transcripts_gene ON transcripts(gene_id);
CREATE INDEX idx_transcripts_type ON transcripts(transcript_type);
CREATE INDEX idx_transcripts_expression ON transcripts(expression_fold_change);
CREATE INDEX idx_transcripts_created ON transcripts(created_at);

-- -----------------------------------------------------------------------------
-- gene_cross_references: External database ID mappings
-- -----------------------------------------------------------------------------
CREATE TABLE gene_cross_references (
    id SERIAL PRIMARY KEY,
    gene_id VARCHAR(50) NOT NULL REFERENCES genes(gene_id) ON DELETE CASCADE,
    external_db VARCHAR(50) NOT NULL,  -- UniProt, NCBI, EntrezGene, RefSeq, HGNC, HAVANA, PDB
    external_id VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(gene_id, external_db, external_id)
);

COMMENT ON TABLE gene_cross_references IS 'Maps genes to external database identifiers';
COMMENT ON COLUMN gene_cross_references.external_db IS 'Database name: UniProt, NCBI, EntrezGene, RefSeq, HGNC, HAVANA, PDB';

CREATE INDEX idx_gene_xref_gene ON gene_cross_references(gene_id);
CREATE INDEX idx_gene_xref_db ON gene_cross_references(external_db);
CREATE INDEX idx_gene_xref_external_id ON gene_cross_references(external_id);
CREATE INDEX idx_gene_xref_lookup ON gene_cross_references(external_db, external_id);

-- -----------------------------------------------------------------------------
-- gene_annotations: Flexible key-value annotations for genes
-- -----------------------------------------------------------------------------
CREATE TABLE gene_annotations (
    id SERIAL PRIMARY KEY,
    gene_id VARCHAR(50) NOT NULL REFERENCES genes(gene_id) ON DELETE CASCADE,
    annotation_type VARCHAR(100) NOT NULL,  -- product_type, molecular_function, cellular_location
    annotation_value TEXT NOT NULL,
    source VARCHAR(100) DEFAULT 'UniProt',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(gene_id, annotation_type, annotation_value, source)
);

COMMENT ON TABLE gene_annotations IS 'Flexible annotations for genes (product types, functions, locations)';
COMMENT ON COLUMN gene_annotations.annotation_type IS 'Type: product_type, molecular_function, cellular_location';

CREATE INDEX idx_gene_annotations_gene ON gene_annotations(gene_id);
CREATE INDEX idx_gene_annotations_type ON gene_annotations(annotation_type);
CREATE INDEX idx_gene_annotations_value ON gene_annotations(annotation_value);
CREATE INDEX idx_gene_annotations_source ON gene_annotations(source);

-- ============================================================================
-- PART 4: Normalized Relationship Tables (Biological Associations)
-- ============================================================================

-- -----------------------------------------------------------------------------
-- gene_pathways: Gene-pathway associations from Reactome
-- Enhanced with v0.3.0 hierarchy and evidence tracking
-- -----------------------------------------------------------------------------
CREATE TABLE gene_pathways (
    id SERIAL PRIMARY KEY,
    gene_id VARCHAR(50) NOT NULL REFERENCES genes(gene_id) ON DELETE CASCADE,
    pathway_id VARCHAR(100) NOT NULL,  -- Reactome ID (e.g., R-HSA-1640170)
    pathway_name TEXT NOT NULL,
    pathway_source VARCHAR(50) DEFAULT 'Reactome',

    -- v0.3.0 enhancements
    parent_pathway_id VARCHAR(100),
    pathway_level INTEGER DEFAULT 1,  -- 1=top-level, 2=sub-pathway, 3=detailed
    pathway_category VARCHAR(200),  -- metabolism, signaling, immune_system, etc.
    evidence_code VARCHAR(10) DEFAULT 'IEA',  -- GO/ECO evidence codes
    confidence_score DECIMAL(3,2) DEFAULT 0.80,  -- 0.0-1.0 data quality score
    gene_role VARCHAR(100),  -- member, regulator, target
    pmids TEXT[],  -- PubMed IDs supporting annotation

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(gene_id, pathway_id, pathway_source)
);

COMMENT ON TABLE gene_pathways IS 'Gene-pathway associations with hierarchical organization and evidence tracking';
COMMENT ON COLUMN gene_pathways.pathway_level IS 'Hierarchy level: 1=top-level, 2=sub-pathway, 3=detailed';
COMMENT ON COLUMN gene_pathways.evidence_code IS 'GO/ECO evidence code (IEA, IDA, IMP, TAS, etc.)';
COMMENT ON COLUMN gene_pathways.confidence_score IS 'Data quality score 0.0-1.0';
COMMENT ON COLUMN gene_pathways.gene_role IS 'Gene role in pathway (member, regulator, target, etc.)';

CREATE INDEX idx_gene_pathways_gene ON gene_pathways(gene_id);
CREATE INDEX idx_gene_pathways_pathway ON gene_pathways(pathway_id);
CREATE INDEX idx_gene_pathways_source ON gene_pathways(pathway_source);
CREATE INDEX idx_gene_pathways_parent ON gene_pathways(parent_pathway_id);
CREATE INDEX idx_gene_pathways_level ON gene_pathways(pathway_level);
CREATE INDEX idx_gene_pathways_category ON gene_pathways(pathway_category);
CREATE INDEX idx_gene_pathways_evidence ON gene_pathways(evidence_code);
CREATE INDEX idx_gene_pathways_confidence ON gene_pathways(confidence_score);
CREATE INDEX idx_gene_pathways_role ON gene_pathways(gene_role);
CREATE INDEX idx_gene_pathways_pmids ON gene_pathways USING GIN(pmids);

-- -----------------------------------------------------------------------------
-- gene_drug_interactions: Drug-gene interaction data
-- Enhanced with v0.3.0 clinical and pharmacological fields
-- -----------------------------------------------------------------------------
CREATE TABLE gene_drug_interactions (
    id SERIAL PRIMARY KEY,
    gene_id VARCHAR(50) NOT NULL REFERENCES genes(gene_id) ON DELETE CASCADE,
    drug_name VARCHAR(500) NOT NULL,
    drug_id VARCHAR(50),  -- DrugCentral struct_id
    interaction_type VARCHAR(100),  -- inhibitor, agonist, antagonist, modulator, etc.
    evidence_level VARCHAR(50),  -- experimental, computational, clinical
    source VARCHAR(50) DEFAULT 'DrugCentral',
    pmid TEXT,  -- Single PMID (legacy)

    -- v0.3.0 enhancements
    drug_chembl_id VARCHAR(50),  -- ChEMBL database identifier
    drugbank_id VARCHAR(20),  -- DrugBank identifier
    clinical_phase VARCHAR(50),  -- Preclinical, Phase I/II/III, Approved, Withdrawn
    approval_status VARCHAR(50),  -- Regulatory approval status
    activity_value DECIMAL(10,4),  -- IC50, Ki, Kd, EC50 value
    activity_unit VARCHAR(20),  -- nM, uM, mg/mL, etc.
    activity_type VARCHAR(50),  -- IC50, Ki, Kd, EC50, etc.
    drug_class VARCHAR(200),  -- Therapeutic drug classification
    drug_type VARCHAR(50),  -- small_molecule, antibody, protein, etc.
    evidence_strength INTEGER DEFAULT 1,  -- 1-5, higher is stronger
    pmids TEXT[],  -- Array of PMIDs

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(gene_id, drug_name, drug_id)
);

COMMENT ON TABLE gene_drug_interactions IS 'Drug-gene interactions with clinical phase and pharmacology data';
COMMENT ON COLUMN gene_drug_interactions.drug_chembl_id IS 'ChEMBL database identifier for cross-referencing';
COMMENT ON COLUMN gene_drug_interactions.clinical_phase IS 'Clinical development phase (Preclinical, Phase I/II/III, Approved, Withdrawn)';
COMMENT ON COLUMN gene_drug_interactions.activity_value IS 'Pharmacological activity value (IC50, Ki, Kd, EC50)';
COMMENT ON COLUMN gene_drug_interactions.evidence_strength IS 'Evidence quality score 1-5 (1=low, 5=high)';

CREATE INDEX idx_gene_drug_gene ON gene_drug_interactions(gene_id);
CREATE INDEX idx_gene_drug_name ON gene_drug_interactions(drug_name);
CREATE INDEX idx_gene_drug_drug_id ON gene_drug_interactions(drug_id);
CREATE INDEX idx_gene_drug_type ON gene_drug_interactions(interaction_type);
CREATE INDEX idx_gene_drug_chembl ON gene_drug_interactions(drug_chembl_id);
CREATE INDEX idx_gene_drug_drugbank ON gene_drug_interactions(drugbank_id);
CREATE INDEX idx_gene_drug_clinical_phase ON gene_drug_interactions(clinical_phase);
CREATE INDEX idx_gene_drug_approval ON gene_drug_interactions(approval_status);
CREATE INDEX idx_gene_drug_activity_type ON gene_drug_interactions(activity_type);
CREATE INDEX idx_gene_drug_class ON gene_drug_interactions(drug_class);
CREATE INDEX idx_gene_drug_drug_type ON gene_drug_interactions(drug_type);
CREATE INDEX idx_gene_drug_evidence_strength ON gene_drug_interactions(evidence_strength);
CREATE INDEX idx_gene_drug_pmids ON gene_drug_interactions USING GIN(pmids);
CREATE INDEX idx_gene_drug_clinical_relevance ON gene_drug_interactions(clinical_phase, approval_status, evidence_strength);

-- -----------------------------------------------------------------------------
-- transcript_go_terms: Gene Ontology term associations
-- -----------------------------------------------------------------------------
CREATE TABLE transcript_go_terms (
    id SERIAL PRIMARY KEY,
    transcript_id VARCHAR(50) NOT NULL REFERENCES transcripts(transcript_id) ON DELETE CASCADE,
    go_id VARCHAR(20) NOT NULL,  -- GO:XXXXXXX
    go_term TEXT NOT NULL,
    go_category VARCHAR(50),  -- molecular_function, biological_process, cellular_component
    evidence_code VARCHAR(10) DEFAULT 'IEA',  -- GO evidence codes
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(transcript_id, go_id)
);

COMMENT ON TABLE transcript_go_terms IS 'Gene Ontology term associations for transcripts';
COMMENT ON COLUMN transcript_go_terms.go_category IS 'GO aspect: molecular_function, biological_process, cellular_component';
COMMENT ON COLUMN transcript_go_terms.evidence_code IS 'GO evidence code (IEA, IDA, IMP, IGI, IEP, etc.)';

CREATE INDEX idx_transcript_go_transcript ON transcript_go_terms(transcript_id);
CREATE INDEX idx_transcript_go_id ON transcript_go_terms(go_id);
CREATE INDEX idx_transcript_go_category ON transcript_go_terms(go_category);
CREATE INDEX idx_transcript_go_evidence ON transcript_go_terms(evidence_code);

-- ============================================================================
-- PART 5: Legacy Tables (Backwards Compatibility - OPTIONAL)
-- ============================================================================
-- Note: These tables are maintained for backwards compatibility with existing
-- queries and analytics. New ETL code uses the normalized schema above.
-- -----------------------------------------------------------------------------

-- -----------------------------------------------------------------------------
-- cancer_transcript_base: Monolithic legacy table
-- -----------------------------------------------------------------------------
CREATE TABLE cancer_transcript_base (
    transcript_id TEXT PRIMARY KEY,
    gene_symbol TEXT,
    gene_id TEXT,
    gene_type TEXT,
    chromosome TEXT,
    coordinates JSONB,
    product_type TEXT[] DEFAULT '{}',
    go_terms JSONB DEFAULT '{}'::jsonb,
    pathways TEXT[] DEFAULT '{}',
    drugs JSONB DEFAULT '{}'::jsonb,
    expression_fold_change FLOAT DEFAULT 1.0,
    expression_freq JSONB DEFAULT '{"high": [], "low": []}'::jsonb,
    cancer_types TEXT[] DEFAULT '{}',
    features JSONB DEFAULT '{}'::jsonb,
    molecular_functions TEXT[] DEFAULT '{}',
    cellular_location TEXT[] DEFAULT '{}',
    drug_scores JSONB DEFAULT '{}'::jsonb,
    alt_transcript_ids JSONB DEFAULT '{}'::jsonb,
    alt_gene_ids JSONB DEFAULT '{}'::jsonb,
    uniprot_ids TEXT[] DEFAULT '{}',
    ncbi_ids TEXT[] DEFAULT '{}',
    refseq_ids TEXT[] DEFAULT '{}',
    source_references JSONB DEFAULT jsonb_build_object(
        'go_terms', jsonb_build_array(),
        'uniprot', jsonb_build_array(),
        'drugs', jsonb_build_array(),
        'pathways', jsonb_build_array(),
        'publications', jsonb_build_array(),
        'pharmgkb_pathways', jsonb_build_array(),
        'evidence_scoring', jsonb_build_array()
    ),
    pdb_ids TEXT[] DEFAULT '{}',
    pharmgkb_pathways JSONB DEFAULT '{}'::jsonb,
    evidence_quality_metrics JSONB DEFAULT jsonb_build_object(
        'overall_confidence', 0.0,
        'evidence_count', 0,
        'source_diversity', 0,
        'clinical_evidence_ratio', 0.0,
        'publication_support_ratio', 0.0,
        'last_assessment', CURRENT_TIMESTAMP
    ),
    pharmgkb_variants JSONB DEFAULT '{}'::jsonb
);

COMMENT ON TABLE cancer_transcript_base IS 'LEGACY: Monolithic table for backwards compatibility (use normalized schema for new code)';

-- Legacy indexes
CREATE INDEX idx_gene_symbol ON cancer_transcript_base(gene_symbol);
CREATE INDEX idx_gene_id ON cancer_transcript_base(gene_id);
CREATE INDEX idx_transcript_gene_symbol ON cancer_transcript_base(gene_symbol);  -- Alias for verification
CREATE INDEX idx_transcript_gene_type ON cancer_transcript_base(gene_type);
CREATE INDEX idx_transcript_chromosome ON cancer_transcript_base(chromosome);
CREATE INDEX idx_product_type ON cancer_transcript_base USING GIN(product_type);
CREATE INDEX idx_pathways ON cancer_transcript_base USING GIN(pathways);
CREATE INDEX idx_drugs ON cancer_transcript_base USING GIN(drugs);
CREATE INDEX idx_features ON cancer_transcript_base USING GIN(features);
CREATE INDEX idx_molecular_functions ON cancer_transcript_base USING GIN(molecular_functions);
CREATE INDEX idx_cellular_location ON cancer_transcript_base USING GIN(cellular_location);
CREATE INDEX idx_alt_transcript_ids ON cancer_transcript_base USING GIN(alt_transcript_ids);
CREATE INDEX idx_alt_gene_ids ON cancer_transcript_base USING GIN(alt_gene_ids);
CREATE INDEX idx_uniprot_ids ON cancer_transcript_base USING GIN(uniprot_ids);
CREATE INDEX idx_ncbi_ids ON cancer_transcript_base USING GIN(ncbi_ids);
CREATE INDEX idx_refseq_ids ON cancer_transcript_base USING GIN(refseq_ids);
CREATE INDEX idx_source_references ON cancer_transcript_base USING GIN(source_references);
CREATE INDEX idx_cross_ref_ids ON cancer_transcript_base USING GIN(uniprot_ids, ncbi_ids, refseq_ids, pdb_ids);
CREATE INDEX idx_pharmgkb_pathways ON cancer_transcript_base USING GIN(pharmgkb_pathways);
CREATE INDEX idx_drugs_pharmgkb ON cancer_transcript_base USING GIN(drugs, pharmgkb_pathways);
CREATE INDEX idx_evidence_quality_metrics ON cancer_transcript_base USING GIN(evidence_quality_metrics);
CREATE INDEX idx_pharmgkb_variants_jsonb ON cancer_transcript_base USING GIN(pharmgkb_variants);

-- -----------------------------------------------------------------------------
-- evidence_scoring_metadata: Evidence scoring system
-- -----------------------------------------------------------------------------
CREATE TABLE evidence_scoring_metadata (
    id SERIAL PRIMARY KEY,
    gene_symbol TEXT NOT NULL,
    drug_id TEXT,
    evidence_score JSONB NOT NULL,
    use_case TEXT NOT NULL DEFAULT 'therapeutic_target',
    confidence_lower FLOAT,
    confidence_upper FLOAT,
    evidence_count INTEGER,
    evidence_quality FLOAT,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    scoring_version TEXT DEFAULT '1.0',
    UNIQUE(gene_symbol, drug_id, use_case)
);

COMMENT ON TABLE evidence_scoring_metadata IS 'LEGACY: Multi-dimensional evidence scoring system';

CREATE INDEX idx_evidence_scoring_gene ON evidence_scoring_metadata(gene_symbol);
CREATE INDEX idx_evidence_scoring_drug ON evidence_scoring_metadata(drug_id);
CREATE INDEX idx_evidence_scoring_use_case ON evidence_scoring_metadata(use_case);
CREATE INDEX idx_evidence_scoring_quality ON evidence_scoring_metadata(evidence_quality);
CREATE INDEX idx_evidence_scoring_updated ON evidence_scoring_metadata(last_updated);
CREATE INDEX idx_evidence_scoring_jsonb ON evidence_scoring_metadata USING GIN(evidence_score);

-- ============================================================================
-- PART 6: Views (Query Convenience)
-- ============================================================================

-- -----------------------------------------------------------------------------
-- gene_id_lookup: Legacy compatibility view
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW gene_id_lookup AS
SELECT
    transcript_id,
    gene_symbol,
    gene_id,
    uniprot_ids,
    ncbi_ids,
    refseq_ids,
    alt_gene_ids,
    alt_transcript_ids,
    CASE
        WHEN pharmgkb_pathways != '{}'::jsonb THEN TRUE
        ELSE FALSE
    END as has_pharmgkb_data
FROM cancer_transcript_base;

COMMENT ON VIEW gene_id_lookup IS 'LEGACY: Simplified view for ID lookups (compatibility)';

-- -----------------------------------------------------------------------------
-- pathway_annotation_coverage: Data quality view
-- -----------------------------------------------------------------------------
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

COMMENT ON VIEW pathway_annotation_coverage IS 'Data quality metrics for pathway annotations';

-- -----------------------------------------------------------------------------
-- drug_interaction_coverage: Data quality view
-- -----------------------------------------------------------------------------
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

COMMENT ON VIEW drug_interaction_coverage IS 'Data quality metrics for drug interactions';

-- ============================================================================
-- PART 7: Materialized Views (Analytics Performance)
-- ============================================================================

-- -----------------------------------------------------------------------------
-- pathway_gene_counts: Pathway enrichment analysis
-- -----------------------------------------------------------------------------
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

COMMENT ON MATERIALIZED VIEW pathway_gene_counts IS 'Pre-computed pathway statistics for enrichment analysis';

CREATE UNIQUE INDEX idx_pathway_counts_id ON pathway_gene_counts(pathway_id, pathway_source);
CREATE INDEX idx_pathway_counts_gene_count ON pathway_gene_counts(gene_count);
CREATE INDEX idx_pathway_counts_category ON pathway_gene_counts(pathway_category);
CREATE INDEX idx_pathway_counts_level ON pathway_gene_counts(pathway_level);
CREATE INDEX idx_pathway_counts_confidence ON pathway_gene_counts(avg_confidence);
CREATE INDEX idx_pathway_counts_members ON pathway_gene_counts USING GIN(gene_members);
CREATE INDEX idx_pathway_counts_symbols ON pathway_gene_counts USING GIN(gene_symbols);

-- -----------------------------------------------------------------------------
-- pathway_druggability: Therapeutic targeting analysis
-- -----------------------------------------------------------------------------
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

COMMENT ON MATERIALIZED VIEW pathway_druggability IS 'Pathway druggability metrics for therapeutic targeting';

CREATE UNIQUE INDEX idx_pathway_drug_id ON pathway_druggability(pathway_id, pathway_source);
CREATE INDEX idx_pathway_drug_percentage ON pathway_druggability(druggability_percentage);
CREATE INDEX idx_pathway_drug_category ON pathway_druggability(pathway_category);
CREATE INDEX idx_pathway_drug_approved ON pathway_druggability USING GIN(approved_drugs);

-- -----------------------------------------------------------------------------
-- drug_gene_summary: Drug target profile
-- -----------------------------------------------------------------------------
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

COMMENT ON MATERIALIZED VIEW drug_gene_summary IS 'Comprehensive drug target profiles with pathway context';

CREATE UNIQUE INDEX idx_drug_summary_name ON drug_gene_summary(drug_name);
CREATE INDEX idx_drug_summary_chembl ON drug_gene_summary(drug_chembl_id);
CREATE INDEX idx_drug_summary_drugbank ON drug_gene_summary(drugbank_id);
CREATE INDEX idx_drug_summary_class ON drug_gene_summary(drug_class);
CREATE INDEX idx_drug_summary_phase ON drug_gene_summary(clinical_phase);
CREATE INDEX idx_drug_summary_target_count ON drug_gene_summary(target_gene_count);
CREATE INDEX idx_drug_summary_genes ON drug_gene_summary USING GIN(target_genes);
CREATE INDEX idx_drug_summary_pathways ON drug_gene_summary USING GIN(affected_pathways);

-- ============================================================================
-- PART 8: Functions (Data Management)
-- ============================================================================

-- -----------------------------------------------------------------------------
-- refresh_pathway_drug_views: Refresh all materialized views
-- -----------------------------------------------------------------------------
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

COMMENT ON FUNCTION refresh_pathway_drug_views() IS 'Refresh all pathway and drug materialized views';

-- -----------------------------------------------------------------------------
-- get_pathway_druggability: Query pathway druggability by name
-- -----------------------------------------------------------------------------
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

COMMENT ON FUNCTION get_pathway_druggability(TEXT) IS 'Query pathway druggability metrics by pathway name';

-- -----------------------------------------------------------------------------
-- get_clinically_relevant_drugs: Find approved/clinical drugs for a gene
-- -----------------------------------------------------------------------------
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

COMMENT ON FUNCTION get_clinically_relevant_drugs(TEXT) IS 'Find clinically relevant drugs for a gene symbol';

-- ============================================================================
-- PART 9: Schema Version Tracking
-- ============================================================================

INSERT INTO schema_version (version_name, description)
VALUES (
    'v0.3.0',
    'Complete bootstrap schema with normalized tables, enhanced pathways/drugs, and materialized views'
);

-- ============================================================================
-- Bootstrap Complete
-- ============================================================================

-- Verify table creation
SELECT
    'Bootstrap complete - Tables created:' as status,
    COUNT(*) as table_count
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE';

-- Show schema version
SELECT version_name, description, applied_at
FROM schema_version
ORDER BY applied_at DESC
LIMIT 1;

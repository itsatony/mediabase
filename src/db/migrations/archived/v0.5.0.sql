-- Update schema to v0.5.0 with PubTator Central gene-publication associations
-- This migration adds comprehensive literature support for LLM-assisted oncology queries

-- =============================================================================
-- PART 1: GENE PUBLICATIONS TABLE (PubTator Central)
-- =============================================================================

-- Create gene_publications table for literature associations
CREATE TABLE IF NOT EXISTS gene_publications (
    id SERIAL PRIMARY KEY,
    gene_id VARCHAR(50) NOT NULL REFERENCES genes(gene_id) ON DELETE CASCADE,
    pmid VARCHAR(20) NOT NULL,
    mention_count INTEGER DEFAULT 1,
    first_seen_year INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (gene_id, pmid)
);

-- Add comprehensive table and column comments for LLM understanding
COMMENT ON TABLE gene_publications IS
'Gene-publication associations from PubTator Central (NCBI).
Source: https://ftp.ncbi.nlm.nih.gov/pub/lu/PubTatorCentral/
License: Public Domain (US Government work)
Update Frequency: Monthly
Coverage: ~95% of genes with published research

Use Cases for LLM Queries:
- Find research papers discussing patient''s aberrantly expressed genes
- Identify recent publications (last 5 years) for novel therapeutic targets
- Discover resistance mechanism literature for upregulated genes
- Find preclinical studies supporting drug-gene interactions
- Identify biomarker validation studies for diagnostic genes

Example Queries:
1. "Show me recent papers about genes overexpressed in my patient"
2. "Find publications discussing resistance mechanisms for ERBB2"
3. "Which of my upregulated genes have the most research literature?"
4. "Find papers linking TP53 mutations to treatment response"

Schema v0.5.0';

COMMENT ON COLUMN gene_publications.gene_id IS
'Internal gene identifier from genes table.
Links to gene_symbol, NCBI Gene ID, and transcript information.';

COMMENT ON COLUMN gene_publications.pmid IS
'PubMed ID (PMID) uniquely identifying the publication.
Can be used to fetch full article metadata from PubMed E-utilities:
https://www.ncbi.nlm.nih.gov/pmc/pmctopmid/#converter';

COMMENT ON COLUMN gene_publications.mention_count IS
'Number of times gene is mentioned in the publication.
Higher counts may indicate more central role in the research.
Extracted using GNormPlus gene normalization tool.';

COMMENT ON COLUMN gene_publications.first_seen_year IS
'Publication year (future enhancement).
Currently NULL - will be populated from PubMed metadata in future versions.
Useful for filtering recent vs historical literature.';

COMMENT ON COLUMN gene_publications.last_updated IS
'Timestamp of last data refresh.
PubTator Central is updated monthly - track when this record was last synchronized.';

-- =============================================================================
-- PART 2: INDEXES FOR EFFICIENT QUERIES
-- =============================================================================

-- Primary lookup indexes
CREATE INDEX IF NOT EXISTS idx_gene_publications_gene_id
ON gene_publications(gene_id);

CREATE INDEX IF NOT EXISTS idx_gene_publications_pmid
ON gene_publications(pmid);

-- Query optimization indexes
CREATE INDEX IF NOT EXISTS idx_gene_publications_mention_count
ON gene_publications(mention_count DESC);

CREATE INDEX IF NOT EXISTS idx_gene_publications_year
ON gene_publications(first_seen_year DESC)
WHERE first_seen_year IS NOT NULL;

-- Composite index for common query pattern: gene + high mention count
CREATE INDEX IF NOT EXISTS idx_gene_publications_gene_mentions
ON gene_publications(gene_id, mention_count DESC);

-- =============================================================================
-- PART 3: MATERIALIZED VIEWS FOR PERFORMANCE
-- =============================================================================

-- Drop existing view if it exists (for clean migration)
DROP MATERIALIZED VIEW IF EXISTS gene_literature_summary CASCADE;

-- Create literature summary view for each gene
CREATE MATERIALIZED VIEW gene_literature_summary AS
SELECT
    g.gene_id,
    g.gene_symbol,
    g.gene_name,
    COUNT(DISTINCT gp.pmid) as publication_count,
    SUM(gp.mention_count) as total_mentions,
    AVG(gp.mention_count) as avg_mentions_per_paper,
    MAX(gp.mention_count) as max_mentions_in_paper,
    MIN(gp.first_seen_year) as earliest_publication_year,
    MAX(gp.first_seen_year) as latest_publication_year,
    COUNT(DISTINCT gp.pmid) FILTER (WHERE gp.first_seen_year >= EXTRACT(YEAR FROM CURRENT_DATE) - 5) as recent_papers_5yr,
    COUNT(DISTINCT gp.pmid) FILTER (WHERE gp.first_seen_year >= EXTRACT(YEAR FROM CURRENT_DATE) - 2) as recent_papers_2yr,
    COUNT(DISTINCT gp.pmid) FILTER (WHERE gp.mention_count >= 10) as highly_discussed_papers,
    array_agg(gp.pmid ORDER BY gp.mention_count DESC) FILTER (WHERE gp.mention_count >= 10) as top_papers,
    MAX(gp.last_updated) as last_updated
FROM genes g
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
GROUP BY g.gene_id, g.gene_symbol, g.gene_name;

-- Create indexes on materialized view
CREATE UNIQUE INDEX idx_literature_summary_gene_id
ON gene_literature_summary(gene_id);

CREATE INDEX idx_literature_summary_symbol
ON gene_literature_summary(gene_symbol);

CREATE INDEX idx_literature_summary_pub_count
ON gene_literature_summary(publication_count DESC);

CREATE INDEX idx_literature_summary_recent_5yr
ON gene_literature_summary(recent_papers_5yr DESC);

CREATE INDEX idx_literature_summary_top_papers
ON gene_literature_summary USING GIN(top_papers);

-- =============================================================================
-- PART 4: PUBLICATION COVERAGE VIEW
-- =============================================================================

-- Create view for publication annotation coverage
CREATE OR REPLACE VIEW publication_coverage AS
SELECT
    COUNT(DISTINCT g.gene_id) as total_genes,
    COUNT(DISTINCT gp.gene_id) as genes_with_publications,
    ROUND(
        (COUNT(DISTINCT gp.gene_id)::DECIMAL / NULLIF(COUNT(DISTINCT g.gene_id), 0) * 100),
        2
    ) as publication_coverage_percentage,
    COUNT(DISTINCT gp.pmid) as unique_publications,
    COUNT(*) as total_gene_publication_associations,
    AVG(gls.publication_count) FILTER (WHERE gls.publication_count > 0) as avg_papers_per_gene,
    MAX(gls.publication_count) as max_papers_for_gene,
    COUNT(DISTINCT gp.gene_id) FILTER (WHERE gls.publication_count >= 100) as highly_studied_genes,
    COUNT(DISTINCT gp.gene_id) FILTER (WHERE gls.recent_papers_5yr >= 10) as actively_researched_genes
FROM genes g
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
LEFT JOIN gene_literature_summary gls ON g.gene_id = gls.gene_id;

COMMENT ON VIEW publication_coverage IS
'Summary statistics for publication annotation coverage across all genes.
Useful for assessing data quality and completeness for LLM queries.';

-- =============================================================================
-- PART 5: UTILITY FUNCTIONS
-- =============================================================================

-- Function to refresh literature summary view
CREATE OR REPLACE FUNCTION refresh_literature_views()
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    REFRESH MATERIALIZED VIEW gene_literature_summary;
    RAISE NOTICE 'Refreshed gene_literature_summary materialized view';
END;
$$;

COMMENT ON FUNCTION refresh_literature_views() IS
'Refresh all literature-related materialized views.
Should be called after each PubTator Central ETL run.
Example: SELECT refresh_literature_views();';

-- Function to get most discussed papers for a gene
CREATE OR REPLACE FUNCTION get_top_papers_for_gene(
    gene_symbol_filter TEXT,
    limit_count INTEGER DEFAULT 10
)
RETURNS TABLE(
    pmid TEXT,
    mention_count INTEGER,
    first_seen_year INTEGER
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        gp.pmid::TEXT,
        gp.mention_count,
        gp.first_seen_year
    FROM gene_publications gp
    INNER JOIN genes g ON gp.gene_id = g.gene_id
    WHERE g.gene_symbol = gene_symbol_filter
    ORDER BY gp.mention_count DESC, gp.first_seen_year DESC NULLS LAST
    LIMIT limit_count;
END;
$$;

COMMENT ON FUNCTION get_top_papers_for_gene(TEXT, INTEGER) IS
'Get top publications for a specific gene symbol, ordered by mention count.
Parameters:
  - gene_symbol_filter: Gene symbol (e.g., ''BRCA1'', ''TP53'')
  - limit_count: Number of papers to return (default 10)
Returns: PMID, mention count, publication year
Example: SELECT * FROM get_top_papers_for_gene(''ERBB2'', 20);';

-- Function to find genes with recent research activity
CREATE OR REPLACE FUNCTION get_recently_researched_genes(
    years_back INTEGER DEFAULT 5,
    min_papers INTEGER DEFAULT 10
)
RETURNS TABLE(
    gene_symbol VARCHAR,
    gene_name VARCHAR,
    recent_paper_count BIGINT,
    total_paper_count BIGINT,
    research_trend_percentage NUMERIC
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        gls.gene_symbol,
        gls.gene_name,
        gls.recent_papers_5yr as recent_paper_count,
        gls.publication_count as total_paper_count,
        ROUND(
            (gls.recent_papers_5yr::DECIMAL / NULLIF(gls.publication_count, 0) * 100),
            2
        ) as research_trend_percentage
    FROM gene_literature_summary gls
    WHERE gls.recent_papers_5yr >= min_papers
    ORDER BY gls.recent_papers_5yr DESC, gls.publication_count DESC
    LIMIT 100;
END;
$$;

COMMENT ON FUNCTION get_recently_researched_genes(INTEGER, INTEGER) IS
'Find genes with significant recent research activity (trending genes).
Useful for identifying emerging therapeutic targets or biomarkers.
Parameters:
  - years_back: Years to look back (default 5)
  - min_papers: Minimum recent papers required (default 10)
Returns: Top 100 genes with most recent research publications
Example: SELECT * FROM get_recently_researched_genes(3, 20);';

-- =============================================================================
-- PART 6: INTEGRATION WITH EXISTING TABLES
-- =============================================================================

-- Add publication count to existing enriched views
-- This is handled by the gene_literature_summary materialized view
-- which can be joined with other tables

-- =============================================================================
-- PART 7: OPEN TARGETS PLATFORM INTEGRATION
-- =============================================================================

-- Create disease ontology table
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
'Disease ontology from Open Targets Platform (https://platform.opentargets.org).
Source: European Bioinformatics Institute (EBI)
License: Creative Commons Attribution 4.0 (CC BY 4.0)
Update Frequency: Quarterly releases
Coverage: ~23,000 diseases with ~7,000 cancer-related entries

Use Cases for LLM Queries:
- Map patient cancer type to standardized disease ontology
- Find related cancer subtypes (e.g., breast cancer → HER2+ breast cancer)
- Identify therapeutic areas for drug development focus
- Discover disease hierarchies for broader therapeutic strategies

Example Queries:
1. "What cancer subtypes are included under breast neoplasm?"
2. "Show me all diseases in the carcinoma therapeutic area"
3. "Find diseases related to ERBB2 amplification"
4. "Which oncology therapeutic areas have the most drug targets?"

Schema v0.5.0';

COMMENT ON COLUMN opentargets_diseases.disease_id IS
'EFO, MONDO, or other ontology identifier (e.g., EFO_0000616 for neoplasm).
Can be used to join with opentargets_gene_disease_associations and opentargets_known_drugs.';

COMMENT ON COLUMN opentargets_diseases.is_cancer IS
'Boolean flag: true if disease is classified under neoplasm/cancer therapeutic areas.
Filter by this column for oncology-specific queries.';

COMMENT ON COLUMN opentargets_diseases.parent_disease_ids IS
'Array of parent disease IDs in ontology hierarchy.
Example: HER2+ breast cancer → breast cancer → carcinoma → neoplasm
Useful for finding related diseases and therapeutic strategies.';

COMMENT ON COLUMN opentargets_diseases.therapeutic_areas IS
'Array of therapeutic area names (e.g., "oncology", "hematology").
Useful for grouping diseases by treatment approach.';

-- Create gene-disease associations table
CREATE TABLE IF NOT EXISTS opentargets_gene_disease_associations (
    association_id SERIAL PRIMARY KEY,
    gene_id TEXT NOT NULL,
    disease_id TEXT NOT NULL REFERENCES opentargets_diseases(disease_id),
    overall_score NUMERIC(5,4) NOT NULL,

    genetic_association_score NUMERIC(5,4),
    somatic_mutation_score NUMERIC(5,4),
    known_drug_score NUMERIC(5,4),
    literature_score NUMERIC(5,4),
    rna_expression_score NUMERIC(5,4),
    pathways_systems_biology_score NUMERIC(5,4),
    animal_model_score NUMERIC(5,4),

    is_direct BOOLEAN DEFAULT true,
    evidence_count INTEGER,
    datasource_count INTEGER,

    tractability_clinical_precedence BOOLEAN,
    tractability_discovery_precedence BOOLEAN,

    metadata JSONB,
    ot_version TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(gene_id, disease_id, ot_version)
);

COMMENT ON TABLE opentargets_gene_disease_associations IS
'Gene-disease associations from Open Targets Platform with comprehensive evidence scores.
Evidence scores range from 0-1, with higher scores indicating stronger associations.

Thresholds for Interpretation:
- overall_score ≥ 0.5: Moderate evidence (default filter)
- overall_score ≥ 0.7: Strong evidence (high confidence for clinical decisions)
- overall_score ≥ 0.85: Very strong evidence (established therapeutic targets)

Use Cases for LLM Queries:
- Identify cancer genes implicated in patient''s disease type
- Find therapeutic targets with strong evidence for specific cancers
- Discover resistance mechanisms via somatic mutation evidence
- Prioritize drug targets based on clinical precedence
- Identify novel biomarkers for cancer subtypes

Example Queries:
1. "Which genes have strong evidence (≥0.7) for association with HER2+ breast cancer?"
2. "Show me genes with high somatic mutation scores for lung adenocarcinoma"
3. "Find targetable genes (tractability_clinical_precedence=true) for colorectal cancer"
4. "Which of my patient''s overexpressed genes have known drug associations?"

Schema v0.5.0';

COMMENT ON COLUMN opentargets_gene_disease_associations.overall_score IS
'Combined evidence score from all data sources (0-1 scale).
Thresholds: ≥0.5 moderate, ≥0.7 strong, ≥0.85 very strong evidence.
Use this score as primary filter for clinical relevance.';

COMMENT ON COLUMN opentargets_gene_disease_associations.somatic_mutation_score IS
'Evidence score from cancer somatic mutations (Cancer Gene Census, COSMIC, IntOGen).
Higher scores indicate well-established cancer driver genes.
Range 0-1, with ≥0.7 indicating strong mutation-disease association.';

COMMENT ON COLUMN opentargets_gene_disease_associations.known_drug_score IS
'Evidence from approved or clinical-phase drugs targeting this gene for this disease.
Higher scores indicate clinically actionable targets with existing therapeutic precedence.
Range 0-1, with ≥0.5 indicating drugs in clinical development.';

COMMENT ON COLUMN opentargets_gene_disease_associations.literature_score IS
'Evidence score from text mining of scientific literature.
Extracted from PubMed abstracts and full-text articles using Europe PMC.
Range 0-1, with higher scores indicating extensive research literature.';

COMMENT ON COLUMN opentargets_gene_disease_associations.tractability_clinical_precedence IS
'Boolean flag: true if gene target has drugs in clinical development or approved.
Indicates higher likelihood of successful drug development.';

-- Create known drugs table
CREATE TABLE IF NOT EXISTS opentargets_known_drugs (
    drug_id SERIAL PRIMARY KEY,
    molecule_chembl_id TEXT,
    molecule_name TEXT NOT NULL,
    molecule_type TEXT,

    target_gene_id TEXT,
    disease_id TEXT REFERENCES opentargets_diseases(disease_id),

    clinical_phase NUMERIC(3,1),
    clinical_phase_label TEXT,
    clinical_status TEXT,

    mechanism_of_action TEXT,
    action_type TEXT,

    drug_type TEXT,
    is_approved BOOLEAN,
    approval_year INTEGER,

    clinical_trial_ids TEXT[],

    metadata JSONB,
    ot_version TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE opentargets_known_drugs IS
'Approved and clinical-stage drugs with target and disease associations from Open Targets Platform.
Data integrated from ChEMBL, FDA, EMA, and ClinicalTrials.gov.

Clinical Phase Interpretation:
- Phase 0: Preclinical (exploratory studies)
- Phase 1: Safety and dosage (20-80 participants)
- Phase 2: Efficacy and side effects (100-300 participants)
- Phase 3: Efficacy and monitoring (300-3000 participants)
- Phase 4: Approved and post-market surveillance

Use Cases for LLM Queries:
- Find approved drugs for patient''s cancer type
- Identify clinical trial opportunities for specific gene targets
- Discover drug repurposing candidates (approved for different indications)
- Assess mechanism of action for therapeutic decision-making
- Find drugs targeting patient''s overexpressed genes

Example Queries:
1. "What approved drugs (phase=4) target ERBB2 for breast cancer?"
2. "Show me clinical trial drugs (phase 2-3) for genes overexpressed in my patient"
3. "Find kinase inhibitors targeting PIK3CA with clinical precedence"
4. "Which drugs have both approved status and target my patient''s resistance genes?"

Schema v0.5.0';

COMMENT ON COLUMN opentargets_known_drugs.clinical_phase IS
'Clinical development phase on 0-4 scale.
0=preclinical, 1-3=clinical trials, 4=approved.
NULL for withdrawn or terminated drugs.
Higher phases indicate greater likelihood of efficacy and safety.';

COMMENT ON COLUMN opentargets_known_drugs.is_approved IS
'Boolean flag: true if drug is approved for any indication.
May differ from specific disease indication in this row.
Use to identify repurposing opportunities (approved for disease A, investigating for disease B).';

COMMENT ON COLUMN opentargets_known_drugs.molecule_chembl_id IS
'ChEMBL identifier for drug molecule (e.g., CHEMBL1743070 for afatinib).
Can be used to cross-reference with ChEMBL database for additional drug properties.';

COMMENT ON COLUMN opentargets_known_drugs.mechanism_of_action IS
'Description of how the drug exerts its therapeutic effect.
Example: "ERBB2 receptor antagonist", "Tyrosine kinase inhibitor".
Useful for understanding drug class and therapeutic strategy.';

-- Create target tractability table
CREATE TABLE IF NOT EXISTS opentargets_target_tractability (
    gene_id TEXT PRIMARY KEY,

    sm_clinical_precedence BOOLEAN,
    sm_discovery_precedence BOOLEAN,
    sm_predicted_tractable BOOLEAN,
    sm_top_bucket TEXT,

    ab_clinical_precedence BOOLEAN,
    ab_predicted_tractable BOOLEAN,
    ab_top_bucket TEXT,

    other_modality_tractable BOOLEAN,

    tractability_summary TEXT,

    metadata JSONB,
    ot_version TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE opentargets_target_tractability IS
'Druggability assessment for gene targets from Open Targets Platform.
Evaluates likelihood of successful small molecule or antibody drug development.

Tractability Categories:
- Clinical Precedence: Drugs exist for this target or family members
- Discovery Precedence: Target has druggable domains/binding sites
- Predicted Tractable: Computational models predict druggability

Use Cases for LLM Queries:
- Prioritize drug targets by druggability for precision oncology
- Identify genes suitable for small molecule vs antibody therapies
- Assess feasibility of targeting novel genes discovered in patient data
- Focus therapeutic development on tractable targets

Example Queries:
1. "Which of my patient''s overexpressed genes have clinical precedence for small molecules?"
2. "Show me genes suitable for antibody therapy (ab_clinical_precedence=true)"
3. "Find tractable targets among resistance mechanism genes"
4. "Which novel targets are predicted tractable but lack clinical precedence?"

Schema v0.5.0';

COMMENT ON COLUMN opentargets_target_tractability.sm_clinical_precedence IS
'Small molecule clinical precedence: true if drugs exist for this target or closely related family members.
Highest confidence for successful drug development.';

COMMENT ON COLUMN opentargets_target_tractability.ab_clinical_precedence IS
'Antibody clinical precedence: true if antibody drugs exist for this target.
Indicates target is accessible to large molecule therapeutics.';

COMMENT ON COLUMN opentargets_target_tractability.sm_predicted_tractable IS
'Computational prediction of small molecule tractability.
Based on structural features, binding pockets, and physicochemical properties.';

-- Create metadata tracking table
CREATE TABLE IF NOT EXISTS opentargets_metadata (
    version TEXT PRIMARY KEY,
    release_date DATE,
    loaded_date TIMESTAMP DEFAULT NOW(),
    record_counts JSONB,
    validation_results JSONB,
    notes TEXT
);

COMMENT ON TABLE opentargets_metadata IS
'Version tracking and statistics for Open Targets Platform data loads.
Use to verify data currency and coverage.';

-- =============================================================================
-- PART 8: INDEXES FOR OPEN TARGETS TABLES
-- =============================================================================

-- Disease indexes
CREATE INDEX IF NOT EXISTS idx_ot_diseases_name
ON opentargets_diseases USING gin(to_tsvector('english', disease_name));

CREATE INDEX IF NOT EXISTS idx_ot_diseases_cancer
ON opentargets_diseases(is_cancer) WHERE is_cancer = true;

CREATE INDEX IF NOT EXISTS idx_ot_diseases_therapeutic_areas
ON opentargets_diseases USING gin(therapeutic_areas);

-- Association indexes for efficient gene and disease lookups
CREATE INDEX IF NOT EXISTS idx_ot_assoc_gene
ON opentargets_gene_disease_associations(gene_id);

CREATE INDEX IF NOT EXISTS idx_ot_assoc_disease
ON opentargets_gene_disease_associations(disease_id);

CREATE INDEX IF NOT EXISTS idx_ot_assoc_score
ON opentargets_gene_disease_associations(overall_score DESC);

CREATE INDEX IF NOT EXISTS idx_ot_assoc_gene_score
ON opentargets_gene_disease_associations(gene_id, overall_score DESC);

-- Partial index for cancer genes with moderate+ evidence
CREATE INDEX IF NOT EXISTS idx_ot_assoc_cancer_genes
ON opentargets_gene_disease_associations(gene_id, overall_score)
WHERE overall_score >= 0.5;

-- Partial index for strong evidence associations
CREATE INDEX IF NOT EXISTS idx_ot_assoc_strong_evidence
ON opentargets_gene_disease_associations(gene_id, disease_id, overall_score)
WHERE overall_score >= 0.7;

-- Index for somatic mutation evidence (cancer driver genes)
CREATE INDEX IF NOT EXISTS idx_ot_assoc_somatic
ON opentargets_gene_disease_associations(gene_id, somatic_mutation_score DESC)
WHERE somatic_mutation_score IS NOT NULL AND somatic_mutation_score >= 0.5;

-- Drug indexes for target and disease lookups
CREATE INDEX IF NOT EXISTS idx_ot_drugs_target
ON opentargets_known_drugs(target_gene_id);

CREATE INDEX IF NOT EXISTS idx_ot_drugs_disease
ON opentargets_known_drugs(disease_id);

CREATE INDEX IF NOT EXISTS idx_ot_drugs_approved
ON opentargets_known_drugs(is_approved, clinical_phase);

CREATE INDEX IF NOT EXISTS idx_ot_drugs_chembl
ON opentargets_known_drugs(molecule_chembl_id)
WHERE molecule_chembl_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ot_drugs_name
ON opentargets_known_drugs USING gin(to_tsvector('english', molecule_name));

-- Partial index for high-phase drugs (Phase 2+)
CREATE INDEX IF NOT EXISTS idx_ot_drugs_clinical
ON opentargets_known_drugs(target_gene_id, clinical_phase, is_approved)
WHERE clinical_phase >= 2;

-- Tractability indexes for druggability assessment
CREATE INDEX IF NOT EXISTS idx_ot_tract_sm
ON opentargets_target_tractability(gene_id)
WHERE sm_clinical_precedence = true OR sm_predicted_tractable = true;

CREATE INDEX IF NOT EXISTS idx_ot_tract_ab
ON opentargets_target_tractability(gene_id)
WHERE ab_clinical_precedence = true OR ab_predicted_tractable = true;

CREATE INDEX IF NOT EXISTS idx_ot_tract_clinical
ON opentargets_target_tractability(gene_id)
WHERE sm_clinical_precedence = true OR ab_clinical_precedence = true;

-- =============================================================================
-- PART 9: SCHEMA VERSION TRACKING
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
    'v0.5.0',
    'PubTator Central and Open Targets Platform integration: comprehensive literature, disease-gene associations, and drug-target evidence for LLM-assisted precision oncology'
)
ON CONFLICT (version_name) DO UPDATE
SET
    applied_at = CURRENT_TIMESTAMP,
    description = EXCLUDED.description;

-- =============================================================================
-- FINAL NOTES
-- =============================================================================

-- MEDIABASE Schema v0.5.0: Comprehensive Precision Oncology Data Platform
--
-- This migration transforms MEDIABASE into a complete LLM-assisted precision oncology
-- platform by integrating two major data sources:
--
-- =============================================================================
-- PART A: PUBTATOR CENTRAL INTEGRATION (NCBI)
-- =============================================================================
--
-- Use Cases:
-- 1. LLM-assisted queries about gene research (e.g., "What papers discuss resistance mechanisms?")
-- 2. Patient-specific literature discovery (e.g., "Find papers about my overexpressed genes")
-- 3. Research trend analysis (e.g., "Which genes are actively being studied?")
-- 4. Evidence-based therapeutic recommendations (e.g., "Show me papers supporting this drug target")
--
-- Data Source: PubTator Central (NCBI)
-- URL: https://ftp.ncbi.nlm.nih.gov/pub/lu/PubTatorCentral/
-- Coverage: ~95% of human genes with research publications
-- Update Frequency: Monthly
-- License: Public Domain (US Government work)
--
-- Expected Statistics (full database):
-- - ~20,000 genes with publication links
-- - ~10-15 million gene-PMID associations
-- - ~5-7 million unique publications
-- - Average ~500-1000 papers per gene
-- - Highly studied genes: >10,000 papers (e.g., TP53, BRCA1, EGFR)
--
-- Tables Added:
-- - gene_publications: Gene-PMID associations with mention counts
-- - gene_literature_summary: Materialized view with publication statistics
-- - publication_coverage: View for data quality assessment
--
-- =============================================================================
-- PART B: OPEN TARGETS PLATFORM INTEGRATION (EBI)
-- =============================================================================
--
-- Use Cases:
-- 1. Disease-gene association discovery (e.g., "Which genes are implicated in HER2+ breast cancer?")
-- 2. Drug-target identification (e.g., "What approved drugs target ERBB2 for breast cancer?")
-- 3. Target prioritization (e.g., "Which overexpressed genes have strong clinical evidence?")
-- 4. Druggability assessment (e.g., "Are my patient's resistance genes tractable targets?")
-- 5. Clinical trial opportunities (e.g., "Find Phase 2-3 drugs for my patient's biomarkers")
-- 6. Drug repurposing (e.g., "Which approved drugs target genes similar to my patient's profile?")
--
-- Data Source: Open Targets Platform (EBI)
-- URL: https://platform.opentargets.org
-- FTP: ftp://ftp.ebi.ac.uk/pub/databases/opentargets/platform/
-- Coverage: ~23,000 diseases (7,000 cancer-related) with evidence-based gene associations
-- Update Frequency: Quarterly releases
-- License: Creative Commons Attribution 4.0 (CC BY 4.0)
--
-- Expected Statistics (cancer-filtered database):
-- - ~7,000 cancer diseases and subtypes
-- - ~50,000-100,000 gene-disease associations (score ≥0.5)
-- - ~10,000-15,000 known drug-target-disease combinations
-- - ~15,000-20,000 genes with tractability assessments
-- - Clinical precedence: ~3,000-5,000 genes with existing drugs
--
-- Evidence Score Thresholds:
-- - overall_score ≥ 0.5: Moderate evidence (suitable for hypothesis generation)
-- - overall_score ≥ 0.7: Strong evidence (high confidence for clinical decisions)
-- - overall_score ≥ 0.85: Very strong evidence (established therapeutic targets)
--
-- Clinical Phase Values:
-- - Phase 0: Preclinical/exploratory
-- - Phase 1-3: Clinical trials (safety, efficacy, large-scale validation)
-- - Phase 4: Approved drugs (post-market surveillance)
--
-- Tables Added:
-- - opentargets_diseases: Cancer disease ontology with hierarchies
-- - opentargets_gene_disease_associations: Evidence-based gene-disease links
-- - opentargets_known_drugs: Clinical-stage and approved drugs with mechanisms
-- - opentargets_target_tractability: Druggability assessments
-- - opentargets_metadata: Version tracking and statistics
--
-- =============================================================================
-- INTEGRATION QUERIES - COMBINING BOTH DATA SOURCES
-- =============================================================================
--
-- Example 1: Find well-researched genes with strong disease associations
-- SELECT
--   g.gene_symbol,
--   gls.publication_count as papers,
--   ogda.overall_score as disease_score,
--   od.disease_name
-- FROM genes g
-- JOIN gene_literature_summary gls ON g.gene_id = gls.gene_id
-- JOIN opentargets_gene_disease_associations ogda ON g.gene_id = ogda.gene_id
-- JOIN opentargets_diseases od ON ogda.disease_id = od.disease_id
-- WHERE gls.publication_count >= 100
--   AND ogda.overall_score >= 0.7
--   AND od.is_cancer = true
-- ORDER BY ogda.overall_score DESC, gls.publication_count DESC
-- LIMIT 50;
--
-- Example 2: Find approved drugs with strong literature support
-- SELECT
--   okd.molecule_name,
--   okd.target_gene_id,
--   g.gene_symbol,
--   gls.publication_count,
--   gls.recent_papers_5yr,
--   okd.mechanism_of_action,
--   od.disease_name
-- FROM opentargets_known_drugs okd
-- JOIN genes g ON okd.target_gene_id = g.gene_id
-- JOIN gene_literature_summary gls ON g.gene_id = gls.gene_id
-- JOIN opentargets_diseases od ON okd.disease_id = od.disease_id
-- WHERE okd.is_approved = true
--   AND gls.recent_papers_5yr >= 10
--   AND od.is_cancer = true
-- ORDER BY gls.recent_papers_5yr DESC
-- LIMIT 30;
--
-- Example 3: Patient-specific therapeutic recommendations
-- SELECT
--   ct.gene_symbol,
--   ct.expression_fold_change,
--   ogda.overall_score as disease_evidence,
--   ogda.known_drug_score,
--   okd.molecule_name,
--   okd.clinical_phase,
--   okd.mechanism_of_action,
--   gls.publication_count,
--   ott.sm_clinical_precedence as druggable
-- FROM cancer_transcript_base ct
-- JOIN opentargets_gene_disease_associations ogda ON ct.gene_id = ogda.gene_id
-- LEFT JOIN opentargets_known_drugs okd ON ct.gene_id = okd.target_gene_id
-- LEFT JOIN opentargets_target_tractability ott ON ct.gene_id = ott.gene_id
-- LEFT JOIN gene_literature_summary gls ON ct.gene_id = gls.gene_id
-- WHERE ct.expression_fold_change >= 2.0  -- Overexpressed genes
--   AND ogda.overall_score >= 0.7         -- Strong disease evidence
--   AND okd.clinical_phase >= 2           -- Clinical stage or approved
-- ORDER BY ogda.overall_score DESC, okd.clinical_phase DESC
-- LIMIT 20;
--
-- =============================================================================
-- POST-MIGRATION STEPS
-- =============================================================================
--
-- 1. Run PubTator ETL:
--    poetry run python scripts/run_etl.py --modules pubtator
--
-- 2. Run Open Targets ETL:
--    poetry run python scripts/run_etl.py --modules opentargets
--
-- 3. Refresh materialized views:
--    SELECT refresh_literature_views();
--
-- 4. Validate data coverage:
--    SELECT * FROM publication_coverage;
--    SELECT * FROM opentargets_metadata;
--
-- 5. Test integrated queries (examples above)
--
-- Schema Version: v0.5.0
-- Migration Date: 2025-11-16

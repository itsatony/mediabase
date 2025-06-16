-- Update schema to v0.1.8 with enhanced evidence scoring support

-- Add evidence scoring metadata table
CREATE TABLE IF NOT EXISTS evidence_scoring_metadata (
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

-- Create indexes for evidence scoring queries
CREATE INDEX IF NOT EXISTS idx_evidence_scoring_gene ON evidence_scoring_metadata(gene_symbol);
CREATE INDEX IF NOT EXISTS idx_evidence_scoring_drug ON evidence_scoring_metadata(drug_id);
CREATE INDEX IF NOT EXISTS idx_evidence_scoring_use_case ON evidence_scoring_metadata(use_case);
CREATE INDEX IF NOT EXISTS idx_evidence_scoring_quality ON evidence_scoring_metadata(evidence_quality);
CREATE INDEX IF NOT EXISTS idx_evidence_scoring_updated ON evidence_scoring_metadata(last_updated);

-- Add GIN index for evidence score JSONB queries
CREATE INDEX IF NOT EXISTS idx_evidence_scoring_jsonb ON evidence_scoring_metadata USING GIN(evidence_score);

-- Update cancer_transcript_base to support enhanced evidence scoring
ALTER TABLE cancer_transcript_base
ALTER COLUMN drug_scores SET DEFAULT jsonb_build_object(
    'use_case_scores', jsonb_build_object(),
    'drug_specific_scores', jsonb_build_object(),
    'last_updated', CURRENT_TIMESTAMP,
    'scoring_version', '1.0'
);

-- Add evidence quality metrics column
ALTER TABLE cancer_transcript_base
ADD COLUMN IF NOT EXISTS evidence_quality_metrics JSONB DEFAULT jsonb_build_object(
    'overall_confidence', 0.0,
    'evidence_count', 0,
    'source_diversity', 0,
    'clinical_evidence_ratio', 0.0,
    'publication_support_ratio', 0.0,
    'last_assessment', CURRENT_TIMESTAMP
);

-- Create GIN index for evidence quality metrics
CREATE INDEX IF NOT EXISTS idx_evidence_quality_metrics ON cancer_transcript_base USING GIN(evidence_quality_metrics);

-- Create materialized view for evidence scoring analytics
CREATE MATERIALIZED VIEW IF NOT EXISTS evidence_scoring_analytics AS
SELECT 
    gene_symbol,
    COUNT(DISTINCT drug_id) FILTER (WHERE drug_id IS NOT NULL) as unique_drugs,
    COUNT(*) as total_evidence_records,
    AVG(evidence_quality) as avg_evidence_quality,
    AVG(confidence_upper - confidence_lower) as avg_confidence_interval_width,
    MAX(last_updated) as latest_update,
    COUNT(*) FILTER (WHERE use_case = 'drug_repurposing') as repurposing_scores,
    COUNT(*) FILTER (WHERE use_case = 'biomarker_discovery') as biomarker_scores,
    COUNT(*) FILTER (WHERE use_case = 'pathway_analysis') as pathway_scores,
    COUNT(*) FILTER (WHERE use_case = 'therapeutic_target') as target_scores
FROM evidence_scoring_metadata
GROUP BY gene_symbol;

-- Create index on materialized view
CREATE UNIQUE INDEX IF NOT EXISTS idx_evidence_analytics_gene ON evidence_scoring_analytics(gene_symbol);

-- Create view for high-confidence drug targets
CREATE OR REPLACE VIEW high_confidence_drug_targets AS
SELECT DISTINCT
    ctb.gene_symbol,
    ctb.gene_id,
    ctb.gene_type,
    ctb.chromosome,
    esm.drug_id,
    (esm.evidence_score->>'overall_score')::float as overall_score,
    esm.confidence_lower,
    esm.confidence_upper,
    esm.evidence_quality,
    esm.evidence_count,
    esm.use_case,
    ctb.drugs->(esm.drug_id)->>'name' as drug_name,
    ctb.drugs->(esm.drug_id)->>'max_phase' as max_phase,
    array_length(ctb.pathways, 1) as pathway_count,
    jsonb_object_keys(ctb.go_terms) as go_term_count
FROM cancer_transcript_base ctb
JOIN evidence_scoring_metadata esm ON ctb.gene_symbol = esm.gene_symbol
WHERE esm.evidence_quality >= 0.7
  AND (esm.evidence_score->>'overall_score')::float >= 60.0
  AND esm.confidence_lower >= 50.0
  AND esm.evidence_count >= 3;

-- Create view for drug repurposing candidates
CREATE OR REPLACE VIEW drug_repurposing_candidates AS
SELECT 
    gene_symbol,
    drug_id,
    (evidence_score->'use_case_scores'->'drug_repurposing'->>'overall_score')::float as repurposing_score,
    (evidence_score->'component_scores'->>'clinical')::float as clinical_score,
    (evidence_score->'component_scores'->>'safety')::float as safety_score,
    evidence_quality,
    evidence_count,
    last_updated
FROM evidence_scoring_metadata
WHERE use_case = 'drug_repurposing'
  AND (evidence_score->'use_case_scores'->'drug_repurposing'->>'overall_score')::float >= 65.0
  AND evidence_quality >= 0.6
ORDER BY (evidence_score->'use_case_scores'->'drug_repurposing'->>'overall_score')::float DESC;

-- Create view for biomarker discovery targets
CREATE OR REPLACE VIEW biomarker_discovery_targets AS
SELECT 
    gene_symbol,
    drug_id,
    (evidence_score->'use_case_scores'->'biomarker_discovery'->>'overall_score')::float as biomarker_score,
    (evidence_score->'component_scores'->>'genomic')::float as genomic_score,
    (evidence_score->'component_scores'->>'clinical')::float as clinical_score,
    evidence_quality,
    evidence_count,
    last_updated
FROM evidence_scoring_metadata
WHERE use_case = 'biomarker_discovery'
  AND (evidence_score->'use_case_scores'->'biomarker_discovery'->>'overall_score')::float >= 60.0
  AND evidence_quality >= 0.5
ORDER BY (evidence_score->'use_case_scores'->'biomarker_discovery'->>'overall_score')::float DESC;

-- Add function to refresh evidence scoring analytics
CREATE OR REPLACE FUNCTION refresh_evidence_scoring_analytics()
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    REFRESH MATERIALIZED VIEW evidence_scoring_analytics;
END;
$$;

-- Add function to get evidence score summary for a gene
CREATE OR REPLACE FUNCTION get_gene_evidence_summary(gene_name TEXT)
RETURNS TABLE(
    use_case TEXT,
    overall_score FLOAT,
    confidence_interval TEXT,
    evidence_count INTEGER,
    evidence_quality FLOAT,
    component_scores JSONB
) 
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        esm.use_case,
        (esm.evidence_score->>'overall_score')::float,
        CONCAT('[', esm.confidence_lower::text, ', ', esm.confidence_upper::text, ']'),
        esm.evidence_count,
        esm.evidence_quality,
        esm.evidence_score->'component_scores'
    FROM evidence_scoring_metadata esm
    WHERE esm.gene_symbol = gene_name
    ORDER BY (esm.evidence_score->>'overall_score')::float DESC;
END;
$$;

-- Add function to compare drugs for a gene across use cases
CREATE OR REPLACE FUNCTION compare_drugs_for_gene(gene_name TEXT)
RETURNS TABLE(
    drug_id TEXT,
    drug_name TEXT,
    repurposing_score FLOAT,
    biomarker_score FLOAT,
    pathway_score FLOAT,
    target_score FLOAT,
    avg_evidence_quality FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        esm.drug_id,
        ctb.drugs->esm.drug_id->>'name' as drug_name,
        MAX(CASE WHEN esm.use_case = 'drug_repurposing' 
            THEN (esm.evidence_score->>'overall_score')::float END) as repurposing_score,
        MAX(CASE WHEN esm.use_case = 'biomarker_discovery' 
            THEN (esm.evidence_score->>'overall_score')::float END) as biomarker_score,
        MAX(CASE WHEN esm.use_case = 'pathway_analysis' 
            THEN (esm.evidence_score->>'overall_score')::float END) as pathway_score,
        MAX(CASE WHEN esm.use_case = 'therapeutic_target' 
            THEN (esm.evidence_score->>'overall_score')::float END) as target_score,
        AVG(esm.evidence_quality) as avg_evidence_quality
    FROM evidence_scoring_metadata esm
    JOIN cancer_transcript_base ctb ON esm.gene_symbol = ctb.gene_symbol
    WHERE esm.gene_symbol = gene_name 
      AND esm.drug_id IS NOT NULL
    GROUP BY esm.drug_id, ctb.drugs->esm.drug_id->>'name'
    HAVING COUNT(*) >= 2  -- At least 2 use cases scored
    ORDER BY AVG(esm.evidence_quality) DESC, target_score DESC NULLS LAST;
END;
$$;

-- Update source_references to include evidence scoring references
ALTER TABLE cancer_transcript_base
ALTER COLUMN source_references SET DEFAULT jsonb_build_object(
    'go_terms', jsonb_build_array(),
    'uniprot', jsonb_build_array(),
    'drugs', jsonb_build_array(),
    'pathways', jsonb_build_array(),
    'publications', jsonb_build_array(),
    'pharmgkb_pathways', jsonb_build_array(),
    'evidence_scoring', jsonb_build_array()
);

-- Update existing rows to include evidence_scoring array if missing
UPDATE cancer_transcript_base
SET source_references = source_references || '{"evidence_scoring": []}'::jsonb
WHERE NOT (source_references ? 'evidence_scoring');

-- Create trigger to update evidence quality metrics when drug_scores change
CREATE OR REPLACE FUNCTION update_evidence_quality_metrics()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    quality_data JSONB;
    overall_confidence FLOAT;
    evidence_count INTEGER;
    source_diversity INTEGER;
    clinical_ratio FLOAT;
    publication_ratio FLOAT;
BEGIN
    -- Extract quality metrics from drug_scores
    IF NEW.drug_scores IS NOT NULL AND NEW.drug_scores != '{}'::jsonb THEN
        -- Calculate overall confidence from use case scores
        SELECT AVG((value->'confidence_interval'->1)::float - (value->'confidence_interval'->0)::float)
        INTO overall_confidence
        FROM jsonb_each(NEW.drug_scores->'use_case_scores');
        
        -- Get evidence count
        SELECT MAX((value->>'evidence_count')::integer)
        INTO evidence_count
        FROM jsonb_each(NEW.drug_scores->'use_case_scores');
        
        -- Calculate source diversity (approximate)
        SELECT COUNT(DISTINCT key)
        INTO source_diversity
        FROM jsonb_each(NEW.source_references);
        
        -- Calculate clinical evidence ratio
        clinical_ratio := CASE 
            WHEN evidence_count > 0 THEN 
                COALESCE((NEW.drug_scores->'use_case_scores'->'drug_repurposing'->'component_scores'->>'clinical')::float / 30.0, 0)
            ELSE 0 
        END;
        
        -- Calculate publication support ratio
        publication_ratio := CASE 
            WHEN evidence_count > 0 THEN 
                COALESCE((NEW.drug_scores->'use_case_scores'->'therapeutic_target'->'component_scores'->>'publication')::float / 20.0, 0)
            ELSE 0 
        END;
        
        -- Build quality metrics object
        quality_data := jsonb_build_object(
            'overall_confidence', COALESCE(1.0 - (overall_confidence / 100.0), 0.0),
            'evidence_count', COALESCE(evidence_count, 0),
            'source_diversity', COALESCE(source_diversity, 0),
            'clinical_evidence_ratio', COALESCE(clinical_ratio, 0.0),
            'publication_support_ratio', COALESCE(publication_ratio, 0.0),
            'last_assessment', CURRENT_TIMESTAMP
        );
        
        NEW.evidence_quality_metrics := quality_data;
    END IF;
    
    RETURN NEW;
END;
$$;

-- Create trigger
DROP TRIGGER IF EXISTS trg_update_evidence_quality ON cancer_transcript_base;
CREATE TRIGGER trg_update_evidence_quality
    BEFORE UPDATE OF drug_scores ON cancer_transcript_base
    FOR EACH ROW
    EXECUTE FUNCTION update_evidence_quality_metrics();

-- Insert schema version record
INSERT INTO schema_version (version_name, description) 
VALUES ('v0.1.8', 'Enhanced evidence scoring system with multi-dimensional analysis')
ON CONFLICT (version_name) DO UPDATE
SET applied_at = CURRENT_TIMESTAMP;
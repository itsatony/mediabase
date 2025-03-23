-- Update schema to v0.1.5 with enhanced publication reference support

-- Create publication reference type
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

-- Add default source_references structure and validation
ALTER TABLE cancer_transcript_base 
ALTER COLUMN source_references SET DEFAULT '{
    "go_terms": [],
    "uniprot": [],
    "drugs": [],
    "pathways": []
}'::jsonb;

-- Add check constraint for source_references structure
ALTER TABLE cancer_transcript_base 
ADD CONSTRAINT valid_source_references 
CHECK (
    jsonb_typeof(source_references) = 'object' 
    AND source_references ? 'go_terms' 
    AND source_references ? 'uniprot' 
    AND source_references ? 'drugs' 
    AND source_references ? 'pathways'
);

-- Create view for common publication queries
CREATE VIEW publication_summary AS
WITH RECURSIVE all_refs AS (
    SELECT jsonb_array_elements(source_references->'go_terms') as ref, 'go_terms' as source
    FROM cancer_transcript_base
    WHERE source_references->'go_terms' IS NOT NULL
    UNION ALL
    SELECT jsonb_array_elements(source_references->'drugs') as ref, 'drugs' as source
    FROM cancer_transcript_base
    WHERE source_references->'drugs' IS NOT NULL
    UNION ALL
    SELECT jsonb_array_elements(source_references->'pathways') as ref, 'pathways' as source
    FROM cancer_transcript_base
    WHERE source_references->'pathways' IS NOT NULL
    UNION ALL
    SELECT jsonb_array_elements(source_references->'uniprot') as ref, 'uniprot' as source
    FROM cancer_transcript_base
    WHERE source_references->'uniprot' IS NOT NULL
)
SELECT DISTINCT 
    ref->>'pmid' as pmid,
    ref->>'title' as title,
    ref->>'journal' as journal,
    (ref->>'year')::integer as year,
    ref->>'evidence_type' as evidence_type,
    ref->>'source_db' as source_db,
    array_agg(DISTINCT source) as reference_sources,
    count(*) as reference_count
FROM all_refs
WHERE ref->>'pmid' IS NOT NULL
GROUP BY ref->>'pmid', ref->>'title', ref->>'journal', ref->>'year', 
         ref->>'evidence_type', ref->>'source_db';

-- Create index for efficient querying
CREATE INDEX idx_source_refs_gin ON cancer_transcript_base 
USING gin ((source_references->'go_terms'), 
          (source_references->'uniprot'), 
          (source_references->'drugs'), 
          (source_references->'pathways'));

-- Update schema version
UPDATE schema_version SET version = 'v0.1.5';

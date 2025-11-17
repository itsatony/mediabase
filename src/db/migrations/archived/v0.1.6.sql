-- Update schema to v0.1.6 with enhanced ID mapping support

-- Add PDB IDs array for protein structure references
ALTER TABLE cancer_transcript_base
ADD COLUMN IF NOT EXISTS pdb_ids TEXT[] DEFAULT '{}';

-- Add cross-reference index
CREATE INDEX IF NOT EXISTS idx_cross_ref_ids ON cancer_transcript_base 
USING GIN(uniprot_ids, ncbi_ids, refseq_ids, pdb_ids);

-- Update source_references to include all reference types
ALTER TABLE cancer_transcript_base
ALTER COLUMN source_references SET DEFAULT jsonb_build_object(
    'go_terms', jsonb_build_array(),
    'uniprot', jsonb_build_array(),
    'drugs', jsonb_build_array(),
    'pathways', jsonb_build_array(),
    'publications', jsonb_build_array()
);

-- Update existing rows to include publications array if missing
UPDATE cancer_transcript_base
SET source_references = source_references || '{"publications": []}'::jsonb
WHERE NOT (source_references ? 'publications');

-- Create optimized view for ID lookups
CREATE OR REPLACE VIEW gene_id_lookup AS
SELECT 
    transcript_id,
    gene_symbol,
    gene_id,
    uniprot_ids,
    ncbi_ids,
    refseq_ids,
    alt_gene_ids,
    alt_transcript_ids
FROM cancer_transcript_base;

-- Update schema version
INSERT INTO schema_version (version_name, description) 
VALUES ('v0.1.6', 'Enhanced ID cross-referencing')
ON CONFLICT (version_name) DO UPDATE
SET applied_at = CURRENT_TIMESTAMP;

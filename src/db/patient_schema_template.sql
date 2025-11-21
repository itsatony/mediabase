-- MEDIABASE Patient Schema Template
-- Version: 0.6.0
-- Purpose: Template for creating patient-specific schemas in shared core database
--
-- Usage: Replace ${PATIENT_ID} with actual patient identifier
-- Example: patient_DEMO_HER2, patient_PATIENT123, patient_TNBC_001
--
-- Design Philosophy:
-- - Sparse storage: Only store fold_change values != 1.0 (baseline)
-- - Simple joins: patient schema joins to public.transcripts via transcript_id
-- - No denormalization: gene_symbol, gene_id remain in public.genes only
-- - LLM-friendly: Clear names, comprehensive COMMENT ON statements

-- ============================================================================
-- SCHEMA CREATION
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS ${SCHEMA_NAME};

COMMENT ON SCHEMA ${SCHEMA_NAME} IS
'Patient-specific data schema for patient ID: ${PATIENT_ID}.
Architecture: Shared core (public schema) + patient schemas.
Created: ${CREATED_DATE}
Storage approach: Sparse (only non-default fold changes stored).';

-- ============================================================================
-- TABLE: expression_data
-- ============================================================================

CREATE TABLE ${SCHEMA_NAME}.expression_data (
    transcript_id VARCHAR(50) PRIMARY KEY,
    expression_fold_change FLOAT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Constraint: Only store non-default values (space optimization)
    CONSTRAINT check_fold_change_not_default CHECK (expression_fold_change != 1.0),

    -- Constraint: Fold change must be positive
    CONSTRAINT check_fold_change_positive CHECK (expression_fold_change > 0)
);

COMMENT ON TABLE ${SCHEMA_NAME}.expression_data IS
'Patient-specific gene expression fold changes.
- Only stores transcripts with fold_change != 1.0 (sparse storage)
- Baseline fold_change = 1.0 is implicit for all transcripts not in this table
- Join with public.transcripts for full transcript metadata
- Join with public.genes (via transcripts) for gene-level data

Query pattern:
  SELECT g.gene_symbol,
         COALESCE(pe.expression_fold_change, t.expression_fold_change, 1.0) as fold_change
  FROM public.transcripts t
  LEFT JOIN ${SCHEMA_NAME}.expression_data pe ON t.transcript_id = pe.transcript_id
  JOIN public.genes g ON t.gene_id = g.gene_id
  WHERE COALESCE(pe.expression_fold_change, t.expression_fold_change, 1.0) > 2.0;';

COMMENT ON COLUMN ${SCHEMA_NAME}.expression_data.transcript_id IS
'Ensembl transcript ID (e.g., ENST00000269305).
References public.transcripts.transcript_id (enforced at application level).';

COMMENT ON COLUMN ${SCHEMA_NAME}.expression_data.expression_fold_change IS
'Linear fold change value relative to normal tissue.
- Values > 1.0: Upregulation/overexpression
- Values < 1.0: Downregulation/underexpression
- Example: 6.0 = 6-fold overexpression, 0.5 = 50% reduced expression
- Conversion from log2FC: fold_change = 2^log2FC';

COMMENT ON COLUMN ${SCHEMA_NAME}.expression_data.created_at IS
'Timestamp when this expression value was first inserted.';

COMMENT ON COLUMN ${SCHEMA_NAME}.expression_data.updated_at IS
'Timestamp when this expression value was last updated.
Updated automatically via trigger on UPDATE operations.';

-- ============================================================================
-- TABLE: metadata
-- ============================================================================

CREATE TABLE ${SCHEMA_NAME}.metadata (
    patient_id VARCHAR(100) PRIMARY KEY,
    upload_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    source_file VARCHAR(500),
    file_format VARCHAR(50),  -- 'deseq2', 'standard', 'custom', 'synthetic'
    normalization_method VARCHAR(100),
    total_transcripts_uploaded INTEGER,
    transcripts_matched INTEGER,
    transcripts_unmatched INTEGER,
    matching_success_rate FLOAT,
    clinical_notes TEXT,
    cancer_type VARCHAR(100),
    cancer_subtype VARCHAR(100),
    tissue_type VARCHAR(100),
    sample_type VARCHAR(100),  -- 'tumor', 'normal', 'cell_line', 'organoid'
    sequencing_platform VARCHAR(100),
    read_depth_millions FLOAT,
    metadata_json JSONB DEFAULT '{}'::jsonb,

    -- Constraint: Success rate between 0 and 1
    CONSTRAINT check_success_rate_valid CHECK (matching_success_rate >= 0 AND matching_success_rate <= 1)
);

COMMENT ON TABLE ${SCHEMA_NAME}.metadata IS
'Patient-specific metadata including upload information and clinical context.
Single row per patient containing provenance and quality metrics.';

COMMENT ON COLUMN ${SCHEMA_NAME}.metadata.patient_id IS
'Unique patient identifier matching the schema name suffix.
Example: For schema patient_DEMO_HER2, patient_id = "DEMO_HER2"';

COMMENT ON COLUMN ${SCHEMA_NAME}.metadata.source_file IS
'Original filename of uploaded transcriptome data.
Example: "patient_results_deseq2_2024.csv"';

COMMENT ON COLUMN ${SCHEMA_NAME}.metadata.file_format IS
'Format of source data file.
Values: "deseq2" (DESeq2 results), "standard" (transcript_id+fold_change),
        "custom" (user-defined), "synthetic" (generated test data)';

COMMENT ON COLUMN ${SCHEMA_NAME}.metadata.normalization_method IS
'RNA-seq normalization method used.
Examples: "DESeq2", "TPM", "FPKM", "TMM", "Upper Quartile"';

COMMENT ON COLUMN ${SCHEMA_NAME}.metadata.matching_success_rate IS
'Fraction of uploaded transcripts successfully matched to database.
Value 0.0-1.0. Example: 0.92 = 92% of transcripts matched successfully.';

COMMENT ON COLUMN ${SCHEMA_NAME}.metadata.cancer_type IS
'Primary cancer type.
Examples: "Breast Cancer", "Lung Adenocarcinoma", "Colorectal Cancer"';

COMMENT ON COLUMN ${SCHEMA_NAME}.metadata.cancer_subtype IS
'Cancer molecular subtype.
Examples: "HER2+", "Triple-Negative", "EGFR-mutant", "MSI-high"';

COMMENT ON COLUMN ${SCHEMA_NAME}.metadata.metadata_json IS
'Flexible JSONB field for additional metadata.
Can store: clinical stage, mutation status, treatment history, etc.
Example: {"stage": "III", "tp53_status": "mutant", "prior_therapy": "none"}';

-- ============================================================================
-- INDEXES
-- ============================================================================

-- Index on fold change for filtering overexpressed/underexpressed genes
CREATE INDEX idx_${SCHEMA_NAME}_expression_fold
ON ${SCHEMA_NAME}.expression_data(expression_fold_change);

-- Index on update timestamp for tracking changes
CREATE INDEX idx_${SCHEMA_NAME}_expression_updated
ON ${SCHEMA_NAME}.expression_data(updated_at DESC);

-- GIN index on JSONB for fast metadata queries
CREATE INDEX idx_${SCHEMA_NAME}_metadata_json
ON ${SCHEMA_NAME}.metadata USING GIN (metadata_json);

-- ============================================================================
-- TRIGGERS
-- ============================================================================

-- Trigger function to update updated_at timestamp
CREATE OR REPLACE FUNCTION ${SCHEMA_NAME}.update_expression_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to automatically update updated_at on row modification
CREATE TRIGGER trigger_update_expression_timestamp
    BEFORE UPDATE ON ${SCHEMA_NAME}.expression_data
    FOR EACH ROW
    EXECUTE FUNCTION ${SCHEMA_NAME}.update_expression_timestamp();

-- ============================================================================
-- PERMISSIONS
-- ============================================================================

-- Grant usage on schema to database user
GRANT USAGE ON SCHEMA ${SCHEMA_NAME} TO ${DB_USER};

-- Grant SELECT, INSERT, UPDATE, DELETE on all tables
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA ${SCHEMA_NAME} TO ${DB_USER};

-- Grant usage on all sequences (for any future serial columns)
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA ${SCHEMA_NAME} TO ${DB_USER};

-- Grant execute on all functions (for triggers)
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA ${SCHEMA_NAME} TO ${DB_USER};

-- ============================================================================
-- VALIDATION QUERIES
-- ============================================================================

-- Query 1: Count patient-specific expression values
-- SELECT COUNT(*) as patient_expression_count
-- FROM ${SCHEMA_NAME}.expression_data;

-- Query 2: Verify sparse storage (should have no fold_change = 1.0)
-- SELECT COUNT(*) as invalid_rows
-- FROM ${SCHEMA_NAME}.expression_data
-- WHERE expression_fold_change = 1.0;
-- Expected: 0 rows

-- Query 3: Check metadata completeness
-- SELECT * FROM ${SCHEMA_NAME}.metadata;

-- Query 4: Verify all transcript_ids exist in public.transcripts
-- SELECT COUNT(*) as orphaned_transcripts
-- FROM ${SCHEMA_NAME}.expression_data pe
-- LEFT JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
-- WHERE t.transcript_id IS NULL;
-- Expected: 0 rows

-- Query 5: Sample patient expression with gene symbols
-- SELECT
--     g.gene_symbol,
--     pe.expression_fold_change,
--     CASE
--         WHEN pe.expression_fold_change > 2.0 THEN 'Overexpressed'
--         WHEN pe.expression_fold_change < 0.5 THEN 'Underexpressed'
--         ELSE 'Normal'
--     END as expression_status
-- FROM ${SCHEMA_NAME}.expression_data pe
-- JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
-- JOIN public.genes g ON t.gene_id = g.gene_id
-- ORDER BY ABS(pe.expression_fold_change - 1.0) DESC
-- LIMIT 20;

-- ============================================================================
-- CLEANUP (if needed)
-- ============================================================================

-- To drop this patient schema completely:
-- DROP SCHEMA IF EXISTS ${SCHEMA_NAME} CASCADE;

-- =============================================================================
-- Schema Cleanup Migration v0.5.1
-- =============================================================================
-- Purpose: Remove legacy/unused fields from cancer_transcript_base
-- Target: Clean up schema before full production ETL run
-- Date: 2025-01-17
--
-- IMPORTANT: This migration removes fields that are no longer used:
-- 1. expression_freq - Never populated, unclear usage
-- 2. cancer_types - Never populated in current ETL
-- 3. pharmgkb_pathways - PharmGKB integration incomplete
-- 4. pharmgkb_variants - PharmGKB integration incomplete
--
-- These fields and their indexes will be permanently removed.
-- =============================================================================

BEGIN;

-- =============================================================================
-- PART 1: Drop unused indexes (must be done before dropping columns)
-- =============================================================================

-- Drop index for pharmgkb_pathways
DROP INDEX IF EXISTS idx_pharmgkb_pathways;
DROP INDEX IF EXISTS idx_drugs_pharmgkb;  -- Composite index involving pharmgkb_pathways
DROP INDEX IF EXISTS idx_pharmgkb_variants_jsonb;

-- =============================================================================
-- PART 2: Remove legacy columns from cancer_transcript_base
-- =============================================================================

-- Remove expression frequency tracking (never populated)
ALTER TABLE cancer_transcript_base
DROP COLUMN IF EXISTS expression_freq CASCADE;

-- Remove cancer types array (never populated)
ALTER TABLE cancer_transcript_base
DROP COLUMN IF EXISTS cancer_types CASCADE;

-- Remove PharmGKB pathway data (incomplete integration)
ALTER TABLE cancer_transcript_base
DROP COLUMN IF EXISTS pharmgkb_pathways CASCADE;

-- Remove PharmGKB variant data (incomplete integration)
ALTER TABLE cancer_transcript_base
DROP COLUMN IF EXISTS pharmgkb_variants CASCADE;

-- =============================================================================
-- PART 3: Clean up source_references JSONB
-- =============================================================================

-- Remove pharmgkb_pathways key from source_references JSONB
-- This ensures the JSONB structure doesn't reference removed fields
UPDATE cancer_transcript_base
SET source_references = source_references - 'pharmgkb_pathways'
WHERE source_references ? 'pharmgkb_pathways';

-- =============================================================================
-- PART 4: Update schema version
-- =============================================================================

-- Track migration completion
DO $$
BEGIN
    -- Check if we need to create schema_version table
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_name = 'schema_version') THEN
        CREATE TABLE schema_version (
            version_name VARCHAR(20) PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            description TEXT
        );
    END IF;

    -- Record this migration
    INSERT INTO schema_version (version_name, description)
    VALUES ('v0.5.1', 'Schema cleanup: Removed legacy fields (expression_freq, cancer_types, pharmgkb_*)')
    ON CONFLICT (version_name) DO NOTHING;
END $$;

COMMIT;

-- =============================================================================
-- Verification queries (run manually after migration)
-- =============================================================================

-- Verify columns were removed:
-- \d cancer_transcript_base

-- Verify no references remain:
-- SELECT column_name FROM information_schema.columns
-- WHERE table_name = 'cancer_transcript_base'
-- AND column_name IN ('expression_freq', 'cancer_types', 'pharmgkb_pathways', 'pharmgkb_variants');

-- Verify schema version:
-- SELECT * FROM schema_version ORDER BY applied_at DESC LIMIT 5;

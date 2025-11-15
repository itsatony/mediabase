#!/usr/bin/env python3
"""
Chunked Migration Script for MEDIABASE

This script executes the migration in smaller, manageable chunks to handle
the large dataset (385K records) without timing out. It creates the normalized
schema incrementally and provides detailed progress tracking.
"""

import sys
import time
import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple
import psycopg2
from psycopg2.extras import execute_batch

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from src.db.database import get_db_manager
from src.utils.logging import get_logger
from src.migration import (
    MigrationController,
    RobustDataExtractor,
    PerformanceOptimizer
)

logger = get_logger(__name__)

def load_db_config() -> Dict[str, Any]:
    """Load database configuration from environment variables."""
    import os
    from dotenv import load_dotenv

    project_root = Path(__file__).parent.parent
    load_dotenv(project_root / '.env')

    return {
        "host": os.environ.get("MB_POSTGRES_HOST", "localhost"),
        "port": int(os.environ.get("MB_POSTGRES_PORT", "5432")),
        "dbname": os.environ.get("MB_POSTGRES_DB", "mbase"),
        "user": os.environ.get("MB_POSTGRES_USER", "postgres"),
        "password": os.environ.get("MB_POSTGRES_PASSWORD", "postgres")
    }

def create_normalized_schema(db_manager) -> bool:
    """Create the normalized database schema."""
    logger.info("🏗️  Creating normalized database schema...")

    schema_sql = """
    -- Normalized genes table
    CREATE TABLE IF NOT EXISTS genes (
        gene_id VARCHAR(50) PRIMARY KEY,
        gene_symbol VARCHAR(100) UNIQUE NOT NULL,
        gene_name TEXT,
        gene_type VARCHAR(100),
        chromosome VARCHAR(10),
        start_position BIGINT,
        end_position BIGINT,
        strand VARCHAR(10),
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Normalized transcripts table
    CREATE TABLE IF NOT EXISTS transcripts (
        transcript_id VARCHAR(50) PRIMARY KEY,
        gene_id VARCHAR(50) REFERENCES genes(gene_id),
        transcript_name TEXT,
        transcript_type VARCHAR(100),
        transcript_support_level INTEGER,
        expression_fold_change DECIMAL DEFAULT 1.0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Gene annotations relationship table
    CREATE TABLE IF NOT EXISTS gene_annotations (
        id SERIAL PRIMARY KEY,
        gene_id VARCHAR(50) REFERENCES genes(gene_id),
        annotation_type VARCHAR(100),
        annotation_value TEXT,
        source VARCHAR(100),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Drug interactions table
    CREATE TABLE IF NOT EXISTS gene_drug_interactions (
        id SERIAL PRIMARY KEY,
        gene_id VARCHAR(50) REFERENCES genes(gene_id),
        drug_name VARCHAR(200),
        drug_id VARCHAR(100),
        interaction_type VARCHAR(100),
        evidence_level VARCHAR(50),
        source VARCHAR(100),
        pmid VARCHAR(20),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- GO terms relationship table
    CREATE TABLE IF NOT EXISTS transcript_go_terms (
        id SERIAL PRIMARY KEY,
        transcript_id VARCHAR(50) REFERENCES transcripts(transcript_id),
        go_id VARCHAR(20),
        go_term TEXT,
        go_category VARCHAR(50),
        evidence_code VARCHAR(10),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Pathways relationship table
    CREATE TABLE IF NOT EXISTS gene_pathways (
        id SERIAL PRIMARY KEY,
        gene_id VARCHAR(50) REFERENCES genes(gene_id),
        pathway_id VARCHAR(100),
        pathway_name TEXT,
        pathway_source VARCHAR(100),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Publications table
    CREATE TABLE IF NOT EXISTS gene_publications (
        id SERIAL PRIMARY KEY,
        gene_id VARCHAR(50) REFERENCES genes(gene_id),
        pmid VARCHAR(20),
        title TEXT,
        authors TEXT,
        journal VARCHAR(200),
        publication_date DATE,
        relevance_score DECIMAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Cross-references table
    CREATE TABLE IF NOT EXISTS gene_cross_references (
        id SERIAL PRIMARY KEY,
        gene_id VARCHAR(50) REFERENCES genes(gene_id),
        external_db VARCHAR(50),
        external_id VARCHAR(100),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Create indexes for performance
    CREATE INDEX IF NOT EXISTS idx_genes_symbol ON genes(gene_symbol);
    CREATE INDEX IF NOT EXISTS idx_transcripts_gene_id ON transcripts(gene_id);
    CREATE INDEX IF NOT EXISTS idx_gene_annotations_gene_id ON gene_annotations(gene_id);
    CREATE INDEX IF NOT EXISTS idx_gene_drug_interactions_gene_id ON gene_drug_interactions(gene_id);
    CREATE INDEX IF NOT EXISTS idx_transcript_go_terms_transcript_id ON transcript_go_terms(transcript_id);
    CREATE INDEX IF NOT EXISTS idx_gene_pathways_gene_id ON gene_pathways(gene_id);
    CREATE INDEX IF NOT EXISTS idx_gene_publications_gene_id ON gene_publications(gene_id);
    CREATE INDEX IF NOT EXISTS idx_gene_cross_references_gene_id ON gene_cross_references(gene_id);
    """

    try:
        with db_manager.transaction():
            db_manager.cursor.execute(schema_sql)
        logger.info("✅ Normalized schema created successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Schema creation failed: {e}")
        return False

def extract_and_load_genes_chunked(db_manager, chunk_size: int = 10000) -> bool:
    """Extract gene data from cancer_transcript_base and load into normalized genes table."""
    logger.info("🧬 Extracting and loading gene data (chunked)...")

    try:
        # Get total count for progress tracking
        db_manager.cursor.execute("SELECT COUNT(DISTINCT gene_id) FROM cancer_transcript_base WHERE gene_id IS NOT NULL")
        total_genes = db_manager.cursor.fetchone()[0]
        logger.info(f"Processing {total_genes:,} unique genes")

        # Extract unique genes with deduplication
        extraction_sql = """
        SELECT DISTINCT ON (gene_id)
            gene_id,
            gene_symbol,
            gene_symbol as gene_name,
            gene_type,
            chromosome,
            CASE WHEN coordinates->>'start' IS NOT NULL
                 THEN (coordinates->>'start')::BIGINT
                 ELSE NULL END as start_position,
            CASE WHEN coordinates->>'end' IS NOT NULL
                 THEN (coordinates->>'end')::BIGINT
                 ELSE NULL END as end_position,
            CASE WHEN coordinates->>'strand' IS NOT NULL
                 THEN coordinates->>'strand'
                 ELSE NULL END as strand,
            'Extracted from cancer_transcript_base' as description
        FROM cancer_transcript_base
        WHERE gene_id IS NOT NULL
            AND gene_symbol IS NOT NULL
            AND gene_symbol NOT ILIKE '%metazoa%'
            AND gene_symbol NOT ILIKE '%scaffold%'
            AND gene_symbol NOT ILIKE '%contig%'
        ORDER BY gene_id, gene_symbol
        """

        db_manager.cursor.execute(extraction_sql)
        all_genes = db_manager.cursor.fetchall()

        # Process in chunks
        processed = 0
        for i in range(0, len(all_genes), chunk_size):
            chunk = all_genes[i:i + chunk_size]

            # Insert chunk
            insert_sql = """
            INSERT INTO genes (gene_id, gene_symbol, gene_name, gene_type, chromosome,
                             start_position, end_position, strand, description)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (gene_id) DO NOTHING
            """

            try:
                execute_batch(
                    db_manager.cursor,
                    insert_sql,
                    chunk,
                    page_size=1000
                )
                db_manager.conn.commit()

                processed += len(chunk)
                logger.info(f"  Processed {processed:,} / {len(all_genes):,} genes ({(processed/len(all_genes))*100:.1f}%)")

            except psycopg2.IntegrityError as e:
                if "duplicate key value" in str(e):
                    logger.warning(f"Duplicate gene detected, skipping chunk: {e}")
                    db_manager.conn.rollback()
                    continue
                else:
                    raise

        # Verify results
        db_manager.cursor.execute("SELECT COUNT(*) FROM genes")
        final_count = db_manager.cursor.fetchone()[0]
        logger.info(f"✅ Loaded {final_count:,} unique genes successfully")

        return True

    except Exception as e:
        logger.error(f"❌ Gene extraction failed: {e}")
        return False

def extract_and_load_transcripts_chunked(db_manager, chunk_size: int = 10000) -> bool:
    """Extract transcript data and load into normalized transcripts table."""
    logger.info("📝 Extracting and loading transcript data (chunked)...")

    try:
        # Get total count
        db_manager.cursor.execute("SELECT COUNT(*) FROM cancer_transcript_base WHERE transcript_id IS NOT NULL")
        total_transcripts = db_manager.cursor.fetchone()[0]
        logger.info(f"Processing {total_transcripts:,} transcripts")

        # Extract transcripts that have corresponding genes
        extraction_sql = """
        SELECT
            ctb.transcript_id,
            ctb.gene_id,
            ctb.transcript_id as transcript_name,
            'protein_coding' as transcript_type,
            1 as transcript_support_level,
            COALESCE(ctb.expression_fold_change, 1.0) as expression_fold_change
        FROM cancer_transcript_base ctb
        INNER JOIN genes g ON g.gene_id = ctb.gene_id
        WHERE ctb.transcript_id IS NOT NULL
        ORDER BY ctb.transcript_id
        """

        db_manager.cursor.execute(extraction_sql)
        all_transcripts = db_manager.cursor.fetchall()

        # Process in chunks
        processed = 0
        for i in range(0, len(all_transcripts), chunk_size):
            chunk = all_transcripts[i:i + chunk_size]

            # Insert chunk
            insert_sql = """
            INSERT INTO transcripts (transcript_id, gene_id, transcript_name, transcript_type,
                                   transcript_support_level, expression_fold_change)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (transcript_id) DO UPDATE SET
                expression_fold_change = EXCLUDED.expression_fold_change
            """

            execute_batch(
                db_manager.cursor,
                insert_sql,
                chunk,
                page_size=1000
            )
            db_manager.conn.commit()

            processed += len(chunk)
            if processed % (chunk_size * 5) == 0 or processed == len(all_transcripts):
                logger.info(f"  Processed {processed:,} / {len(all_transcripts):,} transcripts ({(processed/len(all_transcripts))*100:.1f}%)")

        # Verify results
        db_manager.cursor.execute("SELECT COUNT(*) FROM transcripts")
        final_count = db_manager.cursor.fetchone()[0]
        logger.info(f"✅ Loaded {final_count:,} transcripts successfully")

        return True

    except Exception as e:
        logger.error(f"❌ Transcript extraction failed: {e}")
        return False

def create_materialized_views(db_manager) -> bool:
    """Create materialized views for optimized SOTA queries."""
    logger.info("📊 Creating materialized views for SOTA query optimization...")

    try:
        optimizer = PerformanceOptimizer(db_manager)
        result = optimizer.create_all_materialized_views()

        views_created = len(result.get('views_created', []))
        views_failed = len(result.get('views_failed', []))

        logger.info(f"✅ Materialized views: {views_created} created, {views_failed} failed")

        return views_created > views_failed

    except Exception as e:
        logger.error(f"❌ Materialized view creation failed: {e}")
        return False

def main():
    """Execute chunked migration."""
    logger.info("🚀 Starting chunked MEDIABASE migration...")

    # Load database configuration
    try:
        db_config = load_db_config()
        db_manager = get_db_manager(db_config)
        logger.info("✅ Database connection established")
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return False

    # Create backup
    logger.info("💾 Creating backup...")
    migration_id = f"chunked_{int(time.time())}"
    try:
        controller = MigrationController(db_manager, {'checkpoints_dir': './migration_checkpoints'})
        controller.migration_id = migration_id
        backup_schema = controller.create_backup_schema()
        logger.info(f"✅ Backup created: {backup_schema}")
    except Exception as e:
        logger.error(f"❌ Backup creation failed: {e}")
        return False

    # Execute migration stages
    stages = [
        ("Create normalized schema", create_normalized_schema),
        ("Extract and load genes", extract_and_load_genes_chunked),
        ("Extract and load transcripts", extract_and_load_transcripts_chunked),
        ("Create materialized views", create_materialized_views)
    ]

    for stage_name, stage_func in stages:
        logger.info(f"📍 Stage: {stage_name}")
        start_time = time.time()

        try:
            success = stage_func(db_manager)
            elapsed = time.time() - start_time

            if success:
                logger.info(f"✅ {stage_name} completed in {elapsed:.2f}s")
            else:
                logger.error(f"❌ {stage_name} failed after {elapsed:.2f}s")
                logger.error("Migration aborted. Use backup to rollback if needed.")
                return False

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"❌ {stage_name} crashed after {elapsed:.2f}s: {e}")
            return False

    logger.info("🎉 Chunked migration completed successfully!")
    logger.info("The normalized database schema is now ready for use.")

    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
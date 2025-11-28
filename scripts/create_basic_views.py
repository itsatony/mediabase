#!/usr/bin/env python3
"""
Create basic materialized views for the normalized MEDIABASE schema.

This script creates simplified materialized views that work with the currently
migrated normalized data (genes and transcripts tables).
"""

import sys
import time
import logging
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.db.database import get_db_manager
from src.utils.logging import get_logger

logger = get_logger(__name__)


def load_db_config():
    """Load database configuration from environment variables."""
    import os
    from dotenv import load_dotenv

    project_root = Path(__file__).parent.parent
    load_dotenv(project_root / ".env")

    return {
        "host": os.environ.get("MB_POSTGRES_HOST", "localhost"),
        "port": int(os.environ.get("MB_POSTGRES_PORT", "5435")),
        "dbname": os.environ.get("MB_POSTGRES_DB", "mbase"),
        "user": os.environ.get("MB_POSTGRES_USER", "mbase_user"),
        "password": os.environ.get("MB_POSTGRES_PASSWORD", "mbase_secret"),
    }


def create_basic_materialized_views(db_manager) -> bool:
    """Create basic materialized views that work with current normalized schema."""
    logger.info("📊 Creating basic materialized views...")

    views_sql = """
    -- Gene summary view (basic version)
    DROP MATERIALIZED VIEW IF EXISTS gene_summary_view CASCADE;
    CREATE MATERIALIZED VIEW gene_summary_view AS
    SELECT
        g.gene_id,
        g.gene_symbol,
        g.gene_name,
        g.gene_type,
        g.chromosome,
        g.start_position,
        g.end_position,
        g.strand,
        COUNT(t.transcript_id) as transcript_count,
        AVG(t.expression_fold_change) as avg_expression_fold_change,
        MAX(t.expression_fold_change) as max_expression_fold_change,
        MIN(t.expression_fold_change) as min_expression_fold_change
    FROM genes g
    LEFT JOIN transcripts t ON g.gene_id = t.gene_id
    GROUP BY g.gene_id, g.gene_symbol, g.gene_name, g.gene_type,
             g.chromosome, g.start_position, g.end_position, g.strand;

    -- Transcript enrichment view
    DROP MATERIALIZED VIEW IF EXISTS transcript_enrichment_view CASCADE;
    CREATE MATERIALIZED VIEW transcript_enrichment_view AS
    SELECT
        t.transcript_id,
        t.gene_id,
        g.gene_symbol,
        g.gene_name,
        g.gene_type,
        g.chromosome,
        t.transcript_name,
        t.transcript_type,
        t.transcript_support_level,
        t.expression_fold_change,
        CASE
            WHEN t.expression_fold_change > 2.0 THEN 'upregulated'
            WHEN t.expression_fold_change < 0.5 THEN 'downregulated'
            ELSE 'normal'
        END as expression_status
    FROM transcripts t
    INNER JOIN genes g ON t.gene_id = g.gene_id;

    -- Patient query optimized view (simplified)
    DROP MATERIALIZED VIEW IF EXISTS patient_query_optimized_view CASCADE;
    CREATE MATERIALIZED VIEW patient_query_optimized_view AS
    SELECT
        g.gene_id,
        g.gene_symbol,
        g.gene_name,
        g.gene_type,
        g.chromosome,
        COUNT(t.transcript_id) as transcript_count,
        AVG(t.expression_fold_change) as avg_expression,
        MAX(t.expression_fold_change) as max_expression,
        MIN(t.expression_fold_change) as min_expression,
        CASE
            WHEN MAX(t.expression_fold_change) > 2.0 OR MIN(t.expression_fold_change) < 0.5
            THEN true
            ELSE false
        END as has_significant_expression_change
    FROM genes g
    LEFT JOIN transcripts t ON g.gene_id = t.gene_id
    GROUP BY g.gene_id, g.gene_symbol, g.gene_name, g.gene_type, g.chromosome;

    -- Create indexes on materialized views
    CREATE UNIQUE INDEX IF NOT EXISTS idx_gene_summary_gene_id ON gene_summary_view (gene_id);
    CREATE INDEX IF NOT EXISTS idx_gene_summary_symbol ON gene_summary_view (gene_symbol);
    CREATE INDEX IF NOT EXISTS idx_gene_summary_chromosome ON gene_summary_view (chromosome);
    CREATE INDEX IF NOT EXISTS idx_gene_summary_transcript_count ON gene_summary_view (transcript_count DESC);
    CREATE INDEX IF NOT EXISTS idx_gene_summary_expression ON gene_summary_view (avg_expression_fold_change DESC);

    CREATE UNIQUE INDEX IF NOT EXISTS idx_transcript_enrichment_id ON transcript_enrichment_view (transcript_id);
    CREATE INDEX IF NOT EXISTS idx_transcript_enrichment_gene_id ON transcript_enrichment_view (gene_id);
    CREATE INDEX IF NOT EXISTS idx_transcript_enrichment_symbol ON transcript_enrichment_view (gene_symbol);
    CREATE INDEX IF NOT EXISTS idx_transcript_enrichment_status ON transcript_enrichment_view (expression_status);
    CREATE INDEX IF NOT EXISTS idx_transcript_enrichment_fold_change ON transcript_enrichment_view (expression_fold_change DESC);

    CREATE UNIQUE INDEX IF NOT EXISTS idx_patient_opt_gene_id ON patient_query_optimized_view (gene_id);
    CREATE INDEX IF NOT EXISTS idx_patient_opt_symbol ON patient_query_optimized_view (gene_symbol);
    CREATE INDEX IF NOT EXISTS idx_patient_opt_chromosome ON patient_query_optimized_view (chromosome);
    CREATE INDEX IF NOT EXISTS idx_patient_opt_expression_change ON patient_query_optimized_view (has_significant_expression_change);
    CREATE INDEX IF NOT EXISTS idx_patient_opt_max_expression ON patient_query_optimized_view (max_expression DESC);
    """

    try:
        with db_manager.transaction():
            db_manager.cursor.execute(views_sql)

        logger.info("✅ Basic materialized views created successfully")

        # Get view statistics
        stats_sql = """
        SELECT
            schemaname,
            matviewname,
            n_tup_ins as row_count
        FROM pg_stat_user_tables
        WHERE schemaname = 'public'
        AND relname LIKE '%_view'
        ORDER BY matviewname;
        """

        db_manager.cursor.execute(stats_sql)
        view_stats = db_manager.cursor.fetchall()

        logger.info("📊 View statistics:")
        for schema, view_name, row_count in view_stats:
            logger.info(f"  {view_name}: {row_count:,} rows")

        return True

    except Exception as e:
        logger.error(f"❌ Failed to create basic materialized views: {e}")
        return False


def main():
    """Create basic materialized views."""
    logger.info("🚀 Creating basic materialized views for normalized MEDIABASE...")

    # Load database configuration
    try:
        db_config = load_db_config()
        db_manager = get_db_manager(db_config)
        logger.info("✅ Database connection established")
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return False

    # Create basic materialized views
    success = create_basic_materialized_views(db_manager)

    if success:
        logger.info("🎉 Basic materialized views created successfully!")
        logger.info("The normalized schema is now ready with optimized query views.")
    else:
        logger.error("❌ Failed to create materialized views")

    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

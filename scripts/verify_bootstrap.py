#!/usr/bin/env python3
"""
Bootstrap Schema Verification Script

This script validates that the bootstrap_schema.sql creates all expected
database objects including tables, indexes, views, materialized views,
and functions for the v0.3.0 schema.
"""

import sys
import os
from pathlib import Path
from typing import Dict, List, Set
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.database import get_db_manager

console = Console()


# Expected database objects for v0.3.0 schema
EXPECTED_TABLES = {
    # Normalized core tables
    'genes',
    'transcripts',
    'gene_cross_references',
    'gene_annotations',

    # Normalized relationship tables
    'gene_pathways',
    'gene_drug_interactions',
    'transcript_go_terms',

    # Legacy tables (backwards compatibility)
    'cancer_transcript_base',
    'evidence_scoring_metadata',

    # Infrastructure
    'schema_version',
}

EXPECTED_INDEXES = {
    # genes table indexes
    'genes_pkey',
    'idx_genes_symbol',
    'idx_genes_type',
    'idx_genes_chromosome',

    # transcripts table indexes
    'transcripts_pkey',
    'idx_transcripts_gene',
    'idx_transcripts_type',

    # gene_cross_references indexes
    'gene_cross_references_pkey',
    'idx_gene_xref_gene',
    'idx_gene_xref_db',
    'idx_gene_xref_external_id',

    # gene_annotations indexes
    'gene_annotations_pkey',
    'idx_gene_annotations_gene',
    'idx_gene_annotations_type',

    # gene_pathways indexes
    'gene_pathways_pkey',
    'idx_gene_pathways_gene',
    'idx_gene_pathways_pathway',
    'idx_gene_pathways_source',
    'idx_gene_pathways_parent',
    'idx_gene_pathways_level',
    'idx_gene_pathways_category',
    'idx_gene_pathways_evidence',
    'idx_gene_pathways_confidence',
    'idx_gene_pathways_role',
    'idx_gene_pathways_pmids',

    # gene_drug_interactions indexes
    'gene_drug_interactions_pkey',
    'idx_gene_drug_gene',
    'idx_gene_drug_name',
    'idx_gene_drug_chembl',
    'idx_gene_drug_drugbank',
    'idx_gene_drug_clinical_phase',
    'idx_gene_drug_approval',
    'idx_gene_drug_activity_type',
    'idx_gene_drug_class',
    'idx_gene_drug_type',
    'idx_gene_drug_evidence_strength',
    'idx_gene_drug_pmids',
    'idx_gene_drug_clinical_relevance',

    # transcript_go_terms indexes
    'transcript_go_terms_pkey',
    'idx_transcript_go_transcript',
    'idx_transcript_go_id',
    'idx_transcript_go_category',

    # cancer_transcript_base indexes
    'cancer_transcript_base_pkey',
    'idx_transcript_gene_symbol',
    'idx_transcript_gene_type',
    'idx_transcript_chromosome',

    # schema_version indexes
    'schema_version_pkey',
}

EXPECTED_MATERIALIZED_VIEWS = {
    'pathway_gene_counts',
    'pathway_druggability',
    'drug_gene_summary',
}

EXPECTED_REGULAR_VIEWS = {
    'pathway_annotation_coverage',
    'drug_interaction_coverage',
}

EXPECTED_FUNCTIONS = {
    'refresh_pathway_drug_views',
    'get_pathway_druggability',
    'get_clinically_relevant_drugs',
}

EXPECTED_TYPES = {
    'publication_reference',
}


def get_existing_tables(db_manager) -> Set[str]:
    """Get all existing tables in the database."""
    if not db_manager.cursor:
        return set()

    db_manager.cursor.execute("""
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
    """)
    return {row[0] for row in db_manager.cursor.fetchall()}


def get_existing_indexes(db_manager) -> Set[str]:
    """Get all existing indexes in the database."""
    if not db_manager.cursor:
        return set()

    db_manager.cursor.execute("""
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = 'public'
    """)
    return {row[0] for row in db_manager.cursor.fetchall()}


def get_existing_materialized_views(db_manager) -> Set[str]:
    """Get all existing materialized views in the database."""
    if not db_manager.cursor:
        return set()

    db_manager.cursor.execute("""
        SELECT matviewname
        FROM pg_matviews
        WHERE schemaname = 'public'
    """)
    return {row[0] for row in db_manager.cursor.fetchall()}


def get_existing_regular_views(db_manager) -> Set[str]:
    """Get all existing regular views in the database."""
    if not db_manager.cursor:
        return set()

    db_manager.cursor.execute("""
        SELECT viewname
        FROM pg_views
        WHERE schemaname = 'public'
    """)
    return {row[0] for row in db_manager.cursor.fetchall()}


def get_existing_functions(db_manager) -> Set[str]:
    """Get all existing functions in the database."""
    if not db_manager.cursor:
        return set()

    db_manager.cursor.execute("""
        SELECT DISTINCT proname
        FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE n.nspname = 'public'
    """)
    return {row[0] for row in db_manager.cursor.fetchall()}


def get_existing_types(db_manager) -> Set[str]:
    """Get all existing custom types in the database."""
    if not db_manager.cursor:
        return set()

    db_manager.cursor.execute("""
        SELECT typname
        FROM pg_type
        WHERE typtype = 'c'
        AND typnamespace = 'public'::regnamespace
    """)
    return {row[0] for row in db_manager.cursor.fetchall()}


def get_schema_version(db_manager) -> str:
    """Get current schema version."""
    if not db_manager.cursor:
        return "Unknown"

    try:
        db_manager.cursor.execute("""
            SELECT version_name
            FROM schema_version
            ORDER BY applied_at DESC
            LIMIT 1
        """)
        result = db_manager.cursor.fetchone()
        return result[0] if result else "No version found"
    except Exception:
        return "schema_version table not found"


def print_comparison_table(
    title: str,
    expected: Set[str],
    actual: Set[str],
    show_extra: bool = True
) -> bool:
    """Print a comparison table between expected and actual items."""
    missing = expected - actual
    extra = actual - expected if show_extra else set()

    table = Table(title=title, show_header=True)
    table.add_column("Status", style="bold")
    table.add_column("Object Name")

    # All expected items found
    for item in sorted(expected & actual):
        table.add_row("[green]✓[/green]", item)

    # Missing items
    for item in sorted(missing):
        table.add_row("[red]✗ MISSING[/red]", item)

    # Extra items (if requested)
    if show_extra:
        for item in sorted(extra):
            table.add_row("[yellow]+ EXTRA[/yellow]", item)

    console.print(table)
    console.print()

    return len(missing) == 0


def verify_foreign_keys(db_manager) -> bool:
    """Verify critical foreign key constraints exist."""
    if not db_manager.cursor:
        return False

    expected_fks = {
        ('transcripts', 'gene_id', 'genes'),
        ('gene_cross_references', 'gene_id', 'genes'),
        ('gene_annotations', 'gene_id', 'genes'),
        ('gene_pathways', 'gene_id', 'genes'),
        ('gene_drug_interactions', 'gene_id', 'genes'),
        ('transcript_go_terms', 'transcript_id', 'transcripts'),
    }

    db_manager.cursor.execute("""
        SELECT
            tc.table_name,
            kcu.column_name,
            ccu.table_name AS foreign_table_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage AS ccu
            ON ccu.constraint_name = tc.constraint_name
            AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_schema = 'public'
    """)

    actual_fks = {(row[0], row[1], row[2]) for row in db_manager.cursor.fetchall()}

    table = Table(title="Foreign Key Constraints", show_header=True)
    table.add_column("Status", style="bold")
    table.add_column("Table")
    table.add_column("Column")
    table.add_column("References")

    all_found = True
    for table_name, column_name, ref_table in sorted(expected_fks):
        if (table_name, column_name, ref_table) in actual_fks:
            table.add_row("[green]✓[/green]", table_name, column_name, ref_table)
        else:
            table.add_row("[red]✗ MISSING[/red]", table_name, column_name, ref_table)
            all_found = False

    console.print(table)
    console.print()

    return all_found


def main():
    """Main verification routine."""
    console.print(Panel.fit(
        "[bold cyan]Bootstrap Schema Verification[/bold cyan]\n"
        "Validating v0.3.0 database schema",
        border_style="cyan"
    ))
    console.print()

    # Load configuration
    project_root = Path(__file__).parent.parent
    env_path = project_root / '.env'
    load_dotenv(env_path)

    config = {
        "host": os.environ.get("MB_POSTGRES_HOST", "localhost"),
        "port": int(os.environ.get("MB_POSTGRES_PORT", "5435")),
        "dbname": os.environ.get("MB_POSTGRES_NAME", "mediabase"),
        "user": os.environ.get("MB_POSTGRES_USER", "mbase_user"),
        "password": os.environ.get("MB_POSTGRES_PASSWORD", "mbase_secret")
    }

    # Connect to database
    db_manager = get_db_manager(config)
    if not db_manager.connect():
        console.print("[red]Failed to connect to database[/red]")
        return 1

    console.print(f"[green]Connected to database:[/green] {config['dbname']} at {config['host']}:{config['port']}")
    console.print()

    # Check schema version
    version = get_schema_version(db_manager)
    if version == "v0.3.0":
        console.print(f"[green]Schema version: {version} ✓[/green]")
    else:
        console.print(f"[red]Schema version: {version} (expected v0.3.0) ✗[/red]")
    console.print()

    # Run all verifications
    all_passed = True

    # Tables
    existing_tables = get_existing_tables(db_manager)
    tables_ok = print_comparison_table("Tables", EXPECTED_TABLES, existing_tables, show_extra=True)
    all_passed = all_passed and tables_ok

    # Indexes (show only missing, not extra)
    existing_indexes = get_existing_indexes(db_manager)
    indexes_ok = print_comparison_table("Indexes", EXPECTED_INDEXES, existing_indexes, show_extra=False)
    all_passed = all_passed and indexes_ok

    # Materialized Views
    existing_mat_views = get_existing_materialized_views(db_manager)
    mat_views_ok = print_comparison_table("Materialized Views", EXPECTED_MATERIALIZED_VIEWS, existing_mat_views)
    all_passed = all_passed and mat_views_ok

    # Regular Views
    existing_views = get_existing_regular_views(db_manager)
    views_ok = print_comparison_table("Regular Views", EXPECTED_REGULAR_VIEWS, existing_views)
    all_passed = all_passed and views_ok

    # Functions
    existing_functions = get_existing_functions(db_manager)
    functions_ok = print_comparison_table("Functions", EXPECTED_FUNCTIONS, existing_functions, show_extra=False)
    all_passed = all_passed and functions_ok

    # Custom Types
    existing_types = get_existing_types(db_manager)
    types_ok = print_comparison_table("Custom Types", EXPECTED_TYPES, existing_types)
    all_passed = all_passed and types_ok

    # Foreign Keys
    fks_ok = verify_foreign_keys(db_manager)
    all_passed = all_passed and fks_ok

    # Final summary
    console.print()
    if all_passed:
        console.print(Panel.fit(
            "[bold green]✓ All verifications passed![/bold green]\n"
            "Bootstrap schema is correctly configured.",
            border_style="green"
        ))
        return 0
    else:
        console.print(Panel.fit(
            "[bold red]✗ Some verifications failed[/bold red]\n"
            "See details above for missing or incorrect objects.",
            border_style="red"
        ))
        return 1


if __name__ == "__main__":
    sys.exit(main())

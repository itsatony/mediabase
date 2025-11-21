#!/usr/bin/env python3
"""
Example queries for the new normalized MEDIABASE schema.

This script demonstrates how to query the normalized database schema
with optimized materialized views for high-performance cancer transcriptomics analysis.

Usage:
    poetry run python scripts/query_examples_normalized.py --example oncogenes
    poetry run python scripts/query_examples_normalized.py --example drug-targets
    poetry run python scripts/query_examples_normalized.py --example pathways
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from src.db.database import get_db_manager
from src.utils.logging import setup_logging, console
from rich.table import Table
from rich.panel import Panel

# Setup logging
logger = setup_logging(module_name=__name__)


class NormalizedSchemaExamples:
    """Example queries for the normalized MEDIABASE schema."""

    def __init__(self, db_config: Dict[str, Any]):
        """Initialize with database configuration."""
        self.db_manager = get_db_manager(db_config)
        if not self.db_manager.ensure_connection():
            raise Exception("Failed to connect to database")

    def find_oncogenes(
        self, min_fold_change: float = 2.0, limit: int = 20
    ) -> List[Dict]:
        """
        Example 1: Find significantly upregulated oncogenes

        Uses the normalized schema with optimized joins to identify
        potential oncogene targets based on expression fold change.
        """
        query = """
            SELECT
                t.transcript_id,
                g.gene_symbol,
                g.gene_type,
                g.chromosome,
                t.expression_fold_change,
                STRING_AGG(DISTINCT ga.annotation_value, '; ') as product_types,
                STRING_AGG(DISTINCT gp.pathway_name, '; ') as pathways,
                COUNT(DISTINCT gdi.drug_name) as available_drugs,
                CASE
                    WHEN t.expression_fold_change > 5.0 THEN 'High Priority'
                    WHEN t.expression_fold_change > 3.0 THEN 'Medium Priority'
                    ELSE 'Standard'
                END as priority_level
            FROM transcripts t
            JOIN genes g ON t.gene_id = g.gene_id
            LEFT JOIN gene_annotations ga ON g.gene_id = ga.gene_id AND ga.annotation_type = 'product_type'
            LEFT JOIN gene_pathways gp ON g.gene_id = gp.gene_id
            LEFT JOIN gene_drug_interactions gdi ON g.gene_id = gdi.gene_id
            WHERE t.expression_fold_change >= %s
                AND g.gene_type = 'protein_coding'
            GROUP BY t.transcript_id, g.gene_symbol, g.gene_type, g.chromosome, t.expression_fold_change
            ORDER BY t.expression_fold_change DESC
            LIMIT %s
        """

        cursor = self.db_manager.cursor
        cursor.execute(query, (min_fold_change, limit))

        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def find_drug_targets(
        self, min_fold_change: float = 1.5, limit: int = 15
    ) -> List[Dict]:
        """
        Example 2: Find druggable targets with existing drug interactions

        Identifies genes with both significant expression changes and
        existing drug interactions for therapeutic targeting.
        """
        query = """
            SELECT DISTINCT
                g.gene_symbol,
                t.expression_fold_change,
                gdi.drug_name,
                gdi.interaction_type,
                gdi.source as drug_source,
                CASE
                    WHEN gdi.source = 'drugcentral' THEN 'High Confidence'
                    WHEN gdi.source = 'chembl' THEN 'Medium Confidence'
                    ELSE 'Standard'
                END as confidence_level
            FROM transcripts t
            JOIN genes g ON t.gene_id = g.gene_id
            JOIN gene_drug_interactions gdi ON g.gene_id = gdi.gene_id
            WHERE t.expression_fold_change >= %s
                AND g.gene_type = 'protein_coding'
            ORDER BY t.expression_fold_change DESC, gdi.drug_name
            LIMIT %s
        """

        cursor = self.db_manager.cursor
        cursor.execute(query, (min_fold_change, limit))

        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def analyze_pathways(self, min_gene_count: int = 3) -> List[Dict]:
        """
        Example 3: Pathway enrichment analysis using normalized schema

        Analyzes pathway-level expression changes by aggregating
        transcript-level data across pathway memberships.
        """
        query = """
            WITH pathway_stats AS (
                SELECT
                    gp.pathway_name,
                    COUNT(DISTINCT g.gene_id) as gene_count,
                    COUNT(DISTINCT t.transcript_id) as transcript_count,
                    AVG(t.expression_fold_change) as avg_expression,
                    STDDEV(t.expression_fold_change) as expression_variance,
                    ARRAY_AGG(DISTINCT g.gene_symbol ORDER BY t.expression_fold_change DESC) as top_genes
                FROM gene_pathways gp
                JOIN genes g ON gp.gene_id = g.gene_id
                JOIN transcripts t ON g.gene_id = t.gene_id
                WHERE ABS(t.expression_fold_change - 1.0) > 0.3  -- Significant change
                GROUP BY gp.pathway_name
                HAVING COUNT(DISTINCT g.gene_id) >= %s
            )
            SELECT
                pathway_name,
                gene_count,
                transcript_count,
                ROUND(avg_expression::numeric, 2) as average_expression,
                ROUND(expression_variance::numeric, 2) as variance,
                CASE
                    WHEN avg_expression > 1.5 THEN 'Activated'
                    WHEN avg_expression < 0.7 THEN 'Suppressed'
                    ELSE 'Mixed'
                END as pathway_status,
                top_genes[1:5] as example_genes
            FROM pathway_stats
            ORDER BY ABS(avg_expression - 1.0) DESC, gene_count DESC
            LIMIT 20
        """

        cursor = self.db_manager.cursor
        cursor.execute(query, (min_gene_count,))

        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_gene_summary_stats(self) -> Dict[str, int]:
        """
        Example 4: Database statistics using normalized schema

        Demonstrates querying across multiple normalized tables
        to get comprehensive database statistics.
        """
        stats = {}
        cursor = self.db_manager.cursor

        # Basic counts
        cursor.execute("SELECT COUNT(*) FROM genes")
        stats["total_genes"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM transcripts")
        stats["total_transcripts"] = cursor.fetchone()[0]

        # Enrichment stats
        cursor.execute("SELECT COUNT(DISTINCT gene_id) FROM gene_drug_interactions")
        stats["genes_with_drugs"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT gene_id) FROM gene_pathways")
        stats["genes_with_pathways"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT transcript_id) FROM transcript_go_terms")
        stats["transcripts_with_go_terms"] = cursor.fetchone()[0]

        # Coverage percentages
        if stats["total_genes"] > 0:
            stats["drug_coverage_percent"] = round(
                (stats["genes_with_drugs"] / stats["total_genes"]) * 100, 1
            )
            stats["pathway_coverage_percent"] = round(
                (stats["genes_with_pathways"] / stats["total_genes"]) * 100, 1
            )

        return stats


def display_results(results: List[Dict], title: str, description: str):
    """Display query results in a formatted table."""
    if not results:
        console.print(f"[yellow]No results found for {title}[/yellow]")
        return

    # Create table
    table = Table(title=title, show_header=True, header_style="bold magenta")

    # Add columns based on first result
    for key in results[0].keys():
        table.add_column(key.replace("_", " ").title())

    # Add rows
    for result in results:
        values = []
        for value in result.values():
            if isinstance(value, (list, tuple)) and value:
                # Format arrays nicely
                values.append(
                    str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
                )
            elif isinstance(value, float):
                values.append(f"{value:.2f}")
            else:
                values.append(str(value) if value is not None else "")
        table.add_row(*values)

    # Display with description
    console.print(Panel(description, title="Query Description", border_style="blue"))
    console.print(table)
    console.print()


def main():
    """Run example queries for the normalized schema."""
    parser = argparse.ArgumentParser(
        description="Run example queries for normalized MEDIABASE schema"
    )
    parser.add_argument(
        "--example",
        choices=["oncogenes", "drug-targets", "pathways", "stats", "all"],
        default="all",
        help="Which example to run",
    )
    parser.add_argument("--db-name", default="mediabase", help="Database name")

    args = parser.parse_args()

    # Database configuration
    db_config = {
        "host": "localhost",
        "port": 5435,
        "dbname": args.db_name,
        "user": "mbase_user",
        "password": "mbase_secret",
    }

    try:
        examples = NormalizedSchemaExamples(db_config)

        console.print(
            "[bold green]MEDIABASE Normalized Schema Query Examples[/bold green]"
        )
        console.print(f"[dim]Database: {args.db_name}[/dim]")
        console.print()

        if args.example in ["oncogenes", "all"]:
            results = examples.find_oncogenes()
            display_results(
                results,
                "Upregulated Oncogenes",
                "Find significantly overexpressed genes using normalized schema with optimized joins",
            )

        if args.example in ["drug-targets", "all"]:
            results = examples.find_drug_targets()
            display_results(
                results,
                "Druggable Targets",
                "Identify therapeutic targets with existing drug interactions",
            )

        if args.example in ["pathways", "all"]:
            results = examples.analyze_pathways()
            display_results(
                results,
                "Pathway Analysis",
                "Pathway-level expression analysis using normalized gene_pathways table",
            )

        if args.example in ["stats", "all"]:
            stats = examples.get_gene_summary_stats()
            console.print(
                Panel.fit(
                    "\n".join(
                        [
                            f"[bold]{k.replace('_', ' ').title()}:[/bold] {v:,}"
                            for k, v in stats.items()
                        ]
                    ),
                    title="Database Statistics",
                    border_style="green",
                )
            )

        console.print(
            "[bold green]✓[/bold green] Query examples completed successfully!"
        )

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        logger.error(f"Failed to run examples: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Evidence Scoring CLI for MEDIABASE.

This script runs the comprehensive evidence scoring system that integrates
multiple data sources to generate confidence-based scores for cancer research.
"""

import sys
import argparse
import json
from pathlib import Path
from typing import Dict, Any

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.etl.evidence_scoring import EvidenceScoringProcessor
from src.db.database import get_db_manager
from src.utils.logging import setup_logging
from rich.console import Console
from rich.table import Table

console = Console()
logger = setup_logging(module_name=__name__)


def load_config() -> Dict[str, Any]:
    """Load configuration for evidence scoring."""
    import os
    from dotenv import load_dotenv
    
    # Load environment variables
    project_root = Path(__file__).parent.parent
    env_path = project_root / '.env'
    load_dotenv(env_path)
    
    return {
        'cache_dir': '/tmp/mediabase/cache',
        'skip_scores': False,
        'force_download': False,
        'host': os.environ.get('MB_POSTGRES_HOST', 'localhost'),
        'port': int(os.environ.get('MB_POSTGRES_PORT', '5435')),
        'dbname': os.environ.get('MB_POSTGRES_NAME', 'mediabase'),
        'user': os.environ.get('MB_POSTGRES_USER', 'mbase_user'),
        'password': os.environ.get('MB_POSTGRES_PASSWORD', 'mbase_secret')
    }


def display_scoring_results(stats: Dict[str, Any]) -> None:
    """Display evidence scoring results in a formatted table."""
    if not stats:
        console.print("[yellow]No scoring results to display[/yellow]")
        return
    
    # Overall statistics table
    overall_table = Table(title="Evidence Scoring Results - Overall Statistics")
    overall_table.add_column("Metric", style="cyan")
    overall_table.add_column("Value", style="green")
    
    overall_stats = stats.get('overall_statistics', {})
    overall_table.add_row("Total Genes Scored", str(stats.get('total_genes_scored', 0)))
    overall_table.add_row("Mean Score", f"{overall_stats.get('mean_score', 0):.2f}")
    overall_table.add_row("Median Score", f"{overall_stats.get('median_score', 0):.2f}")
    overall_table.add_row("Standard Deviation", f"{overall_stats.get('std_score', 0):.2f}")
    overall_table.add_row("Min Score", f"{overall_stats.get('min_score', 0):.2f}")
    overall_table.add_row("Max Score", f"{overall_stats.get('max_score', 0):.2f}")
    
    console.print(overall_table)
    
    # Use case statistics table
    use_case_stats = stats.get('use_case_statistics', {})
    if use_case_stats:
        console.print("\n")
        use_case_table = Table(title="Evidence Scoring Results - By Use Case")
        use_case_table.add_column("Use Case", style="cyan")
        use_case_table.add_column("Mean Score", style="green")
        use_case_table.add_column("High Confidence (>70)", style="bold green")
        use_case_table.add_column("Medium Confidence (40-70)", style="yellow")
        use_case_table.add_column("Low Confidence (<40)", style="red")
        
        for use_case, case_stats in use_case_stats.items():
            use_case_table.add_row(
                use_case.replace('_', ' ').title(),
                f"{case_stats.get('mean_score', 0):.2f}",
                str(case_stats.get('high_confidence_genes', 0)),
                str(case_stats.get('medium_confidence_genes', 0)),
                str(case_stats.get('low_confidence_genes', 0))
            )
        
        console.print(use_case_table)


def test_evidence_scoring(limit_records: int = 10) -> None:
    """Test evidence scoring with a limited number of records."""
    console.print(f"[cyan]Testing evidence scoring with {limit_records} records[/cyan]")
    
    config = load_config()
    
    try:
        # Get database configuration from config
        db_config = {
            'host': config['host'],
            'port': config['port'],
            'dbname': config['dbname'],
            'user': config['user'],
            'password': config['password']
        }
        
        db_manager = get_db_manager(db_config)
        if not db_manager.connect():
            console.print("[red]Failed to connect to database[/red]")
            return
        
        # Initialize evidence scoring processor
        processor = EvidenceScoringProcessor(config)
        processor.connection = db_manager.conn
        
        # Run evidence scoring
        console.print("[yellow]Running evidence scoring...[/yellow]")
        stats = processor.process_evidence_scoring(limit_records=limit_records)
        
        # Display results
        display_scoring_results(stats)
        
        # Save results to file
        results_file = project_root / "evidence_scoring_results.json"
        with open(results_file, 'w') as f:
            json.dump(stats, f, indent=2, default=str)
        
        console.print(f"\n[green]Results saved to: {results_file}[/green]")
        
    except Exception as e:
        console.print(f"[red]Error during evidence scoring: {e}[/red]")
        import traceback
        traceback.print_exc()


def run_full_evidence_scoring() -> None:
    """Run evidence scoring for all records in the database."""
    console.print("[cyan]Running full evidence scoring for all records[/cyan]")
    
    config = load_config()
    
    try:
        # Get database configuration from config
        db_config = {
            'host': config['host'],
            'port': config['port'],
            'dbname': config['dbname'],
            'user': config['user'],
            'password': config['password']
        }
        
        db_manager = get_db_manager(db_config)
        if not db_manager.connect():
            console.print("[red]Failed to connect to database[/red]")
            return
        
        # Initialize evidence scoring processor
        processor = EvidenceScoringProcessor(config)
        processor.connection = db_manager.conn
        
        # Run evidence scoring
        console.print("[yellow]Running evidence scoring for all records...[/yellow]")
        stats = processor.process_evidence_scoring()
        
        # Display results
        display_scoring_results(stats)
        
        # Save results to file
        results_file = project_root / "evidence_scoring_full_results.json"
        with open(results_file, 'w') as f:
            json.dump(stats, f, indent=2, default=str)
        
        console.print(f"\n[green]Full results saved to: {results_file}[/green]")
        
    except Exception as e:
        console.print(f"[red]Error during evidence scoring: {e}[/red]")
        import traceback
        traceback.print_exc()


def main():
    """Main function to handle command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run evidence scoring for MEDIABASE cancer research database"
    )
    parser.add_argument(
        '--test', 
        action='store_true',
        help='Run test with limited records (default: 10 records)'
    )
    parser.add_argument(
        '--limit', 
        type=int, 
        default=10,
        help='Number of records to process in test mode (default: 10)'
    )
    parser.add_argument(
        '--full',
        action='store_true',
        help='Run evidence scoring for all records in database'
    )
    
    args = parser.parse_args()
    
    if args.test:
        test_evidence_scoring(limit_records=args.limit)
    elif args.full:
        run_full_evidence_scoring()
    else:
        console.print("[yellow]Please specify --test or --full mode[/yellow]")
        parser.print_help()


if __name__ == "__main__":
    main()
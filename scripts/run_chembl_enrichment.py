#!/usr/bin/env python
"""Run ChEMBL drug data integration for Cancer Transcriptome Base.

This script downloads, processes, and integrates ChEMBL drug data with
the Cancer Transcriptome Base.
"""

# Standard library imports
import argparse
import logging
import sys
import os
from typing import Dict, Any

# Add parent directory to path to allow imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Local imports
from src.etl.chembl_drugs import ChemblDrugProcessor
from src.db.database import get_db_manager
from src.utils.logging import setup_logging, console


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed argument namespace
    """
    parser = argparse.ArgumentParser(description="Run ChEMBL drug data integration")

    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Force download of ChEMBL data even if cached",
    )

    parser.add_argument(
        "--skip-scores", action="store_true", help="Skip drug score calculation"
    )

    parser.add_argument(
        "--max-phase-cutoff",
        type=int,
        default=0,
        help="Only include drugs with max phase >= this value (0-4, where 4 is approved)",
    )

    parser.add_argument(
        "--chembl-schema",
        type=str,
        default="chembl_temp",
        help="Schema name for ChEMBL data tables",
    )

    parser.add_argument(
        "--chembl-version", type=str, default="35", help="ChEMBL version to use"
    )

    parser.add_argument(
        "--no-temp-schema",
        action="store_true",
        help="Do not use a temporary schema for ChEMBL data",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set the logging level",
    )

    parser.add_argument(
        "--batch-size", type=int, default=100, help="Batch size for database operations"
    )

    return parser.parse_args()


def main() -> None:
    """Run ChEMBL integration pipeline."""
    args = parse_args()

    # Set up logging
    setup_logging()
    # Set the logging level directly
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    # Display header
    console.print("\n[bold cyan]Running ChEMBL Drug Enrichment[/bold cyan]")
    console.print(f"Log level: [green]{args.log_level}[/green]")

    # Build processor configuration
    config: Dict[str, Any] = {
        "force_download": args.force_download,
        "skip_scores": args.skip_scores,
        "use_temp_schema": not args.no_temp_schema,
        "chembl_schema": args.chembl_schema,
        "max_phase_cutoff": args.max_phase_cutoff,
        "batch_size": args.batch_size,
        "chembl_version": args.chembl_version,
    }

    # Initialize the database manager
    db_manager = get_db_manager()

    if not db_manager.check_connection():
        console.print(
            "[bold red]Database connection failed. Please check your configuration.[/bold red]"
        )
        sys.exit(1)

    # Initialize and run the ChEMBL processor
    try:
        processor = ChemblDrugProcessor(config)
        # The processor already has the config from initialization, so we don't pass it again
        processor.run()
        console.print(
            "[bold green]ChEMBL drug enrichment completed successfully![/bold green]"
        )
    except Exception as e:
        console.print(f"[bold red]ChEMBL drug enrichment failed: {e}[/bold red]")
        raise
    finally:
        # Close database connection
        if db_manager.conn and not getattr(db_manager.conn, "closed", True):
            db_manager.conn.close()


if __name__ == "__main__":
    main()

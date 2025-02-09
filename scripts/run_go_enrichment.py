#!/usr/bin/env python3
"""
Script to run GO term enrichment pipeline for Cancer Transcriptome Base.

This script handles the downloading and processing of GO terms,
calculating term hierarchies, and enriching transcript data.
"""

import sys
import logging
import argparse
from pathlib import Path
from typing import Dict, Any
import os
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.logging import RichHandler
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.etl.go_terms import GOTermProcessor

# Setup logging with rich handler
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)]
)
logger = logging.getLogger("go_enrichment")
console = Console()

def load_config() -> Dict[str, Any]:
    """Load configuration from environment variables."""
    # Load .env file
    load_dotenv(project_root / '.env')
    
    # Required environment variables
    required_vars = [
        'MB_POSTGRES_HOST',
        'MB_POSTGRES_PORT',
        'MB_POSTGRES_NAME',
        'MB_POSTGRES_USER',
        'MB_POSTGRES_PASSWORD',
        'MB_GOTERM_DATA_URL',
        'MB_CACHE_DIR'
    ]
    
    # Check for missing variables
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        console.print(f"[red]Missing required environment variables: {', '.join(missing)}[/red]")
        sys.exit(1)
    
    return {
        'go_obo_url': os.getenv('MB_GOTERM_DATA_URL'),
        'cache_dir': os.getenv('MB_CACHE_DIR'),
        'cache_ttl': int(os.getenv('MB_CACHE_TTL', '86400')),
        'batch_size': int(os.getenv('MB_BATCH_SIZE', '1000')),
        'host': os.getenv('MB_POSTGRES_HOST'),
        'port': int(os.getenv('MB_POSTGRES_PORT', '5432')),
        'dbname': os.getenv('MB_POSTGRES_NAME'),
        'user': os.getenv('MB_POSTGRES_USER'),
        'password': os.getenv('MB_POSTGRES_PASSWORD')
    }

def setup_argument_parser() -> argparse.ArgumentParser:
    """Set up command line argument parser."""
    parser = argparse.ArgumentParser(
        description="Run GO term enrichment pipeline for Cancer Transcriptome Base"
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        help='Number of terms to process per batch'
    )
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Set logging level'
    )
    parser.add_argument(
        '--force-download',
        action='store_true',
        help='Force new download of GO.obo file'
    )
    parser.add_argument(
        '--aspect',
        choices=['molecular_function', 'biological_process', 'cellular_component'],
        help='Filter by GO aspect'
    )
    return parser

def main():
    """Main execution function."""
    parser = setup_argument_parser()
    args = parser.parse_args()
    
    # Set log level
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    # Load configuration
    config = load_config()
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Initializing GO term processor...", total=None)
            processor = GOTermProcessor(config)
            
            # Verify schema version
            if processor.db_manager.get_current_version() != 'v0.1.4':
                raise RuntimeError("Database schema must be v0.1.4")
            
            progress.update(task, description="Running GO term enrichment pipeline...")
            processor.run()
            
            # Verify source references
            if processor.db_manager.cursor:
                processor.db_manager.cursor.execute("""
                    SELECT COUNT(*) 
                    FROM cancer_transcript_base 
                    WHERE source_references->'go_terms' != '[]'::jsonb
                """)
                result = processor.db_manager.cursor.fetchone()
                ref_count = result[0] if result else 0
                console.print(f"\n[green]Added GO term references to {ref_count:,} records[/green]")
            
        console.print("\n[green]GO term enrichment completed successfully![/green]")
        
    except Exception as e:
        console.print(f"\n[red]Error: {str(e)}[/red]")
        logger.exception("Pipeline failed")
        sys.exit(1)

if __name__ == "__main__":
    main()

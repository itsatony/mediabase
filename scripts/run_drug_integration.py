#!/usr/bin/env python3
"""Script to run drug integration pipeline."""

import sys
import os
import logging
import argparse
from pathlib import Path
from typing import Dict, Any
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.logging import RichHandler
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.etl.drugs import DrugProcessor
from src.etl.publications import PublicationsProcessor

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)]
)
logger = logging.getLogger("drug_integration")
console = Console()

def check_environment() -> bool:
    """Verify required environment variables."""
    required_vars = [
        'MB_DRUGCENTRAL_DATA_URL',
        'MB_POSTGRES_HOST',
        'MB_POSTGRES_NAME',
        'MB_POSTGRES_USER',
        'MB_POSTGRES_PASSWORD'
    ]
    
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        console.print(f"[red]Missing required environment variables: {', '.join(missing)}[/red]")
        return False
        
    # Validate DrugCentral URL format
    drugcentral_url = os.getenv('MB_DRUGCENTRAL_DATA_URL', '')
    if not drugcentral_url.endswith(('.tsv', '.tsv.gz')):
        console.print("[red]MB_DRUGCENTRAL_DATA_URL should point to a .tsv or .tsv.gz file[/red]")
        return False
        
    return True

def main() -> None:
    """Main execution function for the drug integration pipeline."""
    load_dotenv()
    
    parser = argparse.ArgumentParser(description="Run drug integration pipeline")
    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Batch size for processing'
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
        help='Force new download of DrugCentral data'
    )
    parser.add_argument(
        '--skip-scores',
        action='store_true',
        help='Skip drug score calculation'
    )
    parser.add_argument(
        '--skip-publication-enrichment',
        action='store_true',
        help='Skip publication reference enrichment'
    )
    
    args = parser.parse_args()
    
    logging.getLogger().setLevel(args.log_level)
    logger.debug("Debug logging enabled")
    
    if not check_environment():
        sys.exit(1)
    
    config = {
        'drugcentral_url': os.getenv('MB_DRUGCENTRAL_DATA_URL'),
        'cache_dir': os.getenv('MB_CACHE_DIR', '/tmp/mediabase/cache'),
        'cache_ttl': int(os.getenv('MB_CACHE_TTL', '86400')),
        'batch_size': args.batch_size,
        # Database connectivity
        'host': os.getenv('MB_POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('MB_POSTGRES_PORT', '5432')),
        'dbname': os.getenv('MB_POSTGRES_NAME', 'mediabase'),
        'user': os.getenv('MB_POSTGRES_USER', 'postgres'),
        'password': os.getenv('MB_POSTGRES_PASSWORD', 'postgres'),
        # Optional synergy weighting
        'drug_pathway_weight': float(os.getenv('MB_DRUG_PATHWAY_WEIGHT', '1.0'))
    }

    try:
        console.print("\n[bold]Starting Drug Integration Pipeline[/bold]")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Initializing drug processor...", total=None)
            processor = DrugProcessor(config)
            processor.run()
            
            # Run publication enrichment if not skipped
            if not args.skip_publication_enrichment:
                progress.update(task, description="Enriching drug publications...")
                pub_processor = PublicationsProcessor(config)
                pub_processor.run()
                
        console.print("\n[green]Drug integration completed successfully![/green]")
    except Exception as e:
        console.print(f"\n[red]Drug integration pipeline failed:[/red] {str(e)}")
        logger.exception("Pipeline failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
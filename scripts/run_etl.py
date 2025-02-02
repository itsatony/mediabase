#!/usr/bin/env python3
"""Master ETL script to process transcripts, gene products, pathways, and drugs."""

import sys
import logging
from pathlib import Path
from rich.console import Console
from rich.logging import RichHandler
from dotenv import load_dotenv
import os

from src.etl.transcript import TranscriptProcessor
from src.etl.products import ProductProcessor
from src.etl.pathways import PathwayProcessor
from src.etl.drugs import DrugProcessor

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)]
)
logger = logging.getLogger("master_etl")
console = Console()

def main() -> None:
    """Main ETL orchestration function."""
    load_dotenv()
    config = {
        'cache_dir':  Path(os.getenv('MB_CACHE_DIR', '/tmp/mediabase/cache')),
        'batch_size': int(os.getenv('MB_BATCH_SIZE', '1000')),
        'host':       os.getenv('MB_POSTGRES_HOST', 'localhost'),
        'port':       int(os.getenv('MB_POSTGRES_PORT', '5432')),
        'dbname':     os.getenv('MB_POSTGRES_NAME', 'mediabase'),
        'user':       os.getenv('MB_POSTGRES_USER', 'postgres'),
        'password':   os.getenv('MB_POSTGRES_PASSWORD', 'postgres')
    }

    try:
        console.print("[bold green]Starting transcript ETL...[/bold green]")
        transcript_processor = TranscriptProcessor(config)
        transcript_processor.run()
        
        console.print("[bold green]Running product classification...[/bold green]")
        product_processor = ProductProcessor(config)
        product_processor.run()
        
        console.print("[bold green]Running pathway enrichment...[/bold green]")
        pathway_processor = PathwayProcessor(config)
        pathway_processor.enrich_transcripts()
        
        console.print("[bold green]Running drug integration...[/bold green]")
        drug_processor = DrugProcessor(config)
        drug_processor.run()
        
        console.print("[green]\nAll ETL steps completed successfully![/green]")
    except Exception as e:
        logger.exception(f"ETL pipeline failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
"""ETL pipeline runner script."""

import os
import logging
from pathlib import Path
import argparse
from dotenv import load_dotenv
from src.etl.transcript import TranscriptProcessor

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_config():
    """Load configuration from environment variables."""
    # Load .env file
    env_path = Path(__file__).parent.parent / '.env'
    load_dotenv(env_path)
    
    return {
        'gtf_url': os.getenv('MB_GENCODE_GTF_URL'),
        'cache_dir': os.getenv('MB_CACHE_DIR', '/tmp/mediabase/cache'),
        'batch_size': int(os.getenv('MB_BATCH_SIZE', '1000')),
        'host': os.getenv('MB_POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('MB_POSTGRES_PORT', '5432')),
        'dbname': os.getenv('MB_POSTGRES_NAME', 'mediabase'),
        'user': os.getenv('MB_POSTGRES_USER', 'postgres'),
        'password': os.getenv('MB_POSTGRES_PASSWORD', 'postgres')
    }

def main():
    """Main entry point for ETL pipeline."""
    parser = argparse.ArgumentParser(description='Run ETL pipeline')
    parser.add_argument('--module', choices=['transcript'], 
                       default='transcript',
                       help='ETL module to run')
    args = parser.parse_args()
    
    config = load_config()
    
    if args.module == 'transcript':
        processor = TranscriptProcessor(config)
        processor.run()

if __name__ == '__main__':
    main()

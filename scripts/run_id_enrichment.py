#!/usr/bin/env python3
"""Script to run ID enrichment pipeline for Cancer Transcriptome Base."""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any
from rich.console import Console
from rich.logging import RichHandler
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.etl.id_enrichment import IDEnrichmentProcessor

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)]
)
logger = logging.getLogger("id_enrichment")
console = Console()

def load_config() -> Dict[str, Any]:
    """Load configuration from environment variables."""
    load_dotenv()
    
    # Required environment variables
    required_vars = [
        'MB_POSTGRES_HOST',
        'MB_POSTGRES_PORT',
        'MB_POSTGRES_NAME',
        'MB_POSTGRES_USER',
        'MB_POSTGRES_PASSWORD',
        'MB_CACHE_DIR'
    ]
    
    # Check for missing variables
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        console.print(f"[red]Missing required environment variables: {', '.join(missing)}[/red]")
        sys.exit(1)
    
    return {
        'uniprot_mapping_url': os.getenv('MB_UNIPROT_MAPPING_URL', 'https://rest.uniprot.org/idmapping/run'),
        'ncbi_gene_info_url': os.getenv('MB_NCBI_GENE_INFO_URL', 'https://ftp.ncbi.nlm.nih.gov/gene/DATA/gene_info.gz'),
        'hgnc_complete_set_url': os.getenv('MB_HGNC_COMPLETE_SET_URL', 'https://ftp.ebi.ac.uk/pub/databases/genenames/hgnc/tsv/hgnc_complete_set.txt'),
        'ensembl_refseq_url': os.getenv('MB_ENSEMBL_REFSEQ_URL', 'https://ftp.ensembl.org/pub/current_tsv/homo_sapiens/Homo_sapiens.GRCh38.113.refseq.tsv.gz'),
        'ensembl_entrez_url': os.getenv('MB_ENSEMBL_ENTREZ_URL', 'https://ftp.ensembl.org/pub/current_tsv/homo_sapiens/Homo_sapiens.GRCh38.113.entrez.tsv.gz'),
        'cache_dir': os.getenv('MB_CACHE_DIR'),
        'cache_ttl': int(os.getenv('MB_CACHE_TTL') or '86400'),
        'batch_size': int(os.getenv('MB_BATCH_SIZE') or '1000'),
        'host': os.getenv('MB_POSTGRES_HOST'),
        'port': int(os.getenv('MB_POSTGRES_PORT') or '5432'),
        'dbname': os.getenv('MB_POSTGRES_NAME'),
        'user': os.getenv('MB_POSTGRES_USER'),
        'password': os.getenv('MB_POSTGRES_PASSWORD')
    }

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Run ID enrichment pipeline")
    parser.add_argument(
        '--batch-size',
        type=int,
        help='Number of records to process per batch'
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
        help='Force new download of ID mapping files'
    )
    parser.add_argument(
        '--id-types',
        choices=['all', 'uniprot', 'ncbi', 'ensembl', 'hgnc', 'refseq'],
        default='all',
        help='Specific ID types to enrich'
    )
    return parser.parse_args()

def main() -> None:
    """Main execution function."""
    args = parse_args()
    
    # Set log level
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    # Load configuration
    config = load_config()
    
    # Add command-line arguments to config
    if args.batch_size:
        config['batch_size'] = args.batch_size
    config['force_download'] = args.force_download
    config['id_types'] = args.id_types
    
    try:
        # Initialize and run ID enrichment processor
        processor = IDEnrichmentProcessor(config)
        processor.run()
        
        console.print("[green]ID enrichment completed successfully![/green]")
        
    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
        logger.exception("Pipeline failed")
        sys.exit(1)

if __name__ == "__main__":
    main()

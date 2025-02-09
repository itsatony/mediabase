#!/usr/bin/env python3
"""Master ETL script to process transcripts, gene products, pathways, and drugs."""

import sys
import logging
from pathlib import Path
from rich.console import Console
from rich.logging import RichHandler
from dotenv import load_dotenv
import os
import argparse
from typing import Dict, Any

# Local imports from ETL modules
from src.etl.transcript import TranscriptProcessor
from src.etl.products import ProductProcessor
from src.etl.pathways import PathwayProcessor
from src.etl.drugs import DrugProcessor
from src.db.database import get_db_manager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)]
)
logger = logging.getLogger("master_etl")
console = Console()

def load_config() -> Dict[str, Any]:
    """Load configuration from environment variables."""
    load_dotenv()
    return {
        'cache_dir':  Path(os.getenv('MB_CACHE_DIR', '/tmp/mediabase/cache')),
        'batch_size': int(os.getenv('MB_BATCH_SIZE', '1000')),
        'host':       os.getenv('MB_POSTGRES_HOST', 'localhost'),
        'port':       int(os.getenv('MB_POSTGRES_PORT', '5432')),
        'dbname':     os.getenv('MB_POSTGRES_NAME', 'mediabase'),
        'user':       os.getenv('MB_POSTGRES_USER', 'postgres'),
        'password':   os.getenv('MB_POSTGRES_PASSWORD', 'postgres'),
        'gtf_url':    os.getenv('MB_GENCODE_GTF_URL')
    }

def run_etl(args: argparse.Namespace) -> None:
    """Run ETL pipeline with specified modules."""
    # Create unified configuration
    config = {
        # Database configuration
        'host': os.getenv('MB_POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('MB_POSTGRES_PORT', '5432')),
        'dbname': os.getenv('MB_POSTGRES_NAME', 'mediabase'),
        'user': os.getenv('MB_POSTGRES_USER', 'postgres'),
        'password': os.getenv('MB_POSTGRES_PASSWORD', 'postgres'),
        
        # ETL configuration
        'batch_size': args.batch_size,
        'cache_dir': os.getenv('MB_CACHE_DIR', '/tmp/mediabase/cache'),
        'force_download': args.force_download,
        
        # Data source URLs
        'gtf_url': os.getenv('MB_GENCODE_GTF_URL', 'ftp://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_44/gencode.v44.annotation.gtf.gz'),
        'go_obo_url': 'http://purl.obolibrary.org/obo/go.obo',
        'go_basic_url': 'http://purl.obolibrary.org/obo/go/go-basic.obo',
        'reactome_url': os.getenv('MB_REACTOME_DOWNLOAD_URL', 'https://reactome.org/download/current/NCBI2Reactome_All_Levels.txt'),
        'drugcentral_url': os.getenv('MB_DRUGCENTRAL_DATA_URL', 'https://unmtid-shinyapps.net/download/DrugCentral/20231006/drugcentral-pgdump_20231006.sql.gz')
    }

    # Validate required URLs
    required_urls = {
        'transcript': ['gtf_url'],
        'go_terms': ['go_obo_url', 'go_basic_url'],
        'pathways': ['reactome_url'],
        'drugs': ['drugcentral_url']
    }

    if args.module != 'all':
        # Check only URLs needed for specified module
        for url in required_urls.get(args.module, []):
            if not config.get(url):
                raise ValueError(f"Missing required URL configuration: {url}")
    else:
        # Check all URLs when running all modules
        for urls in required_urls.values():
            for url in urls:
                if not config.get(url):
                    raise ValueError(f"Missing required URL configuration: {url}")
    
    db_manager = get_db_manager(config)
    
    try:
        if not db_manager.cursor:
            raise RuntimeError("Could not establish database connection")
        
        # Verify schema version
        version_query = db_manager.cursor.execute("SELECT version FROM schema_version")
        version = version_query.fetchone() if version_query else None
        current_version = version[0] if version else None
        
        if current_version != 'v0.1.4':
            console.print("[yellow]Migrating database schema to v0.1.4...[/yellow]")
            if not db_manager.migrate_to_version('v0.1.4'):
                raise RuntimeError("Schema migration failed")
            
        # Run modules in correct order to handle dependencies
        module_sequence = {
            'transcript': 1,  # Base data must come first
            'products': 2,    # Products need transcript data
            'go_terms': 3,    # GO terms can enhance product classification
            'pathways': 4,    # Pathways may reference products and GO terms
            'drugs': 5        # Drugs need all previous data
        }
        
        # Sort modules if running multiple
        if args.module == 'all':
            modules = list(module_sequence.keys())
        else:
            modules = [args.module]
            
        modules.sort(key=lambda m: module_sequence.get(m, 999))
        
        for module in modules:
            if module == 'transcript':
                console.print("[bold green]Starting transcript ETL...[/bold green]")
                transcript_processor = TranscriptProcessor(config)
                transcript_processor.run()
                console.print("[green]Transcript ETL completed[/green]")
            
            elif module == 'products':
                console.print("[bold green]Running product classification...[/bold green]")
                product_processor = ProductProcessor(config)
                product_processor.run()
                console.print("[green]Product classification completed[/green]")
            
            elif module == 'go_terms':
                console.print("[bold green]Running GO term enrichment...[/bold green]")
                from src.etl.go_terms import GOTermProcessor
                go_processor = GOTermProcessor(config)
                go_processor.run()
                console.print("[green]GO term enrichment completed[/green]")
            
            elif module == 'pathways':
                console.print("[bold green]Running pathway enrichment...[/bold green]")
                pathway_processor = PathwayProcessor(config)
                pathway_processor.run()  # Changed from enrich_transcripts() to run()
                console.print("[green]Pathway enrichment completed[/green]")
            
            elif module == 'drugs':
                console.print("[bold green]Running drug integration...[/bold green]")
                drug_processor = DrugProcessor(config)
                drug_processor.run()
                console.print("[green]Drug integration completed[/green]")
        
        # Verify data integrity with proper null checks
        if db_manager.cursor:
            db_manager.cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN source_references IS NOT NULL 
                          AND source_references != '{}'::jsonb THEN 1 END) as with_refs,
                    COUNT(CASE WHEN (alt_transcript_ids IS NOT NULL 
                          AND alt_transcript_ids != '{}'::jsonb)
                          OR (alt_gene_ids IS NOT NULL 
                          AND alt_gene_ids != '{}'::jsonb) THEN 1 END) as with_alt_ids
                FROM cancer_transcript_base
            """)
            result = db_manager.cursor.fetchone()
            if result:
                console.print(
                    f"\n[bold green]Pipeline completed successfully![/bold green]\n"
                    f"Total records: {result[0]:,}\n"
                    f"Records with references: {result[1]:,}\n"
                    f"Records with alternative IDs: {result[2]:,}"
                )
        
    except Exception as e:
        console.print(f"[bold red]ETL pipeline failed: {str(e)}[/bold red]")
        logger.exception("Detailed error trace:")
        sys.exit(1)
    finally:
        if db_manager.conn is not None:
            db_manager.conn.close()

def main() -> None:
    """Main entry point for ETL pipeline."""
    parser = argparse.ArgumentParser(description='Run ETL pipeline')
    parser.add_argument(
        '--module', 
        choices=['all', 'transcript', 'products', 'go_terms', 'pathways', 'drugs'],
        default='all',
        help='ETL module to run'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=1000,
        help='Batch size for processing (default: 1000)'
    )
    parser.add_argument(
        '--force-download',
        action='store_true',
        help='Force download of source data files'
    )
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Set logging level'
    )
    
    args = parser.parse_args()
    
    # Configure logging based on argument
    logging.getLogger().setLevel(args.log_level)
    
    run_etl(args)

if __name__ == '__main__':
    main()

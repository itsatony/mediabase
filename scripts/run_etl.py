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
from src.db.database import get_db_manager  # This should now be properly recognized

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    datefmt="%H:%M:%S",  # 24h format with hours, minutes, seconds
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
        'gtf_url':    os.getenv('MB_GENCODE_GTF_URL'),
        'go_obo_url': os.getenv('MB_GO_OBO_URL'),
        'go_basic_url': os.getenv('MB_GO_BASIC_URL'),
        'reactome_url': os.getenv('MB_REACTOME_DOWNLOAD_URL'),
        'drugcentral_url': os.getenv('MB_DRUGCENTRAL_DATA_URL')
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
        'batch_size': args.batch_size,  # Will use new default of 100 from argparse
        'cache_dir': os.getenv('MB_CACHE_DIR', '/tmp/mediabase/cache'),
        'force_download': args.force_download,
        
        # New: Transcript limit configuration
        'limit_transcripts': args.limit_transcripts,
        
        # Data source URLs
        'gtf_url': os.getenv('MB_GENCODE_GTF_URL', 'ftp://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_44/gencode.v44.annotation.gtf.gz'),
        'uniprot_idmapping_selected_url': os.getenv('MB_UNIPROT_IDMAPPING_SELECTED_URL', 'https://ftp.uniprot.org/pub/databases/uniprot/current_release/knowledgebase/idmapping/idmapping_selected.tab.gz'),
        'ncbi_gene_info_url': os.getenv('MB_NCBI_GENE_INFO_URL', 'https://ftp.ncbi.nlm.nih.gov/gene/DATA/gene_info.gz'),
        'vgnc_gene_set_url': os.getenv('MB_VGNC_GENE_SET_URL', 'ftp://ftp.ebi.ac.uk/pub/databases/genenames/vgnc/json/all/all_vgnc_gene_set_All.json'),
        'ensembl_refseq_url': os.getenv('MB_ENSEMBL_REFSEQ_URL', 'https://ftp.ensembl.org/pub/current_tsv/homo_sapiens/Homo_sapiens.GRCh38.113.refseq.tsv.gz'),
        'ensembl_entrez_url': os.getenv('MB_ENSEMBL_ENTREZ_URL', 'https://ftp.ensembl.org/pub/current_tsv/homo_sapiens/Homo_sapiens.GRCh38.113.entrez.tsv.gz'),
        'go_obo_url': os.getenv('MB_GO_OBO_URL', 'http://purl.obolibrary.org/obo/go.obo'),
        'go_basic_url': os.getenv('MB_GO_BASIC_URL', 'http://purl.obolibrary.org/obo/go/go-basic.obo'),
        'drugcentral_url': os.getenv('MB_DRUGCENTRAL_DATA_URL', 'https://unmtid-shinyapps.net/download/DrugCentral/20231006/drugcentral-pgdump_20231006.sql.gz'),
        'reactome_url': os.getenv('MB_REACTOME_DOWNLOAD_URL', 'https://reactome.org/download/current/NCBI2Reactome_All_Levels.txt'),
        
        # Add PubMed specific configurations
        'pubmed_api_key': os.getenv('MB_PUBMED_API_KEY', ''),
        'pubmed_email': os.getenv('MB_PUBMED_EMAIL', ''),
        'force_refresh': args.force_refresh,
        'rate_limit': args.rate_limit,
    }

    # Validate required URLs
    required_urls = {
        'transcript': ['gtf_url'],
        'id_enrichment': ['ncbi_gene_info_url', 'vgnc_gene_set_url', 'uniprot_idmapping_selected_url', 'ensembl_refseq_url', 'ensembl_entrez_url'],
        'go_terms': ['go_obo_url', 'go_basic_url'],
        'pathways': ['reactome_url'],
        'drugs': ['drugcentral_url'],
        'publications': []  # PubMed API doesn't need URLs, just API credentials
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
    
    # Add robust database connection validation
    if not db_manager.ensure_connection():
        error_msg = "Could not establish database connection"
        console.print(f"[bold red]{error_msg}[/bold red]")
        raise RuntimeError(error_msg)
    
    try:
        # Handle reset_db if requested
        if args.reset_db:
            console.print("[yellow]Resetting database tables...[/yellow]")
            if not db_manager.reset():
                raise RuntimeError("Database reset failed")
            console.print("[green]Database tables reset successful[/green]")
        
        # Transcript limit warning if not resetting
        if args.limit_transcripts and not args.reset_db:
            console.print(
                "[bold yellow]WARNING: Using --limit-transcripts without --reset-db may result "
                "in inconsistent data. Consider using them together.[/bold yellow]"
            )
            if not args.force:
                if not console.input(
                    "\nContinue anyway? (y/n): "
                ).lower().startswith('y'):
                    console.print("[yellow]Aborting.[/yellow]")
                    return
        
        # Verify schema version - Fix the way we check schema version
        # Ensure connection is valid before executing
        if not db_manager.ensure_connection():
            raise RuntimeError("Database connection lost when checking schema version")
        
        if not db_manager.cursor:
            raise RuntimeError("Database cursor is not available")

        db_manager.cursor.execute("SELECT version FROM schema_version")
        version_row = db_manager.cursor.fetchone()
        current_version = version_row[0] if version_row else None
        
        if current_version != 'v0.1.4':
            console.print("[yellow]Migrating database schema to v0.1.4...[/yellow]")
            if not db_manager.migrate_to_version('v0.1.4'):
                raise RuntimeError("Schema migration failed")
            
        # Run modules in correct order to handle dependencies
        module_sequence = {
            'transcript': 1,    # Base data must come first
            'id_enrichment': 2, # ID enrichment should happen right after transcript loading
            'products': 3,      # Products need transcript data and IDs
            'go_terms': 4,      # GO terms can enhance product classification
            'pathways': 5,      # Pathways may reference products and GO terms
            'drugs': 6,         # Drugs need all previous data
            'publications': 7   # Publications should be processed last
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
            
            elif module == 'id_enrichment':
                console.print("[bold green]Starting ID enrichment...[/bold green]")
                from src.etl.id_enrichment import IDEnrichmentProcessor
                id_processor = IDEnrichmentProcessor(config)
                id_processor.run()
                console.print("[green]ID enrichment completed[/green]")
            
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
            
            elif module == 'publications':
                console.print("[bold green]Running publications enrichment...[/bold green]")
                from src.etl.publications import PublicationsProcessor
                publications_processor = PublicationsProcessor(config)
                publications_processor.run()
                console.print("[green]Publications enrichment completed[/green]")
        
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
                
                # Print note about transcript limit if it was used
                if args.limit_transcripts and result[0] < args.limit_transcripts:
                    console.print(
                        f"[yellow]Note: Requested limit was {args.limit_transcripts:,} transcripts "
                        f"but only {result[0]:,} were processed. "
                        f"This may be due to filtering or limited data in the source file.[/yellow]"
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
        choices=['all', 'transcript', 'id_enrichment', 'products', 'go_terms', 'pathways', 'drugs', 'publications'],
        default='all',
        help='ETL module to run'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,  # Changed from 1000 to 100
        help='Batch size for processing (default: 100)'
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
    # New arguments for transcript limiting and database reset
    parser.add_argument(
        '--limit-transcripts',
        type=int,
        help='Limit the number of transcripts to process (useful for testing)'
    )
    parser.add_argument(
        '--reset-db',
        action='store_true',
        help='Reset the database before running the ETL pipeline'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force operation without confirmation prompts'
    )
    
    # Add publication-specific arguments
    parser.add_argument(
        '--force-refresh',
        action='store_true',
        help='Force refresh of cached data (including publications)'
    )
    parser.add_argument(
        '--rate-limit',
        type=float,
        default=0.34,
        help='Rate limit for API calls in seconds (default: 0.34, ~3 requests/sec)'
    )
    
    args = parser.parse_args()
    
    # Configure logging based on argument
    logging.getLogger().setLevel(args.log_level)
    
    run_etl(args)

if __name__ == '__main__':
    main()

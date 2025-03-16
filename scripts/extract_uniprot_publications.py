#!/usr/bin/env python3
"""
Script to extract publication references from UniProt feature annotations.

This script analyzes UniProt feature annotations and extracts PubMed IDs (PMIDs)
to create publication references in the source_references field.
"""

import sys
import logging
import argparse
from pathlib import Path
import os
from typing import Dict, Any, List
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress
from rich.logging import RichHandler
import json
import gzip
from psycopg2.extras import execute_batch

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.db.database import get_db_manager
from src.utils.publication_utils import extract_pmid_from_text, extract_pmids_from_text
from src.etl.publications import PublicationsProcessor
from src.etl.products import ProductClassifier

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)]
)
logger = logging.getLogger("uniprot_publications")
console = Console()

def load_config() -> Dict[str, Any]:
    """Load configuration from environment variables."""
    # Load .env file
    load_dotenv(project_root / '.env')
    
    return {
        'host': os.getenv('MB_POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('MB_POSTGRES_PORT', '5432')),
        'dbname': os.getenv('MB_POSTGRES_NAME', 'mediabase'),
        'user': os.getenv('MB_POSTGRES_USER', 'postgres'),
        'password': os.getenv('MB_POSTGRES_PASSWORD', 'postgres'),
        'batch_size': int(os.getenv('MB_BATCH_SIZE', '100')),
        'pubmed_api_key': os.getenv('MB_PUBMED_API_KEY', ''),
        'pubmed_email': os.getenv('MB_PUBMED_EMAIL', ''),
        'cache_dir': os.getenv('MB_CACHE_DIR', '/tmp/mediabase/cache')
    }

def process_uniprot_features() -> None:
    """Process UniProt features and extract publication references."""
    config = load_config()
    db_manager = get_db_manager(config)
    batch_size = config.get('batch_size', 100)
    
    try:
        if not db_manager.conn or not db_manager.cursor:
            raise RuntimeError("Could not establish database connection")
            
        # Check schema version
        if db_manager.get_current_version() != 'v0.1.4':
            raise RuntimeError("Database schema must be v0.1.4")
            
        # Initialize product classifier to access UniProt data
        console.print("[blue]Initializing product classifier...[/blue]")
        classifier = ProductClassifier(config)
        
        # Get gene symbols from database
        console.print("[blue]Fetching protein-coding genes...[/blue]")
        db_manager.cursor.execute("""
            SELECT DISTINCT gene_symbol 
            FROM cancer_transcript_base 
            WHERE gene_type = 'protein_coding'
        """)
        
        gene_symbols = [row[0] for row in db_manager.cursor.fetchall()]
        console.print(f"[green]Found {len(gene_symbols)} protein-coding genes[/green]")
        
        # Process genes in batches
        updates = []
        total_refs = 0
        genes_with_refs = 0
        
        with Progress() as progress:
            task = progress.add_task("[cyan]Processing genes...", total=len(gene_symbols))
            
            for gene_symbol in gene_symbols:
                # Extract publication references
                publications = classifier.extract_publication_references(gene_symbol)
                
                # Add to database updates if we have refs
                if publications:
                    genes_with_refs += 1
                    total_refs += len(publications)
                    
                    # Convert to JSON
                    pub_json = json.dumps([dict(p) for p in publications])
                    
                    updates.append((pub_json, gene_symbol))
                    
                    # Process in batches
                    if len(updates) >= batch_size:
                        execute_batch(
                            db_manager.cursor,
                            """
                            UPDATE cancer_transcript_base
                            SET source_references = jsonb_set(
                                COALESCE(source_references, '{}'::jsonb),
                                '{uniprot}',
                                %s::jsonb
                            )
                            WHERE gene_symbol = %s
                            """,
                            updates,
                            page_size=batch_size
                        )
                        
                        if db_manager.conn:
                            db_manager.conn.commit()
                            
                        updates = []
                
                progress.update(task, advance=1)
                
            # Process any remaining updates
            if updates:
                execute_batch(
                    db_manager.cursor,
                    """
                    UPDATE cancer_transcript_base
                    SET source_references = jsonb_set(
                        COALESCE(source_references, '{}'::jsonb),
                        '{uniprot}',
                        %s::jsonb
                    )
                    WHERE gene_symbol = %s
                    """,
                    updates,
                    page_size=batch_size
                )
                
                if db_manager.conn:
                    db_manager.conn.commit()
        
        # Enrich extracted references
        console.print("[blue]Enriching publication references with metadata...[/blue]")
        pub_processor = PublicationsProcessor(config)
        pub_processor.run()
        
        console.print(f"[green]Extraction complete:[/green]")
        console.print(f"  - Processed {len(gene_symbols)} genes")
        console.print(f"  - Found {total_refs} publication references")
        console.print(f"  - Added references to {genes_with_refs} genes")
        
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        logger.exception("Processing failed")
        if db_manager.conn:
            db_manager.conn.rollback()
    finally:
        if db_manager.conn:
            db_manager.conn.close()

def main() -> None:
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Extract publication references from UniProt feature annotations"
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Batch size for database operations'
    )
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Set logging level'
    )
    
    args = parser.parse_args()
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    process_uniprot_features()

if __name__ == "__main__":
    main()

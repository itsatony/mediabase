#!/usr/bin/env python3
"""
Script to extract publication references from drug data in the database.

This script analyzes drug evidence and reference data in the database and extracts
PubMed IDs (PMIDs) to create publication references in the source_references field.
"""

import sys
import logging
import argparse
from pathlib import Path
import os
from typing import Dict, Any, List, Set, Tuple
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress
from rich.logging import RichHandler
import json
from psycopg2.extras import execute_batch

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.db.database import get_db_manager
from src.utils.publication_utils import extract_pmid_from_text, extract_pmids_from_text
from src.etl.publications import PublicationsProcessor, Publication

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)]
)
logger = logging.getLogger("drug_publications")
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
        'pubmed_email': os.getenv('MB_PUBMED_EMAIL', '')
    }

def extract_drug_reference(drug_data: Dict[str, Any]) -> List[Publication]:
    """Extract publication references from drug data.
    
    Args:
        drug_data: Drug data dictionary
        
    Returns:
        List[Publication]: List of extracted publication references
    """
    publications: List[Publication] = []
    
    # Check for various reference fields
    ref_fields = ['references', 'evidence', 'evidence_references', 'publications']
    for field in ref_fields:
        if field in drug_data and drug_data[field]:
            # Extract PMIDs from the field
            pmids = extract_pmids_from_text(str(drug_data[field]))
            for pmid in pmids:
                publication = PublicationsProcessor.create_publication_reference(
                    pmid=pmid,
                    evidence_type="DrugCentral",
                    source_db="DrugCentral"
                )
                publications.append(publication)
    
    return publications

def process_drug_references() -> None:
    """Process drug references in the database and extract publication IDs."""
    config = load_config()
    db_manager = get_db_manager(config)
    batch_size = config.get('batch_size', 100)
    
    try:
        if not db_manager.conn or not db_manager.cursor:
            raise RuntimeError("Could not establish database connection")
            
        # Check schema version
        if db_manager.get_current_version() != 'v0.1.4':
            raise RuntimeError("Database schema must be v0.1.4")
            
        # Get genes with drug data
        console.print("[blue]Fetching genes with drug information...[/blue]")
        db_manager.cursor.execute("""
            SELECT gene_symbol, drugs 
            FROM cancer_transcript_base 
            WHERE drugs IS NOT NULL 
            AND drugs != '{}'::jsonb
        """)
        
        rows = db_manager.cursor.fetchall()
        console.print(f"[green]Found {len(rows)} genes with drug information[/green]")
        
        # Process each gene's drug data
        updates = []
        total_refs = 0
        genes_with_refs = 0
        
        with Progress() as progress:
            task = progress.add_task("[cyan]Processing drug references...", total=len(rows))
            
            for gene_symbol, drugs in rows:
                references: List[Publication] = []
                
                # Process each drug
                for drug_id, drug_data in drugs.items():
                    drug_refs = extract_drug_reference(drug_data)
                    if drug_refs:
                        references.extend(drug_refs)
                
                # Add to database if references found
                if references:
                    genes_with_refs += 1
                    total_refs += len(references)
                    updates.append((
                        json.dumps([dict(ref) for ref in references]),
                        gene_symbol
                    ))
                    
                # Process in batches
                if len(updates) >= batch_size:
                    execute_batch(
                        db_manager.cursor,
                        """
                        UPDATE cancer_transcript_base
                        SET source_references = jsonb_set(
                            COALESCE(source_references, '{}'::jsonb),
                            '{drugs}',
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
                
            # Process remaining updates
            if updates:
                execute_batch(
                    db_manager.cursor,
                    """
                    UPDATE cancer_transcript_base
                    SET source_references = jsonb_set(
                        COALESCE(source_references, '{}'::jsonb),
                        '{drugs}',
                        %s::jsonb
                    )
                    WHERE gene_symbol = %s
                    """,
                    updates,
                    page_size=batch_size
                )
                if db_manager.conn:
                    db_manager.conn.commit()
        
        # Enrich the references
        console.print("[blue]Enriching publication references with metadata...[/blue]")
        pub_processor = PublicationsProcessor(config)
        pub_processor.run()
        
        # Verify results
        db_manager.cursor.execute("""
            SELECT COUNT(*) as genes_with_refs
            FROM cancer_transcript_base
            WHERE source_references->'drugs' IS NOT NULL
            AND source_references->'drugs' != '[]'::jsonb
        """)
        result = db_manager.cursor.fetchone()
        final_count = result[0] if result else 0
        
        console.print(f"[green]Extraction complete:[/green]")
        console.print(f"  - Processed {len(rows)} genes with drug information")
        console.print(f"  - Found {total_refs} publication references")
        console.print(f"  - Added references to {genes_with_refs} genes")
        console.print(f"  - Final count of genes with drug references: {final_count}")
        
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
        description="Extract publication references from drug data"
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
    
    config = load_config()
    config['batch_size'] = args.batch_size
    
    process_drug_references()

if __name__ == "__main__":
    main()

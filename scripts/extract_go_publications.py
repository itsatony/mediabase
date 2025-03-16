#!/usr/bin/env python3
"""
Script to extract publication references from GO evidence codes in the database.

This script analyzes GO term evidence codes in the database and extracts
PubMed IDs (PMIDs) to create publication references in the source_references field.
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
import re
import json
import psycopg2
from psycopg2.extras import execute_batch

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.db.database import get_db_manager
from src.utils.publication_utils import extract_pmid_from_text, extract_pmids_from_text
from src.etl.publications import PublicationsProcessor

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)]
)
logger = logging.getLogger("go_publications")
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

def extract_pmids_from_go_evidence(evidence_code: str) -> List[str]:
    """Extract PMIDs from GO evidence code.
    
    Args:
        evidence_code: GO evidence code string
        
    Returns:
        List[str]: List of extracted PMIDs
    """
    pmids = []
    
    # Common patterns in GO evidence codes
    if not evidence_code:
        return pmids
        
    # Pattern 1: Direct PMID reference
    pmid_match = re.search(r'PMID:(\d+)', evidence_code, re.IGNORECASE)
    if pmid_match:
        pmids.append(pmid_match.group(1))
        
    # Pattern 2: PubMed reference
    pubmed_match = re.search(r'PubMed:(\d+)', evidence_code, re.IGNORECASE) 
    if pubmed_match:
        pmids.append(pubmed_match.group(1))
        
    # Pattern 3: Reference in format GOC:ref|PMID:12345678
    if '|' in evidence_code:
        parts = evidence_code.split('|')
        for part in parts:
            part_pmid = extract_pmid_from_text(part)
            if part_pmid:
                pmids.append(part_pmid)
                
    return pmids

def process_go_terms() -> None:
    """Process GO terms in the database and extract publication references."""
    config = load_config()
    db_manager = get_db_manager(config)
    batch_size = config.get('batch_size', 100)
    
    try:
        if not db_manager.conn or not db_manager.cursor:
            raise RuntimeError("Could not establish database connection")
            
        # Check schema version
        if db_manager.get_current_version() != 'v0.1.4':
            raise RuntimeError("Database schema must be v0.1.4")
        
        # Get GO terms with evidence codes
        console.print("[blue]Fetching GO terms with evidence codes...[/blue]")
        db_manager.cursor.execute("""
            SELECT gene_symbol, go_terms 
            FROM cancer_transcript_base 
            WHERE go_terms IS NOT NULL 
            AND go_terms != '{}'::jsonb
        """)
        
        rows = db_manager.cursor.fetchall()
        console.print(f"[green]Found {len(rows)} genes with GO terms[/green]")
        
        # Process each gene's GO terms
        updates = []
        pmid_count = 0
        gene_with_refs = 0
        
        with Progress() as progress:
            task = progress.add_task("[cyan]Processing genes...", total=len(rows))
            
            for gene_symbol, go_terms in rows:
                if not isinstance(go_terms, dict):
                    try:
                        go_terms = json.loads(go_terms)
                    except json.JSONDecodeError:
                        progress.update(task, advance=1)
                        continue
                
                references = []
                for go_id, term_data in go_terms.items():
                    if not isinstance(term_data, dict):
                        continue
                        
                    evidence = term_data.get('evidence', '')
                    if not evidence:
                        continue
                        
                    # Try to extract PMIDs from evidence
                    pmids = extract_pmids_from_go_evidence(evidence)
                    
                    # Create references for each PMID
                    for pmid in pmids:
                        reference = {
                            "pmid": pmid,
                            "evidence_type": evidence,
                            "source_db": "GO"
                        }
                        references.append(reference)
                        pmid_count += 1
                
                # If we found references
                if references:
                    gene_with_refs += 1
                    updates.append((
                        json.dumps(references),
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
                            '{go_terms}',
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
                        '{go_terms}',
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
        console.print("[blue]Enriching publication references...[/blue]")
        pub_processor = PublicationsProcessor(config)
        pub_processor.run()
        
        console.print(f"[green]Extraction complete:[/green]")
        console.print(f"  - Found {pmid_count} PMIDs in GO evidence codes")
        console.print(f"  - Added references to {gene_with_refs} genes")
        
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
        description="Extract publication references from GO evidence codes"
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
    
    process_go_terms()

if __name__ == "__main__":
    main()

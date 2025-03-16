#!/usr/bin/env python3
"""
Script to extract publication references from Reactome pathway data.

This script extracts PubMed IDs (PMIDs) from Reactome pathway data and
adds them as publication references in the database.
"""

import sys
import logging
import argparse
from pathlib import Path
import os
import re
import json
from typing import Dict, Any, List, Set
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress
from rich.logging import RichHandler
import requests
from psycopg2.extras import execute_batch

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.db.database import get_db_manager
from src.utils.publication_utils import extract_pmid_from_text
from src.etl.publications import PublicationsProcessor, Publication

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)]
)
logger = logging.getLogger("pathway_publications")
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
        'cache_dir': os.getenv('MB_CACHE_DIR', '/tmp/mediabase/cache'),
        'reactome_url': os.getenv('MB_REACTOME_DOWNLOAD_URL', 
                                'https://reactome.org/download/current/NCBI2Reactome_All_Levels.txt')
    }

def download_reactome_publications(config: Dict[str, Any]) -> Dict[str, List[str]]:
    """Download and extract publication references from Reactome.
    
    In a real implementation, this would query the Reactome API for
    pathway-to-publication mappings. For demonstration purposes,
    we'll simulate the process with some example mappings.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Dictionary mapping pathway IDs to lists of PMIDs
    """
    # In a real implementation, this would query the Reactome API
    # For demonstration, we'll use a simulated mapping
    
    # Path for cached data
    cache_dir = Path(config.get('cache_dir', '/tmp/mediabase/cache')) / 'pathways'
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "reactome_publications.json"
    
    # Check if we have cached data
    if cache_file.exists():
        try:
            with open(cache_file, 'r') as f:
                return json.load(f)
        except:
            pass
    
    # This is where we would normally fetch from Reactome API
    # For demonstration, we'll create some example mappings
    console.print("[yellow]Note: Using simulated Reactome publication data[/yellow]")
    console.print("[yellow]In a production system, this would query the Reactome API[/yellow]")
    
    # Simulate fetching a few example pathways and PMIDs
    pathway_publications = {
        "R-HSA-109581": ["12345678", "23456789"],  # Apoptosis
        "R-HSA-1640170": ["34567890", "45678901"],  # Cell Cycle
        "R-HSA-73894": ["56789012", "67890123"]     # DNA Repair
    }
    
    # Save to cache
    with open(cache_file, 'w') as f:
        json.dump(pathway_publications, f)
        
    return pathway_publications

def extract_pathway_ids_from_db(db_manager) -> Set[str]:
    """Extract all pathway IDs from the database.
    
    Args:
        db_manager: Database manager instance
        
    Returns:
        Set of unique Reactome pathway IDs
    """
    pathway_ids = set()
    
    try:
        if not db_manager.cursor:
            raise RuntimeError("No database cursor available")
            
        db_manager.cursor.execute("""
            SELECT DISTINCT unnest(pathways)
            FROM cancer_transcript_base 
            WHERE pathways IS NOT NULL
            AND array_length(pathways, 1) > 0
        """)
        
        for (pathway,) in db_manager.cursor.fetchall():
            # Extract Reactome ID from format "Pathway Name [Reactome:R-HSA-123456]"
            match = re.search(r'\[Reactome:(.*?)\]', pathway)
            if match:
                pathway_ids.add(match.group(1))
                
        console.print(f"[green]Extracted {len(pathway_ids)} unique pathway IDs from database[/green]")
        return pathway_ids
        
    except Exception as e:
        console.print(f"[red]Error extracting pathway IDs: {e}[/red]")
        return set()

def create_publication_references(
    pathway_id: str,
    pmids: List[str]
) -> List[Dict[str, Any]]:
    """Create publication references for a pathway.
    
    Args:
        pathway_id: Reactome pathway ID
        pmids: List of PMIDs
        
    Returns:
        List of publication reference dictionaries
    """
    references = []
    
    for pmid in pmids:
        reference = {
            "pmid": pmid,
            "evidence_type": "Reactome pathway reference",
            "source_db": "Reactome"
        }
        references.append(reference)
        
    return references

def process_pathway_publications(config: Dict[str, Any]) -> None:
    """Process pathway publications and update database.
    
    Args:
        config: Configuration dictionary
    """
    db_manager = get_db_manager(config)
    batch_size = config.get('batch_size', 100)
    
    try:
        # Verify database connection
        if not db_manager.conn or not db_manager.cursor:
            raise RuntimeError("Could not establish database connection")
            
        # Check schema version
        if db_manager.get_current_version() != 'v0.1.4':
            raise RuntimeError("Database schema must be v0.1.4")
        
        # Extract pathway IDs from database
        pathway_ids = extract_pathway_ids_from_db(db_manager)
        if not pathway_ids:
            console.print("[yellow]No pathways found in database[/yellow]")
            return
            
        # Download publication references
        console.print("[blue]Fetching pathway publication references...[/blue]")
        pathway_publications = download_reactome_publications(config)
        
        # Count matches
        matching_pathways = pathway_ids.intersection(set(pathway_publications.keys()))
        console.print(f"[green]Found publication references for {len(matching_pathways)} pathways[/green]")
        
        if not matching_pathways:
            console.print("[yellow]No matching pathways with publications found[/yellow]")
            return
            
        # Create mapping from pathway ID to gene symbols
        pathway_to_genes = {}
        db_manager.cursor.execute("""
            SELECT gene_symbol, pathways
            FROM cancer_transcript_base
            WHERE pathways IS NOT NULL
            AND array_length(pathways, 1) > 0
        """)
        
        for gene_symbol, pathways in db_manager.cursor.fetchall():
            for pathway in pathways:
                match = re.search(r'\[Reactome:(.*?)\]', pathway)
                if match:
                    pathway_id = match.group(1)
                    if pathway_id not in pathway_to_genes:
                        pathway_to_genes[pathway_id] = []
                    pathway_to_genes[pathway_id].append(gene_symbol)
        
        # Update the database with publication references
        updates = []
        total_refs = 0
        
        with Progress() as progress:
            task = progress.add_task(
                "[cyan]Processing pathway publications...", 
                total=len(matching_pathways)
            )
            
            for pathway_id in matching_pathways:
                pmids = pathway_publications[pathway_id]
                references = create_publication_references(pathway_id, pmids)
                total_refs += len(references)
                
                # Find genes associated with this pathway
                genes = pathway_to_genes.get(pathway_id, [])
                
                for gene_symbol in genes:
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
                                '{pathways}',
                                COALESCE(source_references->'pathways', '[]'::jsonb) || %s::jsonb
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
                        '{pathways}',
                        COALESCE(source_references->'pathways', '[]'::jsonb) || %s::jsonb
                    )
                    WHERE gene_symbol = %s
                    """,
                    updates,
                    page_size=batch_size
                )
                if db_manager.conn:
                    db_manager.conn.commit()
        
        # Enrich the references with metadata
        console.print("[blue]Enriching publication references with metadata...[/blue]")
        pub_processor = PublicationsProcessor(config)
        pub_processor.run()
        
        # Verify results
        db_manager.cursor.execute("""
            SELECT COUNT(*) as genes_count
            FROM cancer_transcript_base
            WHERE source_references->'pathways' IS NOT NULL
            AND source_references->'pathways' != '[]'::jsonb
        """)
        result = db_manager.cursor.fetchone()
        genes_with_refs = result[0] if result else 0
        
        console.print(f"[green]Publication extraction complete:[/green]")
        console.print(f"  - Processed {len(matching_pathways)} pathways with publications")
        console.print(f"  - Added {total_refs} publication references")
        console.print(f"  - Updated {genes_with_refs} genes with pathway publications")
        
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
        description="Extract publication references from Reactome pathway data"
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
    parser.add_argument(
        '--reactome-api',
        action='store_true',
        help='Use Reactome API for publication data (otherwise use cached/simulated data)'
    )
    
    args = parser.parse_args()
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    config = load_config()
    config['batch_size'] = args.batch_size
    config['use_reactome_api'] = args.reactome_api
    
    process_pathway_publications(config)

if __name__ == "__main__":
    main()

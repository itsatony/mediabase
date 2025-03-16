#!/usr/bin/env python3
"""Script to run pathway enrichment pipeline."""

import sys
import logging
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.logging import RichHandler
from dotenv import load_dotenv
import os
import argparse
from typing import Dict, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.etl.pathways import PathwayProcessor
from src.etl.publications import PublicationsProcessor

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)]
)
logger = logging.getLogger("pathway_enrichment")
console = Console()

def load_config() -> Dict[str, Any]:
    """Load configuration from environment variables."""
    load_dotenv()
    return {
        'reactome_url': os.getenv('MB_REACTOME_DOWNLOAD_URL'),
        'cache_dir': os.getenv('MB_CACHE_DIR'),
        'cache_ttl': int(os.getenv('MB_CACHE_TTL', '86400')),
        'batch_size': int(os.getenv('MB_BATCH_SIZE', '1000')),
        # Database connection params
        'host': os.getenv('MB_POSTGRES_HOST'),
        'port': int(os.getenv('MB_POSTGRES_PORT', '5432')),
        'dbname': os.getenv('MB_POSTGRES_NAME'),
        'user': os.getenv('MB_POSTGRES_USER'),
        'password': os.getenv('MB_POSTGRES_PASSWORD'),
        # Publication enrichment params
        'pubmed_api_key': os.getenv('MB_PUBMED_API_KEY', ''),
        'pubmed_email': os.getenv('MB_PUBMED_EMAIL', '')
    }

def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(description="Run pathway enrichment pipeline")
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
        help='Force new download of Reactome data'
    )
    parser.add_argument(
        '--skip-publication-enrichment',
        action='store_true',
        help='Skip publication reference enrichment'
    )
    
    args = parser.parse_args()
    
    # Configure logging based on argument
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    try:
        # Load configuration
        config = load_config()
        
        # Override config with command line arguments
        config['batch_size'] = args.batch_size
        config['force_download'] = args.force_download
        
        # Verify required environment variables
        if not config.get('reactome_url'):
            raise ValueError("Missing MB_REACTOME_DOWNLOAD_URL environment variable")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Initializing pathway processor...", total=None)
            processor = PathwayProcessor(config)
            
            # Verify schema version
            if not processor.db_manager.cursor:
                raise RuntimeError("No database connection")
            
            processor.db_manager.cursor.execute("SELECT version FROM schema_version")
            version_row = processor.db_manager.cursor.fetchone()
            if not version_row or version_row[0] != 'v0.1.4':
                raise RuntimeError("Database schema must be v0.1.4")
            
            progress.update(task, description="Processing pathways...")
            processor.run()
            
            # Run publication enrichment if not skipped
            if not args.skip_publication_enrichment:
                progress.update(task, description="Enriching pathway publications...")
                pub_processor = PublicationsProcessor(config)
                pub_processor.run()
            
            # Verify results with proper null checks
            if processor.db_manager.cursor:
                processor.db_manager.cursor.execute("""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(CASE WHEN source_references->'pathways' IS NOT NULL 
                              AND source_references->'pathways' != '[]'::jsonb 
                              THEN 1 END) as with_refs
                    FROM cancer_transcript_base 
                """)
                result = processor.db_manager.cursor.fetchone()
                if result:
                    total, ref_count = result
                    console.print(f"\n[green]Added pathway information to {total:,} records[/green]")
                    console.print(f"[green]Added pathway references to {ref_count:,} records[/green]")
            
        console.print("\n[green]Pathway enrichment completed successfully![/green]")
        
    except Exception as e:
        console.print(f"\n[red]Error: {str(e)}[/red]")
        logger.exception("Pipeline failed")
        sys.exit(1)

if __name__ == "__main__":
    main()

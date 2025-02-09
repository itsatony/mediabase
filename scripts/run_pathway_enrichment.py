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

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.etl.pathways import PathwayProcessor

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)]
)
logger = logging.getLogger("pathway_enrichment")
console = Console()

def main():
    """Main execution function."""
    try:
        # Load configuration
        load_dotenv()
        
        # Verify required environment variables
        if not os.getenv('MB_REACTOME_DOWNLOAD_URL'):
            raise ValueError("Missing MB_REACTOME_DOWNLOAD_URL environment variable")
        
        config = {
            'reactome_data_url': os.getenv('MB_REACTOME_DOWNLOAD_URL'),
            'cache_dir': os.getenv('MB_CACHE_DIR'),
            'cache_ttl': int(os.getenv('MB_CACHE_TTL', '86400')),
            'batch_size': int(os.getenv('MB_BATCH_SIZE', '1000')),
            # Database connection params
            'host': os.getenv('MB_POSTGRES_HOST'),
            'port': int(os.getenv('MB_POSTGRES_PORT', '5432')),
            'dbname': os.getenv('MB_POSTGRES_NAME'),
            'user': os.getenv('MB_POSTGRES_USER'),
            'password': os.getenv('MB_POSTGRES_PASSWORD')
        }
        
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
                
            version_query = processor.db_manager.cursor.execute(
                "SELECT version FROM schema_version"
            )
            version = version_query.fetchone() if version_query else None
            if not version or version[0] != 'v0.1.4':
                raise RuntimeError("Database schema must be v0.1.4")
            
            progress.update(task, description="Processing pathways...")
            processor.run()
            
            # Verify results with proper null checks
            if processor.db_manager.cursor:
                processor.db_manager.cursor.execute("""
                    SELECT COUNT(*) 
                    FROM cancer_transcript_base 
                    WHERE source_references->>'pathways' IS NOT NULL
                    AND source_references->>'pathways' != '[]'
                """)
                result = processor.db_manager.cursor.fetchone()
                ref_count = result[0] if result else 0
                console.print(f"\n[green]Added pathway references to {ref_count:,} records[/green]")
            
        console.print("\n[green]Pathway enrichment completed successfully![/green]")
        
    except Exception as e:
        console.print(f"\n[red]Error: {str(e)}[/red]")
        logger.exception("Pipeline failed")
        sys.exit(1)

if __name__ == "__main__":
    main()

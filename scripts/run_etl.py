"""ETL pipeline orchestrator for Cancer Transcriptome Base."""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
from rich.console import Console
from rich.progress import Progress, SpinnerColumn
from rich.logging import RichHandler

# Add src to Python path
src_path = Path(__file__).resolve().parent.parent
sys.path.append(str(src_path))

from src.db.database import get_db_manager
from src.etl.transcript import TranscriptProcessor
from src.etl.products import ProductProcessor
from src.etl.go_terms import GOTermProcessor
from src.etl.pathways import PathwayProcessor
from src.etl.drugs import DrugProcessor
from src.etl.publications import PublicationsProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        RichHandler(rich_tracebacks=True),
        logging.FileHandler("etl_pipeline.log")
    ]
)
logger = logging.getLogger(__name__)
console = Console()

def get_config() -> Dict[str, Any]:
    """Load configuration from environment variables."""
    return {
        'db': {
            'host': os.getenv('MB_POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('MB_POSTGRES_PORT', '5432')),
            'dbname': os.getenv('MB_POSTGRES_NAME', 'mediabase'),
            'user': os.getenv('MB_POSTGRES_USER', 'postgres'),
            'password': os.getenv('MB_POSTGRES_PASSWORD', 'postgres')
        },
        'cache_dir': os.getenv('MB_CACHE_DIR', '/tmp/mediabase/cache'),
        'gencode_gtf_url': os.getenv('MB_GENCODE_GTF_URL'),
        'drugcentral_url': os.getenv('MB_DRUGCENTRAL_DATA_URL'),
        'reactome_url': os.getenv('MB_REACTOME_DOWNLOAD_URL'),
        'pubmed_email': os.getenv('MB_PUBMED_EMAIL'),
        'pubmed_api_key': os.getenv('MB_PUBMED_API_KEY'),
        'batch_size': int(os.getenv('MB_BATCH_SIZE', '1000')),
        'cache_ttl': int(os.getenv('MB_CACHE_TTL', '86400')),
        'max_workers': int(os.getenv('MB_MAX_WORKERS', '4'))
    }

def run_module(
    module_name: str,
    config: Dict[str, Any],
    limit_transcripts: Optional[int] = None,
    reset_db: bool = False
) -> bool:
    """Run a specific ETL module.
    
    Args:
        module_name: Name of module to run
        config: Configuration dictionary
        limit_transcripts: Optional limit on number of transcripts to process
        reset_db: Optional flag to reset database before running module
        
    Returns:
        bool: True if successful
    """
    try:
        if limit_transcripts:
            logger.info(f"Processing limited to {limit_transcripts} transcripts")
            config['limit_transcripts'] = limit_transcripts

        if reset_db:
            logger.info("Resetting database...")
            db = get_db_manager(config['db'])
            db.reset_database()
            logger.info("Database reset complete")

        if module_name == 'transcripts':
            processor = TranscriptProcessor(config)
            processor.run()
        elif module_name == 'products':
            processor = ProductProcessor(config)
            processor.run()
        elif module_name == 'go_terms':
            processor = GOTermProcessor(config)
            processor.run()
        elif module_name == 'pathways':
            processor = PathwayProcessor(config)
            processor.run()
        elif module_name == 'drugs':
            processor = DrugProcessor(config)
            processor.run()
        elif module_name == 'publications':
            processor = PublicationsProcessor(config)
            processor.run()
        else:
            logger.error(f"Unknown module: {module_name}")
            return False

        return True

    except Exception as e:
        logger.error(f"Module {module_name} failed: {e}")
        return False

def run_pipeline(
    config: Dict[str, Any],
    modules: Optional[List[str]] = None,
    limit_transcripts: Optional[int] = None,
    reset_db: bool = False
) -> None:
    """Run the complete ETL pipeline or specified modules.
    
    Args:
        config: Configuration dictionary
        modules: Optional list of specific modules to run
        limit_transcripts: Optional limit on number of transcripts to process
        reset_db: Optional flag to reset database before running pipeline
    """
    all_modules = [
        'transcripts',
        'products',
        'go_terms',
        'pathways',
        'drugs',
        'publications'
    ]

    modules_to_run = modules if modules else all_modules
    
    # Validate database connection first
    db = get_db_manager(config['db'])
    if not db.ensure_connection():
        logger.error("Failed to establish database connection")
        return

    with Progress(
        SpinnerColumn(),
        *Progress.get_default_columns(),
        console=console
    ) as progress:
        task = progress.add_task("Running ETL pipeline...", total=len(modules_to_run))
        
        for module in modules_to_run:
            progress.update(task, description=f"Processing {module}...")
            if not run_module(module, config, limit_transcripts, reset_db):
                logger.error(f"Pipeline failed at module: {module}")
                return
            progress.advance(task)

        progress.update(task, description="Pipeline completed!")

def main() -> None:
    """Main entry point for ETL pipeline."""
    parser = argparse.ArgumentParser(description="Run MediaBase ETL pipeline")
    parser.add_argument(
        "--modules",
        nargs="+",
        choices=['transcripts', 'products', 'go_terms', 'pathways', 'drugs', 'publications'],
        help="Specific modules to run"
    )
    parser.add_argument(
        "--limit-transcripts",
        type=int,
        help="Limit number of transcripts to process"
    )
    parser.add_argument(
        "--log-level",
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help="Set logging level"
    )
    parser.add_argument(
        "--reset-db",
        action="store_true",
        help="Reset database before running pipeline"
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Force refresh of cached data"
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        help="API rate limit in seconds"
    )

    args = parser.parse_args()
    
    # Configure logging level
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    # Load configuration
    config = get_config()
    
    # Add optional configurations
    if args.force_refresh:
        config['force_refresh'] = True
    if args.rate_limit:
        config['rate_limit'] = args.rate_limit

    try:
        run_pipeline(
            config, 
            args.modules, 
            args.limit_transcripts,
            reset_db=args.reset_db
        )
    except KeyboardInterrupt:
        logger.info("Pipeline interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

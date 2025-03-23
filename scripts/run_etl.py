"""ETL pipeline orchestrator for Cancer Transcriptome Base."""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List

# Add src to Python path
src_path = Path(__file__).resolve().parent.parent
sys.path.append(str(src_path))

# Import our centralized logging first
from src.utils.logging import setup_logging, get_progress, console

# Use centralized logging with proper module name
logger = setup_logging(
    module_name=__name__,
    log_file="etl_pipeline.log"
)

# Now import other modules
from src.db.database import get_db_manager
from src.etl.transcript import TranscriptProcessor
from src.etl.products import ProductProcessor
from src.etl.go_terms import GOTermProcessor
from src.etl.pathways import PathwayProcessor
from src.etl.drugs import DrugProcessor
from src.etl.publications import PublicationsProcessor

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
            
            # Use the improved reset_database method
            if not db.reset_database():
                logger.error("Database reset failed, cannot continue")
                return False
                
            # Validate schema was properly applied
            if not db.validate_schema():
                logger.error("Schema validation failed after reset")
                return False
                
            logger.info("Database reset complete with schema v0.1.5 applied")

        # Construct the processor for the requested module
        processor = None
        if module_name == 'transcripts':
            processor = TranscriptProcessor(config)
        elif module_name == 'products':
            processor = ProductProcessor(config)
        elif module_name == 'go_terms':
            processor = GOTermProcessor(config)
        elif module_name == 'pathways':
            processor = PathwayProcessor(config)
        elif module_name == 'drugs':
            processor = DrugProcessor(config)
        elif module_name == 'publications':
            processor = PublicationsProcessor(config)
        else:
            logger.error(f"Unknown module: {module_name}")
            return False
            
        # Run the processor
        processor.run()
        logger.info(f"Module {module_name} completed successfully")
        return True

    except Exception as e:
        logger.error(f"Module {module_name} failed: {e}", exc_info=True)
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

    # Get shared progress instance
    progress = get_progress()
    
    # Single progress instance for all modules
    with progress:
        task = progress.add_task("[bold green]Running ETL pipeline...", total=len(modules_to_run))
        
        # If reset_db is True, handle it once at the start
        if reset_db:
            logger.info("Resetting database once for all modules")
            if not db.reset_database():
                logger.error("Database reset failed, cannot continue pipeline")
                return
                
            # Validate schema was properly applied
            if not db.validate_schema():
                logger.error("Schema validation failed after reset")
                return
                
            logger.info("Database has been reset and schema v0.1.5 applied")
        
        for module in modules_to_run:
            progress.update(task, description=f"[bold cyan]Processing {module}...")
            if not run_module(module, config, limit_transcripts, reset_db=False):  # Don't reset again
                logger.error(f"Pipeline failed at module: {module}")
                return
            progress.advance(task)

        progress.update(task, description="[bold green]Pipeline completed!", completed=len(modules_to_run))

def main() -> int:  # Change return type to int for clarity
    """Main entry point for ETL pipeline.
    
    Returns:
        int: 0 for success, 1 for error
    """
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
        # Modify the section where database reset is performed
        if args.reset_db:
            logger.info("Resetting database...")
            
            db_manager = None
            try:
                db_manager = get_db_manager(config['db'])
                db_manager.display_config()
                
                # Reset database using new simplified method
                if not db_manager.reset_database():
                    logger.error("Database reset failed, cannot continue")
                    return 1
                    
                # Verify schema was properly applied with validation
                if not db_manager.validate_schema():
                    logger.error("Schema validation failed after reset")
                    return 1
                    
                logger.info("Database reset complete with schema v0.1.5 properly applied")
            except Exception as e:
                logger.error(f"Database reset error: {e}")
                return 1
            finally:
                if db_manager and db_manager.conn:
                    db_manager.close()
        
        run_pipeline(
            config, 
            args.modules, 
            args.limit_transcripts,
            reset_db=args.reset_db
        )
        return 0  # Explicit successful return
    except KeyboardInterrupt:
        logger.info("Pipeline interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())  # Use sys.exit with the return value

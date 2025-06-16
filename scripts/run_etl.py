"""ETL pipeline orchestrator for Cancer Transcriptome Base."""

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional, List

# Add project root to Python path
src_path = Path(__file__).resolve().parent.parent
sys.path.append(str(src_path))

# Import our centralized logging first
from src.utils.logging import setup_logging, get_progress_bar, console

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
from src.etl.id_enrichment import IDEnrichmentProcessor
from src.etl.chembl_drugs import ChemblDrugProcessor

from config.etl_sequence import get_optimal_sequence, validate_sequence

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
        # Ensure any previous progress bars are completed
        from src.utils.logging import complete_all_progress_bars
        complete_all_progress_bars()
        
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
                
            logger.info("Database reset complete with schema v0.1.6 applied")
        else:
            # Check and upgrade schema if needed
            db = get_db_manager(config['db'])
            current_version = db.get_current_version()
            if current_version and current_version < 'v0.1.6':
                logger.info(f"Upgrading database schema from {current_version} to v0.1.6")
                if not db.migrate_to_version('v0.1.6'):
                    logger.error("Schema migration failed")
                    return False
                logger.info("Schema successfully upgraded to v0.1.6")

        # Construct the processor for the requested module
        processor = None
        if module_name == 'transcripts':
            processor = TranscriptProcessor(config)
        elif module_name == 'id_enrichment':  # Add the ID enrichment module
            processor = IDEnrichmentProcessor(config)
        elif module_name == 'go_terms':
            processor = GOTermProcessor(config)
        elif module_name == 'products':
            processor = ProductProcessor(config)
        elif module_name == 'pathways':
            processor = PathwayProcessor(config)
        elif module_name == 'drugs':
            # Check if we should use ChEMBL instead of DrugCentral
            if config.get('use_chembl', True):
                logger.info("Using ChEMBL for drug data instead of DrugCentral")
                processor = ChemblDrugProcessor(config)
            else:
                processor = DrugProcessor(config)
        elif module_name == 'chembl_drugs':
            # Explicit ChEMBL drug processor
            processor = ChemblDrugProcessor(config)
        elif module_name == 'publications':
            processor = PublicationsProcessor(config)
        else:
            logger.error(f"Unknown module: {module_name}")
            return False
            
        # Run the processor
        processor.run()
        
        # Make sure progress bars are completed before logging
        complete_all_progress_bars()
        
        logger.info(f"Module {module_name} completed successfully")
        return True

    except Exception as e:
        # Complete any progress bars before logging errors
        from src.utils.logging import complete_all_progress_bars
        complete_all_progress_bars()
        
        logger.error(f"Module {module_name} failed: {e}", exc_info=True)
        return False

def run_pipeline(
    config: Dict[str, Any],
    modules: Optional[List[str]] = None,
    limit_transcripts: Optional[int] = None,
    reset_db: bool = False
) -> None:
    """Run the complete ETL pipeline or specified modules."""
    all_modules = [
        'transcripts',
        'id_enrichment',  # Make sure id_enrichment comes early
        'go_terms',
        'products',
        'pathways',
        'drugs',
        'publications'
    ]

    # Now check if modules list is provided and if id_enrichment is in the list
    if modules and 'id_enrichment' not in modules:
        # Add warning that we're missing important id mapping steps
        logger.warning("ID enrichment module is not included. This could affect other modules that rely on ID mappings.")
    
    modules_to_run = modules if modules else all_modules
    
    # Validate database connection first
    db = get_db_manager(config['db'])
    if not db.ensure_connection():
        logger.error("Failed to establish database connection")
        return

    # Create the progress bar AFTER completing any existing ones
    from src.utils.logging import complete_all_progress_bars
    complete_all_progress_bars()
    
    # Use our enhanced progress bar for the pipeline
    progress_bar = get_progress_bar(
        total=len(modules_to_run),
        desc="Running ETL pipeline",
        module_name="pipeline",
        unit="modules"
    )
    
    try:
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
                
            logger.info("Database has been reset and schema v0.1.6 applied")
        
        # Process each module in sequence
        for i, module in enumerate(modules_to_run):
            # Log the start of module processing
            logger.info(f"Processing module: {module}")
            
            # Run the module (no progress bar completion here to avoid deadlocks)
            success = run_module(module, config, limit_transcripts, reset_db=False)
            
            if not success:
                logger.error(f"Pipeline failed at module: {module}")
                break
                
            # Update pipeline progress
            progress_bar.update(1)
            
            # Log a separator between modules
            if i < len(modules_to_run) - 1:
                logger.info("-" * 40)

        logger.info("Pipeline completed successfully!")
    finally:
        # Close progress bar if it exists and is not already closed
        if 'progress_bar' in locals() and not progress_bar._is_finished:
            progress_bar.close()

# Update the code that determines which modules to run
def get_modules_to_run(args) -> List[str]:
    """Get the list of modules to run based on command-line arguments."""
    if args.module:
        # Split comma-separated list of modules
        requested_modules = args.module.split(',')
        
        # Handle the case where chembl_drugs is requested
        if 'chembl_drugs' in requested_modules and 'drugs' in requested_modules:
            # If both are specified, remove regular drugs to avoid duplicates
            requested_modules.remove('drugs')
            logger.info("Both 'drugs' and 'chembl_drugs' were specified. Using only 'chembl_drugs'")
        
        # Get optimal sequence that includes all dependencies
        modules_to_run = get_optimal_sequence(requested_modules)
        
        # Handle the case where drugs module is part of dependencies but chembl_drugs is requested
        if 'chembl_drugs' in requested_modules and 'drugs' in modules_to_run and 'chembl_drugs' not in modules_to_run:
            # Replace drugs with chembl_drugs in the sequence
            modules_to_run = [m if m != 'drugs' else 'chembl_drugs' for m in modules_to_run]
        
        # Validate the sequence
        if not validate_sequence(modules_to_run):
            logging.error("Invalid module sequence. Check dependencies.")
            sys.exit(1)
            
        # Log the final sequence with dependency information
        logging.info(f"Running modules in optimal sequence: {', '.join(modules_to_run)}")
        if set(modules_to_run) != set(requested_modules):
            additional = set(modules_to_run) - set(requested_modules)
            logging.info(f"Added dependency modules: {', '.join(additional)}")
            
        return modules_to_run
    else:
        # Run all modules in the correct order
        return get_optimal_sequence()

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Run ETL pipeline")
    
    parser.add_argument(
        "--module",
        type=str,
        help="Comma-separated list of modules to run (transcripts,id_enrichment,go_terms,products,pathways,drugs,publications,chembl_drugs)"
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
        "--force-download",
        action="store_true",
        help="Force download of data files even if cache exists"
    )
    parser.add_argument(
        "--skip-scores",
        action="store_true",
        help="Skip score calculation in applicable modules"
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=1.0,
        help="API rate limit in seconds for external data sources"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for database operations"
    )
    # ChEMBL-specific arguments
    parser.add_argument(
        "--use-chembl",
        action="store_true",
        help="Use ChEMBL instead of DrugCentral for drug data"
    )
    parser.add_argument(
        "--chembl-max-phase",
        type=int,
        default=0,
        choices=[0, 1, 2, 3, 4],
        help="Only include ChEMBL drugs with max phase >= this value (0-4, where 4 is approved)"
    )
    parser.add_argument(
        "--chembl-schema",
        type=str,
        default="chembl_temp",
        help="Schema name for ChEMBL data tables"
    )
    parser.add_argument(
        "--no-chembl-temp-schema",
        action="store_true",
        help="Do not use a temporary schema for ChEMBL data (use permanent schema)"
    )
    
    return parser.parse_args()

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

    # Add ChEMBL-specific configurations
    if args.use_chembl:
        config['use_chembl'] = True
        config['chembl_max_phase'] = args.chembl_max_phase
        config['chembl_schema'] = args.chembl_schema
        config['use_temp_schema'] = not args.no_chembl_temp_schema

    try:
        # Make sure any previous progress bars are completed
        from src.utils.logging import complete_all_progress_bars
        complete_all_progress_bars()
        
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
                    
                logger.info("Database reset complete with schema v0.1.6 properly applied")
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
        # Ensure progress bars are completed on interruption
        from src.utils.logging import complete_all_progress_bars
        complete_all_progress_bars()
        
        logger.info("Pipeline interrupted by user")
        return 1
    except Exception as e:
        # Ensure progress bars are completed on error
        from src.utils.logging import complete_all_progress_bars
        complete_all_progress_bars()
        
        logger.error(f"Pipeline failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())  # Use sys.exit with the return value

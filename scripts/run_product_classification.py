"""CLI script to run gene product classification."""

import os
import argparse
import logging
from pathlib import Path
from rich.progress import Progress, SpinnerColumn, TextColumn
from src.etl.products import ProductClassifier
from src.utils.validation import validate_db_config

logger = logging.getLogger(__name__)

def setup_logging(level: str = 'INFO') -> None:
    """Setup logging configuration."""
    logging.basicConfig(
        level=getattr(logging, level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def run_classification(config: dict) -> None:
    """Run the product classification pipeline."""
    logger.info("Starting gene product classification")
    
    classifier = ProductClassifier(config=config)
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        task = progress.add_task("Updating gene product classifications...", total=None)
        classifier.update_database_classifications()
        progress.update(task, completed=True)
        
def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run gene product classification")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()
    
    setup_logging(args.log_level)
    
    # Prepare configuration
    db_config = {
        'host': os.getenv('MB_POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('MB_POSTGRES_PORT', '5432')),
        'dbname': os.getenv('MB_POSTGRES_NAME', 'mediabase'),
        'user': os.getenv('MB_POSTGRES_USER', 'postgres'),
        'password': os.getenv('MB_POSTGRES_PASSWORD', 'postgres')
    }
    
    # Validate database configuration
    validated_db_config = validate_db_config(db_config)
    
    config = {
        'batch_size': args.batch_size,
        'db': validated_db_config,
        'cache_dir': os.getenv('MB_CACHE_DIR', '/tmp/mediabase/cache')
    }
    
    try:
        run_classification(config)
        logger.info("Product classification completed successfully")
    except Exception as e:
        logger.error(f"Error during product classification: {e}")
        raise

if __name__ == "__main__":
    main()

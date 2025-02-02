"""
CLI script to run gene product classification.
"""

import asyncio
import argparse
import logging
from rich.progress import Progress, SpinnerColumn, TextColumn
from src.etl.products import ProductClassifier
import logging

def setup_logging() -> None:
    """Setup logging configuration."""
    logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

async def run_classification(uniprot_url: str, config: dict) -> None:
    """Run the product classification pipeline."""
    classifier = ProductClassifier(uniprot_url, config)
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task("Updating gene product classifications...", total=None)
        await classifier.update_database_classifications()
        
def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run gene product classification")
    parser.add_argument("--uniprot-url", default="https://rest.uniprot.org/uniprotkb")
    parser.add_argument("--cache-ttl", type=int, default=86400)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-retries", type=int, default=3)
    args = parser.parse_args()
    
    setup_logging()
    
    config = {
        'cache_ttl': args.cache_ttl,
        'batch_size': args.batch_size,
        'max_retries': args.max_retries,
        'timeout': 30
    }
    
    try:
        asyncio.run(run_classification(args.uniprot_url, config))
        logger.info("Product classification completed successfully")
    except Exception as e:
        logger.error(f"Error during product classification: {e}")
        raise

if __name__ == "__main__":
    main()

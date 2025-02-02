#!/usr/bin/env python3
"""ETL pipeline runner script."""

import os
import logging
from pathlib import Path
import argparse
from dotenv import load_dotenv
from src.etl.transcript import TranscriptProcessor

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_config():
    """Load configuration from environment variables."""
    # Load .env file
    env_path = Path(__file__).parent.parent / '.env'
    load_dotenv(env_path)
    
    return {
        'gtf_url': os.getenv('MB_GENCODE_GTF_URL'),
        'cache_dir': os.getenv('MB_CACHE_DIR', '/tmp/mediabase/cache'),
        'batch_size': int(os.getenv('MB_BATCH_SIZE', '1000')),
        'host': os.getenv('MB_POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('MB_POSTGRES_PORT', '5432')),
        'dbname': os.getenv('MB_POSTGRES_NAME', 'mediabase'),
        'user': os.getenv('MB_POSTGRES_USER', 'postgres'),
        'password': os.getenv('MB_POSTGRES_PASSWORD', 'postgres')
    }

def main():
    """Main entry point for ETL pipeline."""
    parser = argparse.ArgumentParser(description='Run ETL pipeline')
    parser.add_argument('--module', choices=['transcript'], 
                       default='transcript',
                       help='ETL module to run')
    args = parser.parse_args()
    
    config = load_config()
    
    if args.module == 'transcript':
        processor = TranscriptProcessor(config)
        processor.run()

if __name__ == '__main__':
    main()

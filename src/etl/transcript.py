"""Transcript ETL module for processing gene transcript data."""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import pandas as pd
import numpy as np
from gtfparse import read_gtf
import psycopg2
from psycopg2.extras import execute_batch
from ..utils.validation import validate_transcript_data
from ..db.connection import get_db_connection
import hashlib
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)

class TranscriptProcessor:
    """Process and load transcript data into the database."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize the transcript processor.
        
        Args:
            config: Configuration dictionary containing:
                - gtf_url: URL to download Gencode GTF file
                - cache_dir: Directory to store downloaded files
                - batch_size: Size of batches for database operations
        """
        self.config = config
        self.cache_dir = Path(config['cache_dir'])
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.batch_size = config.get('batch_size', 1000)
        
        # Add database configuration
        self.db_config = {
            'host': config['host'],
            'port': config['port'],
            'dbname': config['dbname'],
            'user': config['user'],
            'password': config['password']
        }
        
        # Add cache control settings
        self.cache_ttl = int(config.get('cache_ttl', 86400))  # 24 hours default
        self.cache_meta_file = self.cache_dir / "gtf_meta.json"

    def _get_cache_key(self, url: str) -> str:
        """Generate a cache key from URL."""
        return hashlib.sha256(url.encode()).hexdigest()

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cache is still valid."""
        if not self.cache_meta_file.exists():
            return False
            
        try:
            with open(self.cache_meta_file, 'r') as f:
                meta = json.load(f)
                
            if cache_key not in meta:
                return False
                
            cache_time = datetime.fromisoformat(meta[cache_key]['timestamp'])
            return datetime.now() - cache_time < timedelta(seconds=self.cache_ttl)
        except (json.JSONDecodeError, KeyError, ValueError):
            return False

    def _update_cache_meta(self, cache_key: str, file_path: Path) -> None:
        """Update cache metadata."""
        meta = {}
        if self.cache_meta_file.exists():
            try:
                with open(self.cache_meta_file, 'r') as f:
                    meta = json.load(f)
            except json.JSONDecodeError:
                pass
        
        meta[cache_key] = {
            'timestamp': datetime.now().isoformat(),
            'file_path': str(file_path)
        }
        
        with open(self.cache_meta_file, 'w') as f:
            json.dump(meta, f)

    def download_gtf(self) -> Path:
        """Download GTF file if not in cache or cache is invalid."""
        cache_key = self._get_cache_key(self.config['gtf_url'])
        gtf_path = self.cache_dir / f"gencode_{cache_key}.gtf.gz"
        
        # Check if we have a valid cached file
        if gtf_path.exists() and self._is_cache_valid(cache_key):
            logger.info("Using cached GTF file")
            return gtf_path

        # Download new file
        logger.info("Downloading GTF file...")
        import requests
        from tqdm import tqdm

        response = requests.get(self.config['gtf_url'], stream=True)
        total_size = int(response.headers.get('content-length', 0))

        with open(gtf_path, 'wb') as f, tqdm(
            desc="Downloading",
            total=total_size,
            unit='iB',
            unit_scale=True
        ) as pbar:
            for data in response.iter_content(chunk_size=1024):
                size = f.write(data)
                pbar.update(size)

        # Update cache metadata
        self._update_cache_meta(cache_key, gtf_path)
        return gtf_path

    def process_gtf(self, gtf_path: Path) -> pd.DataFrame:
        """Process GTF file into transcript records."""
        logger.info("Reading GTF file...")
        df = read_gtf(str(gtf_path))
        if not isinstance(df, pd.DataFrame):
            raise TypeError("Expected a pandas DataFrame")
        
        # Filter for transcript entries
        transcript_mask = df['feature'] == 'transcript'
        transcripts: pd.DataFrame = df.loc[transcript_mask].copy()
        
        # Extract coordinates with proper typing
        def create_coordinates(row: pd.Series) -> Dict[str, int]:
            return {
                'start': int(row['start']),
                'end': int(row['end']),
                'strand': 1 if row['strand'] == '+' else -1
            }
        
        transcripts['coordinates'] = transcripts.apply(create_coordinates, axis=1)

        # Select and rename columns with proper typing
        result = pd.DataFrame({
            'transcript_id': transcripts['transcript_id'].astype(str),
            'gene_symbol': transcripts['gene_name'].astype(str),
            'gene_id': transcripts['gene_id'].astype(str),
            'gene_type': transcripts['gene_type'].astype(str),
            'chromosome': transcripts['seqname'].astype(str),
            'coordinates': transcripts['coordinates'].tolist()
        })

        return result

    def prepare_transcript_records(
        self,
        df: pd.DataFrame
    ) -> List[Tuple[str, str, str, str, str, Dict[str, Any]]]:
        """Prepare transcript records for database insertion.
        
        Args:
            df: DataFrame with transcript data
            
        Returns:
            List of tuples ready for database insertion
        """
        records = []
        for _, row in df.iterrows():
            record = (
                row['transcript_id'],
                row['gene_symbol'],
                row['gene_id'],
                row['gene_type'],
                row['chromosome'],
                row['coordinates']
            )
            records.append(record)
        return records

    def load_transcripts(self, records: List[Tuple]) -> None:
        """Load transcript records into database.
        
        Args:
            records: List of transcript record tuples
        """
        conn = get_db_connection(self.db_config)  # Use db_config instead of config
        try:
            with conn.cursor() as cur:
                # Clear existing data
                cur.execute("TRUNCATE TABLE cancer_transcript_base")
                
                # Insert new records
                execute_batch(
                    cur,
                    """
                    INSERT INTO cancer_transcript_base (
                        transcript_id,
                        gene_symbol,
                        gene_id,
                        gene_type,
                        chromosome,
                        coordinates
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    records,
                    page_size=self.batch_size
                )
            conn.commit()
            logger.info(f"Loaded {len(records)} transcript records")
        except Exception as e:
            conn.rollback()
            logger.error(f"Error loading transcripts: {e}")
            raise
        finally:
            conn.close()

    def validate_data(self, df: pd.DataFrame) -> bool:
        """Validate processed transcript data.
        
        Args:
            df: DataFrame with transcript data
            
        Returns:
            bool: True if validation passes
        """
        return validate_transcript_data(df)

    def run(self) -> None:
        """Run the complete transcript processing pipeline."""
        try:
            # Download GTF file
            gtf_path = self.download_gtf()
            
            # Process GTF data
            df = self.process_gtf(gtf_path)
            
            # Validate processed data
            if not self.validate_data(df):
                raise ValueError("Transcript data validation failed")
            
            # Prepare records
            records = self.prepare_transcript_records(df)
            
            # Load into database
            self.load_transcripts(records)
            
            logger.info("Transcript processing completed successfully")
            
        except Exception as e:
            logger.error(f"Transcript processing failed: {e}")
            raise

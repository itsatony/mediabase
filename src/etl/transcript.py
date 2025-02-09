"""Transcript ETL module for processing gene transcript data."""

# Standard library imports
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from gtfparse import read_gtf
import hashlib
import json

# Third party imports
import pandas as pd
from psycopg2.extras import execute_batch

# Local imports
from ..utils.validation import validate_transcript_data
from ..db.database import get_db_manager

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
        self.db_manager = get_db_manager(self.db_config)

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

    def _inspect_gtf_structure(self, df: pd.DataFrame) -> None:
        """Inspect and log GTF file structure for debugging."""
        logger.info(f"GTF DataFrame columns: {df.columns.tolist()}")
        logger.info(f"Number of records: {len(df)}")
        # Log sample of first row for debugging
        if not df.empty:
            logger.info(f"First row sample: {df.iloc[0].to_dict()}")

    def _get_attributes_column(self, df: pd.DataFrame) -> str:
        """Identify the correct attributes column name.
        
        Args:
            df: GTF DataFrame
            
        Returns:
            str: Name of the attributes column
            
        Raises:
            ValueError: If attributes column cannot be found
        """
        # Common variations of attributes column name
        possible_names = ['attribute', 'attributes', 'attribute_string', 'info']
        
        for name in possible_names:
            if name in df.columns:
                return name
                
        # If not found in common names, try to identify by content
        for col in df.columns:
            sample = df[col].iloc[0] if not df.empty else ""
            if isinstance(sample, str) and ';' in sample and '=' in sample:
                return col
                
        raise ValueError(
            "Could not identify attributes column. Available columns: "
            f"{', '.join(df.columns)}"
        )

    def extract_alt_ids(self, row: pd.Series) -> Dict[str, Dict[str, str]]:
        """Extract alternative IDs from GTF attributes.
        
        Args:
            row: DataFrame row with GTF data
            
        Returns:
            Dict containing alternative transcript and gene IDs
        """
        alt_transcript_ids: Dict[str, str] = {}
        alt_gene_ids: Dict[str, str] = {}
        
        try:
            # Direct column access for ID fields
            # Process transcript IDs
            for col in row.index:
                # Handle transcript IDs
                if col.startswith('transcript_id_'):
                    source = col.split('transcript_id_')[1]
                    if bool(pd.notna(row[col])) and row[col] is not None:
                        alt_transcript_ids[source] = str(row[col])
                # Handle gene IDs
                elif col.startswith('gene_id_'):
                    source = col.split('gene_id_')[1]
                    if bool(pd.notna(row[col])):
                        alt_gene_ids[source] = str(row[col])
            
            # Add standard identifiers if available
            if 'hgnc_id' in row and pd.notna(row['hgnc_id']):
                alt_gene_ids['HGNC'] = str(row['hgnc_id'])
            if 'havana_gene' in row and pd.notna(row['havana_gene']):
                alt_gene_ids['HAVANA'] = str(row['havana_gene'])
            if 'havana_transcript' in row and pd.notna(row['havana_transcript']):
                alt_transcript_ids['HAVANA'] = str(row['havana_transcript'])
            if 'ccdsid' in row and pd.notna(row['ccdsid']):
                alt_transcript_ids['CCDS'] = str(row['ccdsid'])
                
        except Exception as e:
            logger.debug(  # Changed to debug level since this is expected for some rows
                f"Could not extract alternative IDs for transcript "
                f"{row.get('transcript_id', 'UNKNOWN')}: {str(e)}"
            )
        
        return {
            'alt_transcript_ids': alt_transcript_ids,
            'alt_gene_ids': alt_gene_ids
        }

    def process_gtf(self, gtf_path: Path) -> pd.DataFrame:
        """Process GTF file into transcript records."""
        logger.info("Reading GTF file...")
        df = read_gtf(str(gtf_path))
        
        # Inspect DataFrame structure
        self._inspect_gtf_structure(df)
        
        # Validate DataFrame
        if not isinstance(df, pd.DataFrame):
            raise TypeError("read_gtf did not return a pandas DataFrame")
        
        # Required columns for basic processing
        required_cols = ['feature', 'transcript_id', 'gene_id', 'gene_name', 
                        'gene_type', 'seqname', 'start', 'end', 'strand']
        
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(
                f"Missing required columns in GTF file: {missing_cols}"
            )
        
        # Filter for transcript entries
        transcript_mask = df['feature'] == 'transcript'
        transcripts = df.loc[transcript_mask].copy()
        
        if transcripts.empty:
            raise ValueError("No transcript records found in GTF file")
            
        logger.info(f"Processing {len(transcripts)} transcript records...")
        
        # Extract coordinates with proper typing and validation
        def create_coordinates(row: pd.Series) -> Dict[str, int]:
            try:
                return {
                    'start': int(row['start']),
                    'end': int(row['end']),
                    'strand': 1 if row['strand'] == '+' else -1
                }
            except (ValueError, TypeError) as e:
                logger.warning(
                    f"Invalid coordinate values for transcript "
                    f"{row.get('transcript_id', 'UNKNOWN')}: {e}"
                )
                return {'start': 0, 'end': 0, 'strand': 0}
        
        # Process coordinates and alternative IDs
        try:
            transcripts['coordinates'] = transcripts.apply(
                create_coordinates, axis=1
            )
            transcripts['alt_ids'] = transcripts.apply(
                self.extract_alt_ids, axis=1
            )
        except Exception as e:
            raise ValueError(f"Error processing transcript data: {e}") from e
        
        # Select and rename columns with proper typing
        try:
            result = pd.DataFrame({
                'transcript_id': transcripts['transcript_id'].astype(str),
                'gene_symbol': transcripts['gene_name'].astype(str),
                'gene_id': transcripts['gene_id'].astype(str),
                'gene_type': transcripts['gene_type'].astype(str),
                'chromosome': transcripts['seqname'].astype(str),
                'coordinates': transcripts['coordinates'].tolist(),
                'alt_transcript_ids': transcripts['alt_ids'].apply(
                    lambda x: x['alt_transcript_ids']
                ).tolist(),
                'alt_gene_ids': transcripts['alt_ids'].apply(
                    lambda x: x['alt_gene_ids']
                ).tolist()
            })
        except Exception as e:
            raise ValueError(
                f"Error creating final DataFrame: {e}"
            ) from e
        
        logger.info(
            f"Processed {len(result)} transcripts with "
            f"{result['alt_transcript_ids'].apply(len).sum()} "
            "alternative transcript IDs"
        )
        
        return result

    def prepare_transcript_records(
        self,
        df: pd.DataFrame
    ) -> List[Tuple[str, str, str, str, str, Dict[str, Any], Dict[str, str], Dict[str, str]]]:
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
                row['coordinates'],
                row['alt_transcript_ids'],
                row['alt_gene_ids']
            )
            records.append(record)
        return records

    def load_transcripts(self, records: List[Tuple]) -> None:
        """Load transcript records into database."""
        try:
            if not self.db_manager.cursor:
                raise RuntimeError("No database connection")
                
            # Clear existing data
            self.db_manager.cursor.execute("TRUNCATE TABLE cancer_transcript_base")
            
            # Insert new records
            execute_batch(
                self.db_manager.cursor,
                """
                INSERT INTO cancer_transcript_base (
                    transcript_id,
                    gene_symbol,
                    gene_id,
                    gene_type,
                    chromosome,
                    coordinates,
                    alt_transcript_ids,
                    alt_gene_ids
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                records,
                page_size=self.batch_size
            )
            
            if self.db_manager.conn:
                self.db_manager.conn.commit()
                
        except Exception as e:
            if self.db_manager.conn:
                self.db_manager.conn.rollback()
            logger.error(f"Error loading transcripts: {e}")
            raise

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

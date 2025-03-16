"""Transcript ETL module for processing gene transcript data."""

# Standard library imports
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import logging
import hashlib
from gtfparse import read_gtf
import pandas as pd
import requests
import json
import os
from tqdm import tqdm

# Third party imports
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
                - limit_transcripts: Optional limit on number of transcripts to process
        """
        self.config = config
        self.cache_dir = Path(config['cache_dir'])
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.batch_size = config.get('batch_size', 1000)
        
        # Add transcript limit configuration
        self.limit_transcripts = config.get('limit_transcripts')
        if self.limit_transcripts is not None:
            if not isinstance(self.limit_transcripts, int) or self.limit_transcripts <= 0:
                raise ValueError("limit_transcripts must be a positive integer")
            logger.info(f"Limiting transcript processing to {self.limit_transcripts} transcripts")
        
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
            return (datetime.now() - cache_time) < timedelta(seconds=self.cache_ttl)
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
                meta = {}
        
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
            logger.info(f"Using cached GTF file: {gtf_path}")
            return gtf_path

        # Download new file
        logger.info(f"Downloading GTF from {self.config['gtf_url']}")
        response = requests.get(self.config['gtf_url'], stream=True)
        total_size = int(response.headers.get('content-length', 0))
        
        with open(gtf_path, 'wb') as f, tqdm(
            desc="Downloading GTF",
            total=total_size,
            unit='iB',
            unit_scale=True
        ) as pbar:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    pbar.update(len(chunk))
        
        self._update_cache_meta(cache_key, gtf_path)
        logger.info(f"GTF file downloaded to {gtf_path}")
        return gtf_path

    def _inspect_gtf_structure(self, df: pd.DataFrame) -> None:
        """Log information about the GTF file structure."""
        logger.info(f"GTF columns: {', '.join(df.columns)}")
        logger.info(f"Feature types: {', '.join(df['feature'].unique())}")
        logger.info(f"Total entries: {len(df)}")
        logger.info(f"Transcript entries: {len(df[df['feature'] == 'transcript'])}")

    def _get_attributes_column(self, df: pd.DataFrame) -> str:
        """Find the attributes column in GTF dataframe."""
        for col_name in ['attribute', 'attributes', 'Additional attributes']:
            if col_name in df.columns:
                return col_name
        raise ValueError("Could not find attributes column in GTF file")

    def extract_alt_ids(self, row: pd.Series) -> Dict[str, Dict[str, str]]:
        """Extract alternative IDs from transcript attributes."""
        alt_transcript_ids = {}
        alt_gene_ids = {}
        
        # Extract HAVANA IDs if available
        if 'havana_transcript' in row:
            alt_transcript_ids['HAVANA'] = row.get('havana_transcript')
        
        if 'havana_gene' in row:
            alt_gene_ids['HAVANA'] = row.get('havana_gene')
        
        # Extract CCDS ID if available
        if 'ccdsid' in row:
            alt_transcript_ids['CCDS'] = row.get('ccdsid')
        
        # Extract HGNC ID if available
        if 'gene_id' in row and 'gene_name' in row:
            gene_name = row.get('gene_name')
            if gene_name:
                alt_gene_ids['HGNC'] = f"HGNC:{row.get('hgnc_id', '')}"
        
        return {
            'alt_transcript_ids': alt_transcript_ids,
            'alt_gene_ids': alt_gene_ids
        }

    def process_gtf(self, gtf_path: Path) -> pd.DataFrame:
        """Process GTF file and extract transcript data."""
        logger.info(f"Processing GTF file: {gtf_path}")
        
        # Read GTF file using gtfparse
        try:
            df = read_gtf(str(gtf_path))
            self._inspect_gtf_structure(df)
            
            # Filter to transcript level
            transcripts = df[df['feature'] == 'transcript'].copy()
            
            # Apply transcript limit if specified
            total_transcripts = len(transcripts)
            if self.limit_transcripts is not None and total_transcripts > self.limit_transcripts:
                logger.info(f"Limiting from {total_transcripts} to {self.limit_transcripts} transcripts")
                transcripts = transcripts.head(self.limit_transcripts)
            else:
                logger.info(f"Processing all {total_transcripts} transcripts")
            
            # Extract coordinates
            transcripts['coordinates'] = transcripts.apply(
                lambda row: {
                    'start': row['start'],
                    'end': row['end'],
                    'strand': 1 if row['strand'] == '+' else -1
                },
                axis=1
            )
            
            # Extract alternative IDs
            alt_ids = transcripts.apply(self.extract_alt_ids, axis=1)
            transcripts['alt_transcript_ids'] = [row['alt_transcript_ids'] for row in alt_ids]
            transcripts['alt_gene_ids'] = [row['alt_gene_ids'] for row in alt_ids]
            
            # Log summary of processed data
            logger.info(
                f"Processed GTF data:\n"
                f"- Total transcripts: {len(transcripts)}\n"
                f"- Unique genes: {transcripts['gene_id'].nunique()}"
            )
            
            return transcripts
            
        except Exception as e:
            logger.error(f"Error processing GTF file: {e}")
            raise

    def prepare_transcript_records(
        self,
        df: pd.DataFrame
    ) -> List[Tuple[str, str, str, str, str, Dict[str, Any], Dict[str, str], Dict[str, str]]]:
        """Prepare transcript records for database insertion.
        
        Randomly selects transcripts while enforcing that each non-coding gene type
        cannot exceed 4% of the total selected transcripts.
        
        Args:
            df: DataFrame containing transcript data
            
        Returns:
            List of tuples formatted for database insertion
        """
        # If no limit is set, process all transcripts
        if not self.limit_transcripts:
            logger.info("Processing all transcripts without filtering")
            return self._prepare_all_records(df)
            
        # Constants for transcript filtering
        PROTEIN_CODING_TYPE = "protein_coding"
        MAX_RATIO_PER_TYPE = 4 / 100  # Maximum 4% per non-coding gene type
        
        logger.info(f"Selecting exactly {self.limit_transcripts} transcripts with maximum {MAX_RATIO_PER_TYPE*100:.2f}% per non-coding gene type")
        
        # Shuffle all transcripts randomly
        shuffled_df = df.sample(frac=1.0, random_state=42).reset_index(drop=True)
        
        selected_indices = []
        selected_type_counts = {}  # Keep track of counts per gene type
        total_selected = 0
        
        # Process each transcript to see if it can be added
        for idx, row in tqdm(shuffled_df.iterrows(), total=len(shuffled_df), desc="Selecting transcripts"):
            if total_selected >= self.limit_transcripts:
                break
                
            gene_type = row.get('gene_type', '').lower()
            
            # Always accept protein coding genes
            if gene_type == PROTEIN_CODING_TYPE:
                selected_indices.append(idx)
                selected_type_counts[gene_type] = selected_type_counts.get(gene_type, 0) + 1
                total_selected += 1
                continue
            
            # For non-coding genes, check if adding would exceed the percentage limit
            current_count = selected_type_counts.get(gene_type, 0)
            new_total = total_selected + 1
            new_percentage = (current_count + 1) / new_total
            
            if new_percentage <= MAX_RATIO_PER_TYPE:
                selected_indices.append(idx)
                selected_type_counts[gene_type] = current_count + 1
                total_selected += 1
        
        # If we went through all transcripts and still haven't reached the limit,
        # log a warning
        if total_selected < self.limit_transcripts:
            logger.warning(
                f"Could only select {total_selected}/{self.limit_transcripts} transcripts "
                f"while maintaining the {MAX_RATIO_PER_TYPE*100:.2f}% rule per non-coding gene type."
            )
        
        # Extract the selected transcripts
        selected_df = shuffled_df.iloc[selected_indices]
        
        # Log selection counts
        logger.info(f"Selected transcript distribution ({total_selected} total):")
        for gene_type, count in sorted(selected_type_counts.items(), key=lambda x: x[1], reverse=True):
            percent = (count / total_selected) * 100
            is_protein_coding = gene_type.lower() == PROTEIN_CODING_TYPE
            status = "OK" if is_protein_coding or percent <= MAX_RATIO_PER_TYPE * 100 else "OVER LIMIT"
            logger.info(f"  - {gene_type}: {count} ({percent:.2f}%) {status}")
        
        # Format the selected records
        records = []
        for _, row in tqdm(selected_df.iterrows(), total=len(selected_df), desc="Processing selected transcripts"):
            try:
                # Clean transcript_id and gene_id by removing version if present
                transcript_id = row.get('transcript_id')
                gene_id = row.get('gene_id', '').split('.')[0] if '.' in row.get('gene_id', '') else row.get('gene_id')
                
                record = (
                    transcript_id,                          # transcript_id
                    row.get('gene_name', ''),               # gene_symbol
                    gene_id,                                # gene_id
                    row.get('gene_type', ''),               # gene_type
                    row.get('seqname', '').replace('chr', ''),  # chromosome
                    json.dumps(row.get('coordinates', {})),  # coordinates
                    json.dumps(row.get('alt_transcript_ids', {})),  # alt_transcript_ids
                    json.dumps(row.get('alt_gene_ids', {}))  # alt_gene_ids
                )
                records.append(record)
            except Exception as e:
                logger.warning(f"Error preparing record for {row.get('transcript_id', 'unknown')}: {e}")
        
        return records

    def _prepare_all_records(self, df: pd.DataFrame) -> List[Tuple]:
        """Prepare all transcript records without filtering."""
        records = []
        for _, row in tqdm(df.iterrows(), total=len(df), desc="Preparing all transcript records"):
            try:
                # Clean transcript_id and gene_id by removing version if present
                transcript_id = row.get('transcript_id')
                gene_id = row.get('gene_id', '').split('.')[0] if '.' in row.get('gene_id', '') else row.get('gene_id')
                
                record = (
                    transcript_id,                       # transcript_id
                    row.get('gene_name', ''),           # gene_symbol
                    gene_id,                            # gene_id
                    row.get('gene_type', ''),           # gene_type
                    row.get('seqname', '').replace('chr', ''),  # chromosome
                    json.dumps(row.get('coordinates', {})),      # coordinates
                    json.dumps(row.get('alt_transcript_ids', {})),  # alt_transcript_ids
                    json.dumps(row.get('alt_gene_ids', {}))      # alt_gene_ids
                )
                records.append(record)
                
            except Exception as e:
                logger.warning(f"Error preparing record for {row.get('transcript_id', 'unknown')}: {e}")
        
        logger.info(f"Prepared {len(records)} transcript records without filtering")
        return records

    def load_transcripts(self, records: List[Tuple]) -> None:
        """Load transcript records into the database."""
        if not records:
            logger.warning("No transcript records to load")
            return
            
        if not self.db_manager or not self.db_manager.cursor:
            raise RuntimeError("No database connection")
            
        try:
            logger.info(f"Loading {len(records)} transcript records into database")
            
            # Execute in batches
            execute_batch(
                self.db_manager.cursor,
                """
                INSERT INTO cancer_transcript_base (
                    transcript_id, gene_symbol, gene_id, gene_type, 
                    chromosome, coordinates, alt_transcript_ids, alt_gene_ids
                ) 
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
                ON CONFLICT (transcript_id) DO UPDATE SET
                    gene_symbol = EXCLUDED.gene_symbol,
                    gene_id = EXCLUDED.gene_id,
                    gene_type = EXCLUDED.gene_type,
                    chromosome = EXCLUDED.chromosome,
                    coordinates = EXCLUDED.coordinates,
                    alt_transcript_ids = EXCLUDED.alt_transcript_ids,
                    alt_gene_ids = EXCLUDED.alt_gene_ids
                """,
                records,
                page_size=self.batch_size
            )
            
            # Commit the transaction - safely check for connection
            if self.db_manager.conn:
                self.db_manager.conn.commit()
                logger.info("Transcript loading completed successfully")
            else:
                logger.warning("Could not commit transaction - no active connection")
            
        except Exception as e:
            logger.error(f"Error loading transcripts: {e}")
            # Safely roll back if we have a connection
            if self.db_manager.conn:
                self.db_manager.conn.rollback()
            raise

    def validate_data(self, df: pd.DataFrame) -> bool:
        """Validate the transcript dataframe."""
        # Validate required columns
        required_columns = ['transcript_id', 'gene_id', 'gene_type', 'seqname', 'start', 'end', 'strand']
        for col in required_columns:
            if col not in df.columns:
                logger.error(f"Missing required column: {col}")
                return False
        
        # Validate transcript IDs (non-empty)
        if df['transcript_id'].isnull().any() or (df['transcript_id'] == '').any():
            logger.error("Found null or empty transcript IDs")
            return False
        
        # Count how many transcripts have alternative IDs
        with_alt_transcript_ids = sum(1 for ids in df['alt_transcript_ids'] if ids)
        with_alt_gene_ids = sum(1 for ids in df['alt_gene_ids'] if ids)
        
        logger.info(f"Transcripts with alternative transcript IDs: {with_alt_transcript_ids}/{len(df)}")
        logger.info(f"Transcripts with alternative gene IDs: {with_alt_gene_ids}/{len(df)}")
        
        return True

    def run(self) -> None:
        """Run the complete transcript processing pipeline."""
        try:
            # Download GTF file
            gtf_path = self.download_gtf()
            
            # Process GTF data
            df = self.process_gtf(gtf_path)
            
            # Validate processed data
            if not self.validate_data(df):
                logger.error("Data validation failed")
                return
            
            # Prepare records for database insertion
            records = self.prepare_transcript_records(df)
            
            # Load records into database
            self.load_transcripts(records)
            
            # Log completion statistics
            if self.db_manager.cursor:
                self.db_manager.cursor.execute("SELECT COUNT(*) FROM cancer_transcript_base")
                result = self.db_manager.cursor.fetchone()
                total_count = result[0] if result else 0
                logger.info(f"Total transcripts in database: {total_count}")
                
                # Log if a limit was applied
                if self.limit_transcripts is not None:
                    logger.info(
                        f"Transcript limit was set to {self.limit_transcripts}. "
                        f"Final count in database: {total_count}"
                    )
            
            logger.info("Transcript processing pipeline completed successfully")
            
        except Exception as e:
            logger.error(f"Transcript processing pipeline failed: {e}")
            raise

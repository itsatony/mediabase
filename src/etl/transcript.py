"""Transcript processing module for Cancer Transcriptome Base.

This module handles downloading, parsing, and loading gene transcript data from
Gencode GTF files into the database. It provides the foundation for all other
data enrichment in the pipeline.
"""

import logging
import json
import re
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set

import gtfparse
import pandas as pd
import requests
from tqdm import tqdm
from psycopg2.extras import execute_batch

from .base_processor import BaseProcessor, DownloadError, ProcessingError, DatabaseError
from ..db.database import get_db_manager

class TranscriptProcessor(BaseProcessor):
    """Process gene transcript data from GTF files.
    
    Handles downloading, parsing and loading of transcript data into the
    cancer_transcript_base table in the database.
    """
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize transcript processor with configuration.
        
        Args:
            config: Configuration dictionary containing all settings
                   including nested db configuration
        """
        super().__init__(config)
        
        self.gtf_url = config.get('gencode_gtf_url')
        if not self.gtf_url:
            raise ValueError("GTF URL not configured")
            
        # File paths derived from cache directory
        self.transcript_dir = self.cache_dir / 'transcripts'
        self.transcript_dir.mkdir(exist_ok=True)
        
        # Processing configuration
        self.limit_transcripts = config.get('limit_transcripts')
        if self.limit_transcripts is not None:
            try:
                self.limit_transcripts = int(self.limit_transcripts)
                self.logger.info(f"Processing limited to {self.limit_transcripts} transcripts")
            except (ValueError, TypeError):
                self.logger.warning(f"Invalid limit_transcripts value: {self.limit_transcripts}, using all transcripts")
                self.limit_transcripts = None
    
    def download_gtf(self) -> Path:
        """Download GTF file with caching.
        
        Returns:
            Path to the GTF file
            
        Raises:
            DownloadError: If download fails
        """
        if not self.gtf_url:
            raise DownloadError("GTF URL not configured")
        
        try:
            # Use the BaseProcessor download method
            return self.download_file(
                url=self.gtf_url,  # Now we've verified it's not None
                file_path=self.transcript_dir / f"gencode.gtf.gz"
            )
        except Exception as e:
            raise DownloadError(f"Failed to download GTF file: {e}")
    
    def parse_gtf(self, gtf_path: Path) -> pd.DataFrame:
        """Parse GTF file and extract transcript data.
        
        Args:
            gtf_path: Path to the GTF file
            
        Returns:
            DataFrame containing transcript data
            
        Raises:
            ProcessingError: If GTF parsing fails
        """
        try:
            self.logger.info(f"Parsing GTF file: {gtf_path}")
            df = gtfparse.read_gtf(gtf_path)
            
            # Filter to transcript entries only
            transcripts = df[df['feature'] == 'transcript'].copy()
            
            # Parse coordinates into structured format
            transcripts['coordinates'] = transcripts.apply(
                lambda row: {
                    'start': int(row['start']),
                    'end': int(row['end']),
                    'strand': 1 if row['strand'] == '+' else -1
                },
                axis=1
            )
            
            # Normalize gene_id by stripping version number if present
            transcripts['gene_id'] = transcripts['gene_id'].str.split('.').str[0]
            
            # Apply limit if specified
            if self.limit_transcripts:
                self.logger.info(f"Limiting to {self.limit_transcripts} transcripts")
                transcripts = transcripts.head(self.limit_transcripts)
            
            self.logger.info(f"Parsed {len(transcripts)} transcripts")
            return transcripts
            
        except Exception as e:
            raise ProcessingError(f"Failed to parse GTF file: {e}")
    
    def load_transcripts(self, transcripts: pd.DataFrame) -> None:
        """Load transcript data into database.
        
        Args:
            transcripts: DataFrame containing transcript data
            
        Raises:
            DatabaseError: If database operations fail
        """
        if not self.ensure_connection():
            raise DatabaseError("Database connection failed")
        
        try:
            # Prepare batches for insertion
            self.logger.info("Preparing transcript data for database insertion")
            
            transcript_data = []
            for _, row in transcripts.iterrows():
                transcript_id = row.get('transcript_id', '')
                gene_id = row.get('gene_id', '')
                gene_name = row.get('gene_name', '')
                gene_type = row.get('gene_type', '')
                chromosome = row.get('seqname', '')
                coordinates = row.get('coordinates', {})
                
                # Build default JSONB fields
                expression_freq = json.dumps({'high': [], 'low': []})
                
                # Extract alt_transcript_ids
                alt_transcript_ids = {}
                for attr in ['ccdsid', 'havana_transcript']:
                    if attr in row and row[attr]:
                        key = 'CCDS' if attr == 'ccdsid' else 'HAVANA'
                        alt_transcript_ids[key] = row[attr]
                
                # Extract alt_gene_ids
                alt_gene_ids = {}
                for attr in ['havana_gene', 'hgnc_id']:
                    if attr in row and row[attr]:
                        key = 'HAVANA' if attr == 'havana_gene' else 'HGNC'
                        alt_gene_ids[key] = row[attr]
                
                # Add to batch
                transcript_data.append((
                    transcript_id,
                    gene_name,
                    gene_id,
                    gene_type,
                    chromosome,
                    json.dumps(coordinates),
                    expression_freq,
                    json.dumps(alt_transcript_ids),
                    json.dumps(alt_gene_ids)
                ))
            
            # Use BaseProcessor execute_batch method
            self.logger.info(f"Loading {len(transcript_data)} transcripts into database")
            self.execute_batch(
                """
                INSERT INTO cancer_transcript_base (
                    transcript_id, gene_symbol, gene_id, gene_type, 
                    chromosome, coordinates, expression_freq,
                    alt_transcript_ids, alt_gene_ids
                ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb)
                ON CONFLICT (transcript_id) DO UPDATE SET
                    gene_symbol = EXCLUDED.gene_symbol,
                    gene_id = EXCLUDED.gene_id,
                    gene_type = EXCLUDED.gene_type,
                    chromosome = EXCLUDED.chromosome,
                    coordinates = EXCLUDED.coordinates,
                    alt_transcript_ids = EXCLUDED.alt_transcript_ids,
                    alt_gene_ids = EXCLUDED.alt_gene_ids
                """, 
                transcript_data
            )
            
            self.logger.info("Transcript data loaded successfully")
            
        except Exception as e:
            raise DatabaseError(f"Failed to load transcripts: {e}")
    
    def run(self) -> None:
        """Run the full transcript processing pipeline.
        
        Steps:
        1. Download GTF file
        2. Parse transcripts
        3. Load into database
        
        Raises:
            various ETLError subclasses based on failure point
        """
        try:
            self.logger.info("Starting transcript processing pipeline")
            
            # Download GTF
            gtf_path = self.download_gtf()
            
            # Parse transcripts
            transcripts = self.parse_gtf(gtf_path)
            
            # Load into database
            self.load_transcripts(transcripts)
            
            self.logger.info("Transcript processing completed successfully")
            
        except Exception as e:
            self.logger.error(f"Transcript processing failed: {e}")
            raise

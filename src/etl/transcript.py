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
            
            # Filter to transcript entries only and make an explicit copy
            transcripts = df[df['feature'] == 'transcript'].copy()
            
            # Parse coordinates into structured format
            transcripts.loc[:, 'coordinates'] = transcripts.apply(
                lambda row: {
                    'start': int(row['start']),
                    'end': int(row['end']),
                    'strand': 1 if row['strand'] == '+' else -1
                },
                axis=1
            )
            
            # Store versioned IDs before normalizing for joining
            transcripts.loc[:, 'gene_id_versioned'] = transcripts['gene_id'].copy()
            transcripts.loc[:, 'transcript_id_versioned'] = transcripts['transcript_id'].copy()
            
            # Normalize gene_id and transcript_id by stripping version numbers for joining
            transcripts.loc[:, 'gene_id'] = transcripts['gene_id'].str.split('.').str[0]
            transcripts.loc[:, 'transcript_id'] = transcripts['transcript_id'].str.split('.').str[0]
            
            # Initialize transcript type counter
            selected_transcript_types = {'protein_coding': 0}
            selected_transcripts = []
            
            # Apply limit if specified
            if self.limit_transcripts:
                self.logger.info(f"Limiting to {self.limit_transcripts} transcripts")
                max_per_type = int(0.05 * self.limit_transcripts)
                # if we are limited, we want to make sure that the small samplesize still gives us enough diversity of gene_types with a focus on protein_coding genes
                # our max shares are 5% of selected transcripts can be any 1 type of non-protein_coding gene. meaning 5% could lcRNA, another 5% could me miRNA, etc.
                # this is a bit of a hack, but we don't want to limit the number of protein_coding genes
                # what we will do is:
                # - establish a loop to randomly pick 1 transcript from all transcripts
                # - check if our "pool" for the picked transcript is below max and add the picked transcript if it is (or if it is protein_coding)
                # - if it is not, we will randomly pick another transcript
                # - we will repeat this until we have our limit
                total_selected = 0
                for _ in range(self.limit_transcripts):
                    while True:
                        # Randomly select a transcript
                        selected_transcript = transcripts.sample(1).iloc[0]
                        
                        # Check if the selected transcript is protein_coding or if we have space in our pool
                        if selected_transcript['gene_type'] == 'protein_coding':
                            selected_transcripts.append(selected_transcript)
                            selected_transcript_types[selected_transcript['gene_type']] += 1
                            total_selected += 1
                            # Check if we have reached the limit
                            if total_selected >= self.limit_transcripts:
                                break
                        else:
                            # Check if we have space in our pool for this non-protein_coding transcript
                            if selected_transcript['gene_type'] not in selected_transcript_types:
                                selected_transcript_types[selected_transcript['gene_type']] = 0
                            elif selected_transcript_types[selected_transcript['gene_type']] >= max_per_type:
                                continue
                            # Add the selected transcript to the pool
                            selected_transcripts.append(selected_transcript)
                            selected_transcript_types[selected_transcript['gene_type']] += 1
                            total_selected += 1
                            # Check if we have reached the limit
                            if total_selected >= self.limit_transcripts:
                                break
                transcripts = pd.DataFrame(selected_transcripts)                
                # Log transcript type statistics
                self.logger.info(f"Parsed {len(transcripts)} transcripts and limited to {self.limit_transcripts}")
                self.logger.info("Transcript type distribution:")
                for gene_type, count in selected_transcript_types.items():
                    self.logger.info(f"  {gene_type}: {count}")
            else:
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
                
                # Enhanced ID extraction - Extract ALL available GTF attributes
                alt_transcript_ids = {}
                alt_gene_ids = {}
                transcript_metadata = {}
                
                # Comprehensive GTF attribute mapping
                transcript_id_attrs = {
                    'ccdsid': 'CCDS',
                    'havana_transcript': 'HAVANA', 
                    'protein_id': 'RefSeq_protein',
                    'transcript_name': 'transcript_name'
                }
                
                gene_id_attrs = {
                    'havana_gene': 'HAVANA',
                    'hgnc_id': 'HGNC'
                }
                
                quality_attrs = {
                    'transcript_support_level': 'TSL',
                    'gene_version': 'gene_version',
                    'transcript_version': 'transcript_version',
                    'level': 'annotation_level',
                    'tag': 'annotation_tags'
                }
                
                # Extract transcript IDs
                for attr, key in transcript_id_attrs.items():
                    if attr in row and row[attr] and str(row[attr]) != 'nan':
                        alt_transcript_ids[key] = str(row[attr])
                
                # Extract gene IDs 
                for attr, key in gene_id_attrs.items():
                    if attr in row and row[attr] and str(row[attr]) != 'nan':
                        alt_gene_ids[key] = str(row[attr])
                
                # Extract quality/annotation metadata
                for attr, key in quality_attrs.items():
                    if attr in row and row[attr] and str(row[attr]) != 'nan':
                        transcript_metadata[key] = str(row[attr])
                
                # Add versioned IDs to metadata for reference
                if 'gene_id_versioned' in row and str(row['gene_id_versioned']) != 'nan':
                    transcript_metadata['gene_id_versioned'] = str(row['gene_id_versioned'])
                if 'transcript_id_versioned' in row and str(row['transcript_id_versioned']) != 'nan':
                    transcript_metadata['transcript_id_versioned'] = str(row['transcript_id_versioned'])
                
                # Add to batch with enhanced metadata
                transcript_data.append((
                    transcript_id,
                    gene_name,
                    gene_id,
                    gene_type,
                    chromosome,
                    json.dumps(coordinates),
                    expression_freq,
                    json.dumps(alt_transcript_ids),
                    json.dumps(alt_gene_ids),
                    json.dumps(transcript_metadata)  # Store quality/annotation data
                ))
            
            # Use BaseProcessor execute_batch method
            self.logger.info(f"Loading {len(transcript_data)} transcripts into database")
            self.execute_batch(
                """
                INSERT INTO cancer_transcript_base (
                    transcript_id, gene_symbol, gene_id, gene_type, 
                    chromosome, coordinates, expression_freq,
                    alt_transcript_ids, alt_gene_ids, features
                ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb)
                ON CONFLICT (transcript_id) DO UPDATE SET
                    gene_symbol = EXCLUDED.gene_symbol,
                    gene_id = EXCLUDED.gene_id,
                    gene_type = EXCLUDED.gene_type,
                    chromosome = EXCLUDED.chromosome,
                    coordinates = EXCLUDED.coordinates,
                    alt_transcript_ids = EXCLUDED.alt_transcript_ids,
                    alt_gene_ids = EXCLUDED.alt_gene_ids,
                    features = EXCLUDED.features
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

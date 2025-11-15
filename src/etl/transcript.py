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
        """Load transcript data into normalized database schema.

        Args:
            transcripts: DataFrame containing transcript data

        Raises:
            DatabaseError: If database operations fail
        """
        if not self.ensure_connection():
            raise DatabaseError("Database connection failed")

        try:
            self.logger.info("Preparing transcript data for normalized schema insertion")

            # Separate gene and transcript data for normalized schema
            gene_data = []
            transcript_data = []
            cross_ref_data = []

            # Track processed genes to avoid duplicates
            processed_genes = set()

            for _, row in transcripts.iterrows():
                transcript_id = row.get('transcript_id', '')
                gene_id = row.get('gene_id', '')
                gene_symbol = row.get('gene_name', '')  # This is actually gene_symbol in GTF
                gene_type = row.get('gene_type', '')
                chromosome = row.get('seqname', '')
                coordinates = row.get('coordinates', {})

                # Extract coordinate details
                start_pos = coordinates.get('start') if coordinates else None
                end_pos = coordinates.get('end') if coordinates else None
                strand = coordinates.get('strand') if coordinates else None

                # Process gene data (deduplicated)
                if gene_id not in processed_genes:
                    gene_data.append((
                        gene_id,
                        gene_symbol,
                        gene_symbol,  # gene_name = gene_symbol for now
                        gene_type,
                        chromosome,
                        start_pos,
                        end_pos,
                        strand,
                        'Extracted from GENCODE GTF'
                    ))
                    processed_genes.add(gene_id)

                    # Add cross-references for genes
                    if 'havana_gene' in row and row['havana_gene'] and str(row['havana_gene']) != 'nan':
                        cross_ref_data.append((gene_id, 'HAVANA', str(row['havana_gene'])))
                    if 'hgnc_id' in row and row['hgnc_id'] and str(row['hgnc_id']) != 'nan':
                        cross_ref_data.append((gene_id, 'HGNC', str(row['hgnc_id'])))

                # Process transcript data
                transcript_support_level = 1  # Default
                if 'transcript_support_level' in row and str(row['transcript_support_level']) != 'nan':
                    try:
                        transcript_support_level = int(row['transcript_support_level'])
                    except:
                        transcript_support_level = 1

                transcript_data.append((
                    transcript_id,
                    gene_id,
                    transcript_id,  # transcript_name = transcript_id for now
                    gene_type,  # Use gene_type as transcript_type
                    transcript_support_level,
                    1.0  # Default expression_fold_change
                ))

            # Insert genes first
            self.logger.info(f"Loading {len(gene_data)} genes into normalized schema")
            if gene_data:
                self.execute_batch(
                    """
                    INSERT INTO genes (gene_id, gene_symbol, gene_name, gene_type, chromosome,
                                     start_position, end_position, strand, description)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (gene_id) DO UPDATE SET
                        gene_symbol = EXCLUDED.gene_symbol,
                        gene_name = EXCLUDED.gene_name,
                        gene_type = EXCLUDED.gene_type,
                        chromosome = EXCLUDED.chromosome,
                        start_position = EXCLUDED.start_position,
                        end_position = EXCLUDED.end_position,
                        strand = EXCLUDED.strand,
                        description = EXCLUDED.description
                    """,
                    gene_data
                )

            # Insert transcripts
            self.logger.info(f"Loading {len(transcript_data)} transcripts into normalized schema")
            if transcript_data:
                self.execute_batch(
                    """
                    INSERT INTO transcripts (transcript_id, gene_id, transcript_name, transcript_type,
                                           transcript_support_level, expression_fold_change)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (transcript_id) DO UPDATE SET
                        gene_id = EXCLUDED.gene_id,
                        transcript_name = EXCLUDED.transcript_name,
                        transcript_type = EXCLUDED.transcript_type,
                        transcript_support_level = EXCLUDED.transcript_support_level,
                        expression_fold_change = EXCLUDED.expression_fold_change
                    """,
                    transcript_data
                )

            # Insert cross-references
            self.logger.info(f"Loading {len(cross_ref_data)} cross-references")
            if cross_ref_data:
                self.execute_batch(
                    """
                    INSERT INTO gene_cross_references (gene_id, external_db, external_id)
                    VALUES (%s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    cross_ref_data
                )

            self.logger.info("Transcript data loaded successfully into normalized schema")

            # Update legacy table for backwards compatibility (if it exists)
            try:
                self.db_manager.cursor.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'cancer_transcript_base'")
                if self.db_manager.cursor.fetchone():
                    self.logger.info("Updating legacy cancer_transcript_base table for backwards compatibility")

                    legacy_data = []
                    for _, row in transcripts.iterrows():
                        transcript_id = row.get('transcript_id', '')
                        gene_symbol = row.get('gene_name', '')
                        gene_id = row.get('gene_id', '')
                        gene_type = row.get('gene_type', '')
                        chromosome = row.get('seqname', '')
                        coordinates = row.get('coordinates', {})

                        # Build minimal legacy record
                        legacy_data.append((
                            transcript_id,
                            gene_symbol,
                            gene_id,
                            gene_type,
                            chromosome,
                            json.dumps(coordinates),
                            json.dumps({'high': [], 'low': []}),  # expression_freq
                            json.dumps({}),  # alt_transcript_ids
                            json.dumps({}),  # alt_gene_ids
                            json.dumps({})   # features
                        ))

                    if legacy_data:
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
                                coordinates = EXCLUDED.coordinates
                            """,
                            legacy_data
                        )
            except Exception as e:
                self.logger.warning(f"Failed to update legacy table (this is normal after migration): {e}")

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

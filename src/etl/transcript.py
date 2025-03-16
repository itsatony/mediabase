"""Transcript ETL module for processing gene transcript data."""

# Standard library imports
from pathlib import Path
from typing import Dict, List, DefaultDict, Any, Tuple
from datetime import datetime, timedelta
import random
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
        self.cache_ttl = int(config.get('cache_ttl', 86400*7))  # 24 hours * 7 default cache
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
            total_transcripts = len(transcripts)
            
            # Record the total count but DON'T limit yet
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
        
        Intelligently selects transcripts while ensuring gene type diversity,
        with a preference for protein-coding genes.
        
        Args:
            df: DataFrame containing transcript data
            
        Returns:
            List of tuples formatted for database insertion
        """
        MAX_PERCENT_NON_CODING = 0.04  # 4% limit for each non-coding gene type
        TARGET_COUNT = self.config.get('limit_transcripts', len(df))  # Target number of records to return
        PROTEIN_CODING_TARGET = int(TARGET_COUNT * 0.70)  # 70% protein coding genes target
        
        # Initialize tracking variables
        records = []
        gene_type_counts = DefaultDict(int)
        processed_indices = set()
        
        # Progress tracking counters
        picked_count = 0
        failed_rules_count = 0
        failed_assembly_count = 0
        
        # First, separate protein coding and non-protein coding transcripts
        protein_coding_indices = []
        other_type_indices = []
        
        # Categorize all indices by gene_type
        gene_types_by_index = {}
        for idx in df.index:
            gene_type = df.loc[idx].get('gene_type', '')
            gene_types_by_index[idx] = gene_type
            if gene_type == 'protein_coding':
                protein_coding_indices.append(idx)
            else:
                other_type_indices.append(idx)
        
        # Shuffle both lists to randomize selection
        random.shuffle(protein_coding_indices)
        random.shuffle(other_type_indices)
        
        # Create progress bar
        pbar = tqdm(total=TARGET_COUNT, desc="Preparing transcripts")
        
        # First, take protein coding genes up to PROTEIN_CODING_TARGET or available amount
        available_protein_coding = min(len(protein_coding_indices), PROTEIN_CODING_TARGET)
        pc_to_process = protein_coding_indices[:available_protein_coding]
        
        # Then distribute remaining slots across non-coding gene types
        remaining_slots = TARGET_COUNT - available_protein_coding
        non_coding_types = set(gene_types_by_index[idx] for idx in other_type_indices)
        
        # Initialize record creation process
        indices_to_process = pc_to_process + other_type_indices
        current_index = 0
        
        # Process records until we reach target count or run out of candidates
        while len(records) < TARGET_COUNT and current_index < len(indices_to_process):
            idx = indices_to_process[current_index]
            current_index += 1
            picked_count += 1
            
            if idx in processed_indices:
                continue
                
            processed_indices.add(idx)
            
            # Get the record and its gene type
            row = df.loc[idx]
            gene_type = row.get('gene_type', '')
            
            # Dynamic gene type percentage calculation
            current_type_count = gene_type_counts[gene_type]
            current_total = len(records)
            
            # Different rules for protein coding vs non-protein coding
            if str(gene_type).strip() == 'protein_coding':
                # Accept if we haven't reached the protein coding target
                if gene_type_counts[gene_type] < PROTEIN_CODING_TARGET:
                    add_record = True
                else:
                    add_record = False
                    failed_rules_count += 1
            else:
                # For non-coding genes, ensure no type exceeds MAX_PERCENT_NON_CODING of total
                if current_total > 0:
                    type_percent = current_type_count / current_total
                    add_record = type_percent < MAX_PERCENT_NON_CODING
                else:
                    # For first records, always accept to bootstrap the process
                    add_record = True
                    
                if not add_record:
                    failed_rules_count += 1
                    
            # Create and add the record if rules passed
            if add_record:
                try:
                    # Clean transcript_id and gene_id by removing version if present
                    transcript_id = row.get('transcript_id')
                    if transcript_id is None or transcript_id == '':
                        failed_assembly_count += 1
                        continue
                        
                    gene_id = row.get('gene_id', '')
                    if gene_id:
                        gene_id = gene_id.split('.')[0] if '.' in gene_id else gene_id
                    
                    record = (
                        transcript_id,                          # transcript_id
                        row.get('gene_name', ''),               # gene_symbol
                        gene_id,                                # gene_id
                        gene_type,                              # gene_type
                        row.get('seqname', '').replace('chr', ''),  # chromosome
                        json.dumps(row.get('coordinates', {})),  # coordinates
                        json.dumps(row.get('alt_transcript_ids', {})),  # alt_transcript_ids
                        json.dumps(row.get('alt_gene_ids', {}))  # alt_gene_ids
                    )
                    # Successfully created record, add it and update counter
                    records.append(record)
                    gene_type_counts[gene_type] += 1
                    
                    # Update progress bar
                    pbar.update(1)
                    
                except Exception as e:
                    failed_assembly_count += 1
                    logger.debug(f"Failed to assemble record: {e}")
                    continue
            
            # Update progress description
            pbar.set_description(
                f"Picked: {picked_count}/{len(df.index)} | "
                f"Added: {len(records)}/{TARGET_COUNT} | "
                f"Failed rules: {failed_rules_count} | "
                f"Failed assembly: {failed_assembly_count}"
            )
            
        # Close progress bar
        pbar.close()
        
        # Log final statistics
        logger.info(
            f"Transcript record preparation complete:\n"
            f"- Total picked: {picked_count}/{len(df.index)}\n"
            f"- Successfully added: {len(records)}/{TARGET_COUNT}\n"
            f"- Failed rule checks: {failed_rules_count}\n"
            f"- Failed record assembly: {failed_assembly_count}"
        )
        
        # Log gene type distribution for diagnosis
        gene_type_distribution = dict(gene_type_counts)
        logger.info(f"Gene type distribution in selected records: {gene_type_distribution}")
        
        if len(records) < TARGET_COUNT:
            logger.warning(
                f"Only {len(records)} records were prepared, which is less than the target of {TARGET_COUNT}. "
                f"This could be due to restrictive filtering or issues with the source data."
            )
            
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

    def update_transcript_ids(self, transcript_id_mappings: Dict[str, Dict[str, Any]]) -> None:
        """Update transcript IDs in the database."""
        
        try:
            # Process in batches
            updates = []
            processed = 0
            
            for transcript_id, mappings in transcript_id_mappings.items():
                # Prepare alt_ids dictionary
                alt_ids = {}
                
                # Add RefSeq transcript IDs if available
                if 'refseq_transcript_ids' in mappings and mappings['refseq_transcript_ids']:
                    alt_ids['RefSeq'] = mappings['refseq_transcript_ids']
                
                # Add any other alternative IDs from mappings
                if 'entrez_transcript_ids' in mappings:
                    alt_ids['Entrez'] = mappings['entrez_transcript_ids']
                
                # Store RefSeq IDs separately to update the refseq_ids array field
                refseq_ids = None
                if 'refseq_transcript_ids' in mappings and mappings['refseq_transcript_ids']:
                    # Ensure we have a clean list of strings
                    refseq_ids = [str(r).strip() for r in mappings['refseq_transcript_ids'] if r]
                    refseq_ids = list(set(filter(None, refseq_ids)))  # Remove duplicates and empty strings
                
                # Add to updates batch - now with proper array handling
                updates.append((
                    json.dumps(alt_ids),
                    refseq_ids,  # This will be cast to text[] by Postgres
                    transcript_id
                ))
                
                if len(updates) >= self.batch_size:
                    execute_batch(
                        self.db_manager.cursor,
                        """
                        UPDATE cancer_transcript_base
                        SET 
                            alt_transcript_ids = alt_transcript_ids || %s::jsonb,
                            refseq_ids = CASE 
                                WHEN %s IS NOT NULL THEN %s::text[]  -- Explicit cast to text array
                                ELSE refseq_ids 
                            END
                        WHERE transcript_id = %s
                        """,
                        [(json_data, ids, ids, t_id) for json_data, ids, t_id in updates],
                        page_size=self.batch_size
                    )
                    updates = []
                    processed += self.batch_size
            
            # Process remaining updates
            if updates:
                execute_batch(
                    self.db_manager.cursor,
                    """
                    UPDATE cancer_transcript_base
                    SET 
                        alt_transcript_ids = alt_transcript_ids || %s::jsonb,
                        refseq_ids = CASE 
                            WHEN %s IS NOT NULL THEN %s::text[]  -- Explicit cast to text array
                            ELSE refseq_ids 
                        END
                    WHERE transcript_id = %s
                    """,
                    [(json_data, ids, ids, t_id) for json_data, ids, t_id in updates],
                    page_size=self.batch_size
                )
                processed += len(updates)
            
            # Commit the transaction - safely check for connection
            if self.db_manager.conn:
                self.db_manager.conn.commit()
                logger.info(f"Transcript ID update completed successfully, processed {processed} records")
            else:
                logger.warning("Could not commit transaction - no active connection")
            
        except Exception as e:
            logger.error(f"Error updating transcript IDs: {e}")
            # Safely roll back if we have a connection
            if self.db_manager.conn:
                self.db_manager.conn.rollback()
            raise

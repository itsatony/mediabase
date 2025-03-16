"""ID enrichment module for Cancer Transcriptome Base.

This module maps different database identifiers to each transcript/gene in the database,
enhancing the ability to match and integrate data from various sources.
"""

import logging
import gzip
import json
import os
from pathlib import Path
from typing import Dict, List, Set, Any, Optional, Tuple
import requests
from tqdm import tqdm
import pandas as pd
import hashlib
from datetime import datetime, timedelta
from psycopg2.extras import execute_batch

from ..db.database import get_db_manager

logger = logging.getLogger(__name__)

# Constants
DEFAULT_CACHE_TTL = 86400  # 24 hours
DEFAULT_BATCH_SIZE = 1000

class IDEnrichmentProcessor:
    """Process and enrich transcript records with external database identifiers."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize ID enrichment processor with configuration.
        
        Args:
            config: Configuration dictionary containing:
                - cache_dir: Directory to cache downloaded mapping files
                - batch_size: Size of batches for database operations
                - uniprot_mapping_url: URL for UniProt ID mapping service
                - ncbi_gene_info_url: URL for NCBI gene info file
                - hgnc_complete_set_url: URL for HGNC complete set
        """
        self.config = config
        self.cache_dir = Path(config.get('cache_dir', '/tmp/mediabase/cache')) / 'id_mapping'
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.batch_size = config.get('batch_size', DEFAULT_BATCH_SIZE)
        self.cache_ttl = config.get('cache_ttl', DEFAULT_CACHE_TTL)
        self.force_download = config.get('force_download', False)
        
        # ID mapping source URLs with defaults
        self.ncbi_gene_info_url = config.get(
            'ncbi_gene_info_url',
            'https://ftp.ncbi.nlm.nih.gov/gene/DATA/gene_info.gz'
        )
        self.hgnc_complete_set_url = config.get(
            'hgnc_complete_set_url',
            'https://ftp.ebi.ac.uk/pub/databases/genenames/hgnc/tsv/hgnc_complete_set.txt'
        )
        self.uniprot_idmapping_selected_url = config.get(
            'uniprot_idmapping_selected_url',
            'https://ftp.uniprot.org/pub/databases/uniprot/current_release/knowledgebase/idmapping/idmapping_selected.tab.gz'
        )
        
        self.db_manager = get_db_manager(config)
        
    def _get_cache_key(self, url: str) -> str:
        """Generate a cache key from URL."""
        return hashlib.sha256(url.encode()).hexdigest()
        
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cache is still valid for a given cache key."""
        meta_path = self.cache_dir / "meta.json"
        if self.force_download:
            return False
        if not meta_path.exists():
            return False
        try:
            with open(meta_path, 'r') as f:
                meta = json.load(f)
            if cache_key not in meta:
                return False
            cache_time = datetime.fromisoformat(meta[cache_key]['timestamp'])
            return (datetime.now() - cache_time) < timedelta(seconds=self.cache_ttl)
        except (json.JSONDecodeError, KeyError, ValueError):
            return False
            
    def _update_cache_meta(self, cache_key: str, file_path: Path) -> None:
        """Update cache metadata."""
        meta_path = self.cache_dir / "meta.json"
        meta = {}
        if meta_path.exists():
            try:
                with open(meta_path, 'r') as f:
                    meta = json.load(f)
            except json.JSONDecodeError:
                pass

        meta[cache_key] = {
            'timestamp': datetime.now().isoformat(),
            'file_path': str(file_path)
        }

        with open(meta_path, 'w') as f:
            json.dump(meta, f)

    def download_ncbi_gene_info(self) -> Path:
        """Download NCBI Gene Info file if not in cache."""
        cache_key = self._get_cache_key(self.ncbi_gene_info_url)
        file_path = self.cache_dir / f"ncbi_gene_info_{cache_key}.gz"
        
        if file_path.exists() and self._is_cache_valid(cache_key):
            logger.info(f"Using cached NCBI gene info file: {file_path}")
            return file_path
            
        logger.info(f"Downloading NCBI gene info from {self.ncbi_gene_info_url}")
        response = requests.get(self.ncbi_gene_info_url, stream=True)
        total_size = int(response.headers.get('content-length', 0))
        
        with open(file_path, 'wb') as f, tqdm(
            desc="Downloading NCBI gene info",
            total=total_size,
            unit='iB',
            unit_scale=True
        ) as pbar:
            for data in response.iter_content(chunk_size=8192):
                size = f.write(data)
                pbar.update(size)
                
        self._update_cache_meta(cache_key, file_path)
        return file_path
            
    def download_hgnc_complete_set(self) -> Path:
        """Download HGNC complete set file if not in cache."""
        cache_key = self._get_cache_key(self.hgnc_complete_set_url)
        file_path = self.cache_dir / f"hgnc_complete_set_{cache_key}.txt"
        
        if file_path.exists() and self._is_cache_valid(cache_key):
            logger.info(f"Using cached HGNC complete set file: {file_path}")
            return file_path
            
        logger.info(f"Downloading HGNC complete set from {self.hgnc_complete_set_url}")
        response = requests.get(self.hgnc_complete_set_url, stream=True)
        total_size = int(response.headers.get('content-length', 0))
        
        with open(file_path, 'wb') as f, tqdm(
            desc="Downloading HGNC complete set",
            total=total_size,
            unit='iB',
            unit_scale=True
        ) as pbar:
            for data in response.iter_content(chunk_size=8192):
                size = f.write(data)
                pbar.update(size)
                
        self._update_cache_meta(cache_key, file_path)
        return file_path
    
    def download_uniprot_idmapping(self) -> Path:
        """Download UniProt idmapping_selected file if not in cache."""
        # We use the selected mapping file which is much smaller than the full mapping
        cache_key = self._get_cache_key(self.uniprot_idmapping_selected_url)
        file_path = self.cache_dir / f"uniprot_idmapping_selected_{cache_key}.tab.gz"
        
        if file_path.exists() and self._is_cache_valid(cache_key):
            logger.info(f"Using cached UniProt idmapping file: {file_path}")
            return file_path
            
        logger.info(f"Downloading UniProt idmapping from {self.uniprot_idmapping_selected_url}")
        response = requests.get(self.uniprot_idmapping_selected_url, stream=True)
        total_size = int(response.headers.get('content-length', 0))
        
        with open(file_path, 'wb') as f, tqdm(
            desc="Downloading UniProt idmapping",
            total=total_size,
            unit='iB',
            unit_scale=True
        ) as pbar:
            for data in response.iter_content(chunk_size=8192):
                size = f.write(data)
                pbar.update(size)
                
        self._update_cache_meta(cache_key, file_path)
        return file_path
    
    def query_uniprot_mapping_service(self, gene_symbols: List[str]) -> Dict[str, Dict[str, str]]:
        """Query UniProt ID mapping service for gene symbols."""
        # Implementation will be added in next iteration
        return {}  # Return empty dict to satisfy type checking
    
    def process_ncbi_gene_info(self, file_path: Path) -> Dict[str, Dict[str, Any]]:
        """Process NCBI Gene Info file to map gene IDs.
        
        Args:
            file_path: Path to the gene_info.gz file
            
        Returns:
            Dictionary mapping gene symbols to various IDs
        """
        logger.info("Processing NCBI gene info file...")
        
        # Define column positions in NCBI gene_info file
        NCBI_TAX_ID = 0
        NCBI_GENE_ID = 1
        NCBI_SYMBOL = 2
        NCBI_SYNONYMS = 4
        NCBI_DB_XREFS = 5
        
        gene_mappings: Dict[str, Dict[str, Any]] = {}
        
        with gzip.open(file_path, 'rt') as f:
            # Skip header line
            next(f)
            
            for line in tqdm(f, desc="Processing NCBI gene records"):
                if line.startswith('#'):
                    continue
                    
                fields = line.strip().split('\t')
                
                # Only process human genes (tax_id=9606)
                if len(fields) > NCBI_TAX_ID and fields[NCBI_TAX_ID] != "9606":
                    continue
                    
                if len(fields) <= NCBI_GENE_ID:
                    continue
                    
                gene_id = fields[NCBI_GENE_ID]
                gene_symbol = fields[NCBI_SYMBOL] if len(fields) > NCBI_SYMBOL else ""
                
                if not gene_symbol:
                    continue
                
                # Initialize entry if needed
                if gene_symbol not in gene_mappings:
                    gene_mappings[gene_symbol] = {
                        'ncbi_id': gene_id,
                        'ensembl_gene_ids': [],
                        'refseq_ids': []
                    }
                
                # Process database cross-references for other IDs
                if len(fields) > NCBI_DB_XREFS:
                    db_xrefs = fields[NCBI_DB_XREFS]
                    if db_xrefs != "-":
                        for xref in db_xrefs.split('|'):
                            if xref.startswith('Ensembl:'):
                                ensembl_id = xref.replace('Ensembl:', '')
                                if ensembl_id:
                                    # Remove version from Ensembl IDs
                                    base_id = ensembl_id.split('.')[0]
                                    if base_id not in gene_mappings[gene_symbol]['ensembl_gene_ids']:
                                        gene_mappings[gene_symbol]['ensembl_gene_ids'].append(base_id)
                            elif xref.startswith('RefSeq:'):
                                refseq_id = xref.replace('RefSeq:', '')
                                if refseq_id and refseq_id not in gene_mappings[gene_symbol]['refseq_ids']:
                                    gene_mappings[gene_symbol]['refseq_ids'].append(refseq_id)
        
        # Log summary statistics
        logger.info(f"Processed NCBI gene info for {len(gene_mappings)} human genes")
        
        return gene_mappings
        
    def process_hgnc_complete_set(self, file_path: Path) -> Dict[str, Dict[str, Any]]:
        """Process HGNC complete set to map gene symbols to various IDs.
        
        Args:
            file_path: Path to the HGNC complete set file
            
        Returns:
            Dictionary mapping gene symbols to various IDs
        """
        logger.info("Processing HGNC complete set file...")
        
        # Load the data into a pandas DataFrame for easier processing
        # HGNC file has header row and tab separation
        try:
            df = pd.read_csv(file_path, sep='\t')
            
            # Check for expected columns
            required_columns = ['symbol', 'hgnc_id', 'entrez_id', 'ensembl_gene_id', 
                                'refseq_accession', 'uniprot_ids']
            
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                available_columns = ', '.join(df.columns)
                logger.warning(f"Missing columns in HGNC file: {missing_columns}. Available columns: {available_columns}")
                
            # Process each row
            gene_mappings: Dict[str, Dict[str, Any]] = {}
            
            for _, row in tqdm(df.iterrows(), total=len(df), desc="Processing HGNC records"):
                gene_symbol = row.get('symbol')
                if not gene_symbol:
                    continue
                    
                # Initialize entry
                gene_mappings[gene_symbol] = {}
                
                # Add HGNC ID if available
                if 'hgnc_id' in row and pd.notna(row['hgnc_id']):
                    gene_mappings[gene_symbol]['hgnc_id'] = row['hgnc_id']
                    
                # Add Entrez ID if available
                if 'entrez_id' in row and pd.notna(row['entrez_id']):
                    gene_mappings[gene_symbol]['entrez_id'] = str(row['entrez_id'])
                    
                # Add Ensembl Gene ID if available
                if 'ensembl_gene_id' in row and pd.notna(row['ensembl_gene_id']):
                    # Remove version if present
                    ensembl_id = str(row['ensembl_gene_id']).split('.')[0]
                    gene_mappings[gene_symbol]['ensembl_gene_id'] = ensembl_id
                    
                # Add RefSeq accessions if available
                if 'refseq_accession' in row and pd.notna(row['refseq_accession']):
                    refseq_ids = str(row['refseq_accession']).split('|')
                    gene_mappings[gene_symbol]['refseq_ids'] = refseq_ids
                    
                # Add UniProt IDs if available
                if 'uniprot_ids' in row and pd.notna(row['uniprot_ids']):
                    uniprot_ids = str(row['uniprot_ids']).split('|')
                    gene_mappings[gene_symbol]['uniprot_ids'] = uniprot_ids
            
            # Log summary statistics
            logger.info(f"Processed HGNC complete set with {len(gene_mappings)} gene symbols")
            return gene_mappings
            
        except Exception as e:
            logger.error(f"Error processing HGNC complete set: {e}")
            return {}
            
    def process_uniprot_idmapping(self, file_path: Path) -> Dict[str, Dict[str, Any]]:
        """Process UniProt idmapping file to map gene symbols to UniProt IDs.
        
        Args:
            file_path: Path to the idmapping_selected.tab.gz file
            
        Returns:
            Dictionary mapping gene symbols to UniProt IDs
        """
        logger.info("Processing UniProt idmapping file...")
        
        # Define column indices for idmapping_selected.tab file
        UNIPROT_ACC = 0
        UNIPROT_ID = 1
        GENE_NAME = 2
        
        gene_mappings: Dict[str, Dict[str, Any]] = {}
        
        try:
            # Process the file line by line to avoid loading everything into memory
            with gzip.open(file_path, 'rt') as f:
                for line in tqdm(f, desc="Processing UniProt idmapping"):
                    # Split the line by tabs
                    fields = line.strip().split('\t')
                    
                    # Check for minimum required fields
                    if len(fields) <= GENE_NAME:
                        continue
                        
                    uniprot_acc = fields[UNIPROT_ACC]
                    uniprot_id = fields[UNIPROT_ID]
                    gene_name = fields[GENE_NAME]
                    
                    if not gene_name or gene_name == "-" or gene_name == "":
                        continue
                        
                    # Gene name may contain multiple symbols separated by spaces
                    gene_symbols = gene_name.split()
                    
                    for gene_symbol in gene_symbols:
                        # Initialize entry if needed
                        if gene_symbol not in gene_mappings:
                            gene_mappings[gene_symbol] = {
                                'uniprot_acc': [],
                                'uniprot_id': []
                            }
                            
                        # Add UniProt accession and ID
                        if uniprot_acc and uniprot_acc not in gene_mappings[gene_symbol]['uniprot_acc']:
                            gene_mappings[gene_symbol]['uniprot_acc'].append(uniprot_acc)
                            
                        if uniprot_id and uniprot_id not in gene_mappings[gene_symbol]['uniprot_id']:
                            gene_mappings[gene_symbol]['uniprot_id'].append(uniprot_id)
        
            # Log summary statistics
            logger.info(f"Processed UniProt idmapping for {len(gene_mappings)} gene symbols")
            return gene_mappings
            
        except Exception as e:
            logger.error(f"Error processing UniProt idmapping: {e}")
            return {}

    def update_gene_ids(self, gene_id_mappings: Dict[str, Dict[str, Any]]) -> None:
        """Update gene IDs in the database.
        
        Args:
            gene_id_mappings: Dictionary mapping gene symbols to other IDs
        """
        logger.info("Updating gene IDs in the database...")
        
        if not gene_id_mappings:
            logger.warning("No gene ID mappings to update")
            return
            
        if not self.db_manager.cursor:
            logger.error("No database connection")
            return
            
        try:
            # Process in batches
            updates = []
            processed = 0
            
            for gene_symbol, mappings in gene_id_mappings.items():
                # Prepare alt_gene_ids JSON
                alt_ids = {}
                
                # Add directly mappable IDs
                for direct_id in ['hgnc_id', 'entrez_id', 'ensembl_gene_id']:
                    if direct_id in mappings and mappings[direct_id]:
                        alt_ids[direct_id] = mappings[direct_id]
                
                # Handle array IDs
                if 'refseq_ids' in mappings and mappings['refseq_ids']:
                    refseq_ids = mappings['refseq_ids']
                    if isinstance(refseq_ids, list) and refseq_ids:
                        alt_ids['refseq_id'] = refseq_ids[0]  # Use first as primary
                
                # Prepare UniProt IDs
                uniprot_ids = []
                if 'uniprot_ids' in mappings and mappings['uniprot_ids']:
                    if isinstance(mappings['uniprot_ids'], list):
                        uniprot_ids = mappings['uniprot_ids']
                    else:
                        uniprot_ids = [mappings['uniprot_ids']]
                elif 'uniprot_acc' in mappings and mappings['uniprot_acc']:
                    if isinstance(mappings['uniprot_acc'], list):
                        uniprot_ids = mappings['uniprot_acc']
                    else:
                        uniprot_ids = [mappings['uniprot_acc']]
                
                # Handle NCBI IDs
                ncbi_ids = []
                if 'ncbi_id' in mappings and mappings['ncbi_id']:
                    ncbi_ids = [mappings['ncbi_id']]
                elif 'entrez_id' in mappings and mappings['entrez_id']:
                    ncbi_ids = [mappings['entrez_id']]
                
                # Prepare RefSeq IDs
                refseq_ids = []
                if 'refseq_ids' in mappings and mappings['refseq_ids']:
                    if isinstance(mappings['refseq_ids'], list):
                        refseq_ids = mappings['refseq_ids']
                    else:
                        refseq_ids = [mappings['refseq_ids']]
                
                # Add to updates batch
                updates.append((
                    json.dumps(alt_ids),
                    uniprot_ids if uniprot_ids else None,
                    ncbi_ids if ncbi_ids else None,
                    refseq_ids if refseq_ids else None,
                    gene_symbol
                ))
                
                if len(updates) >= self.batch_size:
                    execute_batch(
                        self.db_manager.cursor,
                        """
                        UPDATE cancer_transcript_base
                        SET 
                            alt_gene_ids = %s::jsonb,
                            uniprot_ids = %s,
                            ncbi_ids = %s,
                            refseq_ids = %s
                        WHERE gene_symbol = %s
                        """,
                        updates,
                        page_size=self.batch_size
                    )
                    if self.db_manager.conn:
                        self.db_manager.conn.commit()
                    processed += len(updates)
                    updates = []
                    if processed % (self.batch_size * 5) == 0:  # Log periodically
                      tqdm.write(f"Updated {processed}/{len(gene_id_mappings)} gene records so far...")
            
            # Process remaining updates
            if updates:
                execute_batch(
                    self.db_manager.cursor,
                    """
                    UPDATE cancer_transcript_base
                    SET 
                        alt_gene_ids = %s::jsonb,
                        uniprot_ids = %s,
                        ncbi_ids = %s,
                        refseq_ids = %s
                    WHERE gene_symbol = %s
                    """,
                    updates,
                    page_size=self.batch_size
                )
                if self.db_manager.conn:
                    self.db_manager.conn.commit()
                processed += len(updates)
                
            logger.info(f"Updated {processed} gene records with alternative IDs")
            
        except Exception as e:
            if self.db_manager.conn:
                self.db_manager.conn.rollback()
            logger.error(f"Error updating gene IDs: {e}")

    def enrich_gene_ids(self) -> None:
        """Enrich gene IDs using various mapping sources."""
        logger.info("Starting gene ID enrichment...")
        
        # Download and process NCBI gene info
        ncbi_file = self.download_ncbi_gene_info()
        ncbi_mappings = self.process_ncbi_gene_info(ncbi_file)
        
        # Download and process HGNC complete set
        hgnc_file = self.download_hgnc_complete_set()
        hgnc_mappings = self.process_hgnc_complete_set(hgnc_file)
        
        # Download and process UniProt idmapping
        uniprot_file = self.download_uniprot_idmapping()
        uniprot_mappings = self.process_uniprot_idmapping(uniprot_file)
        
        # Merge gene ID mappings
        gene_id_mappings = {}
        
        # Start with HGNC mappings as they are most authoritative
        for gene_symbol, mappings in hgnc_mappings.items():
            if gene_symbol not in gene_id_mappings:
                gene_id_mappings[gene_symbol] = {}
            gene_id_mappings[gene_symbol].update(mappings)
        
        # Add NCBI mappings
        for gene_symbol, mappings in ncbi_mappings.items():
            if gene_symbol not in gene_id_mappings:
                gene_id_mappings[gene_symbol] = {}
            # Merge mappings, giving preference to existing HGNC mappings
            for key, value in mappings.items():
                if key not in gene_id_mappings[gene_symbol] or not gene_id_mappings[gene_symbol][key]:
                    gene_id_mappings[gene_symbol][key] = value
                # Special handling for array fields
                elif isinstance(value, list) and key in gene_id_mappings[gene_symbol]:
                    # Combine lists and remove duplicates
                    if isinstance(gene_id_mappings[gene_symbol][key], list):
                        gene_id_mappings[gene_symbol][key] = list(set(gene_id_mappings[gene_symbol][key] + value))
        
        # Add UniProt mappings
        for gene_symbol, mappings in uniprot_mappings.items():
            if gene_symbol not in gene_id_mappings:
                gene_id_mappings[gene_symbol] = {}
            # Add UniProt specific fields
            for key, value in mappings.items():
                gene_id_mappings[gene_symbol][key] = value
        
        # Update the database with merged mappings
        self.update_gene_ids(gene_id_mappings)
        
        logger.info("Gene ID enrichment completed")

    def update_transcript_ids(self, transcript_id_mappings: Dict[str, Dict[str, str]]) -> None:
        """Update transcript IDs in the database."""
        # Implementation will be added in next iteration
        pass
        
    def enrich_transcript_ids(self) -> None:
        """Enrich transcript IDs using various mapping services."""
        # Implementation will be added in next iteration
        pass
        
    def run(self) -> None:
        """Run the complete ID enrichment pipeline."""
        try:
            logger.info("Starting ID enrichment pipeline...")
            
            # Ensure proper database schema
            self._ensure_db_schema()
            
            # Enrich transcript IDs
            # Currently we don't have specific transcript ID enrichment
            # Most ID mapping is at the gene level
            logger.info("Skipping transcript ID enrichment (not implemented)")
            
            # Enrich gene IDs
            self.enrich_gene_ids()
            
            # Verify results
            self.verify_id_enrichment()
            
            logger.info("ID enrichment pipeline completed successfully")
            
        except Exception as e:
            logger.error(f"ID enrichment failed: {e}")
            raise
            
    def _ensure_db_schema(self) -> None:
        """Ensure database schema has the required columns for ID enrichment."""
        if not self.db_manager.cursor:
            raise RuntimeError("No database connection")
            
        try:
            # Check if required columns exist
            required_columns = [
                'alt_transcript_ids',
                'alt_gene_ids',
                'uniprot_ids',
                'ncbi_ids',
                'refseq_ids'
            ]
            
            # Get current schema version
            self.db_manager.cursor.execute("SELECT version FROM schema_version")
            version = self.db_manager.cursor.fetchone()
            current_version = version[0] if version else None
            
            if current_version != 'v0.1.4':
                logger.info(f"Current schema version {current_version} needs update to v0.1.4")
                if not self.db_manager.migrate_to_version('v0.1.4'):
                    raise RuntimeError("Failed to migrate database schema to v0.1.4")
                logger.info("Schema successfully updated to v0.1.4")
            else:
                # Verify all required columns exist
                for column in required_columns:
                    if not self.db_manager.check_column_exists('cancer_transcript_base', column):
                        raise RuntimeError(f"Required column '{column}' missing in schema v0.1.4")
                
            logger.info("Database schema validated for ID enrichment")
        except Exception as e:
            logger.error(f"Database schema validation failed: {e}")
            raise
        
    def verify_id_enrichment(self) -> None:
        """Verify results of ID enrichment process."""
        if not self.db_manager.cursor:
            logger.error("No database connection")
            return
            
        try:
            # Count records with different ID types
            self.db_manager.cursor.execute("""
                SELECT 
                    COUNT(*) as total_genes,
                    COUNT(CASE WHEN alt_gene_ids IS NOT NULL 
                              AND alt_gene_ids != '{}'::jsonb THEN 1 END) as with_alt_gene_ids,
                    COUNT(CASE WHEN uniprot_ids IS NOT NULL 
                              AND array_length(uniprot_ids, 1) > 0 THEN 1 END) as with_uniprot,
                    COUNT(CASE WHEN ncbi_ids IS NOT NULL 
                              AND array_length(ncbi_ids, 1) > 0 THEN 1 END) as with_ncbi,
                    COUNT(CASE WHEN refseq_ids IS NOT NULL 
                              AND array_length(refseq_ids, 1) > 0 THEN 1 END) as with_refseq,
                    COUNT(CASE WHEN alt_transcript_ids IS NOT NULL 
                              AND alt_transcript_ids != '{}'::jsonb THEN 1 END) as with_alt_transcript_ids
                FROM cancer_transcript_base
            """)
            
            result = self.db_manager.cursor.fetchone()
            
            if result:
                logger.info(
                    f"\nID Enrichment Statistics:\n"
                    f"- Total genes in database: {result[0]:,}\n"
                    f"- Genes with alternative gene IDs: {result[1]:,}\n"
                    f"- Genes with UniProt IDs: {result[2]:,}\n"
                    f"- Genes with NCBI IDs: {result[3]:,}\n"
                    f"- Genes with RefSeq IDs: {result[4]:,}\n"
                    f"- Transcripts with alternative transcript IDs: {result[5]:,}"
                )
                
        except Exception as e:
            logger.error(f"Error verifying ID enrichment: {e}")

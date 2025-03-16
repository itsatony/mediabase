"""ID enrichment module for Cancer Transcriptome Base.

This module maps different database identifiers to each transcript/gene in the database,
enhancing the ability to match and integrate data from various sources.
"""

import logging
import gzip
import json
import os
import sys
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
# Terminal width for padding progress messages
TERM_WIDTH = os.get_terminal_size().columns if sys.stdout.isatty() else 100

# Helper function for single-line progress updates
def update_progress(message: str) -> None:
    """Print progress update on a single, updating line.
    
    Args:
        message: The progress message to display
    """
    # Pad with spaces to clear previous content and add carriage return
    print(f"\r{message:<{TERM_WIDTH}}", end="", flush=True)

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
                - vgnc_gene_set_url: URL for VGNC complete set
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
        self.vgnc_gene_set_url = config.get(
            'vgnc_gene_set_url',
            'https://ftp.ebi.ac.uk/pub/databases/genenames/vgnc/json/all/all_vgnc_gene_set_All.json'
        )
        self.uniprot_idmapping_selected_url = config.get(
            'uniprot_idmapping_selected_url',
            'https://ftp.uniprot.org/pub/databases/uniprot/current_release/knowledgebase/idmapping/idmapping_selected.tab.gz'
        )
        
        # Add transcript mapping source URLs with defaults
        self.ensembl_refseq_url = config.get(
            'ensembl_refseq_url',
            'https://ftp.ensembl.org/pub/current_tsv/homo_sapiens/Homo_sapiens.GRCh38.113.refseq.tsv.gz'
        )
        self.ensembl_entrez_url = config.get(
            'ensembl_entrez_url',
            'https://ftp.ensembl.org/pub/current_tsv/homo_sapiens/Homo_sapiens.GRCh38.113.entrez.tsv.gz'
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
            update_progress(f"Using cached NCBI gene info file: {file_path}")
            return file_path
            
        update_progress(f"Downloading NCBI gene info from {self.ncbi_gene_info_url}")
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
            
    def download_vgnc_gene_set(self) -> Path:
        """Download the VGNC gene set file.
        
        Returns:
            Path: Path to the downloaded file
        """
        from urllib.parse import urlparse
        import ftplib
        from tqdm import tqdm
        import os
        
        # Generate cache file path
        cache_key = self._get_cache_key(self.vgnc_gene_set_url)
        vgnc_file = self.cache_dir / f"vgnc_{cache_key}.json"
        
        # Check if we have a valid cached file
        if vgnc_file.exists() and self._is_cache_valid(cache_key):
            logger.info(f"Using cached VGNC file: {vgnc_file}")
            return vgnc_file
            
        logger.info(f"Downloading VGNC gene set from {self.vgnc_gene_set_url}")
        
        # Parse URL to get FTP server and path
        parsed_url = urlparse(self.vgnc_gene_set_url)
        
        if parsed_url.scheme == 'ftp':
            try:
                # Connect to FTP server
                server = parsed_url.netloc
                path = parsed_url.path
                
                # Create an FTP connection
                ftp = ftplib.FTP(server)
                ftp.login()  # Anonymous login
                
                # Get file size for progress bar
                ftp.sendcmd("TYPE I")  # Switch to binary mode
                file_size = ftp.size(path)
                
                # Download the file with progress bar
                with open(vgnc_file, 'wb') as f, tqdm(
                    desc="Downloading VGNC gene set",
                    total=file_size,
                    unit='B',
                    unit_scale=True
                ) as pbar:
                    def callback(data):
                        f.write(data)
                        pbar.update(len(data))
                    
                    ftp.retrbinary(f"RETR {path}", callback)
                
                ftp.quit()
                
                # Update cache metadata
                self._update_cache_meta(cache_key, vgnc_file)
                logger.info(f"VGNC gene set downloaded to {vgnc_file}")
                
            except Exception as e:
                # If FTP download fails, try HTTP/HTTPS as fallback
                logger.warning(f"FTP download failed: {e}. Trying HTTP download as fallback.")
                http_url = f"https://{parsed_url.netloc}{parsed_url.path}"
                return self._download_http_file(http_url, vgnc_file, cache_key)
        else:
            # Use standard HTTP download for non-FTP URLs
            return self._download_http_file(self.vgnc_gene_set_url, vgnc_file, cache_key)
            
        return vgnc_file
        
    def _download_http_file(self, url: str, file_path: Path, cache_key: str) -> Path:
        """Download a file via HTTP/HTTPS.
        
        Args:
            url: URL to download from
            file_path: Path to save the file to
            cache_key: Cache key for metadata
            
        Returns:
            Path: Path to the downloaded file
        """
        import requests
        from tqdm import tqdm
        
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            
            with open(file_path, 'wb') as f, tqdm(
                desc=f"Downloading {file_path.name}",
                total=total_size,
                unit='B',
                unit_scale=True
            ) as pbar:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))
            
            self._update_cache_meta(cache_key, file_path)
            logger.info(f"File downloaded to {file_path}")
            
        except Exception as e:
            if file_path.exists():
                file_path.unlink()  # Delete partial download
            logger.error(f"Failed to download file: {e}")
            raise
            
        return file_path
    
    def download_uniprot_idmapping(self) -> Path:
        """Download UniProt idmapping_selected file if not in cache."""
        # We use the selected mapping file which is much smaller than the full mapping
        cache_key = self._get_cache_key(self.uniprot_idmapping_selected_url)
        file_path = self.cache_dir / f"uniprot_idmapping_selected_{cache_key}.tab.gz"
        
        if file_path.exists() and self._is_cache_valid(cache_key):
            update_progress(f"Using cached UniProt idmapping file: {file_path}")
            return file_path
            
        update_progress(f"Downloading UniProt idmapping from {self.uniprot_idmapping_selected_url}")
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
        update_progress("Processing NCBI gene info file...")
        
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
        update_progress(f"Processed NCBI gene info for {len(gene_mappings)} human genes")
        
        return gene_mappings
        
    def process_vgnc_gene_set(self, file_path: Path) -> Dict[str, Dict[str, Any]]:
        """Process VGNC gene set to map gene symbols to various IDs.
        
        Args:
            file_path: Path to the VGNC gene set JSON file
            
        Returns:
            Dictionary mapping gene symbols to various IDs
        """
        update_progress("Processing VGNC gene set file...")
        
        # Load the JSON data
        try:
            with open(file_path, 'r') as f:
                vgnc_data = json.load(f)
            
            gene_mappings: Dict[str, Dict[str, Any]] = {}
            
            for record in tqdm(vgnc_data, desc="Processing VGNC records"):
                gene_symbol = record.get('symbol')
                if not gene_symbol:
                    continue
                    
                # Initialize entry for this gene symbol if needed
                if gene_symbol not in gene_mappings:
                    gene_mappings[gene_symbol] = {}
                
                # Add VGNC ID
                if 'vgnc_id' in record:
                    gene_mappings[gene_symbol]['vgnc_id'] = record['vgnc_id']
                
                # Add Entrez/NCBI ID
                if 'ncbi_id' in record:
                    gene_mappings[gene_symbol]['entrez_id'] = record['ncbi_id']
                
                # Add Ensembl Gene ID
                if 'ensembl_gene_id' in record:
                    # Remove version if present
                    ensembl_id = record['ensembl_gene_id'].split('.')[0]
                    gene_mappings[gene_symbol]['ensembl_gene_id'] = ensembl_id
                
                # Add UniProt IDs if available
                if 'uniprot_ids' in record and isinstance(record['uniprot_ids'], list):
                    gene_mappings[gene_symbol]['uniprot_ids'] = record['uniprot_ids']
                
                # Add HGNC orthologs if available
                if 'hgnc_orthologs' in record and isinstance(record['hgnc_orthologs'], list):
                    # Extract just the IDs from orthologs (format is "HGNC:123")
                    hgnc_ids = [h.replace('HGNC:', '') for h in record['hgnc_orthologs'] if h.startswith('HGNC:')]
                    if hgnc_ids:
                        gene_mappings[gene_symbol]['hgnc_id'] = hgnc_ids[0]  # Use first ortholog
                
            # Log summary statistics
            update_progress(f"Processed VGNC gene set with {len(gene_mappings)} gene symbols")
            return gene_mappings
            
        except Exception as e:
            logger.error(f"Error processing VGNC gene set: {e}")
            return {}
    
    def process_uniprot_idmapping(self, file_path: Path) -> Dict[str, Dict[str, Any]]:
        """Process UniProt idmapping file to map gene symbols to UniProt IDs.
        
        Args:
            file_path: Path to the idmapping_selected.tab.gz file
            
        Returns:
            Dictionary mapping gene symbols to UniProt IDs
        """
        update_progress("Processing UniProt idmapping file...")
        
        # Define column indices for idmapping_selected.tab file
        # Column definitions in UniProt idmapping_selected.tab
        UNIPROT_ACC = 0    # UniProtKB-AC
        UNIPROT_ID = 1     # UniProtKB-ID
        GENE_NAME = 2      # GeneID (EntrezGene)
        ENTREZ_GENE = 2    # Same as GENE_NAME (EntrezGene)
        REFSEQ = 3         # RefSeq
        PDB = 5            # PDB
        GO = 6             # GO
        MIM = 13           # OMIM disease associations
        PUBMED = 15        # PubMed
        ENSEMBL = 18       # Ensembl
        ENSEMBL_TRS = 19   # Ensembl_TRS (fixed from 129)
        ADD_PUBMED = 21    # Additional PubMed
        
        gene_mappings: Dict[str, Dict[str, Any]] = {}
        lines = []
        n = 0
        
        try:
            # Process the file line by line to avoid loading everything into memory
            with gzip.open(file_path, 'rt') as f:
                for line in tqdm(f, desc="Processing UniProt idmapping"):
                    if n < 2:
                        lines.append(line)
                    n += 1
                    
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
                                'uniprot_id': [],
                                'entrez_ids': [],
                                'refseq_ids': [],
                                'pdb_ids': [],
                                'go_terms': [],
                                'mim_ids': [],
                                'pubmed_ids': []
                            }
                            
                        # Add UniProt accession and ID
                        if uniprot_acc and uniprot_acc not in gene_mappings[gene_symbol]['uniprot_acc']:
                            gene_mappings[gene_symbol]['uniprot_acc'].append(uniprot_acc)
                            
                        if uniprot_id and uniprot_id not in gene_mappings[gene_symbol]['uniprot_id']:
                            gene_mappings[gene_symbol]['uniprot_id'].append(uniprot_id)
                        
                        # Extract additional IDs when available
                        # Add EntrezGene/NCBI IDs
                        if len(fields) > ENTREZ_GENE and fields[ENTREZ_GENE] and fields[ENTREZ_GENE] != "-":
                            entrez_id = fields[ENTREZ_GENE]
                            if entrez_id not in gene_mappings[gene_symbol]['entrez_ids']:
                                gene_mappings[gene_symbol]['entrez_ids'].append(entrez_id)
                        
                        # Add RefSeq IDs
                        if len(fields) > REFSEQ and fields[REFSEQ] and fields[REFSEQ] != "-":
                            for refseq_id in fields[REFSEQ].split('; '):
                                if refseq_id and refseq_id not in gene_mappings[gene_symbol]['refseq_ids']:
                                    gene_mappings[gene_symbol]['refseq_ids'].append(refseq_id)
                        
                        # Add PDB IDs
                        if len(fields) > PDB and fields[PDB] and fields[PDB] != "-":
                            for pdb_id in fields[PDB].split('; '):
                                if pdb_id and pdb_id not in gene_mappings[gene_symbol]['pdb_ids']:
                                    gene_mappings[gene_symbol]['pdb_ids'].append(pdb_id)
                        
                        # Add GO terms
                        if len(fields) > GO and fields[GO] and fields[GO] != "-":
                            for go_term in fields[GO].split('; '):
                                if go_term and go_term not in gene_mappings[gene_symbol]['go_terms']:
                                    gene_mappings[gene_symbol]['go_terms'].append(go_term)
                        
                        # Add MIM/OMIM disease IDs
                        if len(fields) > MIM and fields[MIM] and fields[MIM] != "-":
                            for mim_id in fields[MIM].split('; '):
                                if mim_id and mim_id not in gene_mappings[gene_symbol]['mim_ids']:
                                    gene_mappings[gene_symbol]['mim_ids'].append(mim_id)
                        
                        # Add PubMed IDs
                        if len(fields) > PUBMED and fields[PUBMED] and fields[PUBMED] != "-":
                            for pubmed_id in fields[PUBMED].split('; '):
                                if pubmed_id and pubmed_id not in gene_mappings[gene_symbol]['pubmed_ids']:
                                    gene_mappings[gene_symbol]['pubmed_ids'].append(pubmed_id)
                        
                        # Add additional PubMed IDs
                        if len(fields) > ADD_PUBMED and fields[ADD_PUBMED] and fields[ADD_PUBMED] != "-":
                            for pubmed_id in fields[ADD_PUBMED].split('; '):
                                if pubmed_id and pubmed_id not in gene_mappings[gene_symbol]['pubmed_ids']:
                                    gene_mappings[gene_symbol]['pubmed_ids'].append(pubmed_id)
            
            # Log summary statistics
            update_progress(f"Processed UniProt idmapping for {len(gene_mappings)} gene symbols")
            
            # Log additional data statistics
            id_counts = {
                'entrez_ids': sum(1 for data in gene_mappings.values() if data['entrez_ids']),
                'refseq_ids': sum(1 for data in gene_mappings.values() if data['refseq_ids']),
                'pdb_ids': sum(1 for data in gene_mappings.values() if data['pdb_ids']),
                'go_terms': sum(1 for data in gene_mappings.values() if data['go_terms']),
                'mim_ids': sum(1 for data in gene_mappings.values() if data['mim_ids']),
                'pubmed_ids': sum(1 for data in gene_mappings.values() if data['pubmed_ids']),
            }
            
            logger.info(f"Extracted ID counts from UniProt mapping:")
            for id_type, count in id_counts.items():
                logger.info(f"  - {id_type}: {count} genes")
                
            return gene_mappings
            
        except Exception as e:
            logger.error(f"Error processing UniProt idmapping: {e}")
            return {}
    
    def download_ensembl_refseq(self) -> Path:
        """Download Ensembl-RefSeq mapping file if not in cache."""
        cache_key = self._get_cache_key(self.ensembl_refseq_url)
        file_path = self.cache_dir / f"ensembl_refseq_{cache_key}.tsv.gz"
        
        if file_path.exists() and self._is_cache_valid(cache_key):
            update_progress(f"Using cached Ensembl-RefSeq mapping file: {file_path}")
            return file_path
            
        update_progress(f"Downloading Ensembl-RefSeq mapping from {self.ensembl_refseq_url}")
        response = requests.get(self.ensembl_refseq_url, stream=True)
        total_size = int(response.headers.get('content-length', 0))
        
        with open(file_path, 'wb') as f, tqdm(
            desc="Downloading Ensembl-RefSeq mapping",
            total=total_size,
            unit='iB',
            unit_scale=True
        ) as pbar:
            for data in response.iter_content(chunk_size=8192):
                size = f.write(data)
                pbar.update(size)
                
        self._update_cache_meta(cache_key, file_path)
        return file_path
    
    def download_ensembl_entrez(self) -> Path:
        """Download Ensembl-Entrez mapping file if not in cache."""
        cache_key = self._get_cache_key(self.ensembl_entrez_url)
        file_path = self.cache_dir / f"ensembl_entrez_{cache_key}.tsv.gz"
        
        if file_path.exists() and self._is_cache_valid(cache_key):
            update_progress(f"Using cached Ensembl-Entrez mapping file: {file_path}")
            return file_path
            
        update_progress(f"Downloading Ensembl-Entrez mapping from {self.ensembl_entrez_url}")
        response = requests.get(self.ensembl_entrez_url, stream=True)
        total_size = int(response.headers.get('content-length', 0))
        
        with open(file_path, 'wb') as f, tqdm(
            desc="Downloading Ensembl-Entrez mapping",
            total=total_size,
            unit='iB',
            unit_scale=True
        ) as pbar:
            for data in response.iter_content(chunk_size=8192):
                size = f.write(data)
                pbar.update(size)
                
        self._update_cache_meta(cache_key, file_path)
        return file_path
        
    def process_ensembl_refseq(self, file_path: Path) -> Dict[str, Dict[str, Any]]:
        """Process Ensembl-RefSeq mapping file to map transcript IDs.
        
        Args:
            file_path: Path to the Ensembl-RefSeq mapping file
            
        Returns:
            Dictionary mapping Ensembl transcript IDs to RefSeq IDs
        """
        update_progress("Processing Ensembl-RefSeq mapping file...")
        
        transcript_mappings: Dict[str, Dict[str, Any]] = {}
        
        try:
            with gzip.open(file_path, 'rt') as f:
                # Skip header line if it exists
                first_line = f.readline().strip()
                if first_line.startswith('#') or 'gene_id' in first_line:
                    pass  # Skip header
                else:
                    # Reset file pointer if no header
                    f.seek(0)
                
                # Process file
                for line in tqdm(f, desc="Processing Ensembl-RefSeq mappings"):
                    fields = line.strip().split('\t')
                    
                    # Ensure the line has enough fields
                    if len(fields) < 2:
                        continue
                    
                    # Extract transcript IDs
                    # Format is typically: ensembl_transcript_id, refseq_transcript_id
                    ensembl_id = fields[0].split('.')[0]  # Remove version if present
                    refseq_id = fields[1]
                    
                    # Skip if either ID is missing
                    if not ensembl_id or not refseq_id:
                        continue
                    
                    # Initialize entry if needed
                    if ensembl_id not in transcript_mappings:
                        transcript_mappings[ensembl_id] = {
                            'refseq_transcript_ids': []
                        }
                    
                    # Add RefSeq ID if not already present
                    if refseq_id not in transcript_mappings[ensembl_id]['refseq_transcript_ids']:
                        transcript_mappings[ensembl_id]['refseq_transcript_ids'].append(refseq_id)
            
            # Log summary statistics
            update_progress(f"Processed Ensembl-RefSeq mappings for {len(transcript_mappings)} Ensembl transcript IDs")
            return transcript_mappings
            
        except Exception as e:
            logger.error(f"Error processing Ensembl-RefSeq mapping: {e}")
            return {}
    
    def process_ensembl_entrez(self, file_path: Path) -> Dict[str, Dict[str, Any]]:
        """Process Ensembl-Entrez mapping file to map transcript IDs.
        
        Args:
            file_path: Path to the Ensembl-Entrez mapping file
            
        Returns:
            Dictionary mapping Ensembl transcript IDs to Entrez IDs
        """
        update_progress("Processing Ensembl-Entrez mapping file...")
        
        transcript_mappings: Dict[str, Dict[str, Any]] = {}
        
        try:
            with gzip.open(file_path, 'rt') as f:
                # Skip header line if it exists
                first_line = f.readline().strip()
                if first_line.startswith('#') or 'gene_id' in first_line:
                    pass  # Skip header
                else:
                    # Reset file pointer if no header
                    f.seek(0)
                
                # Process file
                for line in tqdm(f, desc="Processing Ensembl-Entrez mappings"):
                    fields = line.strip().split('\t')
                    
                    # Ensure the line has enough fields
                    if len(fields) < 2:
                        continue
                    
                    # Extract transcript IDs
                    # Format is typically: ensembl_transcript_id, entrez_id
                    ensembl_id = fields[0].split('.')[0]  # Remove version if present
                    entrez_id = fields[1]
                    
                    # Skip if either ID is missing
                    if not ensembl_id or not entrez_id:
                        continue
                    
                    # Initialize entry if needed
                    if ensembl_id not in transcript_mappings:
                        transcript_mappings[ensembl_id] = {
                            'entrez_transcript_ids': []
                        }
                    
                    # Add Entrez ID if not already present
                    if entrez_id not in transcript_mappings[ensembl_id]['entrez_transcript_ids']:
                        transcript_mappings[ensembl_id]['entrez_transcript_ids'].append(entrez_id)
            
            # Log summary statistics
            update_progress(f"Processed Ensembl-Entrez mappings for {len(transcript_mappings)} Ensembl transcript IDs")
            return transcript_mappings
            
        except Exception as e:
            logger.error(f"Error processing Ensembl-Entrez mapping: {e}")
            return {}
    
    def update_gene_ids(self, gene_id_mappings: Dict[str, Dict[str, Any]]) -> None:
        """Update gene IDs in the database.
        
        Args:
            gene_id_mappings: Dictionary mapping gene symbols to other IDs
        """
        update_progress("Updating gene IDs in the database...")
        
        if not gene_id_mappings:
            update_progress("No gene ID mappings to update")
            print()  # Move to next line
            return
            
        if not self.db_manager.cursor:
            logger.error("No database connection")
            return
            
        try:
            # Process in batches
            updates = []
            processed = 0
            
            pbar = tqdm(total=len(gene_id_mappings), desc="Updating gene records", unit="records")
            
            for gene_symbol, mappings in gene_id_mappings.items():
                # Prepare alt_gene_ids JSON
                alt_ids = {}
                
                # Add directly mappable IDs
                for direct_id in ['hgnc_id', 'entrez_id', 'ensembl_gene_id', 'vgnc_id']:
                    if direct_id in mappings and mappings[direct_id]:
                        alt_ids[direct_id] = mappings[direct_id]
                
                # Handle array IDs
                if 'refseq_ids' in mappings and mappings['refseq_ids']:
                    refseq_ids = mappings['refseq_ids']
                    if isinstance(refseq_ids, list) and refseq_ids:
                        alt_ids['refseq_id'] = refseq_ids[0]  # Use first as primary
                        if len(refseq_ids) > 1:
                            alt_ids['refseq_ids'] = refseq_ids
                
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
                
                # Prepare GO terms
                go_terms = []
                if 'go_terms' in mappings and mappings['go_terms']:
                    if isinstance(mappings['go_terms'], list):
                        go_terms = mappings['go_terms']
                    else:
                        go_terms = [mappings['go_terms']]
                    # Store GO terms in alt_ids for better accessibility
                    alt_ids['go_terms'] = go_terms
                
                # Prepare source references from PubMed IDs
                source_references = {}
                if 'pubmed_ids' in mappings and mappings['pubmed_ids']:
                    pubmed_refs = []
                    for pmid in mappings['pubmed_ids']:
                        if pmid:
                            pubmed_refs.append({
                                "pmid": pmid,
                                "evidence_type": "curated",
                                "source_db": "uniprot"
                            })
                    
                    if pubmed_refs:
                        source_references['uniprot'] = pubmed_refs
                
                # Add to updates batch
                updates.append((
                    json.dumps(alt_ids),
                    uniprot_ids if uniprot_ids else None,
                    ncbi_ids if ncbi_ids else None,
                    refseq_ids if refseq_ids else None,
                    json.dumps(source_references) if source_references else None,
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
                            refseq_ids = %s,
                            source_references = COALESCE(source_references, '{}'::jsonb) || %s::jsonb
                        WHERE gene_symbol = %s
                        """,
                        updates,
                        page_size=self.batch_size
                    )
                    if self.db_manager.conn:
                        self.db_manager.conn.commit()
                    processed += len(updates)
                    pbar.update(len(updates))
                    if processed % (self.batch_size * 5) == 0:  # Log periodically
                        update_progress(f"Updated {processed}/{len(gene_id_mappings)} gene records so far...")
                    updates = []
            
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
                        refseq_ids = %s,
                        source_references = COALESCE(source_references, '{}'::jsonb) || %s::jsonb
                    WHERE gene_symbol = %s
                    """,
                    updates,
                    page_size=self.batch_size
                )
                if self.db_manager.conn:
                    self.db_manager.conn.commit()
                processed += len(updates)
                pbar.update(len(updates))
            pbar.close()
            update_progress(f"Updated {processed} gene records with alternative IDs")
            print()  # Move to next line after completion
            
        except Exception as e:
            if self.db_manager.conn:
                self.db_manager.conn.rollback()
            logger.error(f"Error updating gene IDs: {e}")
    
    def enrich_gene_ids(self) -> None:
        """Enrich gene IDs using various mapping sources."""
        update_progress("Starting gene ID enrichment...")
        
        # Download and process UniProt idmapping (prioritize this source as it's the richest)
        uniprot_file = self.download_uniprot_idmapping()
        uniprot_mappings = self.process_uniprot_idmapping(uniprot_file)
        
        # Download and process VGNC gene set (for vertebrate gene nomenclature)
        vgnc_file = self.download_vgnc_gene_set()
        vgnc_mappings = self.process_vgnc_gene_set(vgnc_file)
        
        # Download and process NCBI gene info (for additional coverage)
        ncbi_file = self.download_ncbi_gene_info()
        ncbi_mappings = self.process_ncbi_gene_info(ncbi_file)
        
        # Merge gene ID mappings, prioritizing the most specific and reliable sources
        gene_id_mappings = {}
        
        # Start with UniProt mappings as they have the richest cross-references
        for gene_symbol, mappings in uniprot_mappings.items():
            if gene_symbol not in gene_id_mappings:
                gene_id_mappings[gene_symbol] = {}
            gene_id_mappings[gene_symbol].update(mappings)
        
        # Add VGNC mappings (authoritative for vertebrate gene nomenclature)
        for gene_symbol, mappings in vgnc_mappings.items():
            if gene_symbol not in gene_id_mappings:
                gene_id_mappings[gene_symbol] = {}
            # For fields that exist in both, prioritize VGNC for official nomenclature
            for key, value in mappings.items():
                if key in ['vgnc_id', 'hgnc_id']:  # Always use VGNC for these official IDs
                    gene_id_mappings[gene_symbol][key] = value
                elif key not in gene_id_mappings[gene_symbol] or not gene_id_mappings[gene_symbol][key]:
                    gene_id_mappings[gene_symbol][key] = value
                # Special handling for array fields
                elif isinstance(value, list) and key in gene_id_mappings[gene_symbol]:
                    # Combine lists and remove duplicates
                    if isinstance(gene_id_mappings[gene_symbol][key], list):
                        gene_id_mappings[gene_symbol][key] = list(set(gene_id_mappings[gene_symbol][key] + value))
        
        # Add NCBI mappings (for additional coverage)
        for gene_symbol, mappings in ncbi_mappings.items():
            if gene_symbol not in gene_id_mappings:
                gene_id_mappings[gene_symbol] = {}
            # Merge mappings, giving lower priority to NCBI
            for key, value in mappings.items():
                if key not in gene_id_mappings[gene_symbol] or not gene_id_mappings[gene_symbol][key]:
                    gene_id_mappings[gene_symbol][key] = value
                # Special handling for array fields
                elif isinstance(value, list) and key in gene_id_mappings[gene_symbol]:
                    # Combine lists and remove duplicates
                    if isinstance(gene_id_mappings[gene_symbol][key], list):
                        existing = gene_id_mappings[gene_symbol][key]
                        gene_id_mappings[gene_symbol][key] = list(set(existing + value))
        
        # Update the database with merged mappings
        self.update_gene_ids(gene_id_mappings)
        
        # Log mapping source statistics
        total_genes = len(gene_id_mappings)
        uniprot_coverage = sum(1 for gene in gene_id_mappings.values() if 'uniprot_acc' in gene and gene['uniprot_acc'])
        vgnc_coverage = sum(1 for gene in gene_id_mappings.values() if 'vgnc_id' in gene and gene['vgnc_id'])
        ncbi_coverage = sum(1 for gene in gene_id_mappings.values() if 'ncbi_id' in gene and gene['ncbi_id'])
        
        logger.info(f"ID source coverage statistics:")
        logger.info(f"  - Total genes: {total_genes}")
        logger.info(f"  - UniProt coverage: {uniprot_coverage} genes ({uniprot_coverage/total_genes*100:.1f}%)")
        logger.info(f"  - VGNC coverage: {vgnc_coverage} genes ({vgnc_coverage/total_genes*100:.1f}%)")
        logger.info(f"  - NCBI coverage: {ncbi_coverage} genes ({ncbi_coverage/total_genes*100:.1f}%)")
        
        update_progress("Gene ID enrichment completed")
        print()  # Move to next line

    def update_transcript_ids(self, transcript_id_mappings: Dict[str, Dict[str, Any]]) -> None:
        """Update transcript IDs in the database.
        
        Args:
            transcript_id_mappings: Dictionary mapping transcript IDs to other IDs
        """
        update_progress("Updating transcript IDs in the database...")
        
        if not transcript_id_mappings:
            update_progress("No transcript ID mappings to update")
            print()  # Move to next line
            return
        
        if not self.db_manager.cursor:
            logger.error("No database connection")
            return
            
        try:
            # Process in batches
            updates = []
            processed = 0
            
            # Initialize progress bar
            pbar = tqdm(
                total=len(transcript_id_mappings),
                desc="Updating transcript records",
                unit="records"
            )
            
            # For periodic progress updates outside of tqdm
            progress_line = ""
            
            for transcript_id, mappings in transcript_id_mappings.items():
                # Prepare alt_transcript_ids JSON
                alt_ids = {}
                
                # Store RefSeq IDs separately to also update the refseq_ids array field
                refseq_ids = None
                
                # Add RefSeq transcript IDs if available
                if 'refseq_transcript_ids' in mappings and mappings['refseq_transcript_ids']:
                    alt_ids['RefSeq'] = mappings['refseq_transcript_ids']
                    # Also store them for the refseq_ids array field
                    refseq_ids = mappings['refseq_transcript_ids']
                
                # Add Entrez transcript IDs if available
                if 'entrez_transcript_ids' in mappings and mappings['entrez_transcript_ids']:
                    alt_ids['Entrez'] = mappings['entrez_transcript_ids']
                
                # Skip if no alternative IDs found
                if not alt_ids:
                    continue
                    
                # Add to updates batch - now including refseq_ids
                updates.append((
                    json.dumps(alt_ids),
                    refseq_ids,  # This is new - pass RefSeq IDs to update the array column
                    transcript_id
                ))
                
                if len(updates) >= self.batch_size:
                    execute_batch(
                        self.db_manager.cursor,
                        """
                        UPDATE cancer_transcript_base
                        SET 
                            alt_transcript_ids = alt_transcript_ids || %s::jsonb,
                            refseq_ids = CASE WHEN %s IS NOT NULL THEN %s ELSE refseq_ids END
                        WHERE transcript_id = %s
                        """,
                        [(json_data, ids, ids, t_id) for json_data, ids, t_id in updates],
                        page_size=self.batch_size
                    )
                    processed += len(updates)
                    pbar.update(len(updates))
                    updates = []
            
            # Process remaining updates
            if updates:
                execute_batch(
                    self.db_manager.cursor,
                    """
                    UPDATE cancer_transcript_base
                    SET 
                        alt_transcript_ids = alt_transcript_ids || %s::jsonb,
                        refseq_ids = CASE WHEN %s IS NOT NULL THEN %s ELSE refseq_ids END
                    WHERE transcript_id = %s
                    """,
                    [(json_data, ids, ids, t_id) for json_data, ids, t_id in updates],
                    page_size=self.batch_size
                )
                processed += len(updates)
                pbar.update(len(updates))
                
            pbar.close()
            update_progress(f"Updated {processed} transcript records with alternative IDs")
            print()  # Move to next line
            
            if self.db_manager.conn:
                self.db_manager.conn.commit()
                
        except Exception as e:
            if self.db_manager.conn:
                self.db_manager.conn.rollback()
            logger.error(f"Error updating transcript IDs: {e}")

    def enrich_transcript_ids(self) -> None:
        """Enrich transcript IDs using various mapping sources."""
        update_progress("Starting transcript ID enrichment...")
        
        # Download and process Ensembl-RefSeq mapping
        ensembl_refseq_file = self.download_ensembl_refseq()
        ensembl_refseq_mappings = self.process_ensembl_refseq(ensembl_refseq_file)
        
        # Download and process Ensembl-Entrez mapping
        ensembl_entrez_file = self.download_ensembl_entrez()
        ensembl_entrez_mappings = self.process_ensembl_entrez(ensembl_entrez_file)
        
        # Merge transcript ID mappings
        transcript_id_mappings = {}
        
        # Start with RefSeq mappings
        for transcript_id, mappings in ensembl_refseq_mappings.items():
            if transcript_id not in transcript_id_mappings:
                transcript_id_mappings[transcript_id] = {}
            transcript_id_mappings[transcript_id].update(mappings)
        
        # Add Entrez mappings
        for transcript_id, mappings in ensembl_entrez_mappings.items():
            if transcript_id not in transcript_id_mappings:
                transcript_id_mappings[transcript_id] = {}
            transcript_id_mappings[transcript_id].update(mappings)
        
        # Update the database with merged mappings
        self.update_transcript_ids(transcript_id_mappings)
        
        update_progress("Transcript ID enrichment completed")
        print()  # Move to next line

    def run(self) -> None:
        """Run the complete ID enrichment pipeline."""
        update_progress("Starting ID enrichment pipeline...")
        print()  # Move to next line since this is a major step
        
        try:
            # Ensure proper database schema
            self._ensure_db_schema()
            
            # Enrich transcript IDs
            self.enrich_transcript_ids()
            
            # Enrich gene IDs
            self.enrich_gene_ids()
            
            # Verify results
            self.verify_id_enrichment()
            
            update_progress("ID enrichment pipeline completed successfully")
            print()  # Move to next line after completion
            
        except Exception as e:
            logger.error(f"ID enrichment failed: {e}")
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
                    COUNT(CASE WHEN array_length(uniprot_ids, 1) > 0 THEN 1 END) as with_uniprot,
                    COUNT(CASE WHEN array_length(ncbi_ids, 1) > 0 THEN 1 END) as with_ncbi,
                    COUNT(CASE WHEN array_length(refseq_ids, 1) > 0 THEN 1 END) as with_refseq,
                    COUNT(CASE WHEN alt_transcript_ids IS NOT NULL 
                               AND alt_transcript_ids != '{}'::jsonb THEN 1 END) as with_alt_transcript_ids,
                    COUNT(CASE WHEN alt_gene_ids ? 'pdb_ids' THEN 1 END) as with_pdb,
                    COUNT(CASE WHEN alt_gene_ids ? 'mim_ids' THEN 1 END) as with_omim,
                    COUNT(CASE WHEN alt_gene_ids ? 'go_terms' THEN 1 END) as with_go_terms,
                    COUNT(CASE WHEN source_references ? 'uniprot' THEN 1 END) as with_uniprot_refs
                FROM cancer_transcript_base
            """)
            
            result = self.db_manager.cursor.fetchone()
            
            if result:
                # For statistics that take multiple lines, use print instead of update_progress
                print("\nID Enrichment Statistics:")
                print(f"- Total genes in database: {result[0]:,}")
                print(f"- Genes with alternative gene IDs: {result[1]:,} ({result[1]/result[0]*100:.1f}%)")
                print(f"- Genes with UniProt IDs: {result[2]:,} ({result[2]/result[0]*100:.1f}%)")
                print(f"- Genes with NCBI IDs: {result[3]:,} ({result[3]/result[0]*100:.1f}%)")
                print(f"- Genes with RefSeq IDs: {result[4]:,} ({result[4]/result[0]*100:.1f}%)")
                print(f"- Transcripts with alternative transcript IDs: {result[5]:,} ({result[5]/result[0]*100:.1f}%)")
                print(f"- Genes with PDB structure IDs: {result[6]:,} ({result[6]/result[0]*100:.1f}%)")
                print(f"- Genes with OMIM disease IDs: {result[7]:,} ({result[7]/result[0]*100:.1f}%)")
                print(f"- Genes with GO terms: {result[8]:,} ({result[8]/result[0]*100:.1f}%)")
                print(f"- Genes with UniProt literature references: {result[9]:,} ({result[9]/result[0]*100:.1f}%)")
                
                # Check coverage redundancy between sources
                self.db_manager.cursor.execute("""
                    SELECT 
                        COUNT(CASE WHEN alt_gene_ids ? 'ensembl_gene_id' AND 
                                    alt_gene_ids ->> 'ensembl_gene_id' IS NOT NULL THEN 1 END) as ensembl_from_alt,
                        COUNT(CASE WHEN alt_gene_ids ? 'refseq_id' AND 
                                    alt_gene_ids ->> 'refseq_id' IS NOT NULL THEN 1 END) as refseq_from_alt
                    FROM cancer_transcript_base
                """)
                
                redundancy = self.db_manager.cursor.fetchone()
                if redundancy:
                    print("\nSource Redundancy Analysis:")
                    print(f"- Genes with Ensembl IDs from alternative sources: {redundancy[0]:,}")
                    print(f"- Genes with RefSeq IDs from alternative sources: {redundancy[1]:,}")
                
        except Exception as e:
            logger.error(f"Error verifying ID enrichment: {e}")
    
    def _ensure_db_schema(self) -> None:
        """Ensure database schema has the required columns for ID enrichment."""
        
        if not self.db_manager.cursor:
            raise RuntimeError("No database connection")
        
        try:
            # Check if required columns exist
            required_columns = [
                'alt_gene_ids',
                'uniprot_ids',
                'ncbi_ids',
                'refseq_ids',
                'alt_transcript_ids',
            ]
            
            for column in required_columns:
                if not self.db_manager.check_column_exists('cancer_transcript_base', column):
                    raise RuntimeError(f"Required column '{column}' missing in schema v0.1.4")
            
            update_progress("Database schema validated for ID enrichment")
            
        except Exception as e:
            logger.error(f"Database schema validation failed: {e}")
            raise

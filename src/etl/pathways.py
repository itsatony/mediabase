"""Pathway enrichment module for Cancer Transcriptome Base."""

import logging
import gzip
import requests
from typing import Dict, List, Optional, Any, Set, Tuple
from pathlib import Path
import hashlib
from datetime import datetime, timedelta
import json
from tqdm import tqdm
from ..db.connection import get_db_connection
from psycopg2.extras import execute_batch

logger = logging.getLogger(__name__)

class PathwayProcessor:
    """Process pathway data and enrich transcript information."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize pathway processor."""
        self.config = config
        self.cache_dir = Path(config['cache_dir']) / 'pathways'
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.batch_size = config.get('batch_size', 1000)
        self.cache_ttl = config.get('cache_ttl', 86400)  # 24 hours default
        
    def _get_cache_key(self, url: str) -> str:
        """Generate a cache key from URL."""
        return hashlib.sha256(url.encode()).hexdigest()

    def download_reactome(self) -> Path:
        """Download Reactome pathway mapping file if not in cache."""
        url = self.config['reactome_data_url']
        cache_key = self._get_cache_key(url)
        file_path = self.cache_dir / f"reactome_{cache_key}.txt"
        meta_path = self.cache_dir / "meta.json"
        
        # Check cache validity
        if file_path.exists() and meta_path.exists():
            try:
                with open(meta_path, 'r') as f:
                    meta = json.load(f)
                if cache_key in meta:
                    cache_time = datetime.fromisoformat(meta[cache_key]['timestamp'])
                    if datetime.now() - cache_time < timedelta(seconds=self.cache_ttl):
                        return file_path
            except (json.JSONDecodeError, KeyError):
                pass

        # Download new file
        logger.info("Downloading Reactome pathway mapping...")
        response = requests.get(url, stream=True)
        total_size = int(response.headers.get('content-length', 0))

        with open(file_path, 'wb') as f, tqdm(
            desc="Downloading",
            total=total_size,
            unit='iB',
            unit_scale=True
        ) as pbar:
            for data in response.iter_content(chunk_size=1024):
                size = f.write(data)
                pbar.update(size)

        # Update metadata
        self._update_cache_meta(cache_key, file_path)
        return file_path

    def _update_cache_meta(self, cache_key: str, file_path: Path) -> None:
        """Update cache metadata."""
        meta_path = self.cache_dir / "meta.json"
        meta = {}
        if meta_path.exists():
            with open(meta_path, 'r') as f:
                try:
                    meta = json.load(f)
                except json.JSONDecodeError:
                    pass

        meta[cache_key] = {
            'timestamp': datetime.now().isoformat(),
            'file_path': str(file_path)
        }

        with open(meta_path, 'w') as f:
            json.dump(meta, f)

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cache is still valid for a given cache_key."""
        meta_path = self.cache_dir / "meta.json"
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

    def process_pathways(self) -> Dict[str, Set[str]]:
        """Process Reactome pathway file and create gene-pathway mappings."""
        file_path = self.download_reactome()
        gene_pathways: Dict[str, Set[str]] = {}
        
        # Initialize counters
        total = 0
        skipped = 0
        non_human = 0
        processed = 0
        unique_pathways = set()
        
        with open(file_path, 'r') as f:
            for line in tqdm(f, desc="Processing pathways"):
                total += 1
                fields = line.strip().split('\t')
                
                try:
                    # We expect exactly 6 fields per line
                    if len(fields) != 6:
                        skipped += 1
                        continue
                        
                    gene_id, pathway_id, _, pathway_name, evidence, species = fields
                    
                    if species != 'Homo sapiens':
                        non_human += 1
                        continue
                    
                    # Log some sample data in debug mode
                    if total <= 5:
                        logger.debug(f"Sample line: gene={gene_id}, pathway={pathway_name}, species={species}")
                        
                    # Standardized format: "Pathway Name [Reactome:ID]"
                    pathway_entry = f"{pathway_name} [Reactome:{pathway_id}]"
                    unique_pathways.add(pathway_entry)
                    
                    processed += 1
                    if gene_id not in gene_pathways:
                        gene_pathways[gene_id] = set()
                    gene_pathways[gene_id].add(pathway_entry)
                    
                except Exception as e:
                    skipped += 1
                    logger.debug(f"Skipping malformed line: {line[:100]}... Error: {e}")
                    continue
        
        logger.info(
            f"Pathway processing completed:\n"
            f"- Total lines processed: {total:,}\n"
            f"- Non-human entries: {non_human:,}\n"
            f"- Lines skipped: {skipped:,}\n"
            f"- Valid entries processed: {processed:,}\n"
            f"- Unique pathways found: {len(unique_pathways):,}\n"
            f"- Genes with annotations: {len(gene_pathways):,}"
        )
        
        # Log sample of gene-pathway mappings
        if gene_pathways:
            sample_gene = next(iter(gene_pathways))
            logger.info(
                f"\nSample gene-pathway mapping for {sample_gene}:\n"
                f"Number of pathways: {len(gene_pathways[sample_gene])}\n"
                f"First few pathways:\n" + 
                "\n".join(list(gene_pathways[sample_gene])[:3])
            )
        
        return gene_pathways

    def _download_id_mapping(self) -> Path:
        """Download NCBI to Ensembl ID mapping file."""
        mapping_url = "https://ftp.ncbi.nlm.nih.gov/gene/DATA/gene2ensembl.gz"
        cache_key = self._get_cache_key(mapping_url)
        file_path = self.cache_dir / f"gene2ensembl_{cache_key}.txt.gz"
        
        if file_path.exists() and self._is_cache_valid(cache_key):
            return file_path
            
        logger.info("Downloading NCBI to Ensembl ID mapping...")
        response = requests.get(mapping_url, stream=True)
        total_size = int(response.headers.get('content-length', 0))

        with open(file_path, 'wb') as f, tqdm(
            desc="Downloading ID mapping",
            total=total_size,
            unit='iB',
            unit_scale=True
        ) as pbar:
            for data in response.iter_content(chunk_size=1024):
                size = f.write(data)
                pbar.update(size)
                
        self._update_cache_meta(cache_key, file_path)
        return file_path

    def _load_id_mapping(self) -> Dict[str, str]:
        """Load NCBI to Ensembl gene ID mapping."""
        file_path = self._download_id_mapping()
        mapping: Dict[str, str] = {}
        
        logger.info("Processing ID mapping file...")
        with gzip.open(file_path, 'rt') as f:
            # Skip header
            next(f)
            for line in tqdm(f, desc="Loading ID mappings"):
                fields = line.strip().split('\t')
                if len(fields) >= 3 and fields[0] == '9606':  # Human only
                    ncbi_id = fields[1]
                    ensembl_id = fields[2].split('.')[0]  # Remove version
                    mapping[ncbi_id] = ensembl_id
        
        logger.info(f"Loaded {len(mapping):,} NCBI to Ensembl ID mappings")
        return mapping

    def _get_ncbi_mapping(self, cur) -> Dict[str, str]:
        """Get mapping between NCBI gene IDs and gene IDs."""
        # First, get all gene IDs from database
        cur.execute("""
            SELECT DISTINCT gene_id, gene_symbol 
            FROM cancer_transcript_base 
            WHERE gene_type = 'protein_coding'
        """)
        db_genes: Dict[str, str] = {}
        for raw_gene_id, gene_symbol in cur.fetchall():
            # Fix: strip version from Ensembl gene IDs for matching
            canonical_id = raw_gene_id.split('.')[0]
            db_genes[canonical_id] = gene_symbol
        
        # Load NCBI to Ensembl mapping
        id_mapping = self._load_id_mapping()
        
        # Create final mapping (NCBI ID -> gene_symbol)
        final_mapping = {}
        for ncbi_id, ensembl_id in id_mapping.items():
            if ensembl_id in db_genes:
                final_mapping[ncbi_id] = db_genes[ensembl_id]
        
        # Log mapping statistics
        logger.info(
            f"ID mapping stats:\n"
            f"- Database genes: {len(db_genes):,}\n"
            f"- NCBI to Ensembl mappings: {len(id_mapping):,}\n"
            f"- Final matched genes: {len(final_mapping):,}"
        )
        
        if not final_mapping:
            logger.warning(
                "No ID mappings found. This might indicate we need to:\n"
                "1. Check gene_id format in database\n"
                "2. Update ID mapping source\n"
                "3. Verify ID mapping process"
            )
        else:
            # Log sample mappings
            sample = list(final_mapping.items())[:5]
            logger.info(
                "Sample ID mappings:\n" +
                "\n".join(f"NCBI:{ncbi} -> {symbol}" for ncbi, symbol in sample)
            )
            
        return final_mapping

    def enrich_transcripts(self) -> None:
        """Enrich transcript data with pathway information."""
        gene_pathways = self.process_pathways()
        
        if not gene_pathways:
            logger.warning("No pathway data to process!")
            return
            
        conn = get_db_connection(self.config)
        try:
            with conn.cursor() as cur:
                # Get current database state
                cur.execute("""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(CASE WHEN pathways IS NOT NULL AND array_length(pathways, 1) > 0 THEN 1 END) as with_pathways
                    FROM cancer_transcript_base 
                    WHERE gene_type = 'protein_coding'
                """)
                before_stats = cur.fetchone()
                if before_stats:
                    logger.info(
                        f"\nBefore enrichment:\n"
                        f"- Total genes in DB: {before_stats[0]:,}\n"
                        f"- Genes with pathways: {before_stats[1]:,}"
                    )
                else:
                    logger.warning("No data found in the database for enrichment statistics.")
                
                # Get NCBI ID to gene symbol mapping
                ncbi_mapping = self._get_ncbi_mapping(cur)
                
                # Sample of mappings for verification
                sample_mappings = list(ncbi_mapping.items())[:5]
                logger.info(
                    f"\nSample NCBI ID mappings:\n" + 
                    "\n".join(f"NCBI:{ncbi} -> {symbol}" for ncbi, symbol in sample_mappings)
                )
                
                # Now map pathways using NCBI IDs
                updates = []
                processed = 0
                matched = 0
                
                for ncbi_id, pathways in gene_pathways.items():
                    if ncbi_id in ncbi_mapping:
                        matched += 1
                        gene_symbol = ncbi_mapping[ncbi_id]
                        pathway_list = list(pathways)
                        updates.append((pathway_list, gene_symbol))
                        
                        if len(updates) >= self.batch_size:
                            self._update_batch(cur, updates)
                            conn.commit()
                            processed += len(updates)
                            updates = []
                
                if updates:
                    self._update_batch(cur, updates)
                    conn.commit()
                    processed += len(updates)
                    
                # Log statistics with better error handling
                cur.execute("""
                    SELECT 
                        COUNT(*) as total_genes,
                        COUNT(CASE WHEN array_length(pathways, 1) > 0 THEN 1 END) as with_pathways,
                        COALESCE(AVG(array_length(pathways, 1)), 0) as avg_pathways
                    FROM cancer_transcript_base
                    WHERE gene_type = 'protein_coding'
                """)
                stats = cur.fetchone()
                
                if stats:
                    logger.info(
                        f"\nEnrichment Results:\n"
                        f"- Total genes processed: {stats[0]:,}\n"
                        f"- NCBI IDs matched: {matched:,}\n"
                        f"- Updates processed: {processed:,}\n"
                        f"- Final genes with pathways: {stats[1]:,}\n"
                        f"- Average pathways per gene: {stats[2]:.1f}"
                    )
                    
                    # Sample verification
                    cur.execute("""
                        SELECT gene_symbol, pathways, gene_id 
                        FROM cancer_transcript_base 
                        WHERE array_length(pathways, 1) > 0 
                        LIMIT 1
                    """)
                    sample = cur.fetchone()
                    if sample:
                        logger.info(
                            f"\nSample gene with pathways:\n"
                            f"Gene: {sample[0]} (ID: {sample[2]})\n"
                            f"Number of pathways: {len(sample[1])}\n"
                            f"First pathway: {sample[1][0] if sample[1] else 'None'}"
                        )
                    
        except Exception as e:
            logger.error(f"Pathway enrichment failed: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

    def _update_batch(self, cur, updates: List[Tuple[List[str], str]]) -> None:
        """Update a batch of pathway data."""
        logger.debug(f"Processing batch update with {len(updates)} entries")
        
        # Show sample of updates
        if updates and logger.level <= logging.DEBUG:
            sample = updates[0]
            logger.debug(
                f"Sample update:\n"
                f"Gene Symbol: {sample[1]}\n"
                f"Pathway count: {len(sample[0])}\n"
                f"First pathway: {sample[0][0] if sample[0] else 'None'}"
            )
        
        execute_batch(
            cur,
            """
            UPDATE cancer_transcript_base
            SET pathways = %s
            WHERE gene_symbol = %s
            AND gene_type = 'protein_coding'
            RETURNING gene_symbol, array_length(pathways, 1) as pathway_count
            """,
            updates
        )

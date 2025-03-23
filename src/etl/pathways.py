"""Pathway enrichment module for Cancer Transcriptome Base."""

import logging
import gzip
import requests
from typing import Dict, List, Optional, Any, Set, Tuple
from pathlib import Path
import hashlib
from datetime import datetime, timedelta
import json
import re  # Add missing import for regex
from tqdm import tqdm
from ..db.database import get_db_manager
from ..etl.publications import Publication, PublicationsProcessor
from ..utils.publication_utils import extract_pmid_from_text
from ..utils.publication_utils import extract_pmids_from_text, format_pmid_url
from psycopg2.extras import execute_batch

logger = logging.getLogger(__name__)

# Constants
DEFAULT_CACHE_TTL = 86400  # 24 hours in seconds
DEFAULT_BATCH_SIZE = 1000
HUMAN_SPECIES = 'Homo sapiens'
ID_MAPPING_BATCH_SIZE = 200  # Batch size for id mapping
HUMAN_TAXONOMY_ID = '9606'  # NCBI taxonomy ID for humans

class PathwayProcessor:
    """Process pathway data and enrich transcript information."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize pathway processor."""
        self.config = config
        self.cache_dir = Path(config.get('cache_dir', '/tmp/mediabase/cache')) / 'pathways'
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.batch_size = config.get('batch_size', DEFAULT_BATCH_SIZE)
        self.cache_ttl = config.get('cache_ttl', DEFAULT_CACHE_TTL)
        self.db_manager = get_db_manager(config)
        
    def _get_cache_key(self, url: str) -> str:
        """Generate a cache key from URL."""
        return hashlib.sha256(url.encode()).hexdigest()

    def download_reactome(self) -> Path:
        """Download Reactome pathway mapping file if not in cache."""
        url = self.config.get('reactome_url')
        if not url:
            raise ValueError("Reactome URL not configured")
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
        
        # Track pathway-publication mappings
        pathway_publications: Dict[str, List[Publication]] = {}
        
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
                    
                    # Safely access fields with bounds checking
                    if len(fields) >= 6:
                        gene_id = fields[0]
                        pathway_id = fields[1]
                        pathway_name = fields[3]
                        evidence = fields[4]
                        species = fields[5]
                    else:
                        skipped += 1
                        continue
                        
                    if species != HUMAN_SPECIES:
                        non_human += 1
                        continue
                    
                    # Log some sample data in debug mode
                    if total <= 5:
                        logger.debug(f"Sample line: gene={gene_id}, pathway={pathway_name}, species={species}")
                        
                    # Standardized format: "Pathway Name [Reactome:ID]"
                    pathway_entry = f"{pathway_name} [Reactome:{pathway_id}]"
                    unique_pathways.add(pathway_entry)
                    
                    # Extract publication references if evidence field contains PMID info
                    if pathway_id not in pathway_publications:
                        pathway_publications[pathway_id] = self._extract_pathway_publications(evidence, pathway_id)
                    
                    processed += 1
                    if gene_id not in gene_pathways:
                        gene_pathways[gene_id] = set()
                    gene_pathways[gene_id].add(pathway_entry)
                    
                except Exception as e:
                    skipped += 1
                    logger.debug(f"Skipping malformed line: {line[:100]}... Error: {e}")
                    continue
        
        # Store pathway publications for later use
        self._save_pathway_publications(pathway_publications)
        
        logger.info(
            f"Pathway processing completed:\n"
            f"- Total lines processed: {total:,}\n"
            f"- Non-human entries: {non_human:,}\n"
            f"- Lines skipped: {skipped:,}\n"
            f"- Valid entries processed: {processed:,}\n"
            f"- Unique pathways found: {len(unique_pathways):,}\n"
            f"- Genes with annotations: {len(gene_pathways):,}\n"
            f"- Pathways with publication references: {len(pathway_publications):,}"
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

    def _extract_pathway_publications(self, evidence: str, pathway_id: str) -> List[Publication]:
        """Extract publication references from pathway evidence data.
        
        Args:
            evidence: Evidence string from Reactome
            pathway_id: Reactome pathway ID
            
        Returns:
            List of Publication references
        """
        publications: List[Publication] = []
        
        # Check if evidence field contains a PMID
        pmid = extract_pmid_from_text(evidence)
        if pmid:
            publication = PublicationsProcessor.create_publication_reference(
                pmid=pmid,
                evidence_type="Reactome",
                source_db="Reactome"
            )
            publications.append(publication)
        
        # If no direct PMID, try the Reactome API to get publications
        # This is a placeholder - in a real implementation you would
        # query the Reactome API for pathway publications
        if not publications:
            # For demonstration, we'll create a reference with just the pathway ID
            reference = PublicationsProcessor.create_publication_reference(
                pmid=None,
                evidence_type=f"Reactome:{pathway_id}",
                source_db="Reactome"
            )
            publications.append(reference)
            
        return publications

    def _save_pathway_publications(self, pathway_publications: Dict[str, List[Publication]]) -> None:
        """Save pathway publication mappings to cache for reuse.
        
        Args:
            pathway_publications: Mapping of pathway IDs to publications
        """
        cache_file = self.cache_dir / "pathway_publications.json"
        
        # Convert Publications to serializable format
        serializable = {}
        for pathway_id, pubs in pathway_publications.items():
            serializable[pathway_id] = [dict(p) for p in pubs]
            
        with open(cache_file, 'w') as f:
            json.dump(serializable, f)
            
        logger.info(f"Saved {len(pathway_publications)} pathway publication references to {cache_file}")

    def _load_pathway_publications(self) -> Dict[str, List[Publication]]:
        """Load pathway publication mappings from cache.
        
        Returns:
            Mapping of pathway IDs to publications
        """
        cache_file = self.cache_dir / "pathway_publications.json"
        
        if not cache_file.exists():
            return {}
            
        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)
                
            # Convert back to Publication objects
            result = {}
            for pathway_id, pubs in data.items():
                result[pathway_id] = [Publication(**p) for p in pubs]
                
            logger.info(f"Loaded {len(result)} pathway publication references from cache")
            return result
        except Exception as e:
            logger.error(f"Error loading pathway publications: {e}")
            return {}

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
                if len(fields) >= 3 and fields[0] == HUMAN_TAXONOMY_ID:  # Human only
                    ncbi_id = fields[1]
                    ensembl_id = fields[2].split('.')[0]  # Remove version
                    mapping[ncbi_id] = ensembl_id
        
        logger.info(f"Loaded {len(mapping):,} NCBI to Ensembl ID mappings")
        return mapping

    def _get_ncbi_mapping(self, cur) -> Dict[str, str]:
        """Get mapping between NCBI gene IDs and gene IDs."""
        # First, get all gene IDs from database
        if not cur:
            raise RuntimeError("No database cursor provided")
            
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
            
        # Improved connection handling
        if not self.db_manager.ensure_connection():
            logger.info("Establishing database connection for pathway enrichment...")
            if not self.db_manager.ensure_connection():
                raise RuntimeError("Failed to establish database connection for pathway enrichment")
            if not self.db_manager.cursor:
                raise RuntimeError("Could not create database cursor for pathway enrichment")
            
        try:
            cur = self.db_manager.cursor
            if not cur:
                raise RuntimeError("Database cursor is None")
                
            # Get initial statistics
            cur.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN pathways IS NOT NULL AND array_length(pathways, 1) > 0 
                         THEN 1 END) as with_pathways
                FROM cancer_transcript_base 
                WHERE gene_type = 'protein_coding'
            """)
            before_stats = cur.fetchone() if cur and not cur.closed else None
            if before_stats:
                logger.info(
                    f"\nBefore enrichment:\n"
                    f"- Total genes in DB: {before_stats[0]:,}\n"
                    f"- Genes with pathways: {before_stats[1]:,}"
                )
            else:
                logger.warning("No data found in the database for enrichment statistics.")
            
            # Get NCBI ID to gene symbol mapping
            if not cur or cur.closed:
                if not self.db_manager.ensure_connection():
                    raise RuntimeError("Lost database connection before mapping gene IDs")
                cur = self.db_manager.cursor
                if not cur:
                    raise RuntimeError("Could not create database cursor after connection refresh")
                    
            ncbi_mapping = self._get_ncbi_mapping(cur)
            
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
                        # Verify connection before batch update
                        if not self.db_manager.ensure_connection():
                            logger.warning("Connection lost during pathway batch update, reconnecting...")
                            if not self.db_manager.ensure_connection():
                                raise RuntimeError("Failed to reestablish database connection")
                            cur = self.db_manager.cursor
                            if not cur:
                                raise RuntimeError("Could not create database cursor after reconnection")
                        
                        self._update_batch(cur, updates)
                        if self.db_manager.conn and not self.db_manager.conn.closed:
                            self.db_manager.conn.commit()
                        processed += len(updates)
                        updates = []
            
            if updates:
                # Verify connection before final update
                if not self.db_manager.ensure_connection():
                    logger.warning("Connection lost before final pathway update, reconnecting...")
                    if not self.db_manager.ensure_connection():
                        raise RuntimeError("Failed to reestablish database connection")
                    cur = self.db_manager.cursor
                    if not cur:
                        raise RuntimeError("Could not create database cursor after reconnection")
                        
                self._update_batch(cur, updates)
                if self.db_manager.conn and not self.db_manager.conn.closed:
                    self.db_manager.conn.commit()
                processed += len(updates)
                    
                # Log statistics with better error handling
                # Verify connection before statistics query
                if not self.db_manager.ensure_connection():
                    logger.warning("Connection lost before collecting statistics, reconnecting...")
                    if not self.db_manager.ensure_connection():
                        logger.error("Failed to reestablish database connection, skipping statistics")
                        return
                    cur = self.db_manager.cursor
                    if not cur:
                        logger.error("Could not create database cursor, skipping statistics")
                        return
                    
            # Final statistics query
            if cur and not cur.closed:
                cur.execute("""
                    SELECT 
                        COUNT(*) as total_genes,
                        COUNT(CASE WHEN array_length(pathways, 1) > 0 THEN 1 END) as with_pathways,
                        COALESCE(AVG(array_length(pathways, 1)), 0) as avg_pathways
                    FROM cancer_transcript_base
                    WHERE gene_type = 'protein_coding'
                """)
                stats = cur.fetchone() if cur and not cur.closed else None
                
                if stats:
                    logger.info(
                        f"\nEnrichment Results:\n"
                        f"- Total genes processed: {stats[0]:,}\n"
                        f"- NCBI IDs matched: {matched:,}\n"
                        f"- Updates processed: {processed:,}\n"
                        f"- Final genes with pathways: {stats[1]:,}\n"
                        f"- Average pathways per gene: {stats[2]:.1f}"
                    )
                    
            else:
                logger.warning("Unable to collect final statistics - cursor is not available")
                    
        except Exception as e:
            logger.error(f"Pathway enrichment failed: {e}")
            if self.db_manager.conn and not self.db_manager.conn.closed:
                self.db_manager.conn.rollback()
            raise

    def _update_batch(self, cur, updates: List[Tuple[List[str], str]]) -> None:
        """Update a batch of pathway data."""
        logger.debug(f"Processing batch update with {len(updates)} entries")
        
        # Get pathway publications
        pathway_publications = self._load_pathway_publications()
        
        # Update one gene at a time to avoid array formatting issues
        for pathway_list, gene_symbol in updates:
            try:
                # Update pathways
                cur.execute(
                    """
                    UPDATE cancer_transcript_base
                    SET pathways = %s
                    WHERE gene_symbol = %s
                    AND gene_type = 'protein_coding'
                    """,
                    (pathway_list, gene_symbol)
                )
                
                # Extract pathway IDs from pathway_list
                pathway_ids = []
                for pathway in pathway_list:
                    # Extract Reactome ID from format "Pathway Name [Reactome:R-HSA-123456]"
                    match = re.search(r'\[Reactome:(.*?)\]', pathway)
                    if match:
                        pathway_ids.append(match.group(1))
                
                # Collect publication references for these pathways
                references = []
                for pathway_id in pathway_ids:
                    if pathway_id in pathway_publications:
                        references.extend(pathway_publications[pathway_id])
                
                # Update publication references if we found any
                if references:
                    pub_json = json.dumps([dict(ref) for ref in references])
                    cur.execute(
                        """
                        UPDATE cancer_transcript_base
                        SET source_references = jsonb_set(
                            COALESCE(source_references, '{}'::jsonb),
                            '{pathways}',
                            COALESCE(source_references->'pathways', '[]'::jsonb) || %s::jsonb
                        )
                        WHERE gene_symbol = %s
                        """,
                        (pub_json, gene_symbol)
                    )
                
            except Exception as e:
                logger.error(f"Error updating pathways for {gene_symbol}: {e}")
                # Continue with other genes
                continue

    def run(self) -> None:
        """Run the complete pathway enrichment pipeline.
        
        This method orchestrates:
        1. Download and process Reactome data
        2. Map gene IDs
        3. Enrich transcripts with pathway information
        4. Update source references
        """
        try:
            logger.info("Starting pathway enrichment pipeline...")
            
            # More thorough connection management
            if not self.db_manager.ensure_connection():
                logger.info("Establishing initial database connection for pathway pipeline...")
                if not self.db_manager.ensure_connection():
                    raise RuntimeError("Failed to establish database connection")
                if not self.db_manager.cursor:
                    raise RuntimeError("Could not create database cursor")
            
            cursor = self.db_manager.cursor
            if not cursor:
                raise RuntimeError("Database cursor is None after connection check")
                
            # Check schema version
            cursor.execute("SELECT version FROM schema_version")
            version = cursor.fetchone() if cursor and not cursor.closed else None
            if not version:
                raise RuntimeError("Could not determine schema version")
                
            if version[0] != 'v0.1.4':
                logger.info(f"Current schema version {version[0]} needs update to v0.1.4")
                if not self.db_manager.migrate_to_version('v0.1.4'):
                    raise RuntimeError("Failed to migrate database schema to v0.1.4")
                logger.info("Schema successfully updated to v0.1.4")
                
            # Verify required columns exist
            required_columns = [
                'pathways',
                'source_references',
                'gene_symbol',
                'gene_type'
            ]
                
            for column in required_columns:
                if not self.db_manager.check_column_exists('cancer_transcript_base', column):
                    raise RuntimeError(
                        f"Required column '{column}' missing. "
                        "Schema must be properly upgraded to v0.1.4"
                    )
            
            # Run enrichment after schema verification
            self.enrich_transcripts()
            
            # Verify connection before verification
            cursor = None
            if not self.db_manager.ensure_connection():
                logger.warning("Connection lost after pathway enrichment, reconnecting for verification...")
                if not self.db_manager.ensure_connection():
                    logger.error("Failed to reestablish connection for verification, skipping verification step")
                    return
                
            cursor = self.db_manager.cursor
            if not cursor:
                logger.error("No database cursor available for verification")
                return
                
            # Verify results
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN pathways IS NOT NULL 
                          AND array_length(pathways, 1) > 0 THEN 1 END) as with_pathways,
                    COUNT(CASE WHEN source_references->'pathways' != '[]'::jsonb 
                          THEN 1 END) as with_refs
                FROM cancer_transcript_base
            """)
            stats = cursor.fetchone() if cursor and not cursor.closed else None
            if stats:
                logger.info(
                    f"Pipeline completed:\n"
                    f"- Total records: {stats[0]:,}\n"
                    f"- Records with pathways: {stats[1]:,}\n"
                    f"- Records with pathway references: {stats[2]:,}"
                )
            
        except Exception as e:
            logger.error(f"Pathway enrichment pipeline failed: {e}")
            if self.db_manager.conn and not self.db_manager.conn.closed:
                self.db_manager.conn.rollback()
            raise
        finally:
            # Only close the connection here, at the end of the entire pipeline
            if self.db_manager.conn and not self.db_manager.conn.closed:
                logger.debug("Closing database connection at end of pathway pipeline")
                self.db_manager.conn.close()

    def extract_pathway_references(self, pathway_data: Dict[str, Any]) -> List[Publication]:
        """Extract publication references from pathway data."""
        publications: List[Publication] = []
        
        # Extract PMIDs from pathway evidence text
        evidence_text = pathway_data.get('evidence', '')
        pmids = extract_pmids_from_text(evidence_text)
        
        for pmid in pmids:
            publication = PublicationsProcessor.create_publication_reference(
                pmid=pmid,
                evidence_type="pathway_association",
                source_db="Reactome",
                url=format_pmid_url(pmid)
            )
            publications.append(publication)
        
        return publications

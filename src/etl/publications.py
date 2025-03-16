"""Publications processing module for Cancer Transcriptome Base."""

import logging
from typing import Dict, List, Optional, Any, Set, TypedDict, cast, Union
import json
from datetime import datetime
import requests
import time
from tqdm import tqdm
from pathlib import Path
import os
import gzip
import hashlib
from ..db.database import get_db_manager
from psycopg2.extras import execute_batch

logger = logging.getLogger(__name__)

# Constants for PubMed API
PUBMED_API_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PUBMED_BATCH_SIZE = 200  # Max recommended by NCBI for single request
PUBMED_RATE_LIMIT = 0.34  # ~3 requests per second (adjust to 0.1 with API key)
DEFAULT_CACHE_TTL = 2592000  # 30 days in seconds for publications (much longer than other data)

class Publication(TypedDict, total=False):
    """Type definition for publication reference data.
    
    Attributes:
        pmid: PubMed ID
        title: Publication title
        abstract: Publication abstract
        year: Publication year
        journal: Journal name
        authors: List of author names
        evidence_type: Type of evidence (experimental, computational, review, etc.)
        citation_count: Number of citations
        source_db: Source database (go_terms, uniprot, drugs, pathways)
        doi: Digital Object Identifier
        url: URL to the publication
    """
    pmid: str
    title: Optional[str]
    abstract: Optional[str]
    year: Optional[int]
    journal: Optional[str]
    authors: Optional[List[str]]
    evidence_type: str
    citation_count: Optional[int]
    source_db: str
    doi: Optional[str]
    url: Optional[str]

class PublicationsProcessor:
    """Process and enrich publication references."""
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize publications processor.
        
        Args:
            config: Configuration dictionary containing:
                - pubmed_api_key: NCBI E-utilities API key (optional)
                - pubmed_email: Contact email for API (required)
                - batch_size: Size of batches for processing
                - cache_dir: Directory for caching publication data
                - rate_limit: Wait time between API requests in seconds
                - force_refresh: Force refresh all publication data
        """
        self.config = config
        self.db_manager = get_db_manager(config)
        self.batch_size = config.get('batch_size', 100)
        self.api_key = config.get('pubmed_api_key')
        self.email = config.get('pubmed_email')
        
        # Set up cache directory
        self.cache_dir = Path(config.get('cache_dir', '/tmp/mediabase/cache')) / 'publications'
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "pubmed_cache.json.gz"
        self.cache_meta_file = self.cache_dir / "pubmed_cache_meta.json"
        
        # Rate limiting configuration
        self.rate_limit = config.get('rate_limit', PUBMED_RATE_LIMIT)
        if self.api_key:
            # Faster rate limit with API key
            self.rate_limit = min(self.rate_limit, 0.1)  # 10 requests per second max with API key
            
        # Force refresh flag
        self.force_refresh = config.get('force_refresh', False)
        
        # Initialize cache
        self.publication_cache = self._load_cache()
        
        # Validate email (required by NCBI)
        if not self.email:
            logger.warning("PubMed API requires an email address. Set MB_PUBMED_EMAIL environment variable.")
    
    def _load_cache(self) -> Dict[str, Dict[str, Any]]:
        """Load publication cache from file.
        
        Returns:
            Dictionary mapping PMIDs to publication metadata
        """
        cache: Dict[str, Dict[str, Any]] = {}
        
        if self.cache_file.exists() and not self.force_refresh:
            try:
                with gzip.open(self.cache_file, 'rt') as f:
                    cache = json.load(f)
                logger.info(f"Loaded {len(cache)} cached publications from {self.cache_file}")
            except Exception as e:
                logger.warning(f"Failed to load publication cache: {e}")
                # Create a new cache file if the existing one is corrupt
                self._save_cache(cache)
        
        return cache
    
    def _save_cache(self, cache: Dict[str, Dict[str, Any]]) -> None:
        """Save publication cache to file.
        
        Args:
            cache: Dictionary mapping PMIDs to publication metadata
        """
        try:
            with gzip.open(self.cache_file, 'wt') as f:
                json.dump(cache, f)
                
            # Update cache metadata
            meta = {
                'timestamp': datetime.now().isoformat(),
                'count': len(cache)
            }
            with open(self.cache_meta_file, 'w') as f:
                json.dump(meta, f)
                
            logger.info(f"Saved {len(cache)} publications to cache")
        except Exception as e:
            logger.error(f"Failed to save publication cache: {e}")
    
    @staticmethod
    def create_publication_reference(
        pmid: Optional[str] = None,
        evidence_type: str = "unknown",
        source_db: str = "unknown"
    ) -> Publication:
        """Create a publication reference with minimal required fields.
        
        Args:
            pmid: PubMed ID
            evidence_type: Type of evidence
            source_db: Source database
            
        Returns:
            Publication: A new publication reference
        """
        reference: Publication = {
            "pmid": pmid or "",
            "evidence_type": evidence_type,
            "source_db": source_db
        }
        return reference
    
    def add_reference_to_transcript(
        self,
        transcript_id: str,
        reference: Publication,
        source_category: str
    ) -> bool:
        """Add a publication reference to a transcript.
        
        Args:
            transcript_id: Transcript ID
            reference: Publication reference
            source_category: Source category (go_terms, uniprot, drugs, pathways)
            
        Returns:
            bool: True if successful
        """
        if not self.db_manager.cursor:
            logger.error("No database connection")
            return False
            
        try:
            # Get current references
            self.db_manager.cursor.execute("""
                SELECT source_references 
                FROM cancer_transcript_base
                WHERE transcript_id = %s
            """, (transcript_id,))
            
            result = self.db_manager.cursor.fetchone()
            if not result:
                logger.warning(f"Transcript {transcript_id} not found")
                return False
                
            source_refs = result[0] or {}
            
            # Add new reference to appropriate category
            if source_category not in source_refs:
                source_refs[source_category] = []
                
            # Check if reference already exists (by PMID)
            if reference.get("pmid"):
                existing_refs = [ref for ref in source_refs.get(source_category, [])
                                if ref.get("pmid") == reference.get("pmid")]
                if existing_refs:
                    # Update existing reference
                    for ref in source_refs[source_category]:
                        if ref.get("pmid") == reference.get("pmid"):
                            ref.update({k: v for k, v in reference.items() if v is not None})
                    updated_refs = source_refs[source_category]
                else:
                    # Add new reference
                    updated_refs = source_refs[source_category] + [reference]
            else:
                # Add new reference without PMID
                updated_refs = source_refs[source_category] + [reference]
                
            source_refs[source_category] = updated_refs
            
            # Update database
            self.db_manager.cursor.execute("""
                UPDATE cancer_transcript_base
                SET source_references = %s
                WHERE transcript_id = %s
            """, (json.dumps(source_refs), transcript_id))
            
            if self.db_manager.conn:
                self.db_manager.conn.commit()
                
            return True
            
        except Exception as e:
            logger.error(f"Failed to add reference: {e}")
            if self.db_manager.conn:
                self.db_manager.conn.rollback()
            return False
        
    def _fetch_pubmed_metadata(self, pmids: Set[str]) -> Dict[str, Dict[str, Any]]:
        """Fetch metadata for PubMed IDs using E-utilities with caching.
        
        Args:
            pmids: Set of PubMed IDs to fetch
            
        Returns:
            Dictionary mapping PMIDs to their metadata
        """
        # First, filter out PMIDs already in cache (unless force_refresh)
        pmids_to_fetch = set()
        result_metadata: Dict[str, Dict[str, Any]] = {}
        
        for pmid in pmids:
            if pmid in self.publication_cache and not self.force_refresh:
                result_metadata[pmid] = self.publication_cache[pmid]
            else:
                pmids_to_fetch.add(pmid)
        
        if not pmids_to_fetch:
            logger.info("All requested publications found in cache")
            return result_metadata
            
        logger.info(f"Fetching {len(pmids_to_fetch)} publications from PubMed")
        
        # Validate required parameters
        if not self.email:
            logger.error("Email is required for PubMed API")
            return result_metadata
            
        try:
            # Process in batches of PUBMED_BATCH_SIZE with rate limiting
            pmid_list = list(pmids_to_fetch)
            
            with tqdm(total=len(pmid_list), desc="Fetching PubMed data") as pbar:
                for i in range(0, len(pmid_list), PUBMED_BATCH_SIZE):
                    batch = pmid_list[i:i + PUBMED_BATCH_SIZE]
                    
                    # Prepare API parameters
                    api_params = {
                        'db': 'pubmed',
                        'tool': 'mediabase',
                        'email': self.email,
                        'retmode': 'json',
                    }
                    
                    # Add API key if available
                    if self.api_key:
                        api_params['api_key'] = self.api_key
                    
                    # First get summary data with retries
                    summary_data = {}
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            summary_params = api_params.copy()
                            summary_params['id'] = ','.join(batch)
                            
                            summary_response = requests.get(
                                f"{PUBMED_API_BASE}/esummary.fcgi", 
                                params=summary_params,
                                timeout=30  # Add timeout to avoid hanging
                            )
                            
                            if summary_response.status_code == 200:
                                data = summary_response.json()
                                summary_data = data
                                break
                            elif summary_response.status_code == 429:  # Too Many Requests
                                wait_time = int(summary_response.headers.get('Retry-After', 60))
                                logger.warning(f"Rate limited by PubMed API. Waiting {wait_time} seconds.")
                                time.sleep(wait_time)
                            else:
                                logger.warning(f"PubMed API error: {summary_response.status_code}")
                                time.sleep(2 ** attempt)  # Exponential backoff
                        except requests.RequestException as e:
                            logger.warning(f"PubMed API request failed: {e}")
                            time.sleep(2 ** attempt)  # Exponential backoff
                    
                    # Process summary data
                    batch_metadata = {}
                    if summary_data and 'result' in summary_data:
                        for pmid, article in summary_data.get('result', {}).items():
                            if pmid != 'uids':
                                try:
                                    pub_date = article.get('pubdate', '')
                                    year = None
                                    if pub_date:
                                        # Handle different date formats
                                        year_part = pub_date.split()[0]
                                        if year_part.isdigit():
                                            year = int(year_part)
                                    
                                    authors = []
                                    if 'authors' in article:
                                        authors = [author.get('name', '') 
                                                for author in article.get('authors', [])]
                                    
                                    batch_metadata[pmid] = {
                                        'year': year,
                                        'citation_count': None,
                                        'title': article.get('title', ''),
                                        'journal': article.get('source', ''),
                                        'authors': authors,
                                        'doi': article.get('elocationid', '').replace('doi: ', '') if article.get('elocationid', '').startswith('doi: ') else article.get('doi', ''),
                                        'url': f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                                    }
                                except Exception as e:
                                    logger.debug(f"Error processing PMID {pmid}: {e}")
                                    continue
                    
                    # Apply rate limiting before next request
                    time.sleep(self.rate_limit)
                    
                    # Then get abstracts using efetch with retries
                    for attempt in range(max_retries):
                        try:
                            abstract_params = api_params.copy()
                            abstract_params['id'] = ','.join(batch)
                            abstract_params['rettype'] = 'abstract'
                            
                            abstract_response = requests.get(
                                f"{PUBMED_API_BASE}/efetch.fcgi", 
                                params=abstract_params,
                                timeout=30
                            )
                            
                            if abstract_response.status_code == 200:
                                # efetch returns XML by default
                                try:
                                    from lxml import etree
                                    
                                    xml_parser = etree.XMLParser(recover=True)
                                    root = etree.fromstring(abstract_response.content, parser=xml_parser)
                                    
                                    for article in root.xpath('//PubmedArticle'):
                                        try:
                                            pmid_nodes = article.xpath('.//PMID/text()')
                                            article_pmid = pmid_nodes[0] if pmid_nodes else None
                                            
                                            if article_pmid and article_pmid in batch_metadata:
                                                # Extract abstract text
                                                abstract_texts = article.xpath('.//AbstractText/text()')
                                                if abstract_texts:
                                                    batch_metadata[article_pmid]['abstract'] = ' '.join(abstract_texts)
                                                    
                                        except (IndexError, KeyError) as e:
                                            logger.debug(f"Error extracting abstract: {e}")
                                            continue
                                except ImportError:
                                    logger.warning("lxml not available for XML parsing. Abstracts will not be included.")
                                except Exception as e:
                                    logger.debug(f"Error parsing XML: {e}")
                                    
                                break
                            elif abstract_response.status_code == 429:  # Too Many Requests
                                wait_time = int(abstract_response.headers.get('Retry-After', 60))
                                logger.warning(f"Rate limited by PubMed API. Waiting {wait_time} seconds.")
                                time.sleep(wait_time)
                            else:
                                logger.warning(f"PubMed API error: {abstract_response.status_code}")
                                time.sleep(2 ** attempt)  # Exponential backoff
                        except requests.RequestException as e:
                            logger.warning(f"PubMed API request failed: {e}")
                            time.sleep(2 ** attempt)  # Exponential backoff
                    
                    # Update results and cache
                    for pmid, metadata in batch_metadata.items():
                        result_metadata[pmid] = metadata
                        self.publication_cache[pmid] = metadata
                    
                    # Save cache periodically
                    if i % (PUBMED_BATCH_SIZE * 5) == 0:
                        self._save_cache(self.publication_cache)
                    
                    # Apply rate limiting before next batch
                    time.sleep(self.rate_limit)
                    
                    # Update progress bar
                    pbar.update(len(batch))
            
            # Save final cache
            self._save_cache(self.publication_cache)
            
        except Exception as e:
            logger.error(f"Error fetching PubMed metadata: {e}")
            
        return result_metadata

    def get_pmids_to_enrich(self) -> Set[str]:
        """Get all PMIDs from the database that need enrichment.
        
        Returns:
            Set of PMIDs that need metadata
        """
        if not self.db_manager.cursor:
            raise RuntimeError("No database connection")
            
        try:
            # First, identify PMIDs from all source categories
            self.db_manager.cursor.execute("""
                WITH RECURSIVE 
                source_refs AS (
                    SELECT jsonb_array_elements(source_references->'go_terms') as ref
                    FROM cancer_transcript_base
                    WHERE source_references->'go_terms' IS NOT NULL
                    UNION ALL
                    SELECT jsonb_array_elements(source_references->'drugs') as ref
                    FROM cancer_transcript_base
                    WHERE source_references->'drugs' IS NOT NULL
                    UNION ALL
                    SELECT jsonb_array_elements(source_references->'pathways') as ref
                    FROM cancer_transcript_base
                    WHERE source_references->'pathways' IS NOT NULL
                    UNION ALL
                    SELECT jsonb_array_elements(source_references->'uniprot') as ref
                    FROM cancer_transcript_base
                    WHERE source_references->'uniprot' IS NOT NULL
                )
                SELECT DISTINCT ref->>'pmid' as pmid
                FROM source_refs
                WHERE ref->>'pmid' IS NOT NULL 
                AND ref->>'pmid' != ''
                AND (ref->>'title' IS NULL OR ref->>'year' IS NULL);
            """)
            
            # Get only PMIDs that are not yet enriched (missing title or year)
            pmids = {row[0] for row in self.db_manager.cursor.fetchall() if row[0]}
            
            logger.info(f"Found {len(pmids)} PMIDs that need enrichment")
            
            # If force_refresh is enabled, get ALL PMIDs instead
            if self.force_refresh:
                self.db_manager.cursor.execute("""
                    WITH RECURSIVE 
                    source_refs AS (
                        SELECT jsonb_array_elements(source_references->'go_terms') as ref
                        FROM cancer_transcript_base
                        WHERE source_references->'go_terms' IS NOT NULL
                        UNION ALL
                        SELECT jsonb_array_elements(source_references->'drugs') as ref
                        FROM cancer_transcript_base
                        WHERE source_references->'drugs' IS NOT NULL
                        UNION ALL
                        SELECT jsonb_array_elements(source_references->'pathways') as ref
                        FROM cancer_transcript_base
                        WHERE source_references->'pathways' IS NOT NULL
                        UNION ALL
                        SELECT jsonb_array_elements(source_references->'uniprot') as ref
                        FROM cancer_transcript_base
                        WHERE source_references->'uniprot' IS NOT NULL
                    )
                    SELECT DISTINCT ref->>'pmid' as pmid
                    FROM source_refs
                    WHERE ref->>'pmid' IS NOT NULL 
                    AND ref->>'pmid' != '';
                """)
                
                all_pmids = {row[0] for row in self.db_manager.cursor.fetchall() if row[0]}
                logger.info(f"Force refresh enabled. Will update all {len(all_pmids)} PMIDs")
                pmids = all_pmids
                
            return pmids
            
        except Exception as e:
            logger.error(f"Error getting PMIDs to enrich: {e}")
            return set()

    def enrich_references(self) -> None:
        """Enrich source-specific references with metadata.
        
        This method:
        1. Identifies references that need enrichment
        2. Fetches publication metadata from PubMed or cache
        3. Updates references in the database
        """
        if not self.db_manager.cursor:
            raise RuntimeError("No database connection")
            
        try:
            # Get PMIDs to enrich
            pmids = self.get_pmids_to_enrich()
            
            if not pmids:
                logger.info("No PMIDs found to enrich")
                return
                
            # Fetch metadata with caching
            metadata = self._fetch_pubmed_metadata(pmids)
            
            if not metadata:
                logger.warning("No metadata retrieved for publications")
                return
                
            # Update references in batches with progress tracking
            logger.info(f"Updating {len(metadata)} publications in the database")
            
            self.db_manager.cursor.execute("""
                SELECT gene_symbol, source_references
                FROM cancer_transcript_base
                WHERE source_references != '{}'::jsonb
            """)
            
            updates = []
            processed = 0
            enriched = 0
            
            for gene_symbol, refs in tqdm(
                self.db_manager.cursor.fetchall(),
                desc="Enriching references in database"
            ):
                if not isinstance(refs, dict):
                    continue
                    
                enriched_refs = refs.copy()
                modified = False
                
                # Process each source's references
                for source in ['go_terms', 'drugs', 'pathways', 'uniprot']:
                    if source in refs and isinstance(refs.get(source), list):
                        enriched_source_refs = []
                        for ref in refs.get(source, []):
                            # Fix: Add a proper null check before dictionary lookup
                            pmid = ref.get("pmid") if isinstance(ref, dict) else None
                            if isinstance(ref, dict) and pmid and pmid in metadata:
                                # Only update fields that don't already exist or are empty
                                for key, value in metadata[pmid].items():
                                    if key not in ref or not ref.get(key):
                                        ref[key] = value
                                        modified = True
                            enriched_source_refs.append(ref)
                        enriched_refs[source] = enriched_source_refs
                
                if modified:
                    updates.append((
                        json.dumps(enriched_refs),
                        gene_symbol
                    ))
                    enriched += 1
                    
                if len(updates) >= self.batch_size:
                    self._update_batch(updates)
                    processed += len(updates)
                    updates = []
                    
            # Process remaining updates
            if updates:
                self._update_batch(updates)
                processed += len(updates)
            
            logger.info(f"Enrichment completed. Enriched {enriched} records. Processed {processed} updates.")
            
        except Exception as e:
            logger.error(f"Reference enrichment failed: {e}")
            if self.db_manager.conn:
                self.db_manager.conn.rollback()
            raise
        finally:
            if self.db_manager.conn:
                self.db_manager.conn.close()

    def _update_batch(self, updates: List[tuple]) -> None:
        """Update a batch of enriched references."""
        execute_batch(
            self.db_manager.cursor,
            """
            UPDATE cancer_transcript_base
            SET source_references = %s::jsonb
            WHERE gene_symbol = %s
            """,
            updates,
            page_size=self.batch_size
        )
        
        if self.db_manager.conn:
            self.db_manager.conn.commit()

    def run(self) -> None:
        """Run the complete publications enrichment pipeline."""
        try:
            # Ensure database schema is compatible
            if not self.db_manager.cursor:
                raise RuntimeError("No database connection")
                
            # Check schema version
            self.db_manager.cursor.execute("SELECT version FROM schema_version")
            result = self.db_manager.cursor.fetchone()
            
            if not result or result[0] != 'v0.1.4':
                logger.warning(f"Schema version {result[0] if result else 'unknown'} detected. Upgrading to v0.1.4")
                if not self.db_manager.migrate_to_version('v0.1.4'):
                    raise RuntimeError("Failed to upgrade database schema to v0.1.4")
            
            # Run the enrichment process
            logger.info("Starting publication metadata enrichment")
            self.enrich_references()
            
            # Print statistics
            if self.db_manager.cursor:
                self.db_manager.cursor.execute("""
                    WITH stats AS (
                        SELECT
                            COUNT(*) as total_genes,
                            COUNT(CASE WHEN source_references IS NOT NULL THEN 1 END) as with_refs,
                            (
                                SELECT COUNT(*)
                                FROM (
                                    WITH RECURSIVE all_refs AS (
                                        SELECT jsonb_array_elements(source_references->'go_terms') as ref
                                        FROM cancer_transcript_base
                                        WHERE source_references->'go_terms' IS NOT NULL
                                        UNION ALL
                                        SELECT jsonb_array_elements(source_references->'drugs') as ref
                                        FROM cancer_transcript_base
                                        WHERE source_references->'drugs' IS NOT NULL
                                        UNION ALL
                                        SELECT jsonb_array_elements(source_references->'pathways') as ref
                                        FROM cancer_transcript_base
                                        WHERE source_references->'pathways' IS NOT NULL
                                        UNION ALL
                                        SELECT jsonb_array_elements(source_references->'uniprot') as ref
                                        FROM cancer_transcript_base
                                        WHERE source_references->'uniprot' IS NOT NULL
                                    )
                                    SELECT DISTINCT ref->>'pmid' as pmid
                                    FROM all_refs
                                    WHERE ref->>'pmid' IS NOT NULL
                                ) pm
                            ) as unique_pmids,
                            (
                                SELECT COUNT(*)
                                FROM (
                                    WITH RECURSIVE all_refs AS (
                                        SELECT jsonb_array_elements(source_references->'go_terms') as ref
                                        FROM cancer_transcript_base
                                        WHERE source_references->'go_terms' IS NOT NULL
                                        UNION ALL
                                        SELECT jsonb_array_elements(source_references->'drugs') as ref
                                        FROM cancer_transcript_base
                                        WHERE source_references->'drugs' IS NOT NULL
                                        UNION ALL
                                        SELECT jsonb_array_elements(source_references->'pathways') as ref
                                        FROM cancer_transcript_base
                                        WHERE source_references->'pathways' IS NOT NULL
                                        UNION ALL
                                        SELECT jsonb_array_elements(source_references->'uniprot') as ref
                                        FROM cancer_transcript_base
                                        WHERE source_references->'uniprot' IS NOT NULL
                                    )
                                    SELECT DISTINCT ref->>'pmid' as pmid
                                    FROM all_refs
                                    WHERE ref->>'pmid' IS NOT NULL
                                    AND ref->>'title' IS NOT NULL
                                ) pm
                            ) as enriched_pmids
                        FROM cancer_transcript_base
                    )
                    SELECT 
                        total_genes, 
                        with_refs, 
                        unique_pmids, 
                        enriched_pmids, 
                        ROUND((enriched_pmids::float / NULLIF(unique_pmids, 0)::float) * 100, 1) as percent_enriched
                    FROM stats;
                """)
                
                result = self.db_manager.cursor.fetchone()
                if result:
                    logger.info(f"Publications enrichment statistics:")
                    logger.info(f"- Total genes in database: {result[0]:,}")
                    logger.info(f"- Genes with references: {result[1]:,}")
                    logger.info(f"- Unique PMIDs: {result[2]:,}")
                    logger.info(f"- Enriched PMIDs: {result[3]:,}")
                    logger.info(f"- Enrichment coverage: {result[4]}%")
            
            logger.info("Publications enrichment completed successfully")
            logger.info(f"Publication cache contains {len(self.publication_cache):,} entries")
            
        except Exception as e:
            logger.error(f"Publications enrichment failed: {e}")
            raise

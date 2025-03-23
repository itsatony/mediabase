"""Publications processing module for Cancer Transcriptome Base.

This module handles downloading, processing, and enrichment of publication metadata
from PubMed for transcript records, enhancing source references with detailed
publication information.
"""

# Standard library imports
import os
import json
import logging
import time
import re
from typing import Dict, List, Optional, Any, Set, TypedDict, cast, Union, Tuple
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET
from urllib.parse import quote

# Third party imports
import requests
from tqdm import tqdm
from psycopg2.extras import execute_batch
from rich.console import Console
from rich.table import Table

# Local imports
from .base_processor import BaseProcessor, DownloadError, ProcessingError, DatabaseError
from ..utils.publication_utils import extract_pmids_from_text, format_pmid_url

# Constants for PubMed API
PUBMED_API_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PUBMED_BATCH_SIZE = 200  # Max recommended by NCBI for single request
PUBMED_RATE_LIMIT = 0.34  # ~3 requests per second (adjust to 0.1 with API key)
DEFAULT_CACHE_TTL = 2592000  # 30 days in seconds for publications (much longer than other data)

class Publication(TypedDict, total=False):
    """Publication reference type definition."""
    pmid: str
    evidence_type: str
    source_db: str
    title: Optional[str]
    abstract: Optional[str]
    year: Optional[int]
    journal: Optional[str]
    authors: Optional[List[str]]
    citation_count: Optional[int]
    doi: Optional[str]
    url: Optional[str]

class PublicationsProcessor(BaseProcessor):
    """Process and enrich publication references."""
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize the publications processor with configuration.
        
        Args:
            config: Configuration dictionary with settings
        """
        super().__init__(config)
        
        # Set up email and API key for PubMed API
        self.email = config.get('email', os.environ.get('MB_PUBMED_EMAIL', ''))
        if not self.email:
            self.logger.warning("No email configured for PubMed API. Set MB_PUBMED_EMAIL in environment.")
            
        self.api_key = config.get('api_key', os.environ.get('MB_PUBMED_API_KEY', ''))
        if self.api_key:
            self.logger.info("Using API key for PubMed requests (higher rate limits)")
            self.rate_limit = 0.1  # 10 requests per second with API key
        else:
            self.rate_limit = PUBMED_RATE_LIMIT
        
        # Allow rate limit override from config
        self.rate_limit = config.get('rate_limit', self.rate_limit)
        
        # Force refresh of publication data
        self.force_refresh = config.get('force_refresh', False)
        
        # Create a directory for publication cache
        self.pub_dir = self.cache_dir / 'publications'
        self.pub_dir.mkdir(exist_ok=True)
        
        # Initialize a cache for frequently accessed publications
        self.publication_cache: Dict[str, Dict[str, Any]] = self._load_cache()
        self.cache_modified = False
        
        # Set a longer cache TTL for publications
        self.cache_ttl = config.get('cache_ttl', DEFAULT_CACHE_TTL)
        
        # Track hit/miss statistics
        self.cache_hits = 0
        self.cache_misses = 0
    
    def _load_cache(self) -> Dict[str, Dict[str, Any]]:
        """Load publication cache from disk.
        
        Returns:
            Dictionary mapping PMIDs to publication metadata
        """
        cache_path = self.pub_dir / "pubmed_cache.json"
        
        if not cache_path.exists():
            self.logger.info("No publication cache found, initializing empty cache")
            return {}
        
        try:
            with open(cache_path, 'r') as f:
                cache_data = json.load(f)
                self.logger.info(f"Loaded {len(cache_data)} publications from cache")
                return cache_data
        except (json.JSONDecodeError, IOError) as e:
            self.logger.warning(f"Failed to load publication cache: {e}")
            return {}
    
    def _save_cache(self, cache: Dict[str, Dict[str, Any]]) -> None:
        """Save publication cache to disk.
        
        Args:
            cache: Dictionary mapping PMIDs to publication metadata
        """
        if not self.cache_modified:
            return
            
        cache_path = self.pub_dir / "pubmed_cache.json"
        
        try:
            with open(cache_path, 'w') as f:
                json.dump(cache, f)
                self.logger.info(f"Saved {len(cache)} publications to cache")
        except IOError as e:
            self.logger.warning(f"Failed to save publication cache: {e}")
    
    @staticmethod
    def create_publication_reference(
        pmid: str,
        evidence_type: str = "unknown",
        source_db: str = "PubMed",
        url: Optional[str] = None
    ) -> Publication:
        """Create a basic publication reference.
        
        Args:
            pmid: PubMed ID
            evidence_type: Type of evidence (e.g., experimental, review)
            source_db: Source database (e.g., GO, UniProt)
            url: Optional URL to the reference
            
        Returns:
            Publication reference dictionary
        """
        # Ensure PMID is a string
        pmid_str = str(pmid)
        
        pub_ref: Publication = {
            'pmid': pmid_str,
            'evidence_type': evidence_type,
            'source_db': source_db
        }
        
        # Add URL if provided, otherwise generate from PMID
        if url:
            pub_ref['url'] = url
        else:
            pub_ref['url'] = format_pmid_url(pmid_str)
            
        return pub_ref
    
    def get_publication_metadata(self, pmid: str) -> Optional[Dict[str, Any]]:
        """Get publication metadata for a specific PMID.
        
        Args:
            pmid: PubMed ID
            
        Returns:
            Publication metadata dictionary or None if not found
        """
        # Check cache first
        if pmid in self.publication_cache and not self.force_refresh:
            self.cache_hits += 1
            return self.publication_cache[pmid]
        
        self.cache_misses += 1
        
        # Fetch from PubMed API
        metadata = self._fetch_pubmed_metadata([pmid])
        
        # Return the specific publication or None
        return metadata.get(pmid)
    
    def get_publications_metadata(self, pmids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get metadata for multiple publications.
        
        Args:
            pmids: List of PubMed IDs
            
        Returns:
            Dictionary mapping PMIDs to publication metadata
        """
        if not pmids:
            return {}
            
        # Deduplicate PMIDs
        unique_pmids = list(set(pmids))
        
        # Split into cached and uncached
        cached_pmids = []
        uncached_pmids = []
        
        for pmid in unique_pmids:
            if pmid in self.publication_cache and not self.force_refresh:
                cached_pmids.append(pmid)
            else:
                uncached_pmids.append(pmid)
        
        # Update cache statistics
        self.cache_hits += len(cached_pmids)
        self.cache_misses += len(uncached_pmids)
        
        # Get cached publications
        result = {pmid: self.publication_cache[pmid] for pmid in cached_pmids}
        
        # Fetch uncached publications if needed
        if uncached_pmids:
            uncached_data = self._fetch_pubmed_metadata(uncached_pmids)
            result.update(uncached_data)
        
        return result
    
    def _fetch_pubmed_metadata(self, pmids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Fetch metadata for multiple publications from PubMed E-utilities.
        
        Args:
            pmids: List of PubMed IDs to fetch
            
        Returns:
            Dictionary mapping PMIDs to publication metadata
        """
        if not pmids:
            return {}
            
        # Deduplicate and validate PMIDs
        valid_pmids = []
        for pmid in pmids:
            if pmid and str(pmid).strip() and str(pmid).isdigit():
                valid_pmids.append(str(pmid).strip())
        
        if not valid_pmids:
            return {}
            
        results: Dict[str, Dict[str, Any]] = {}
        
        # Process in batches to avoid API limits
        with tqdm(total=len(valid_pmids), desc="Fetching PubMed data") as pbar:
            for i in range(0, len(valid_pmids), PUBMED_BATCH_SIZE):
                batch = valid_pmids[i:i+PUBMED_BATCH_SIZE]
                
                try:
                    # Fetch summary data for the batch
                    summary_data = self._fetch_pubmed_summary(batch)
                    
                    # Fetch abstract data for the batch
                    abstract_data = self._fetch_pubmed_abstracts(batch)
                    
                    # Merge summary and abstract data
                    for pmid in batch:
                        pub_data = {}
                        
                        # Add summary data if available
                        if pmid in summary_data:
                            pub_data.update(summary_data[pmid])
                            
                        # Add abstract data if available
                        if pmid in abstract_data:
                            pub_data.update(abstract_data[pmid])
                        
                        # Only add if we have some data
                        if pub_data:
                            results[pmid] = pub_data
                            
                            # Update the cache
                            self.publication_cache[pmid] = pub_data
                            self.cache_modified = True
                    
                    # Update progress
                    pbar.update(len(batch))
                    
                    # Rate limiting
                    time.sleep(self.rate_limit)
                    
                except Exception as e:
                    self.logger.warning(f"Error fetching batch {i}-{i+PUBMED_BATCH_SIZE}: {e}")
                    continue
        
        # Save the updated cache
        self._save_cache(self.publication_cache)
        
        return results
    
    def _fetch_pubmed_summary(self, pmids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Fetch summary data for publications from PubMed ESummary.
        
        Args:
            pmids: List of PubMed IDs
            
        Returns:
            Dictionary mapping PMIDs to summary data
        """
        if not pmids:
            return {}
            
        results: Dict[str, Dict[str, Any]] = {}
        
        # Construct URL with parameters
        pmid_str = ",".join(pmids)
        params = {
            'db': 'pubmed',
            'tool': 'mediabase',
            'email': self.email,
            'retmode': 'json',
            'id': pmid_str
        }
        
        if self.api_key:
            params['api_key'] = self.api_key
            
        url = f"{PUBMED_API_BASE}/esummary.fcgi"
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            # Process each publication in the result
            if 'result' in data:
                for pmid in pmids:
                    if pmid in data['result']:
                        pub_data = data['result'][pmid]
                        
                        # Extract relevant fields
                        title = pub_data.get('title', '')
                        authors = []
                        if 'authors' in pub_data:
                            for author in pub_data['authors']:
                                if 'name' in author:
                                    authors.append(author['name'])
                        
                        journal = pub_data.get('fulljournalname', '')
                        year = None
                        if 'pubdate' in pub_data:
                            # Extract year from date string
                            match = re.search(r'\b\d{4}\b', pub_data['pubdate'])
                            if match:
                                year = int(match.group(0))
                                
                        doi = pub_data.get('elocationid', '')
                        if doi and doi.startswith('doi:'):
                            doi = doi[4:]  # Remove 'doi:' prefix
                            
                        # Create structured result
                        results[pmid] = {
                            'pmid': pmid,
                            'title': title,
                            'authors': authors,
                            'journal': journal,
                            'year': year,
                            'doi': doi,
                            'url': format_pmid_url(pmid)
                        }
            
            return results
            
        except Exception as e:
            self.logger.debug(f"Error fetching publication summaries: {e}")
            return {}
    
    def _fetch_pubmed_abstracts(self, pmids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Fetch abstract data for publications from PubMed EFetch.
        
        Args:
            pmids: List of PubMed IDs
            
        Returns:
            Dictionary mapping PMIDs to abstract data
        """
        if not pmids:
            return {}
            
        results: Dict[str, Dict[str, Any]] = {}
        
        # Construct URL with parameters
        pmid_str = ",".join(pmids)
        params = {
            'db': 'pubmed',
            'tool': 'mediabase',
            'email': self.email,
            'retmode': 'json',
            'id': pmid_str,
            'rettype': 'abstract'
        }
        
        if self.api_key:
            params['api_key'] = self.api_key
            
        url = f"{PUBMED_API_BASE}/efetch.fcgi"
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            # Try to parse as XML
            try:
                # Make sure we have valid XML before attempting to parse
                if response.text and '<PubmedArticleSet>' in response.text:
                    root = ET.fromstring(response.text)
                    
                    # Process each publication
                    for article_elem in root.findall('.//PubmedArticle'):
                        # Safely extract PMID
                        pmid_elem = article_elem.find('.//PMID')
                        if pmid_elem is None or pmid_elem.text is None:
                            continue
                            
                        pmid = pmid_elem.text
                        
                        # Safely extract abstract
                        abstract_texts = []
                        for abstract_elem in article_elem.findall('.//AbstractText'):
                            if abstract_elem is not None and abstract_elem.text:
                                abstract_texts.append(abstract_elem.text)
                        
                        abstract = ' '.join(abstract_texts)
                        
                        results[pmid] = {'abstract': abstract}
                else:
                    self.logger.debug("Response does not contain valid XML")
            except Exception as e:
                self.logger.debug(f"Error parsing XML: {e}")
            
            return results
            
        except Exception as e:
            self.logger.debug(f"Error fetching publication abstracts: {e}")
            return {}
    
    def enrich_publication_references(self) -> None:
        """Enrich all publication references in the database with metadata.
        
        Raises:
            DatabaseError: If database operations fail
        """
        if not self.ensure_connection():
            raise DatabaseError("Database connection failed")
            
        try:
            # Get all unique PMIDs from the database
            if not self.db_manager.cursor:
                raise DatabaseError("No database cursor available")
                
            self.db_manager.cursor.execute("""
                WITH all_refs AS (
                    SELECT 
                        jsonb_array_elements(source_references->'go_terms') as ref
                    FROM cancer_transcript_base
                    WHERE source_references->'go_terms' IS NOT NULL
                    UNION ALL
                    SELECT 
                        jsonb_array_elements(source_references->'uniprot') as ref
                    FROM cancer_transcript_base
                    WHERE source_references->'uniprot' IS NOT NULL
                    UNION ALL
                    SELECT 
                        jsonb_array_elements(source_references->'drugs') as ref
                    FROM cancer_transcript_base
                    WHERE source_references->'drugs' IS NOT NULL
                    UNION ALL
                    SELECT 
                        jsonb_array_elements(source_references->'pathways') as ref
                    FROM cancer_transcript_base
                    WHERE source_references->'pathways' IS NOT NULL
                )
                SELECT DISTINCT
                    ref->>'pmid' as pmid
                FROM all_refs
                WHERE ref->>'pmid' IS NOT NULL
                AND ref->>'pmid' ~ '^[0-9]+$'  -- Only numeric PMIDs
            """)
            
            all_pmids = [row[0] for row in self.db_manager.cursor.fetchall() if row[0]]
            unique_pmids = list(set(all_pmids))
            
            if not unique_pmids:
                self.logger.info("No publication references found to enrich")
                return
                
            self.logger.info(f"Found {len(unique_pmids)} unique PMIDs to enrich")
            
            # Fetch metadata for all PMIDs
            pub_metadata = self.get_publications_metadata(unique_pmids)
            
            # Display cache statistics
            self.logger.info(
                f"Cache statistics: {self.cache_hits} hits, {self.cache_misses} misses "
                f"({self.cache_hits / max(1, self.cache_hits + self.cache_misses) * 100:.1f}% hit rate)"
            )
            
            # Update the database with enriched references
            self._update_publication_references(pub_metadata)
            
        except Exception as e:
            self.logger.error(f"Failed to enrich publication references: {e}")
            raise DatabaseError(f"Publication enrichment failed: {e}")
    
    def _update_publication_references(self, pub_metadata: Dict[str, Dict[str, Any]]) -> None:
        """Update publication references in the database with metadata.
        
        Args:
            pub_metadata: Dictionary mapping PMIDs to publication metadata
            
        Raises:
            DatabaseError: If database operations fail
        """
        if not pub_metadata:
            self.logger.info("No publication metadata to update")
            return
            
        if not self.ensure_connection() or not self.db_manager.cursor:
            raise DatabaseError("Database connection failed")
            
        try:
            self.logger.info(f"Updating {len(pub_metadata)} publications in the database")
            
            # Get the total count of records directly
            row_count = 0
            if self.db_manager.cursor:
                self.db_manager.cursor.execute("SELECT COUNT(*) FROM cancer_transcript_base")
                count_result = self.db_manager.cursor.fetchone()
                if count_result:
                    row_count = count_result[0]
            
            # Process each source reference section
            sections = ['go_terms', 'uniprot', 'drugs', 'pathways']
            
            updates_counter = 0
            records_enriched = 0
            
            # Create a progress bar for the updates
            with tqdm(total=row_count, 
                    desc="Enriching references in database") as pbar:
                
                for section in sections:
                    # Initialize batch updates
                    updates = []
                    
                    # Query for records with references in this section
                    self.db_manager.cursor.execute(f"""
                        SELECT 
                            transcript_id,
                            source_references->'{section}' as refs
                        FROM cancer_transcript_base
                        WHERE source_references->'{section}' IS NOT NULL
                        AND source_references->'{section}' != '[]'::jsonb
                    """)
                    
                    for transcript_id, refs in self.db_manager.cursor.fetchall():
                        if not refs:
                            continue
                            
                        # Convert JSON to Python
                        refs_list = refs if isinstance(refs, list) else json.loads(refs)
                        modified = False
                        
                        # Enrich each reference with metadata if available
                        for ref in refs_list:
                            if not isinstance(ref, dict) or 'pmid' not in ref:
                                continue
                                
                            pmid = ref.get('pmid')
                            if not pmid or not isinstance(pmid, str) or not pmid.isdigit():
                                continue
                                
                            # Add metadata if available
                            if pmid in pub_metadata:
                                meta = pub_metadata[pmid]
                                
                                # Add each metadata field if not already present
                                for key, value in meta.items():
                                    if key not in ref or ref[key] is None:
                                        ref[key] = value
                                        modified = True
                        
                        # Add to update batch if modified
                        if modified:
                            updates.append((
                                json.dumps(refs_list),
                                section,
                                transcript_id
                            ))
                            records_enriched += 1
                        
                        # Process in batches
                        if len(updates) >= self.batch_size:
                            self._execute_publication_updates(updates, section)
                            updates_counter += len(updates)
                            updates = []
                    
                    # Process remaining updates
                    if updates:
                        self._execute_publication_updates(updates, section)
                        updates_counter += len(updates)
                    
                    # Update progress - estimate section completion
                    pbar.update(row_count // len(sections))
            
            self.logger.info(f"Enrichment completed. Enriched {records_enriched} records. Processed {updates_counter} updates.")
            
            # Check enrichment statistics
            self._display_enrichment_statistics()
            
        except Exception as e:
            self.logger.error(f"Failed to update publication references: {e}")
            raise DatabaseError(f"Publication reference update failed: {e}")
    
    def _execute_publication_updates(self, updates: List[Tuple[str, str, str]], section: str) -> None:
        """Execute batch updates for publication references.
        
        Args:
            updates: List of tuples (json_refs, section, transcript_id)
            section: Reference section name
            
        Raises:
            DatabaseError: If batch update fails
        """
        if not updates:
            return
            
        if not self.db_manager.cursor:
            raise DatabaseError("No database cursor available")
            
        try:
            query = f"""
                UPDATE cancer_transcript_base
                SET source_references = jsonb_set(
                    COALESCE(source_references, '{{}}'::jsonb),
                    '{{{section}}}',
                    %s::jsonb,
                    true
                )
                WHERE transcript_id = %s
            """
            
            self.execute_batch(
                query,
                [(refs, transcript_id) for refs, _, transcript_id in updates]
            )
            
        except Exception as e:
            self.logger.error(f"Failed to execute publication updates: {e}")
            raise DatabaseError(f"Publication update batch failed: {e}")
    
    def _display_enrichment_statistics(self) -> None:
        """Display statistics about enriched publications.
        
        Raises:
            DatabaseError: If database operations fail
        """
        if not self.ensure_connection() or not self.db_manager.cursor:
            return
            
        try:
            # Use a safer version of the ROUND function with explicit casting to numeric
            self.db_manager.cursor.execute("""
                WITH stats AS (
                    WITH pmid_counts AS (
                        SELECT
                            COUNT(DISTINCT ref->>'pmid') AS unique_pmids,
                            COUNT(CASE WHEN ref->>'title' IS NOT NULL THEN 1 END) AS enriched_pmids
                        FROM (
                            SELECT jsonb_array_elements(source_references->'go_terms') AS ref
                            FROM cancer_transcript_base
                            WHERE source_references->'go_terms' IS NOT NULL
                            UNION ALL
                            SELECT jsonb_array_elements(source_references->'uniprot') AS ref
                            FROM cancer_transcript_base
                            WHERE source_references->'uniprot' IS NOT NULL
                            UNION ALL
                            SELECT jsonb_array_elements(source_references->'drugs') AS ref
                            FROM cancer_transcript_base
                            WHERE source_references->'drugs' IS NOT NULL
                            UNION ALL
                            SELECT jsonb_array_elements(source_references->'pathways') AS ref
                            FROM cancer_transcript_base
                            WHERE source_references->'pathways' IS NOT NULL
                        ) AS all_refs
                        WHERE ref->>'pmid' IS NOT NULL
                    )
                    SELECT
                        unique_pmids,
                        enriched_pmids,
                        (enriched_pmids::numeric / NULLIF(unique_pmids, 0) * 100)::numeric AS percent_enriched
                    FROM pmid_counts
                )
                SELECT
                    unique_pmids,
                    enriched_pmids,
                    ROUND(percent_enriched::numeric, 2) AS percent_enriched
                FROM stats
            """)
            
            stats = self.db_manager.cursor.fetchone()
            
            if stats:
                unique_pmids, enriched_pmids, percent_enriched = stats
                
                table = Table(title="Publication Enrichment Statistics")
                table.add_column("Metric", style="cyan")
                table.add_column("Value", style="green")
                
                table.add_row("Total Unique PMIDs", f"{unique_pmids:,}")
                table.add_row("Enriched PMIDs", f"{enriched_pmids:,}")
                table.add_row("Enrichment Rate", f"{percent_enriched}%")
                
                console = Console()
                console.print(table)
                
        except Exception as e:
            self.logger.warning(f"Failed to display enrichment statistics: {e}")
    
    def run(self) -> None:
        """Run the complete publication enrichment pipeline.
        
        Raises:
            Various ETLError subclasses based on failure point
        """
        try:
            self.logger.info("Starting publication enrichment pipeline")
            
            # Check if we have an email for PubMed API
            if not self.email:
                self.logger.warning(
                    "No email configured for PubMed API. Set MB_PUBMED_EMAIL in environment. "
                    "Continuing with limited functionality."
                )
            
            # Enrich publication references
            self.enrich_publication_references()
            
            self.logger.info("Publication enrichment completed successfully")
            
        except Exception as e:
            self.logger.error(f"Publications enrichment failed: {e}")
            raise

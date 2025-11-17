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
from typing import Dict, List, Optional, Any, Set, Union, Tuple
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
from ..utils.publication_types import Publication
from ..utils.publication_utils import extract_pmids_from_text, format_pmid_url

# Constants for PubMed API
PUBMED_API_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PUBMED_BATCH_SIZE = 200  # Max recommended by NCBI for single request
PUBMED_RATE_LIMIT = 0.34  # ~3 requests per second (adjust to 0.1 with API key)
DEFAULT_CACHE_TTL = 2592000  # 30 days in seconds for publications (much longer than other data)

# Retry configuration
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 1.0  # seconds
MAX_RETRY_DELAY = 60.0  # seconds
RETRY_BACKOFF_FACTOR = 2.0  # exponential backoff multiplier

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

        # Track failed PMIDs and metrics for production monitoring
        self.failed_pmids: Set[str] = set()
        self.retry_counts: Dict[str, int] = {}
        self.fetch_errors: List[Dict[str, Any]] = []
        self.pmids_fetched = 0
        self.pmids_enriched = 0
    
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

    def _retry_with_backoff(
        self,
        func: Any,
        *args: Any,
        operation_name: str = "API request",
        **kwargs: Any
    ) -> Optional[Any]:
        """Retry a function with exponential backoff.

        Args:
            func: Function to retry
            *args: Positional arguments for the function
            operation_name: Name of the operation for logging
            **kwargs: Keyword arguments for the function

        Returns:
            Function result or None if all retries fail
        """
        last_exception = None
        delay = INITIAL_RETRY_DELAY

        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except requests.exceptions.HTTPError as e:
                last_exception = e
                status_code = e.response.status_code if e.response else None

                # Don't retry on client errors (except 429 rate limit)
                if status_code and 400 <= status_code < 500 and status_code != 429:
                    self.logger.error(f"{operation_name} failed with status {status_code}: {e}")
                    return None

                # Log and retry on server errors or rate limits
                self.logger.warning(
                    f"{operation_name} attempt {attempt + 1}/{MAX_RETRIES} failed "
                    f"(status: {status_code}): {e}"
                )

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                last_exception = e
                self.logger.warning(
                    f"{operation_name} attempt {attempt + 1}/{MAX_RETRIES} failed "
                    f"(network error): {e}"
                )

            except Exception as e:
                last_exception = e
                self.logger.warning(
                    f"{operation_name} attempt {attempt + 1}/{MAX_RETRIES} failed: {e}"
                )

            # Don't sleep after the last attempt
            if attempt < MAX_RETRIES - 1:
                sleep_time = min(delay, MAX_RETRY_DELAY)
                self.logger.debug(f"Retrying in {sleep_time:.1f} seconds...")
                time.sleep(sleep_time)
                delay *= RETRY_BACKOFF_FACTOR

        # All retries failed
        self.logger.error(
            f"{operation_name} failed after {MAX_RETRIES} attempts. "
            f"Last error: {last_exception}"
        )

        # Track the error
        self.fetch_errors.append({
            'operation': operation_name,
            'error': str(last_exception),
            'timestamp': datetime.now().isoformat()
        })

        return None

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
                    # Fetch summary data for the batch with retry logic
                    summary_data = self._retry_with_backoff(
                        self._fetch_pubmed_summary,
                        batch,
                        operation_name=f"PubMed summary batch {i//PUBMED_BATCH_SIZE + 1}"
                    ) or {}

                    # Fetch abstract data for the batch with retry logic
                    abstract_data = self._retry_with_backoff(
                        self._fetch_pubmed_abstracts,
                        batch,
                        operation_name=f"PubMed abstracts batch {i//PUBMED_BATCH_SIZE + 1}"
                    ) or {}

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
                            self.pmids_fetched += 1

                            # Update the cache
                            self.publication_cache[pmid] = pub_data
                            self.cache_modified = True
                        else:
                            # Track failed PMIDs
                            self.failed_pmids.add(pmid)
                            self.logger.debug(f"No data fetched for PMID {pmid}")

                    # Update progress
                    pbar.update(len(batch))

                    # Rate limiting
                    time.sleep(self.rate_limit)

                except Exception as e:
                    # Track failed PMIDs in this batch
                    for pmid in batch:
                        self.failed_pmids.add(pmid)
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
    
    def enrich_publications_bulk(self, publications: List[Publication]) -> List[Publication]:
        """Enrich a bulk list of publications with metadata from PubMed.
        
        Args:
            publications: List of Publication objects to enrich
            
        Returns:
            List of enriched Publication objects
            
        Raises:
            ProcessingError: If publication enrichment fails
        """
        if not publications:
            self.logger.info("No publications to enrich")
            return publications
            
        try:
            self.logger.info(f"Enriching {len(publications)} publications with PubMed metadata")
            
            # Extract PMIDs from publications
            pmids = []
            pmid_to_publication = {}
            
            for pub in publications:
                if pub.get('pmid'):
                    pmid = pub['pmid']
                    pmids.append(pmid)
                    pmid_to_publication[pmid] = pub
            
            if not pmids:
                self.logger.warning("No PMIDs found in publications to enrich")
                return publications
            
            # Get metadata for all PMIDs
            self.logger.info(f"Fetching metadata for {len(pmids)} PMIDs")
            pub_metadata = self.get_publications_metadata(pmids)
            
            # Enrich publications with metadata
            enriched_count = 0
            for pmid, metadata in pub_metadata.items():
                if pmid in pmid_to_publication:
                    publication = pmid_to_publication[pmid]
                    
                    # Add metadata if not already present
                    if metadata.get('title') and not publication.get('title'):
                        publication['title'] = metadata['title']
                    if metadata.get('abstract') and not publication.get('abstract'):
                        publication['abstract'] = metadata['abstract']
                    if metadata.get('year') and not publication.get('year'):
                        publication['year'] = metadata['year']
                    if metadata.get('journal') and not publication.get('journal'):
                        publication['journal'] = metadata['journal']
                    if metadata.get('authors') and not publication.get('authors'):
                        publication['authors'] = metadata['authors']
                    if metadata.get('citation_count') and not publication.get('citation_count'):
                        publication['citation_count'] = metadata['citation_count']
                    if metadata.get('doi') and not publication.get('doi'):
                        publication['doi'] = metadata['doi']
                    
                    enriched_count += 1
            
            self.logger.info(f"Successfully enriched {enriched_count}/{len(pmids)} publications")
            return publications
            
        except Exception as e:
            raise ProcessingError(f"Failed to enrich publications bulk: {e}")

    def generate_production_report(self) -> Dict[str, Any]:
        """Generate comprehensive production metrics report.

        Returns:
            Dictionary containing all production metrics and status
        """
        total_pmids = self.pmids_fetched + len(self.failed_pmids)
        success_rate = (self.pmids_fetched / max(1, total_pmids)) * 100
        cache_hit_rate = (self.cache_hits / max(1, self.cache_hits + self.cache_misses)) * 100

        report = {
            'fetch_stats': {
                'total_pmids_requested': total_pmids,
                'pmids_fetched_successfully': self.pmids_fetched,
                'pmids_failed': len(self.failed_pmids),
                'success_rate_percent': round(success_rate, 2)
            },
            'cache_stats': {
                'cache_hits': self.cache_hits,
                'cache_misses': self.cache_misses,
                'hit_rate_percent': round(cache_hit_rate, 2),
                'total_cached_publications': len(self.publication_cache)
            },
            'error_summary': {
                'total_errors': len(self.fetch_errors),
                'unique_failed_pmids': len(self.failed_pmids)
            }
        }

        # Create detailed report table
        table = Table(title="Publication Enrichment Production Report")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Total PMIDs Requested", f"{total_pmids:,}")
        table.add_row("Successfully Fetched", f"{self.pmids_fetched:,}")
        table.add_row("Failed to Fetch", f"{len(self.failed_pmids):,}")
        table.add_row("Success Rate", f"{success_rate:.2f}%")
        table.add_row("", "")  # Separator
        table.add_row("Cache Hits", f"{self.cache_hits:,}")
        table.add_row("Cache Misses", f"{self.cache_misses:,}")
        table.add_row("Cache Hit Rate", f"{cache_hit_rate:.2f}%")
        table.add_row("Total Cached", f"{len(self.publication_cache):,}")
        table.add_row("", "")  # Separator
        table.add_row("API Errors", f"{len(self.fetch_errors)}")

        console = Console()
        console.print(table)

        # Save failed PMIDs to file for investigation
        if self.failed_pmids:
            failed_pmids_file = self.pub_dir / "failed_pmids.txt"
            try:
                with open(failed_pmids_file, 'w') as f:
                    f.write(f"# Failed PMIDs - {datetime.now().isoformat()}\n")
                    f.write(f"# Total: {len(self.failed_pmids)}\n\n")
                    for pmid in sorted(self.failed_pmids):
                        f.write(f"{pmid}\n")
                self.logger.info(
                    f"Saved {len(self.failed_pmids)} failed PMIDs to {failed_pmids_file}"
                )
            except IOError as e:
                self.logger.warning(f"Failed to save failed PMIDs list: {e}")

        # Save error log if there are errors
        if self.fetch_errors:
            error_log_file = self.pub_dir / f"fetch_errors_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            try:
                with open(error_log_file, 'w') as f:
                    json.dump(self.fetch_errors, f, indent=2)
                self.logger.info(f"Saved error log to {error_log_file}")
            except IOError as e:
                self.logger.warning(f"Failed to save error log: {e}")

        return report

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

            # Generate and display production report
            self.logger.info("Generating production metrics report...")
            production_report = self.generate_production_report()

            self.logger.info("Publication enrichment completed successfully")

            # Log warning if there were significant failures
            if len(self.failed_pmids) > 0:
                failure_rate = (len(self.failed_pmids) / max(1, self.pmids_fetched + len(self.failed_pmids))) * 100
                if failure_rate > 10:
                    self.logger.warning(
                        f"High failure rate detected: {failure_rate:.2f}% of PMIDs failed to fetch. "
                        f"Check failed_pmids.txt and error logs in {self.pub_dir}"
                    )

        except Exception as e:
            self.logger.error(f"Publications enrichment failed: {e}")
            # Still try to generate report even on failure
            try:
                self.generate_production_report()
            except Exception:
                pass
            raise

    def integrate_publications(self, publications_data: Dict[str, List[Dict[str, Any]]]) -> None:
        """Integrate publication data into transcript database.
        
        Args:
            publications_data: Dictionary mapping gene IDs to publication lists
            
        Raises:
            DatabaseError: If database operations fail
        """
        if not self.ensure_connection():
            raise DatabaseError("Database connection failed")
            
        try:
            self.logger.info("Integrating publication data with transcript records")
            
            # Create temporary table for batch updates with multiple ID mapping
            with self.get_db_transaction() as transaction:
                transaction.cursor.execute("""
                    CREATE TEMP TABLE temp_publication_data (
                        gene_symbol TEXT,
                        uniprot_ids TEXT[],
                        ncbi_ids TEXT[],
                        publication_refs JSONB
                    ) ON COMMIT DROP
                """)
            
            updates = []
            processed = 0
            
            # Process each gene's publication data
            for gene_symbol, publications in publications_data.items():
                # Skip empty data
                if not gene_symbol or not publications:
                    continue
                    
                # Get additional IDs for this gene for more comprehensive mapping
                uniprot_ids = []
                ncbi_ids = []
                if self.db_manager.cursor:
                    self.db_manager.cursor.execute("""
                        SELECT uniprot_ids, ncbi_ids 
                        FROM cancer_transcript_base
                        WHERE gene_symbol = %s 
                        AND (uniprot_ids IS NOT NULL OR ncbi_ids IS NOT NULL)
                    """, (gene_symbol,))
                    result = self.db_manager.cursor.fetchone()
                    if result:
                        uniprot_ids = result[0] or []
                        ncbi_ids = result[1] or []
                
                # Format publication references
                publication_refs = self._format_publications(publications)
                
                updates.append((
                    gene_symbol,
                    uniprot_ids,
                    ncbi_ids,
                    json.dumps(publication_refs)
                ))
                
                processed += 1
                
                # Process in batches
                if len(updates) >= self.batch_size:
                    self._update_publication_batch(updates)
                    updates = []
                    self.logger.info(f"Processed {processed} genes with publication data")
            
            # Process any remaining updates
            if updates:
                self._update_publication_batch(updates)
            
            # Update main table from temp table using multiple ID types
            with self.get_db_transaction() as transaction:
                # First update by gene symbol
                transaction.cursor.execute("""
                    UPDATE cancer_transcript_base cb
                    SET source_references = jsonb_set(
                        COALESCE(cb.source_references, '{
                            "go_terms": [],
                            "uniprot": [],
                            "drugs": [],
                            "pathways": []
                        }'::jsonb),
                        '{publications}',
                        COALESCE(cb.source_references->'publications', '[]'::jsonb) || pub.publication_refs,
                        true
                    )
                    FROM temp_publication_data pub
                    WHERE cb.gene_symbol = pub.gene_symbol
                """)
                
                # Then update by UniProt IDs
                transaction.cursor.execute("""
                    UPDATE cancer_transcript_base cb
                    SET source_references = jsonb_set(
                        COALESCE(cb.source_references, '{
                            "go_terms": [],
                            "uniprot": [],
                            "drugs": [],
                            "pathways": []
                        }'::jsonb),
                        '{publications}',
                        COALESCE(cb.source_references->'publications', '[]'::jsonb) || pub.publication_refs,
                        true
                    )
                    FROM temp_publication_data pub
                    WHERE cb.uniprot_ids && pub.uniprot_ids
                    AND cb.gene_symbol != pub.gene_symbol
                    AND pub.uniprot_ids IS NOT NULL
                    AND array_length(pub.uniprot_ids, 1) > 0
                """)
                
                # Also update by NCBI IDs
                transaction.cursor.execute("""
                    UPDATE cancer_transcript_base cb
                    SET source_references = jsonb_set(
                        COALESCE(cb.source_references, '{
                            "go_terms": [],
                            "uniprot": [],
                            "drugs": [],
                            "pathways": []
                        }'::jsonb),
                        '{publications}',
                        COALESCE(cb.source_references->'publications', '[]'::jsonb) || pub.publication_refs,
                        true
                    )
                    FROM temp_publication_data pub
                    WHERE cb.ncbi_ids && pub.ncbi_ids
                    AND cb.gene_symbol != pub.gene_symbol
                    AND pub.ncbi_ids IS NOT NULL
                    AND array_length(pub.ncbi_ids, 1) > 0
                """)
                
                # Clean up
                transaction.cursor.execute("DROP TABLE IF EXISTS temp_publication_data")
            
            self.logger.info(f"Successfully integrated publication data for {processed} genes")
            
        except Exception as e:
            self.logger.error(f"Failed to integrate publication data: {e}")
            raise DatabaseError(f"Publication integration failed: {e}")

    def _update_publication_batch(self, updates: List[Tuple[str, List[str], List[str], str]]) -> None:
        """Update a batch of publication data.
        
        Args:
            updates: List of tuples with (gene_symbol, uniprot_ids, ncbi_ids, publication_refs_json)
            
        Raises:
            DatabaseError: If batch update fails
        """
        try:
            self.execute_batch(
                """
                INSERT INTO temp_publication_data 
                (gene_symbol, uniprot_ids, ncbi_ids, publication_refs)
                VALUES (%s, %s, %s, %s::jsonb)
                """,
                updates
            )
        except Exception as e:
            raise DatabaseError(f"Failed to update publication batch: {e}")

    def _format_publications(self, publications: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format publication data for database storage.
        
        Args:
            publications: List of publication dictionaries
            
        Returns:
            Formatted publication list with standardized fields
        """
        formatted = []
        
        for pub in publications:
            # Convert to our standard publication format
            formatted_pub = {
                'pmid': pub.get('pmid'),
                'title': pub.get('title', ''),
                'abstract': pub.get('abstract', ''),
                'authors': pub.get('authors', []),
                'year': pub.get('year'),
                'journal': pub.get('journal', ''),
                'citation_count': pub.get('citation_count'),
                'evidence_type': pub.get('evidence_type', 'literature'),
                'source_db': pub.get('source_db', 'pubmed'),
                'doi': pub.get('doi', ''),
                'url': pub.get('url', '')
            }
            
            # Only add if we have at least a PMID
            if formatted_pub['pmid']:
                formatted.append(formatted_pub)
        
        return formatted

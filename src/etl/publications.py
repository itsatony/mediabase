"""Publications processing module for Cancer Transcriptome Base."""

import logging
from typing import Dict, List, Optional, Any, Set, TypedDict
import json
from datetime import datetime
import requests
from tqdm import tqdm
from ..db.database import get_db_manager
from psycopg2.extras import execute_batch

logger = logging.getLogger(__name__)

class Publication(TypedDict):
    """Type definition for publication data."""
    pmid: str
    year: Optional[int]
    evidence_type: str
    citation_count: Optional[int]
    source_db: str

class PublicationsProcessor:
    """Process and enrich publication references."""
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize publications processor.
        
        Args:
            config: Configuration dictionary containing:
                - pubmed_api_key: NCBI E-utilities API key
                - pubmed_email: Contact email for API
                - batch_size: Size of batches for processing
        """
        self.config = config
        self.db_manager = get_db_manager(config)
        self.batch_size = config.get('batch_size', 1000)
        self.api_key = config.get('pubmed_api_key')
        self.email = config.get('pubmed_email')
        
        if not (self.api_key and self.email):
            logger.warning("PubMed API key or email not configured")
            
    def _fetch_pubmed_metadata(self, pmids: Set[str]) -> Dict[str, Dict[str, Any]]:
        """Fetch metadata for PubMed IDs using E-utilities.
        
        Args:
            pmids: Set of PubMed IDs to fetch
            
        Returns:
            Dictionary mapping PMIDs to their metadata
        """
        base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
        metadata: Dict[str, Dict[str, Any]] = {}
        
        try:
            # Process in batches of 200 (NCBI recommendation)
            pmid_list = list(pmids)
            for i in range(0, len(pmid_list), 200):
                batch = pmid_list[i:i + 200]
                params = {
                    'db': 'pubmed',
                    'tool': 'mediabase',
                    'email': self.email,
                    'api_key': self.api_key,
                    'retmode': 'json',
                    'id': ','.join(batch)
                }
                
                response = requests.get(f"{base_url}/esummary.fcgi", params=params)
                if response.ok:
                    data = response.json()
                    for pmid, article in data['result'].items():
                        if pmid != 'uids':
                            try:
                                pub_date = article.get('pubdate', '')
                                year = int(pub_date.split()[0]) if pub_date else None
                                
                                metadata[pmid] = {
                                    'year': year,
                                    'citations': None,  # Could be added from other sources
                                    'title': article.get('title', ''),
                                    'journal': article.get('source', '')
                                }
                            except (ValueError, KeyError) as e:
                                logger.debug(f"Error processing PMID {pmid}: {e}")
                                continue
                                
        except Exception as e:
            logger.error(f"Error fetching PubMed metadata: {e}")
            
        return metadata

    def enrich_references(self) -> None:
        """Enrich source-specific references with metadata."""
        if not self.db_manager.cursor:
            raise RuntimeError("No database connection")
            
        try:
            # Get all unique PMIDs
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
                WHERE ref->>'pmid' IS NOT NULL;
            """)
            
            pmids = {row[0] for row in self.db_manager.cursor.fetchall() if row[0]}
            
            if not pmids:
                logger.info("No PMIDs found to enrich")
                return
                
            logger.info(f"Found {len(pmids)} unique PMIDs to enrich")
            
            # Fetch metadata for all PMIDs
            metadata = self._fetch_pubmed_metadata(pmids)
            
            if not metadata:
                logger.warning("No metadata retrieved from PubMed")
                return
                
            # Update references in batches
            processed = 0
            self.db_manager.cursor.execute("""
                SELECT gene_symbol, source_references
                FROM cancer_transcript_base
                WHERE source_references != '{}'::jsonb
            """)
            
            updates = []
            for gene_symbol, refs in tqdm(
                self.db_manager.cursor.fetchall(),
                desc="Enriching references"
            ):
                if not isinstance(refs, dict):
                    continue
                    
                enriched_refs = refs.copy()
                modified = False
                
                # Process each source's references
                for source in ['go_terms', 'drugs', 'pathways', 'uniprot']:
                    if source in refs and isinstance(refs[source], list):
                        enriched_source_refs = []
                        for ref in refs[source]:
                            if isinstance(ref, dict) and 'pmid' in ref:
                                pmid = ref['pmid']
                                if pmid in metadata:
                                    ref.update({
                                        'year': metadata[pmid]['year'],
                                        'title': metadata[pmid]['title'],
                                        'journal': metadata[pmid]['journal']
                                    })
                                    modified = True
                            enriched_source_refs.append(ref)
                        enriched_refs[source] = enriched_source_refs
                
                if modified:
                    updates.append((
                        json.dumps(enriched_refs),
                        gene_symbol
                    ))
                    
                if len(updates) >= self.batch_size:
                    self._update_batch(updates)
                    processed += len(updates)
                    updates = []
                    
            # Process remaining updates
            if updates:
                self._update_batch(updates)
                processed += len(updates)
            
            logger.info(f"Enrichment completed. Processed {processed} records")
            
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
            self.enrich_references()
            logger.info("Publications processing completed successfully")
        except Exception as e:
            logger.error(f"Publications processing failed: {e}")
            raise

"""Publications processing module for Cancer Transcriptome Base."""

import logging
from typing import Dict, List, Optional, Any, Set, TypedDict, cast, Union
import json
from datetime import datetime
import requests
from tqdm import tqdm
from ..db.database import get_db_manager
from psycopg2.extras import execute_batch

logger = logging.getLogger(__name__)

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
                
                # First get summary data
                summary_params = {
                    'db': 'pubmed',
                    'tool': 'mediabase',
                    'email': self.email,
                    'api_key': self.api_key,
                    'retmode': 'json',
                    'id': ','.join(batch)
                }
                
                summary_response = requests.get(f"{base_url}/esummary.fcgi", params=summary_params)
                if summary_response.ok:
                    data = summary_response.json()
                    for pmid, article in data.get('result', {}).items():
                        if pmid != 'uids':
                            try:
                                pub_date = article.get('pubdate', '')
                                year = int(pub_date.split()[0]) if pub_date else None
                                
                                authors = []
                                if 'authors' in article:
                                    authors = [author.get('name', '') 
                                              for author in article.get('authors', [])]
                                
                                metadata[pmid] = {
                                    'year': year,
                                    'citation_count': None,  # Could be added from other sources
                                    'title': article.get('title', ''),
                                    'journal': article.get('source', ''),
                                    'authors': authors,
                                    'doi': article.get('doi', ''),
                                    'url': f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                                }
                            except (ValueError, KeyError) as e:
                                logger.debug(f"Error processing PMID {pmid}: {e}")
                                continue
                
                # Then get abstracts using efetch
                abstract_params = {
                    'db': 'pubmed',
                    'tool': 'mediabase',
                    'email': self.email,
                    'api_key': self.api_key,
                    'retmode': 'json',
                    'rettype': 'abstract',
                    'id': ','.join(batch)
                }
                
                abstract_response = requests.get(f"{base_url}/efetch.fcgi", params=abstract_params)
                if abstract_response.ok:
                    try:
                        # efetch returns XML by default, need to parse it
                        data = abstract_response.json()
                        articles = data.get('PubmedArticleSet', {}).get('PubmedArticle', [])
                        
                        # If only one article is returned, it might not be in a list
                        if not isinstance(articles, list):
                            articles = [articles]
                            
                        for article in articles:
                            article_pmid = None
                            try:
                                article_pmid = article.get('MedlineCitation', {}).get('PMID', {}).get('content', '')
                                if article_pmid in metadata:
                                    abstract_text = article.get('MedlineCitation', {}).get('Article', {}).get('Abstract', {}).get('AbstractText', '')
                                    if abstract_text:
                                        metadata[article_pmid]['abstract'] = abstract_text
                            except (KeyError, AttributeError) as e:
                                logger.debug(f"Error extracting abstract for PMID {article_pmid}: {e}")
                                continue
                    except json.JSONDecodeError:
                        # Handle XML response
                        from lxml import etree
                        
                        html_parser = etree.HTMLParser()
                        root = etree.fromstring(abstract_response.content, parser=html_parser)
                        for article in root.xpath('//PubmedArticle'):
                            try:
                                article_pmid = article.xpath('.//PMID/text()')[0]
                                if article_pmid in metadata:
                                    abstract_texts = article.xpath('.//AbstractText/text()')
                                    if abstract_texts:
                                        metadata[article_pmid]['abstract'] = ' '.join(abstract_texts)
                            except (IndexError, KeyError) as e:
                                logger.debug(f"Error extracting abstract from XML for PMID: {e}")
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
                    if source in refs and isinstance(refs.get(source), list):
                        enriched_source_refs = []
                        for ref in refs.get(source, []):
                            if isinstance(ref, dict) and 'pmid' in ref:
                                pmid = ref.get('pmid')
                                if pmid in metadata:
                                    ref.update({
                                        'year': metadata.get(pmid, {}).get('year'),
                                        'title': metadata.get(pmid, {}).get('title', ''),
                                        'journal': metadata.get(pmid, {}).get('journal', ''),
                                        'abstract': metadata.get(pmid, {}).get('abstract', ''),
                                        'authors': metadata.get(pmid, {}).get('authors', []),
                                        'doi': metadata.get(pmid, {}).get('doi', ''),
                                        'url': metadata.get(pmid, {}).get('url', '')
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

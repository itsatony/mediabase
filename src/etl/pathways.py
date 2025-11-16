"""Pathway enrichment module for Cancer Transcriptome Base.

This module downloads, processes, and integrates pathway data from Reactome
into transcript records, enhancing them with biological pathway information.
"""

import logging
import json
import re
from typing import Dict, List, Optional, Any, Set, Tuple
from pathlib import Path
import csv

import pandas as pd
import requests
from tqdm import tqdm
from psycopg2.extras import execute_batch

from .base_processor import BaseProcessor, DownloadError, ProcessingError, DatabaseError
from .publications import Publication, PublicationsProcessor
from ..utils.publication_utils import extract_pmids_from_text, format_pmid_url
from ..utils.gene_matcher import normalize_gene_symbol, match_genes_bulk, get_gene_match_stats

# Constants
HUMAN_SPECIES = 'Homo sapiens'
HUMAN_TAXONOMY_ID = '9606'  # NCBI taxonomy ID for humans

class PathwayProcessor(BaseProcessor):
    """Process pathway data and enrich transcript information."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize pathway processor with configuration.
        
        Args:
            config: Configuration dictionary
        """
        super().__init__(config)
        
        # Define specific directory for pathway data
        self.pathway_dir = self.cache_dir / 'pathways'
        self.pathway_dir.mkdir(exist_ok=True)
        
        # Reactome data URL
        self.reactome_url = config.get(
            'reactome_url', 
            'https://reactome.org/download/current/NCBI2Reactome_All_Levels.txt'
        )
    
    def download_reactome(self) -> Path:
        """Download Reactome pathway data file with caching.
        
        Returns:
            Path to the downloaded file
            
        Raises:
            DownloadError: If download fails
        """
        try:
            # Use BaseProcessor's download method
            reactome_file = self.download_file(
                url=self.reactome_url,
                file_path=self.pathway_dir / "reactome_pathways.txt"
            )
            
            return reactome_file
        except Exception as e:
            raise DownloadError(f"Failed to download Reactome data: {e}")
    
    def process_pathways(self) -> Dict[str, Set[str]]:
        """Process Reactome pathway data into gene-to-pathway mappings.

        Returns:
            Dictionary mapping gene symbols to sets of pathway identifiers

        Raises:
            ProcessingError: If pathway processing fails
        """
        try:
            # First download the Reactome data
            reactome_file = self.download_reactome()

            self.logger.info(f"Processing Reactome pathway data from {reactome_file}")

            # Initialize gene to pathway mapping
            gene_to_pathways: Dict[str, Set[str]] = {}
            pathway_to_genes: Dict[str, Set[str]] = {}

            # Handle specific mappings between gene IDs and symbols
            ncbi_to_symbol = self._get_ncbi_mapping()

            # Parse file and extract pathway information
            with open(reactome_file, 'r') as f:
                # Skip header if present
                first_line = f.readline()
                if not first_line.startswith('NCBI'):
                    f.seek(0)  # Reset to beginning if no header

                # Process each line
                for line in tqdm(f, desc="Processing pathway data"):
                    parts = line.strip().split('\t')

                    # Check if line has required fields
                    if len(parts) < 6:
                        continue

                    gene_id = parts[0]
                    pathway_name = parts[3]
                    pathway_id = parts[1]
                    species = parts[5]

                    # Skip non-human pathways
                    if species != HUMAN_SPECIES:
                        continue

                    # Map gene ID to symbol if available
                    gene_symbol = ncbi_to_symbol.get(gene_id)
                    if not gene_symbol:
                        continue

                    # Format pathway string: "Pathway Name [Reactome:ID]"
                    pathway_string = f"{pathway_name} [Reactome:{pathway_id}]"

                    # Add to gene mappings
                    if gene_symbol not in gene_to_pathways:
                        gene_to_pathways[gene_symbol] = set()

                    gene_to_pathways[gene_symbol].add(pathway_string)

                    # Track genes per pathway for publication extraction
                    if pathway_id not in pathway_to_genes:
                        pathway_to_genes[pathway_id] = set()
                    pathway_to_genes[pathway_id].add(gene_symbol)

            # Log statistics
            total_genes = len(gene_to_pathways)
            avg_pathways = sum(len(pathways) for pathways in gene_to_pathways.values()) / max(1, total_genes)

            self.logger.info(
                f"Processed Reactome pathways:\n"
                f"- Total genes with pathways: {total_genes:,}\n"
                f"- Average pathways per gene: {avg_pathways:.1f}\n"
                f"- Total pathways: {len(pathway_to_genes):,}"
            )

            # Extract pathway publications using Reactome API
            self.logger.info("Extracting pathway publication references from Reactome API")
            pathway_publications = self._fetch_reactome_publications(pathway_to_genes)

            # Save pathway publications for use in enrichment
            if pathway_publications:
                self._save_pathway_publications(pathway_publications)
                self.logger.info(f"Saved publication data for {len(pathway_publications)} pathways")

            return gene_to_pathways

        except Exception as e:
            raise ProcessingError(f"Failed to process pathway data: {e}")
    
    def _extract_pathway_publications(self, evidence: str, pathway_id: str) -> List[Publication]:
        """Extract publication references from pathway evidence.

        Args:
            evidence: Evidence text from pathway data
            pathway_id: Reactome pathway ID

        Returns:
            List of Publication references
        """
        publications: List[Publication] = []

        # Extract PMIDs from evidence text
        pmids = extract_pmids_from_text(evidence)

        # Create publication references for each PMID
        for pmid in pmids:
            publication = PublicationsProcessor.create_publication_reference(
                pmid=pmid,
                evidence_type="pathway_evidence",
                source_db="Reactome",
                url=f"https://reactome.org/content/detail/{pathway_id}"
            )
            publications.append(publication)

        return publications

    def _fetch_reactome_publications(self, pathway_to_genes: Dict[str, Set[str]]) -> Dict[str, List[Publication]]:
        """Fetch publication references from Reactome Content Service API.

        Args:
            pathway_to_genes: Dictionary mapping pathway IDs to gene symbols

        Returns:
            Dictionary mapping pathway IDs to publication references
        """
        pathway_publications: Dict[str, List[Publication]] = {}
        api_base = "https://reactome.org/ContentService"

        # Sample first 100 pathways to avoid overwhelming the API
        # In production, you might want to cache this or use a different approach
        pathway_ids = list(pathway_to_genes.keys())[:100]

        self.logger.info(f"Fetching publications for {len(pathway_ids)} pathways from Reactome API")

        for pathway_id in tqdm(pathway_ids, desc="Fetching pathway publications"):
            try:
                # Query Reactome API for pathway publications
                url = f"{api_base}/data/pathway/{pathway_id}/literatureReferences"
                response = requests.get(url, timeout=10)

                if response.status_code == 200:
                    lit_refs = response.json()
                    publications = []

                    # Extract PMIDs from literature references
                    for ref in lit_refs:
                        # Check if reference has a PubMed ID
                        if 'pubMedIdentifier' in ref and ref['pubMedIdentifier']:
                            pmid = str(ref['pubMedIdentifier'])
                            publication = PublicationsProcessor.create_publication_reference(
                                pmid=pmid,
                                evidence_type="pathway_evidence",
                                source_db="Reactome",
                                url=f"https://reactome.org/content/detail/{pathway_id}"
                            )
                            publications.append(publication)

                    if publications:
                        pathway_publications[pathway_id] = publications

                elif response.status_code == 404:
                    # Pathway not found in API, skip silently
                    continue
                else:
                    self.logger.warning(f"Failed to fetch publications for pathway {pathway_id}: HTTP {response.status_code}")

            except requests.exceptions.Timeout:
                self.logger.warning(f"Timeout fetching publications for pathway {pathway_id}")
                continue
            except Exception as e:
                self.logger.warning(f"Error fetching publications for pathway {pathway_id}: {e}")
                continue

        total_pmids = sum(len(pubs) for pubs in pathway_publications.values())
        self.logger.info(
            f"Extracted pathway publications:\n"
            f"- Pathways with publications: {len(pathway_publications):,}\n"
            f"- Total PMIDs: {total_pmids:,}\n"
            f"- Average PMIDs per pathway: {total_pmids/max(1, len(pathway_publications)):.1f}"
        )

        return pathway_publications
    
    def _save_pathway_publications(self, pathway_publications: Dict[str, List[Publication]]) -> None:
        """Save pathway publication references to cache.
        
        Args:
            pathway_publications: Dictionary mapping pathways to publication references
        """
        pub_cache_path = self.pathway_dir / "pathway_publications.json"
        
        # Convert Publications to dictionaries for JSON serialization
        serializable_pubs = {}
        for pathway, pubs in pathway_publications.items():
            serializable_pubs[pathway] = [vars(pub) for pub in pubs]
        
        with open(pub_cache_path, 'w') as f:
            json.dump(serializable_pubs, f)
    
    def _load_pathway_publications(self) -> Dict[str, List[Publication]]:
        """Load pathway publication references from cache.
        
        Returns:
            Dictionary mapping pathways to publication references
        """
        pub_cache_path = self.pathway_dir / "pathway_publications.json"
        
        if not pub_cache_path.exists():
            return {}
        
        try:
            with open(pub_cache_path, 'r') as f:
                pub_dict = json.load(f)
            
            # Convert dictionaries back to Publication objects
            publications = {}
            for pathway, pubs in pub_dict.items():
                publications[pathway] = [Publication(**pub) for pub in pubs]
            
            return publications
            
        except Exception as e:
            self.logger.warning(f"Failed to load pathway publications: {e}")
            return {}
    
    def _get_ncbi_mapping(self) -> Dict[str, str]:
        """Get mapping from NCBI gene IDs to gene symbols using normalized schema.

        Returns:
            Dictionary mapping NCBI IDs to gene symbols
        """
        if not self.ensure_connection() or not self.db_manager.cursor:
            self.logger.warning("Cannot get NCBI mappings: no database connection")
            return {}

        try:
            # Query gene_cross_references table for NCBI ID mappings (normalized schema)
            # FIXED: Added 'GeneID' to the filter - this is what transcript.py actually writes
            self.db_manager.cursor.execute("""
                SELECT DISTINCT
                    g.gene_symbol,
                    gcr.external_id as ncbi_id,
                    gcr.external_db
                FROM gene_cross_references gcr
                INNER JOIN genes g ON gcr.gene_id = g.gene_id
                WHERE gcr.external_db IN ('GeneID', 'NCBI', 'EntrezGene')
                    AND gcr.external_id IS NOT NULL
                    AND gcr.external_id ~ '^[0-9]+$'
            """)

            # Build bidirectional mapping dictionary (NCBI→Symbol and Symbol→NCBI)
            ncbi_to_symbol = {}
            symbol_to_ncbi = {}
            db_type_counts = {}

            rows = self.db_manager.cursor.fetchall()
            self.logger.info(f"Found {len(rows)} NCBI ID mappings in gene_cross_references")

            for row in rows:
                gene_symbol, ncbi_id, external_db = row

                # Track which external_db types we're seeing
                db_type_counts[external_db] = db_type_counts.get(external_db, 0) + 1

                if ncbi_id and gene_symbol:
                    # NCBI → Symbol mapping
                    ncbi_to_symbol[ncbi_id] = gene_symbol
                    ncbi_to_symbol[ncbi_id.upper()] = gene_symbol

                    # Symbol → NCBI mapping (for reverse lookups)
                    symbol_to_ncbi[gene_symbol] = ncbi_id
                    symbol_to_ncbi[normalize_gene_symbol(gene_symbol)] = ncbi_id

            # Diagnostic logging
            self.logger.info(f"External DB type distribution: {db_type_counts}")
            if ncbi_to_symbol:
                sample_mappings = list(ncbi_to_symbol.items())[:5]
                self.logger.info(f"Sample NCBI mappings: {sample_mappings}")

            # Combine both mapping directions into single dictionary
            mapping = {**ncbi_to_symbol, **symbol_to_ncbi}

            # If no mappings found in gene_cross_references, use direct gene symbol mapping
            if not mapping:
                self.logger.warning(
                    "No NCBI ID mappings found in gene_cross_references with external_db in "
                    "('GeneID', 'NCBI', 'EntrezGene'). This likely means transcript data was not "
                    "loaded with NCBI cross-references. Using direct symbol mapping as fallback."
                )

                # Query genes table for gene symbols to use for direct mapping
                self.db_manager.cursor.execute("""
                    SELECT DISTINCT gene_symbol
                    FROM genes
                    WHERE gene_symbol IS NOT NULL
                """)

                # Create a self-mapping for known gene symbols with normalized keys
                for row in self.db_manager.cursor.fetchall():
                    gene_symbol = row[0]
                    if gene_symbol:
                        mapping[gene_symbol] = gene_symbol
                        mapping[normalize_gene_symbol(gene_symbol)] = gene_symbol

                self.logger.info(f"Using {len(mapping)} gene symbols for direct mapping")
            else:
                self.logger.info(
                    f"Retrieved {len(ncbi_to_symbol)} NCBI→Symbol and {len(symbol_to_ncbi)} "
                    f"Symbol→NCBI mappings (total {len(mapping)} entries)"
                )

            return mapping

        except Exception as e:
            self.logger.error(f"Failed to get NCBI mappings: {e}", exc_info=True)
            return {}
    
    def enrich_transcripts(self, gene_to_pathways: Dict[str, Set[str]]) -> None:
        """Enrich transcript records with pathway data.
        
        Args:
            gene_to_pathways: Dictionary mapping gene symbols to pathways
            
        Raises:
            DatabaseError: If database operations fail
        """
        if not self.ensure_connection():
            raise DatabaseError("Database connection failed")
        
        if not gene_to_pathways:
            self.logger.warning("No pathway data to enrich transcripts with")
            return
        
        try:
            self.logger.info("Enriching transcripts with pathway data")
            
            # Add diagnostic query to count genes before processing (using normalized schema)
            if not self.db_manager.cursor:
                raise DatabaseError("No database cursor available")

            self.db_manager.cursor.execute("""
                SELECT
                    COUNT(DISTINCT g.gene_id) as total_genes,
                    COUNT(DISTINCT gp.gene_id) as genes_with_pathways
                FROM genes g
                LEFT JOIN gene_pathways gp ON g.gene_id = gp.gene_id
            """)

            stats = self.db_manager.cursor.fetchone()
            if stats:
                self.logger.info(
                    f"Before pathway enrichment:\n"
                    f"- Total genes: {stats[0]:,}\n"
                    f"- Genes with pathways: {stats[1]:,} ({stats[1]/max(1, stats[0])*100:.1f}%)"
                )
                
            # Load pathway publications
            pathway_publications = self._load_pathway_publications()
            
            # Get all gene symbols from the database for matching (using normalized schema)
            if not self.db_manager.cursor:
                raise DatabaseError("No database cursor available")

            self.db_manager.cursor.execute("""
                SELECT DISTINCT gene_symbol FROM genes
                WHERE gene_symbol IS NOT NULL
            """)
            db_genes = [row[0] for row in self.db_manager.cursor.fetchall() if row[0]]
            
            # Match our pathway genes to database genes
            pathway_genes = list(gene_to_pathways.keys())
            matched_genes = match_genes_bulk(pathway_genes, db_genes, use_fuzzy=True)
            
            # Log matching statistics
            match_stats = get_gene_match_stats(pathway_genes, matched_genes)
            self.logger.info(
                f"Gene matching statistics:\n"
                f"- Total pathway genes: {match_stats['total_genes']}\n"
                f"- Matched to database: {match_stats['matched_genes']} ({match_stats['match_rate']}%)\n"
                f"- Unmatched genes: {match_stats['unmatched_genes']}"
            )
            
            # Prepare updates for each gene
            updates = []
            
            for gene_symbol, pathways in tqdm(gene_to_pathways.items(), desc="Preparing pathway updates"):
                # Skip empty pathway sets
                if not pathways:
                    continue
                
                # Use matched gene symbol if available
                db_gene = matched_genes.get(gene_symbol)
                if not db_gene:
                    continue
                    
                # Get publication references for this gene's pathways
                gene_publications = []
                for pathway in pathways:
                    # Extract pathway ID from string
                    match = re.search(r'\[Reactome:(R-[A-Z]+-\d+)\]', pathway)
                    pathway_id = match.group(1) if match else None
                    
                    # Add publication references if available
                    if pathway_id and pathway_id in pathway_publications:
                        gene_publications.extend(pathway_publications[pathway_id])
                
                # Add update to batch
                updates.append((
                    list(pathways),
                    json.dumps(gene_publications),
                    db_gene
                ))
                
                # Process in batches
                if len(updates) >= self.batch_size:
                    self._update_batch(updates)
                    updates = []
            
            # Process remaining updates
            if updates:
                self._update_batch(updates)
            
            # At the end of the method, add another diagnostic query (using normalized schema)
            self.db_manager.cursor.execute("""
                SELECT
                    COUNT(DISTINCT g.gene_id) as total_genes,
                    COUNT(DISTINCT gp.gene_id) as genes_with_pathways,
                    COALESCE(AVG(pathway_counts.pathway_count), 0) as avg_pathway_count
                FROM genes g
                LEFT JOIN gene_pathways gp ON g.gene_id = gp.gene_id
                LEFT JOIN (
                    SELECT gene_id, COUNT(*) as pathway_count
                    FROM gene_pathways
                    GROUP BY gene_id
                ) pathway_counts ON g.gene_id = pathway_counts.gene_id
            """)

            stats = self.db_manager.cursor.fetchone()
            if stats:
                self.logger.info(
                    f"After pathway enrichment:\n"
                    f"- Total genes: {stats[0]:,}\n"
                    f"- Genes with pathways: {stats[1]:,} ({stats[1]/max(1, stats[0])*100:.1f}%)\n"
                    f"- Average pathways per gene: {stats[2]:.2f}"
                )
                
            self.logger.info("Pathway enrichment completed successfully")
            
        except Exception as e:
            if self.db_manager.conn:
                self.db_manager.conn.rollback()
            raise DatabaseError(f"Failed to enrich transcripts with pathways: {e}")
    
    def _update_batch(self, updates: List[Tuple[List[str], str, str]]) -> None:
        """Update a batch of transcript records with pathway data.

        Writes pathway data to the gene_pathways normalized table.

        Args:
            updates: List of tuples with (pathways, publications_json, gene_symbol)

        Raises:
            DatabaseError: If batch update fails
        """
        if not self.db_manager.cursor:
            raise DatabaseError("No database cursor available")

        try:
            # Prepare batch inserts for gene_pathways table
            pathway_inserts = []

            for pathways_list, publications_json, gene_symbol in updates:
                # For each pathway string, extract ID and name
                for pathway_string in pathways_list:
                    # Parse pathway string format: "Pathway Name [Reactome:ID]"
                    match = re.search(r'^(.+)\s+\[Reactome:(R-[A-Z]+-\d+)\]$', pathway_string)
                    if match:
                        pathway_name = match.group(1).strip()
                        pathway_id = match.group(2)

                        pathway_inserts.append((
                            gene_symbol,
                            pathway_id,
                            pathway_name,
                            'Reactome'
                        ))

            if pathway_inserts:
                # Insert into gene_pathways table
                self.db_manager.cursor.execute("""
                    INSERT INTO gene_pathways (gene_id, pathway_id, pathway_name, pathway_source)
                    SELECT
                        g.gene_id,
                        data.pathway_id,
                        data.pathway_name,
                        data.pathway_source
                    FROM (VALUES %s) AS data(gene_symbol, pathway_id, pathway_name, pathway_source)
                    INNER JOIN genes g ON g.gene_symbol = data.gene_symbol
                    ON CONFLICT (gene_id, pathway_id, pathway_source) DO NOTHING
                """ % ','.join([
                    self.db_manager.cursor.mogrify("(%s,%s,%s,%s)", row).decode('utf-8')
                    for row in pathway_inserts
                ]))

                self.db_manager.conn.commit()
                self.logger.debug(f"Inserted {len(pathway_inserts)} pathway mappings from batch of {len(updates)} genes")

        except Exception as e:
            if self.db_manager.conn:
                self.db_manager.conn.rollback()
            raise DatabaseError(f"Failed to update pathway batch: {e}")
    
    def extract_pathway_references(self, pathway_data: Dict[str, Any]) -> List[Publication]:
        """Extract publication references from pathway data.
        
        Args:
            pathway_data: Dictionary containing pathway data
            
        Returns:
            List of Publication references
        """
        publications: List[Publication] = []
        
        # Extract pathway ID and evidence
        pathway_id = pathway_data.get('id', '')
        evidence = pathway_data.get('evidence', '')
        
        # Extract PMIDs from evidence text
        if evidence and isinstance(evidence, str):
            pmids = extract_pmids_from_text(evidence)
            
            for pmid in pmids:
                publication = PublicationsProcessor.create_publication_reference(
                    pmid=pmid,
                    evidence_type="pathway_evidence",
                    source_db="Reactome",
                    url=f"https://reactome.org/content/detail/{pathway_id}" if pathway_id else None
                )
                publications.append(publication)
        
        return publications
    
    def integrate_pathways(self, pathway_data: Dict[str, List[Dict[str, Any]]]) -> None:
        """Integrate pathway data into transcript database.
        
        Args:
            pathway_data: Dictionary mapping gene IDs to pathway lists
            
        Raises:
            DatabaseError: If database operations fail
        """
        if not self.ensure_connection():
            raise DatabaseError("Database connection failed")
            
        try:
            self.logger.info("Integrating pathway data with transcript records")
            
            # Create temporary table for batch updates with extended ID support
            with self.get_db_transaction() as transaction:
                transaction.cursor.execute("""
                    CREATE TEMP TABLE temp_pathway_data (
                        gene_symbol TEXT PRIMARY KEY,
                        uniprot_ids TEXT[],
                        pathways TEXT[],
                        pathway_details JSONB,
                        pathway_references JSONB
                    ) ON COMMIT DROP
                """)
            
            updates = []
            processed = 0
            
            # Process each gene's pathway data
            for gene_symbol, pathways in pathway_data.items():
                # Skip empty data
                if not gene_symbol or not pathways:
                    continue
                    
                # Get additional IDs for this gene from normalized schema (gene_cross_references)
                uniprot_ids = []
                if self.db_manager.cursor:
                    self.db_manager.cursor.execute("""
                        SELECT ARRAY_AGG(DISTINCT gcr.external_id)
                        FROM gene_cross_references gcr
                        INNER JOIN genes g ON gcr.gene_id = g.gene_id
                        WHERE g.gene_symbol = %s
                          AND gcr.external_db = 'UniProt'
                          AND gcr.external_id IS NOT NULL
                    """, (gene_symbol,))
                    result = self.db_manager.cursor.fetchone()
                    if result and result[0]:
                        uniprot_ids = result[0]
                
                # Extract pathway IDs and details
                pathway_ids = []
                pathway_map = {}
                all_references = []
                
                for pathway in pathways:
                    pathway_id = pathway.get('id')
                    if not pathway_id:
                        continue
                        
                    pathway_ids.append(pathway_id)
                    
                    # Structure detailed pathway info
                    pathway_map[pathway_id] = {
                        'name': pathway.get('name', ''),
                        'source': pathway.get('source', 'reactome'),
                        'url': pathway.get('url', '')
                    }
                    
                    # Extract references
                    if 'references' in pathway:
                        all_references.extend(pathway['references'])
                
                updates.append((
                    gene_symbol,
                    uniprot_ids,
                    pathway_ids,
                    json.dumps(pathway_map),
                    json.dumps(all_references)
                ))
                
                processed += 1
                
                # Process in batches
                if len(updates) >= self.batch_size:
                    self._update_pathway_batch(updates)
                    updates = []
                    self.logger.info(f"Processed {processed} genes with pathway data")
            
            # Process any remaining updates
            if updates:
                self._update_pathway_batch(updates)
            
            # Update normalized schema: create gene pathway relationships
            with self.get_db_transaction() as transaction:
                # Insert pathway data into normalized schema
                transaction.cursor.execute("""
                    INSERT INTO gene_pathways (gene_id, pathway_id, pathway_name, pathway_source)
                    SELECT
                        g.gene_id,
                        pathway_detail.key as pathway_id,
                        pathway_detail.value->>'name' as pathway_name,
                        COALESCE(pathway_detail.value->>'source', 'Reactome') as pathway_source
                    FROM temp_pathway_data pw
                    INNER JOIN genes g ON g.gene_symbol = pw.gene_symbol
                    CROSS JOIN LATERAL jsonb_each(pw.pathway_details) as pathway_detail
                    ON CONFLICT DO NOTHING
                """)

                # Legacy table updates removed - using normalized schema only
                # Pathway data is already written to gene_pathways table above (line 565-575)
                self.logger.debug(f"Legacy table updates skipped (using normalized schema)")
                
                # Clean up
                transaction.cursor.execute("DROP TABLE IF EXISTS temp_pathway_data")
            
            self.logger.info(f"Successfully integrated pathway data for {processed} genes")
            
        except Exception as e:
            self.logger.error(f"Failed to integrate pathway data: {e}")
            raise DatabaseError(f"Pathway integration failed: {e}")

    def _update_pathway_batch(self, updates: List[Tuple[str, List[str], List[str], str, str]]) -> None:
        """Update a batch of pathway data.
        
        Args:
            updates: List of tuples with (gene_symbol, uniprot_ids, pathways, pathway_details_json, pathway_references_json)
            
        Raises:
            DatabaseError: If batch update fails
        """
        try:
            self.execute_batch(
                """
                INSERT INTO temp_pathway_data 
                (gene_symbol, uniprot_ids, pathways, pathway_details, pathway_references)
                VALUES (%s, %s, %s, %s::jsonb, %s::jsonb)
                ON CONFLICT (gene_symbol) DO UPDATE SET
                    uniprot_ids = EXCLUDED.uniprot_ids,
                    pathways = array(
                        SELECT DISTINCT unnest(
                            array_cat(temp_pathway_data.pathways, EXCLUDED.pathways)
                        )
                    ),
                    pathway_details = temp_pathway_data.pathway_details || EXCLUDED.pathway_details,
                    pathway_references = temp_pathway_data.pathway_references || EXCLUDED.pathway_references
                """,
                updates
            )
        except Exception as e:
            raise DatabaseError(f"Failed to update pathway batch: {e}")

    def run(self) -> None:
        """Run the complete pathway enrichment pipeline."""
        try:
            self.logger.info("Starting pathway enrichment pipeline")
            
            # Check schema version using enhanced base class method
            if not self.ensure_schema_version('v0.1.3'):
                raise DatabaseError("Incompatible database schema version")
            
            # Process pathway data
            gene_to_pathways = self.process_pathways()
            
            # Enrich transcript records
            self.enrich_transcripts(gene_to_pathways)
            
            self.logger.info("Pathway enrichment pipeline completed successfully")
            
        except Exception as e:
            self.logger.error(f"Pathway enrichment failed: {e}")
            raise

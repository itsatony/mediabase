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
            
            # Log statistics
            total_genes = len(gene_to_pathways)
            avg_pathways = sum(len(pathways) for pathways in gene_to_pathways.values()) / max(1, total_genes)
            
            self.logger.info(
                f"Processed Reactome pathways:\n"
                f"- Total genes with pathways: {total_genes:,}\n"
                f"- Average pathways per gene: {avg_pathways:.1f}"
            )
            
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
        """Get mapping from NCBI gene IDs to gene symbols.
        
        Returns:
            Dictionary mapping NCBI IDs to gene symbols
        """
        if not self.ensure_connection() or not self.db_manager.cursor:
            self.logger.warning("Cannot get NCBI mappings: no database connection")
            return {}
        
        try:
            # Query database for existing gene symbols and NCBI IDs
            self.db_manager.cursor.execute("""
                SELECT 
                    gene_symbol,
                    unnest(ncbi_ids) as ncbi_id
                FROM 
                    cancer_transcript_base
                WHERE 
                    ncbi_ids IS NOT NULL
                    AND array_length(ncbi_ids, 1) > 0
            """)
            
            # Build mapping dictionary
            mapping = {}
            for row in self.db_manager.cursor.fetchall():
                gene_symbol, ncbi_id = row
                if ncbi_id and gene_symbol:
                    mapping[ncbi_id] = gene_symbol
            
            # If no mappings found in database, use a fallback
            if not mapping:
                self.logger.warning("No NCBI ID mappings found in database, using direct symbol mapping")
                
                # Query database for gene symbols to use for direct mapping
                self.db_manager.cursor.execute("""
                    SELECT DISTINCT gene_symbol
                    FROM cancer_transcript_base
                    WHERE gene_type = 'protein_coding'
                """)
                
                # Create a self-mapping for known gene symbols
                for row in self.db_manager.cursor.fetchall():
                    gene_symbol = row[0]
                    if gene_symbol:
                        mapping[gene_symbol] = gene_symbol
            
            self.logger.info(f"Retrieved {len(mapping)} NCBI ID to gene symbol mappings")
            return mapping
            
        except Exception as e:
            self.logger.error(f"Failed to get NCBI mappings: {e}")
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
            
            # Load pathway publications
            pathway_publications = self._load_pathway_publications()
            
            # Prepare updates for each gene
            updates = []
            
            for gene_symbol, pathways in tqdm(gene_to_pathways.items(), desc="Preparing pathway updates"):
                # Skip empty pathway sets
                if not pathways:
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
                    gene_symbol
                ))
                
                # Process in batches
                if len(updates) >= self.batch_size:
                    self._update_batch(updates)
                    updates = []
            
            # Process remaining updates
            if updates:
                self._update_batch(updates)
            
            self.logger.info("Pathway enrichment completed successfully")
            
        except Exception as e:
            if self.db_manager.conn:
                self.db_manager.conn.rollback()
            raise DatabaseError(f"Failed to enrich transcripts with pathways: {e}")
    
    def _update_batch(self, updates: List[Tuple[List[str], str, str]]) -> None:
        """Update a batch of transcript records with pathway data.
        
        Args:
            updates: List of tuples with (pathways, publications_json, gene_symbol)
            
        Raises:
            DatabaseError: If batch update fails
        """
        if not self.db_manager.cursor:
            raise DatabaseError("No database cursor available")
        
        try:
            # First ensure we have a valid transaction
            with self.get_db_transaction():
                # Execute batch update
                # FIX: Change $1, $2, $3 style parameters to %s style parameters
                self.execute_batch(
                    """
                    UPDATE cancer_transcript_base
                    SET 
                        pathways = %s::text[],
                        source_references = jsonb_set(
                            COALESCE(source_references, '{}'::jsonb),
                            '{pathways}',
                            %s::jsonb,
                            true
                        )
                    WHERE gene_symbol = %s
                    """,
                    [(p, j, g) for p, j, g in updates]
                )
                
        except Exception as e:
            self.logger.error(f"Batch update failed: {e}")
            raise DatabaseError(f"Failed to update pathways batch: {e}")
    
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
                        gene_symbol TEXT,
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
                    
                # Get additional IDs for this gene for more comprehensive mapping
                uniprot_ids = []
                if self.db_manager.cursor:
                    self.db_manager.cursor.execute("""
                        SELECT uniprot_ids 
                        FROM cancer_transcript_base
                        WHERE gene_symbol = %s AND uniprot_ids IS NOT NULL
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
            
            # Update main table from temp table using multiple ID types
            with self.get_db_transaction() as transaction:
                # First update by gene symbol
                transaction.cursor.execute("""
                    UPDATE cancer_transcript_base cb
                    SET 
                        pathways = COALESCE(cb.pathways, '{}'::text[]) || pw.pathways,
                        features = COALESCE(cb.features, '{}'::jsonb) || 
                                   jsonb_build_object('pathways', pw.pathway_details),
                        source_references = jsonb_set(
                            COALESCE(cb.source_references, '{
                                "go_terms": [],
                                "uniprot": [],
                                "drugs": [],
                                "pathways": []
                            }'::jsonb),
                            '{pathways}',
                            pw.pathway_references,
                            true
                        )
                    FROM temp_pathway_data pw
                    WHERE cb.gene_symbol = pw.gene_symbol
                """)
                
                # Then update by UniProt IDs for better coverage
                transaction.cursor.execute("""
                    UPDATE cancer_transcript_base cb
                    SET 
                        pathways = COALESCE(cb.pathways, '{}'::text[]) || pw.pathways,
                        features = COALESCE(cb.features, '{}'::jsonb) || 
                                   jsonb_build_object('pathways', pw.pathway_details),
                        source_references = jsonb_set(
                            COALESCE(cb.source_references, '{
                                "go_terms": [],
                                "uniprot": [],
                                "drugs": [],
                                "pathways": []
                            }'::jsonb),
                            '{pathways}',
                            pw.pathway_references,
                            true
                        )
                    FROM temp_pathway_data pw
                    WHERE cb.uniprot_ids && pw.uniprot_ids
                    AND cb.gene_symbol != pw.gene_symbol  -- Only update non-direct matches
                    AND pw.uniprot_ids IS NOT NULL
                    AND array_length(pw.uniprot_ids, 1) > 0
                """)
                
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

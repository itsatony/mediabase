"""Gene product classification module for cancer transcriptome base.

This module provides functionality for classifying gene products based on
UniProt features, GO terms, and other annotations. It enriches transcript
records with product_type classifications.
"""

# Standard library imports
import json
import gzip
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple, Iterator
from datetime import datetime, timedelta

# Third party imports
import pandas as pd
import requests
from tqdm import tqdm
from psycopg2.extras import execute_batch
from rich.console import Console

# Local imports
from .base_processor import BaseProcessor, DownloadError, ProcessingError, DatabaseError
from ..utils.publication_utils import extract_pmids_from_text, format_pmid_url
from .publications import Publication, PublicationsProcessor

# Constants
DEFAULT_PRODUCT_TYPES = [
    "enzyme", "kinase", "phosphatase", "protease", "transcription_factor",
    "ion_channel", "receptor", "transporter", "structural_protein", "signaling_molecule",
    "dna_binding", "rna_binding", "lipid_binding", "metal_binding", "membrane_associated",
    "secreted", "nuclear", "mitochondrial", "cytoplasmic", "chaperone", "regulatory_protein"
]

class ProductClassifier(BaseProcessor):
    """Classifies gene products based on features, GO terms, and annotations."""
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize the product classifier with configuration.
        
        Args:
            config: Configuration dictionary containing cache settings, etc.
        """
        super().__init__(config)
        
        # Set up processor-specific paths
        self.products_dir = self.cache_dir / "products"
        self.products_dir.mkdir(exist_ok=True)
        
        # UniProt data URL
        self.uniprot_url = config.get(
            'uniprot_url', 
            'https://ftp.uniprot.org/pub/databases/uniprot/current_release/knowledgebase/idmapping/by_organism/HUMAN_9606_idmapping.dat.gz'
        )
        
        # Features mapping
        self.feature_to_type = {
            "kinase": ["kinase"],
            "phosphatase": ["phosphatase"],
            "protease": ["protease", "peptidase"],
            "transcription factor": ["transcription_factor", "dna_binding"],
            "ion channel": ["ion_channel", "channel"],
            "receptor": ["receptor"],
            "transport": ["transporter"],
            "DNA binding": ["dna_binding", "transcription_factor"],
            "RNA binding": ["rna_binding"],
            "lipid binding": ["lipid_binding"],
            "metal binding": ["metal_binding"],
            "transmembrane": ["membrane_associated"],
            "signal peptide": ["secreted"],
            "nucleotide binding": ["enzyme"],
            "cofactor": ["enzyme"],
            "active site": ["enzyme"],
            "regulatory": ["regulatory_protein"],
            "chaperone": ["chaperone"],
            "enzyme": ["enzyme"],
            "structural": ["structural_protein"],
            "zinc finger": ["dna_binding"],
            "nuclear": ["nuclear"],
            "mitochondrial": ["mitochondrial"],
            "cytoplasm": ["cytoplasmic"],
        }
        
        # GO term mapping
        self.go_to_type = {
            "GO:0003700": ["transcription_factor", "dna_binding"],  # TF activity
            "GO:0004672": ["kinase"],  # protein kinase activity
            "GO:0004721": ["phosphatase"],  # phosphatase activity
            "GO:0008233": ["protease"],  # peptidase activity
            "GO:0005216": ["ion_channel"],  # ion channel activity
            "GO:0004888": ["receptor"],  # transmembrane receptor activity
            "GO:0005215": ["transporter"],  # transporter activity
            "GO:0003677": ["dna_binding"],  # DNA binding
            "GO:0003723": ["rna_binding"],  # RNA binding
            "GO:0008289": ["lipid_binding"],  # lipid binding
            "GO:0046872": ["metal_binding"],  # metal ion binding
            "GO:0016020": ["membrane_associated"],  # membrane
            "GO:0005576": ["secreted"],  # extracellular region
            "GO:0005634": ["nuclear"],  # nucleus
            "GO:0005739": ["mitochondrial"],  # mitochondrion
            "GO:0005737": ["cytoplasmic"],  # cytoplasm
            "GO:0006457": ["chaperone"],  # protein folding
            "GO:0003824": ["enzyme"],  # catalytic activity
            "GO:0005198": ["structural_protein"],  # structural molecule activity
        }
    
    def download_uniprot_data(self) -> Path:
        """Download UniProt data file with caching.
        
        Returns:
            Path to the downloaded file
            
        Raises:
            DownloadError: If download fails
        """
        try:
            # Use the BaseProcessor download method
            uniprot_file = self.download_file(
                url=self.uniprot_url,
                file_path=self.products_dir / "human_uniprot.dat.gz"
            )
            
            return uniprot_file
        except Exception as e:
            raise DownloadError(f"Failed to download UniProt data: {e}")
    
    def classify_gene(self, gene_data: Dict[str, Any]) -> List[str]:
        """Classify a gene based on its features, GO terms, and keywords.
        
        Args:
            gene_data: Dictionary containing gene data with features, GO terms, etc.
            
        Returns:
            List of product type classifications
        """
        product_types: Set[str] = set()
        
        # Classify based on features
        features = gene_data.get('features', {})
        for feature_key, feature_value in features.items():
            for key_pattern, types in self.feature_to_type.items():
                if key_pattern.lower() in feature_key.lower():
                    product_types.update(types)
        
        # Classify based on GO terms
        go_terms = gene_data.get('go_terms', {})
        for go_id in go_terms:
            if go_id in self.go_to_type:
                product_types.update(self.go_to_type[go_id])
        
        # Classify based on keywords
        keywords = gene_data.get('keywords', [])
        for keyword in keywords:
            keyword_lower = keyword.lower()
            for key_pattern, types in self.feature_to_type.items():
                if key_pattern.lower() in keyword_lower:
                    product_types.update(types)
        
        # Add additional info from function field
        function_text = gene_data.get('function', '')
        if function_text and isinstance(function_text, str):
            # Look for common patterns in function descriptions
            function_text = function_text.lower()
            
            if any(term in function_text for term in ["transcription factor", "dna-binding", "transcriptional regulator"]):
                product_types.update(["transcription_factor", "dna_binding"])
                
            if any(term in function_text for term in ["kinase", "phosphorylation"]):
                product_types.add("kinase")
                
            if any(term in function_text for term in ["phosphatase", "dephosphorylation"]):
                product_types.add("phosphatase")
                
            if any(term in function_text for term in ["protease", "peptidase", "proteolytic"]):
                product_types.add("protease")
                
            if any(term in function_text for term in ["ion channel", "ion transport"]):
                product_types.add("ion_channel")
                
            if any(term in function_text for term in ["receptor", "ligand binding"]):
                product_types.add("receptor")
                
            if any(term in function_text for term in ["transporter", "transport"]):
                product_types.add("transporter")
                
            if "enzyme" in function_text or "catalytic" in function_text:
                product_types.add("enzyme")
        
        return sorted(list(product_types))
    
    def extract_publication_references(self, gene_data: Dict[str, Any]) -> List[Publication]:
        """Extract publication references from gene data.
        
        Args:
            gene_data: Dictionary containing gene data
            
        Returns:
            List of Publication references
        """
        publications: List[Publication] = []
        
        # Extract from function field
        function_text = gene_data.get('function', '')
        if function_text and isinstance(function_text, str):
            pmids = extract_pmids_from_text(function_text)
            for pmid in pmids:
                publication = PublicationsProcessor.create_publication_reference(
                    pmid=pmid,
                    evidence_type="function_description",
                    source_db="UniProt"
                )
                publications.append(publication)
        
        # Extract from features
        features = gene_data.get('features', {})
        for feature_key, feature_value in features.items():
            if isinstance(feature_value, str):
                pmids = extract_pmids_from_text(feature_value)
                for pmid in pmids:
                    publication = PublicationsProcessor.create_publication_reference(
                        pmid=pmid,
                        evidence_type=f"feature:{feature_key}",
                        source_db="UniProt"
                    )
                    publications.append(publication)
        
        return publications

    def run(self) -> None:
        """Run the product classification process."""
        try:
            self.logger.info("Starting gene product classification")
            
            # Download UniProt data
            uniprot_file = self.download_uniprot_data()
            
            # Process data (would be implemented in a subclass or extended here)
            self.logger.info("UniProt data downloaded successfully")
            
        except Exception as e:
            self.logger.error(f"Product classification failed: {e}")
            raise


class ProductProcessor(BaseProcessor):
    """Process gene product data and classify transcripts."""
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize product processor with configuration.
        
        Args:
            config: Configuration dictionary with all needed settings
        """
        super().__init__(config)
        
        # Create classifier for product classification
        self.classifier = ProductClassifier(config)
        
        # Other processor-specific settings
        self.batch_size = config.get('batch_size', 100)
        self.process_limit = config.get('process_limit')
        if self.process_limit:
            try:
                self.process_limit = int(self.process_limit)
                self.logger.info(f"Processing limited to {self.process_limit} genes")
            except (ValueError, TypeError):
                self.logger.warning(f"Invalid process_limit value: {self.process_limit}, processing all genes")
                self.process_limit = None
    
    def get_genes_with_features(self) -> List[Dict[str, Any]]:
        """Get genes with features from the database.
        
        Returns:
            List of genes with features data
            
        Raises:
            DatabaseError: If database operations fail
        """
        if not self.ensure_connection():
            raise DatabaseError("Database connection failed")
        
        try:
            self.logger.info("Retrieving genes with features from database")
            
            if not self.db_manager.cursor:
                raise DatabaseError("No database cursor available")
            
            # Get genes with features
            self.db_manager.cursor.execute("""
                SELECT 
                    gene_symbol, 
                    features,
                    go_terms,
                    source_references
                FROM 
                    cancer_transcript_base
                WHERE 
                    gene_type = 'protein_coding'
                AND 
                    features IS NOT NULL
                AND 
                    features != '{}'::jsonb
                GROUP BY
                    gene_symbol, features, go_terms, source_references
            """)
            
            genes = []
            for row in self.db_manager.cursor.fetchall():
                gene_symbol, features, go_terms, source_refs = row
                genes.append({
                    'gene_symbol': gene_symbol,
                    'features': features,
                    'go_terms': go_terms or {},
                    'source_references': source_refs or {},
                })
            
            if self.process_limit and len(genes) > self.process_limit:
                genes = genes[:self.process_limit]
                self.logger.info(f"Limited to {self.process_limit} genes")
                
            self.logger.info(f"Retrieved {len(genes)} genes with features")
            return genes
            
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve genes with features: {e}")
    
    def classify_genes(self, genes: List[Dict[str, Any]]) -> List[Tuple[str, List[str], List[Publication]]]:
        """Classify genes based on their features and GO terms.
        
        Args:
            genes: List of genes with features and GO terms
            
        Returns:
            List of tuples with (gene_symbol, product_types, publications)
            
        Raises:
            ProcessingError: If classification fails
        """
        try:
            self.logger.info("Classifying genes based on features and GO terms")
            
            classified_genes = []
            for gene in tqdm(genes, desc="Classifying genes"):
                gene_symbol = gene['gene_symbol']
                product_types = self.classifier.classify_gene(gene)
                publications = self.classifier.extract_publication_references(gene)
                
                if product_types:
                    classified_genes.append((gene_symbol, product_types, publications))
            
            self.logger.info(f"Classified {len(classified_genes)} genes")
            return classified_genes
            
        except Exception as e:
            raise ProcessingError(f"Gene classification failed: {e}")
    
    def update_gene_types(self, classified_genes: List[Tuple[str, List[str], List[Publication]]]) -> None:
        """Update gene product types in the database.
        
        Args:
            classified_genes: List of tuples with (gene_symbol, product_types, publications)
            
        Raises:
            DatabaseError: If database operations fail
        """
        if not self.ensure_connection():
            raise DatabaseError("Database connection failed")
        
        try:
            self.logger.info("Updating gene product types in database")
            
            if not self.db_manager.cursor:
                raise DatabaseError("No database cursor available")
            
            # Create temporary table for batch updates
            self.db_manager.cursor.execute("""
                CREATE TEMP TABLE temp_gene_types (
                    gene_symbol TEXT PRIMARY KEY,
                    product_types TEXT[],
                    publications JSONB
                )
            """)
            
            # Process in batches for better performance
            total_genes = len(classified_genes)
            total_inserted = 0
            
            with tqdm(total=total_genes, desc="Updating gene types") as pbar:
                for i in range(0, total_genes, self.batch_size):
                    batch = classified_genes[i:i+self.batch_size]
                    
                    # Insert batch into temp table
                    self.execute_batch(
                        """
                        INSERT INTO temp_gene_types (gene_symbol, product_types, publications)
                        VALUES (%s, %s, %s::jsonb)
                        """,
                        [(gene, types, json.dumps(pubs)) for gene, types, pubs in batch]
                    )
                    
                    # Update from temp table to main table
                    self.db_manager.cursor.execute("""
                        UPDATE cancer_transcript_base AS c
                        SET 
                            product_type = t.product_types,
                            source_references = jsonb_set(
                                COALESCE(c.source_references, '{}'::jsonb),
                                '{uniprot}',
                                t.publications,
                                true
                            )
                        FROM temp_gene_types AS t
                        WHERE c.gene_symbol = t.gene_symbol
                    """)
                    
                    # Clear temp table for next batch
                    self.db_manager.cursor.execute("TRUNCATE temp_gene_types")
                    
                    # Update progress
                    total_inserted += len(batch)
                    pbar.update(len(batch))
            
            # Drop the temporary table
            self.db_manager.cursor.execute("DROP TABLE temp_gene_types")
            
            # Commit changes
            if self.db_manager.conn:
                self.db_manager.conn.commit()
                
            self.logger.info(f"Updated {total_inserted} genes with product types")
            
        except Exception as e:
            # Rollback on error
            if self.db_manager.conn:
                self.db_manager.conn.rollback()
            raise DatabaseError(f"Failed to update gene product types: {e}")
    
    def run(self) -> None:
        """Run the complete product processing pipeline."""
        try:
            self.logger.info("Starting gene product processing")
            
            # Check schema version using enhanced base class method
            if not self.ensure_schema_version('v0.1.2'):
                raise DatabaseError("Incompatible database schema version")
            
            # Get genes with features
            genes = self.get_genes_with_features()
            
            if not genes:
                self.logger.warning("No genes with features found, nothing to process")
                return
            
            # Classify genes
            classified_genes = self.classify_genes(genes)
            
            if not classified_genes:
                self.logger.warning("No genes classified, nothing to update")
                return
            
            # Update gene types in database
            self.update_gene_types(classified_genes)
            
            self.logger.info("Gene product processing completed successfully")
            
        except Exception as e:
            self.logger.error(f"Gene product processing failed: {e}")
            raise

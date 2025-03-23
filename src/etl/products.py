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
from ..utils.publication_types import Publication
from .publications import PublicationsProcessor
from ..utils.gene_matcher import normalize_gene_symbol, match_genes_bulk, get_gene_match_stats

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
    
    def parse_uniprot_data(self, uniprot_file: Path) -> Dict[str, Dict[str, Any]]:
        """Parse UniProt data file to extract features and GO terms.
        
        Args:
            uniprot_file: Path to the UniProt data file
            
        Returns:
            Dictionary mapping gene symbols to features and GO terms
            
        Raises:
            ProcessingError: If parsing fails
        """
        try:
            self.logger.info("Parsing UniProt data to extract features and GO terms")
            
            # Initialize mapping from gene symbols to features and GO terms
            gene_data: Dict[str, Dict[str, Any]] = {}
            
            # Track statistics for reporting
            stats = {
                'total_entries': 0,
                'with_gene_symbol': 0,
                'with_features': 0,
                'with_go_terms': 0,
                'with_keywords': 0,
                'with_function': 0
            }
            
            # Process the file with a progress bar
            with gzip.open(uniprot_file, 'rt') as f:
                # First count lines for progress bar
                self.logger.info("Counting lines in UniProt file...")
                line_count = sum(1 for _ in f)
                f.seek(0)  # Reset file pointer
                
                self.logger.info(f"Processing {line_count:,} UniProt entries")
                
                # Track current entry being processed
                current_entry = {
                    'gene_symbol': None,
                    'features': {},
                    'go_terms': {},
                    'keywords': [],
                    'function': ""
                }
                
                # Use progress bar to show processing status
                for line in tqdm(f, total=line_count, desc="Parsing UniProt data"):
                    stats['total_entries'] += 1
                    
                    parts = line.strip().split('\t')
                    if len(parts) < 3:
                        continue
                    
                    uniprot_id, id_type, value = parts[0], parts[1], parts[2]
                    
                    # Extract gene symbol
                    if id_type == "Gene_Name":
                        current_entry['gene_symbol'] = value.upper()
                        stats['with_gene_symbol'] += 1
                    
                    # Extract features based on various UniProt fields
                    if id_type == "DOMAIN" or id_type == "REGION" or id_type == "MOTIF":
                        current_entry['features'][f"{id_type.lower()}_{len(current_entry['features'])}"] = value
                        stats['with_features'] += 1
                    
                    # Extract GO terms
                    if id_type == "GO" and ":" in value:
                        go_parts = value.split(';')
                        if len(go_parts) >= 1:
                            go_id = go_parts[0].strip()
                            # Make sure it's a proper GO ID format
                            if go_id.startswith('GO:'):
                                go_desc = go_parts[1].strip() if len(go_parts) > 1 else ""
                                current_entry['go_terms'][go_id] = go_desc
                                stats['with_go_terms'] += 1
                    
                    # Extract keywords
                    if id_type == "KEYWORDS":
                        keywords = [k.strip() for k in value.split(';') if k.strip()]
                        current_entry['keywords'].extend(keywords)
                        stats['with_keywords'] += 1
                    
                    # Extract function descriptions
                    if id_type == "FUNCTION":
                        current_entry['function'] = value
                        stats['with_function'] += 1
                    
                    # Store completed entry when we encounter a new gene symbol
                    if current_entry['gene_symbol'] and (id_type == "Gene_Name" or stats['total_entries'] % 1000 == 0):
                        gene_symbol = current_entry['gene_symbol']
                        
                        # Merge with existing data if this gene already has an entry
                        if gene_symbol in gene_data:
                            existing = gene_data[gene_symbol]
                            
                            # Merge features
                            existing['features'].update(current_entry['features'])
                            
                            # Merge GO terms
                            existing['go_terms'].update(current_entry['go_terms'])
                            
                            # Merge keywords (avoid duplicates)
                            for keyword in current_entry['keywords']:
                                if keyword not in existing['keywords']:
                                    existing['keywords'].append(keyword)
                            
                            # Append function descriptions
                            if current_entry['function']:
                                if existing['function']:
                                    existing['function'] += "; " + current_entry['function']
                                else:
                                    existing['function'] = current_entry['function']
                        else:
                            # Create new entry for this gene
                            gene_data[gene_symbol] = {
                                'features': current_entry['features'].copy(),
                                'go_terms': current_entry['go_terms'].copy(),
                                'keywords': current_entry['keywords'].copy(),
                                'function': current_entry['function']
                            }
                        
                        # Reset current entry
                        if id_type == "Gene_Name":
                            current_entry = {
                                'gene_symbol': value.upper(),
                                'features': {},
                                'go_terms': {},
                                'keywords': [],
                                'function': ""
                            }
                        else:
                            current_entry = {
                                'gene_symbol': None,
                                'features': {},
                                'go_terms': {},
                                'keywords': [],
                                'function': ""
                            }
            
            # Log statistics
            self.logger.info(f"UniProt parsing statistics:")
            self.logger.info(f"- Total entries processed: {stats['total_entries']:,}")
            self.logger.info(f"- Entries with gene symbols: {stats['with_gene_symbol']:,}")
            self.logger.info(f"- Entries with features: {stats['with_features']:,}")
            self.logger.info(f"- Entries with GO terms: {stats['with_go_terms']:,}")
            self.logger.info(f"- Entries with keywords: {stats['with_keywords']:,}")
            self.logger.info(f"- Entries with function descriptions: {stats['with_function']:,}")
            self.logger.info(f"- Total genes with data: {len(gene_data):,}")
            
            return gene_data
                
        except Exception as e:
            raise ProcessingError(f"Failed to parse UniProt data: {e}")
    
    def update_gene_features(self, gene_data: Dict[str, Dict[str, Any]]) -> None:
        """Update genes in the database with features and GO terms.
        
        Args:
            gene_data: Dictionary mapping gene symbols to features and GO terms
            
        Raises:
            DatabaseError: If database update fails
        """
        if not self.ensure_connection():
            raise DatabaseError("Database connection failed")
            
        try:
            self.logger.info(f"Updating {len(gene_data):,} genes with features and GO terms")
            
            if not self.db_manager.cursor:
                raise DatabaseError("No database cursor available")
                
            # Get all gene symbols from database for matching
            self.db_manager.cursor.execute("""
                SELECT DISTINCT gene_symbol FROM cancer_transcript_base
                WHERE gene_symbol IS NOT NULL
            """)
            db_gene_symbols = {row[0] for row in self.db_manager.cursor.fetchall() if row[0]}
            self.logger.info(f"Found {len(db_gene_symbols):,} unique gene symbols in database")
            
            # Find overlap between our gene data and database genes
            gene_data_symbols = set(gene_data.keys())
            overlap_symbols = db_gene_symbols.intersection(gene_data_symbols)
            
            self.logger.info(f"Found {len(overlap_symbols):,} overlapping genes to update")
            
            # Process in batches
            batch_size = self.config.get('batch_size', 100)
            updates = []
            updated_genes = 0
            
            # Create temporary table with IF NOT EXISTS to avoid race conditions
            with self.get_db_transaction() as transaction:
                transaction.cursor.execute("""
                    CREATE TEMP TABLE IF NOT EXISTS temp_gene_features (
                        gene_symbol TEXT PRIMARY KEY,
                        features JSONB,
                        go_terms JSONB,
                        keywords TEXT[]
                    ) ON COMMIT PRESERVE ROWS
                """)
            
            for gene_symbol in tqdm(overlap_symbols, desc="Preparing feature updates"):
                data = gene_data.get(gene_symbol, {})
                if not data:
                    continue
                    
                features = data.get('features', {})
                go_terms = data.get('go_terms', {})
                keywords = data.get('keywords', [])
                
                # Add to updates
                updates.append((
                    gene_symbol,
                    json.dumps(features),
                    json.dumps(go_terms),
                    keywords
                ))
                
                # Process in batches
                if len(updates) >= batch_size:
                    self._update_feature_batch(updates)
                    updated_genes += len(updates)
                    updates = []
            
            # Process remaining updates
            if updates:
                self._update_feature_batch(updates)
                updated_genes += len(updates)
            
            self.logger.info(f"Updated {updated_genes:,} genes with features and GO terms")
            
        except Exception as e:
            if self.db_manager.conn:
                self.db_manager.conn.rollback()
            raise DatabaseError(f"Failed to update gene features: {e}")
        finally:
            # Clean up
            try:
                if self.db_manager.cursor:
                    self.db_manager.cursor.execute("DROP TABLE IF EXISTS temp_gene_features")
                if self.db_manager.conn:
                    self.db_manager.conn.commit()
            except Exception as e:
                self.logger.warning(f"Cleanup failed: {e}")
    
    def _update_feature_batch(self, updates: List[Tuple[str, str, str, List[str]]]) -> None:
        """Update a batch of genes with features and GO terms.
        
        Args:
            updates: List of tuples with (gene_symbol, features_json, go_terms_json, keywords)
            
        Raises:
            DatabaseError: If batch update fails
        """
        try:
            # Instead of checking if the table exists and then creating it,
            # use IF NOT EXISTS which is handled atomically by PostgreSQL
            with self.get_db_transaction() as transaction:
                transaction.cursor.execute("""
                    CREATE TEMP TABLE IF NOT EXISTS temp_gene_features (
                        gene_symbol TEXT PRIMARY KEY,
                        features JSONB,
                        go_terms JSONB,
                        keywords TEXT[]
                    ) ON COMMIT PRESERVE ROWS
                """)
            
            # Now insert into temp table with proper conflict handling
            self.execute_batch(
                """
                INSERT INTO temp_gene_features 
                (gene_symbol, features, go_terms, keywords)
                VALUES (%s, %s::jsonb, %s::jsonb, %s)
                ON CONFLICT (gene_symbol) DO UPDATE SET
                    features = temp_gene_features.features || EXCLUDED.features,
                    go_terms = temp_gene_features.go_terms || EXCLUDED.go_terms,
                    keywords = temp_gene_features.keywords || EXCLUDED.keywords
                """,
                updates
            )
            
            # Update from temp table to main table
            if self.db_manager.cursor:
                self.db_manager.cursor.execute("""
                    UPDATE cancer_transcript_base AS c
                    SET 
                        features = COALESCE(c.features, '{}'::jsonb) || t.features,
                        go_terms = COALESCE(c.go_terms, '{}'::jsonb) || t.go_terms
                    FROM temp_gene_features AS t
                    WHERE c.gene_symbol = t.gene_symbol
                """)
                
                # Clear temp table for next batch
                self.db_manager.cursor.execute("TRUNCATE temp_gene_features")
            else:
                raise DatabaseError("No database cursor available")
            
        except Exception as e:
            raise DatabaseError(f"Failed to update feature batch: {e}")
    
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
        """Run the product classification process.
        
        Steps:
        1. Download UniProt data
        2. Parse UniProt data to extract features and GO terms
        3. Update genes with features and GO terms
        """
        try:
            self.logger.info("Starting gene product feature extraction")
            
            # Download UniProt data
            uniprot_file = self.download_uniprot_data()
            
            # Parse UniProt data to extract features and GO terms
            gene_data = self.parse_uniprot_data(uniprot_file)
            
            # Update genes with features and GO terms
            self.update_gene_features(gene_data)
            
            self.logger.info("Gene feature extraction completed successfully")
            
        except Exception as e:
            self.logger.error(f"Product feature extraction failed: {e}")
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
        """Get genes from the database, including those without features.
        
        Returns:
            List of genes with features data (initializing empty features if needed)
            
        Raises:
            DatabaseError: If database operations fail
        """
        if not self.ensure_connection():
            raise DatabaseError("Database connection failed")
        
        try:
            self.logger.info("Retrieving genes for product classification")
            
            if not self.db_manager.cursor:
                raise DatabaseError("No database cursor available")
            
            # Add diagnostic query to count genes before processing
            self.db_manager.cursor.execute("""
                SELECT 
                    COUNT(*) as total_genes,
                    COUNT(CASE WHEN features IS NOT NULL AND features != '{}'::jsonb THEN 1 END) as with_features,
                    COUNT(CASE WHEN go_terms IS NOT NULL AND go_terms != '{}'::jsonb THEN 1 END) as with_go_terms,
                    COUNT(CASE WHEN product_type IS NOT NULL AND array_length(product_type, 1) > 0 THEN 1 END) as with_product_type
                FROM cancer_transcript_base
            """)
            
            stats = self.db_manager.cursor.fetchone()
            if stats:
                self.logger.info(
                    f"Before product classification:\n"
                    f"- Total genes: {stats[0]:,}\n"
                    f"- Genes with features: {stats[1]:,} ({stats[1]/max(1, stats[0])*100:.1f}%)\n"
                    f"- Genes with GO terms: {stats[2]:,} ({stats[2]/max(1, stats[0])*100:.1f}%)\n"
                    f"- Genes with product types: {stats[3]:,} ({stats[3]/max(1, stats[0])*100:.1f}%)"
                )
            
            # Get all genes, without requiring features or go_terms to exist
            self.db_manager.cursor.execute("""
                SELECT 
                    gene_symbol, 
                    COALESCE(features, '{}'::jsonb) as features,
                    COALESCE(go_terms, '{}'::jsonb) as go_terms,
                    COALESCE(source_references, '{
                        "go_terms": [],
                        "uniprot": [],
                        "drugs": [],
                        "pathways": []
                    }'::jsonb) as source_references
                FROM 
                    cancer_transcript_base
                WHERE 
                    gene_symbol IS NOT NULL
                GROUP BY
                    gene_symbol, features, go_terms, source_references
            """)
            
            genes = []
            for row in self.db_manager.cursor.fetchall():
                gene_symbol, features, go_terms, source_refs = row
                genes.append({
                    'gene_symbol': gene_symbol,
                    'features': features,  # Now guaranteed to be at least an empty dict
                    'go_terms': go_terms,  # Now guaranteed to be at least an empty dict
                    'source_references': source_refs,  # Now guaranteed to have a valid structure
                })
            
            if self.process_limit and len(genes) > self.process_limit:
                genes = genes[:self.process_limit]
                self.logger.info(f"Limited to {self.process_limit} genes")
                
            self.logger.info(f"Retrieved {len(genes)} genes for product classification")
            return genes
                
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve genes for product classification: {e}")
    
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
            
            # Get all gene symbols from the database for matching
            self.db_manager.cursor.execute("""
                SELECT DISTINCT gene_symbol FROM cancer_transcript_base
                WHERE gene_symbol IS NOT NULL
            """)
            db_genes = [row[0] for row in self.db_manager.cursor.fetchall() if row[0]]
            
            # Get the gene symbols from our classified genes
            classified_symbols = [gene for gene, _, _ in classified_genes]
            
            # Match our classified genes to database genes
            matched_genes = match_genes_bulk(classified_symbols, db_genes, use_fuzzy=True)
            
            # Log matching statistics
            match_stats = get_gene_match_stats(classified_symbols, matched_genes)
            self.logger.info(
                f"Gene matching statistics:\n"
                f"- Total genes: {match_stats['total_genes']}\n"
                f"- Matched genes: {match_stats['matched_genes']} ({match_stats['match_rate']}%)\n"
                f"- Unmatched genes: {match_stats['unmatched_genes']}"
            )
            
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
                    
                    # Insert batch into temp table, using matched gene symbols
                    batch_data = []
                    for gene, types, pubs in batch:
                        # Use matched gene symbol if available
                        db_gene = matched_genes.get(gene, gene)
                        if db_gene:
                            batch_data.append((db_gene, types, json.dumps(pubs)))
                    
                    # Skip if no valid data
                    if not batch_data:
                        continue
                        
                    # Insert batch data
                    self.execute_batch(
                        """
                        INSERT INTO temp_gene_types (gene_symbol, product_types, publications)
                        VALUES (%s, %s, %s::jsonb)
                        """,
                        batch_data
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
        """Run the complete product processing pipeline.
        
        Steps:
        1. First extract features and GO terms from UniProt data
        2. Then verify GO terms are present in sufficient quantity
        3. Then classify genes based on the extracted features
        4. Update gene product types in database
        
        Note: For optimal enrichment, run the GO terms ETL before this processor.
        This ensures more comprehensive gene classification.
        """
        try:
            self.logger.info("Starting gene product processing")
            
            # Check schema version using enhanced base class method
            if not self.ensure_schema_version('v0.1.2'):
                raise DatabaseError("Incompatible database schema version")
            
            # First run feature extraction using the classifier
            self.logger.info("Extracting features from UniProt data")
            self.classifier.run()
            
            # Check if GO terms are present in the database
            # This helps ensure proper sequencing of ETL steps
            if self.ensure_connection() and self.db_manager.cursor is not None:
                self.db_manager.cursor.execute("""
                    SELECT 
                        COUNT(*) as total_genes,
                        COUNT(CASE WHEN go_terms IS NOT NULL AND go_terms != '{}'::jsonb THEN 1 END) as with_go_terms
                    FROM cancer_transcript_base
                """)
                
                stats = self.db_manager.cursor.fetchone()
                if stats and stats[1] < (stats[0] * 0.1):  # Less than 10% have GO terms
                    self.logger.warning(
                        "Very few genes have GO terms. For optimal classification, "
                        "run the GO terms ETL process before product classification."
                    )
            
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

def integrate_products(self, product_data: Dict[str, Dict[str, Any]]) -> None:
    """Integrate product data with transcripts in the database.
    
    Args:
        product_data: Dictionary mapping transcript IDs to product data
        
    Raises:
        DatabaseError: If database operations fail
    """
    if not self.ensure_connection():
        raise DatabaseError("Database connection failed")
        
    try:
        self.logger.info("Integrating product data with transcript records")
        
        # Create temporary table for batch updates with enhanced ID mapping
        with self.get_db_transaction() as transaction:
            transaction.cursor.execute("""
                CREATE TEMP TABLE temp_product_data (
                    transcript_id TEXT PRIMARY KEY,
                    alt_transcript_ids JSONB,
                    product_type TEXT[],
                    product_details JSONB
                ) ON COMMIT DROP
            """)
        
        updates = []
        processed = 0
        
        # Process each transcript's product data
        for transcript_id, product_info in product_data.items():
            # Skip empty data
            if not transcript_id or not product_info:
                continue
                
            # Get alternative transcript IDs for this transcript if available from the database
            alt_transcript_ids = {}
            if self.db_manager.cursor:
                self.db_manager.cursor.execute("""
                    SELECT alt_transcript_ids 
                    FROM cancer_transcript_base
                    WHERE transcript_id = %s AND alt_transcript_ids IS NOT NULL
                """, (transcript_id,))
                result = self.db_manager.cursor.fetchone()
                if result and result[0]:
                    alt_transcript_ids = result[0]
            
            # Extract product types and details
            product_types = product_info.get('types', [])
            product_details = {
                'protein_length': product_info.get('protein_length'),
                'domains': product_info.get('domains', []),
                'cellular_location': product_info.get('cellular_location', []),
                'functions': product_info.get('functions', [])
            }
            
            updates.append((
                transcript_id,
                json.dumps(alt_transcript_ids),
                product_types,
                json.dumps(product_details)
            ))
            
            processed += 1
            
            # Process in batches
            if len(updates) >= self.batch_size:
                self._update_product_batch(updates)
                updates = []
                self.logger.info(f"Processed {processed} transcripts with product data")
        
        # Process any remaining updates
        if updates:
            self._update_product_batch(updates)
        
        # Update main table from temp table using both primary and alternate transcript IDs
        with self.get_db_transaction() as transaction:
            # First update by direct transcript ID
            transaction.cursor.execute("""
                UPDATE cancer_transcript_base cb
                SET 
                    product_type = COALESCE(cb.product_type, '{}'::text[]) || pd.product_type,
                    features = COALESCE(cb.features, '{}'::jsonb) || pd.product_details
                FROM temp_product_data pd
                WHERE cb.transcript_id = pd.transcript_id
            """)
            
            # Update cellular location for better filtering/querying
            transaction.cursor.execute("""
                UPDATE cancer_transcript_base cb
                SET 
                    cellular_location = ARRAY(
                        SELECT DISTINCT jsonb_array_elements_text(pd.product_details->'cellular_location')
                        FROM temp_product_data pd
                        WHERE cb.transcript_id = pd.transcript_id
                    )
                FROM temp_product_data pd
                WHERE cb.transcript_id = pd.transcript_id
                AND pd.product_details->'cellular_location' IS NOT NULL
                AND jsonb_array_length(pd.product_details->'cellular_location') > 0
            """)
            
            # Update molecular functions from the product details
            transaction.cursor.execute("""
                UPDATE cancer_transcript_base cb
                SET 
                    molecular_functions = ARRAY(
                        SELECT DISTINCT jsonb_array_elements_text(pd.product_details->'functions')
                        FROM temp_product_data pd
                        WHERE cb.transcript_id = pd.transcript_id
                    )
                FROM temp_product_data pd
                WHERE cb.transcript_id = pd.transcript_id
                AND pd.product_details->'functions' IS NOT NULL
                AND jsonb_array_length(pd.product_details->'functions') > 0
            """)
            
            # Then attempt to match by alternative transcript IDs (RefSeq, Ensembl)
            transaction.cursor.execute("""
                WITH alt_id_matches AS (
                    SELECT 
                        cb.transcript_id as cb_id,
                        pd.transcript_id as pd_id
                    FROM cancer_transcript_base cb
                    JOIN temp_product_data pd ON 
                        (cb.alt_transcript_ids->>'RefSeq' = pd.alt_transcript_ids->>'RefSeq' AND 
                         pd.alt_transcript_ids->>'RefSeq' IS NOT NULL) OR
                        (cb.alt_transcript_ids->>'Ensembl' = pd.alt_transcript_ids->>'Ensembl' AND 
                         pd.alt_transcript_ids->>'Ensembl' IS NOT NULL)
                    WHERE cb.transcript_id != pd.transcript_id
                )
                UPDATE cancer_transcript_base cb
                SET 
                    product_type = COALESCE(cb.product_type, '{}'::text[]) || pd.product_type,
                    features = COALESCE(cb.features, '{}'::jsonb) || pd.product_details
                FROM temp_product_data pd, alt_id_matches aim
                WHERE cb.transcript_id = aim.cb_id AND pd.transcript_id = aim.pd_id
            """)
            
            # Clean up
            transaction.cursor.execute("DROP TABLE IF EXISTS temp_product_data")
        
        self.logger.info(f"Successfully integrated product data for {processed} transcripts")
        
    except Exception as e:
        self.logger.error(f"Failed to integrate product data: {e}")
        raise DatabaseError(f"Product integration failed: {e}")

def _update_product_batch(self, updates: List[Tuple[str, str, List[str], str]]) -> None:
    """Update a batch of product data.
    
    Args:
        updates: List of tuples with (transcript_id, alt_transcript_ids_json, product_types, product_details_json)
        
    Raises:
        DatabaseError: If batch update fails
    """
    try:
        self.execute_batch(
            """
            INSERT INTO temp_product_data 
            (transcript_id, alt_transcript_ids, product_type, product_details)
            VALUES (%s, %s::jsonb, %s, %s::jsonb)
            """,
            updates
        )
    except Exception as e:
        raise DatabaseError(f"Failed to update product batch: {e}")

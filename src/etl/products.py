"""Gene product classification module for cancer transcriptome base."""

import logging
import gzip
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from src.utils import validate_gene_symbol
from src.db.connection import get_db_connection

logger = logging.getLogger(__name__)

class ProductClassifier:
    """Classifies gene products based on UniProt data."""

    PRIMARY_TYPES = {
        'transcription_factor': ['GO:0003700', 'transcription factor', 'DNA-binding'],
        'kinase': ['GO:0016301', 'kinase activity'],
        'phosphatase': ['GO:0016791', 'phosphatase activity'],
        'protease': ['GO:0008233', 'peptidase activity'],
        'ion_channel': ['GO:0005216', 'ion channel activity'],
        'receptor': ['GO:0004872', 'receptor activity'],
        'transporter': ['GO:0005215', 'transporter activity'],
        'enzyme': ['GO:0003824', 'catalytic activity'],
        'chaperone': ['GO:0003754', 'chaperone activity'],
        'structural_protein': ['GO:0005198', 'structural molecule activity'],
        'signaling_molecule': ['GO:0005102', 'signaling receptor binding'],
        'hormone': ['hormone', 'GO:0005179'],
        'growth_factor': ['growth factor', 'GO:0008083'],
        'cytokine': ['cytokine', 'GO:0005125'],
        # ... add more primary types
    }

    FUNCTIONAL_MODIFIERS = {
        'membrane_associated': ['GO:0016020', 'membrane'],
        'secreted': ['GO:0005576', 'extracellular region'],
        'nuclear': ['GO:0005634', 'nucleus'],
        'mitochondrial': ['GO:0005739', 'mitochondrion'],
        'cytoplasmic': ['GO:0005737', 'cytoplasm'],
        # ... add more modifiers
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the classifier.
        
        Args:
            config: Optional configuration dictionary with settings
                   Can include 'db' key with database configuration
        """
        self.config = config or {}
        
        # Cache directory setup
        self.cache_dir = Path(os.getenv('MB_CACHE_DIR', '/tmp/mediabase/cache'))
        self.uniprot_dir = self.cache_dir / 'uniprot'
        self.json_path = self.uniprot_dir / "uniprot_processed.json.gz"
        
        # Database configuration - either from config or environment
        if self.config.get('db'):
            self.db_config = self.config['db']
        else:
            self.db_config = {
                'host': os.getenv('MB_POSTGRES_HOST', 'localhost'),
                'port': int(os.getenv('MB_POSTGRES_PORT', '5432')),
                'dbname': os.getenv('MB_POSTGRES_NAME', 'mediabase'),
                'user': os.getenv('MB_POSTGRES_USER', 'postgres'),
                'password': os.getenv('MB_POSTGRES_PASSWORD', 'postgres')
            }
        
        # Load processed data
        if not self.json_path.exists():
            raise FileNotFoundError(
                f"UniProt data not found at {self.json_path}. "
                "Run download_uniprot_data.py first."
            )
            
        with gzip.open(self.json_path, 'rt') as f:
            self._data = json.load(f)
            logger.info(f"Loaded {len(self._data)} UniProt entries")

    def classify_product(self, gene_symbol: str) -> List[str]:
        """Determine product types for a gene with comprehensive classification."""
        if not validate_gene_symbol(gene_symbol):
            logger.warning(f"Invalid gene symbol: {gene_symbol}")
            return []
            
        data = self._data.get(gene_symbol)
        if not data:
            return []

        classifications = set()
        features = data.get('features', [])
        go_terms = [term['id'] for term in data.get('go_terms', [])]
        keywords = data.get('keywords', [])
        functions = data.get('functions', [])

        # Classify primary types
        for type_name, patterns in self.PRIMARY_TYPES.items():
            if self._matches_patterns(patterns, go_terms, keywords, functions):
                classifications.add(type_name)

        # Add functional modifiers
        for modifier, patterns in self.FUNCTIONAL_MODIFIERS.items():
            if self._matches_patterns(patterns, go_terms, keywords, functions):
                classifications.add(modifier)

        return list(classifications)

    def _matches_patterns(self, patterns: List[str], go_terms: List[str], 
                         keywords: List[str], functions: List[str]) -> bool:
        """Check if any pattern matches in GO terms, keywords, or functions."""
        for pattern in patterns:
            if pattern.startswith('GO:'):
                if pattern in go_terms:
                    return True
            else:
                pattern_lower = pattern.lower()
                if any(pattern_lower in kw.lower() for kw in keywords):
                    return True
                if any(pattern_lower in func.lower() for func in functions):
                    return True
        return False

    def update_database_classifications(self) -> None:
        """Update product classifications and features in the database."""
        conn = get_db_connection(self.db_config)
        try:
            with conn.cursor() as cur:
                # Create temporary table for batch updates
                cur.execute("""
                    CREATE TEMP TABLE temp_gene_data (
                        gene_symbol TEXT PRIMARY KEY,
                        product_type TEXT[],
                        features JSONB,
                        molecular_functions TEXT[]
                    ) ON COMMIT DROP
                """)
                
                # Only fetch valid gene symbols
                cur.execute(r"""
                    SELECT DISTINCT gene_symbol 
                    FROM cancer_transcript_base 
                    WHERE gene_symbol ~ '^[A-Z][A-Z0-9\-]{0,254}$'
                """)
                genes = [row[0] for row in cur.fetchall()]
                
                logger.info(f"Processing {len(genes)} genes for classification")
                
                # Process in batches
                batch = []
                batch_size = self.config.get('batch_size', 100)
                
                for gene in genes:
                    try:
                        # Get UniProt data
                        data = self._data.get(gene, {})
                        
                        # Process classifications
                        classifications = self.classify_product(gene)
                        
                        # Process features
                        features = {}
                        for idx, feature in enumerate(data.get('features', [])):
                            # Parse feature string into structured data
                            parts = feature.split(None, 2)  # Split into type and description
                            if len(parts) >= 2:
                                feature_type = parts[0]
                                feature_id = f"{feature_type}_{idx}"
                                features[feature_id] = {
                                    "type": feature_type,
                                    "description": parts[1],
                                    "evidence": "UniProt",  # Default evidence source
                                }
                                if len(parts) > 2:
                                    features[feature_id]["additional_info"] = parts[2]
                        
                        # Process molecular functions from GO terms
                        molecular_functions = []
                        for go_term in data.get('go_terms', []):
                            if 'molecular_function' in go_term.get('aspect', '').lower():
                                molecular_functions.append(go_term['term'])
                        
                        if classifications or features or molecular_functions:
                            batch.append((
                                gene,
                                classifications,
                                json.dumps(features) if features else '{}',
                                molecular_functions
                            ))
                            
                        if len(batch) >= batch_size:
                            self._update_batch(cur, batch)
                            batch = []
                            logger.debug(f"Processed batch of {batch_size} genes")
                            
                    except Exception as e:
                        logger.error(f"Error processing gene {gene}: {e}")
                
                # Process remaining batch
                if batch:
                    self._update_batch(cur, batch)
                    logger.debug(f"Processed remaining {len(batch)} genes")
                
                conn.commit()
                logger.info("Database update completed successfully")
                
        except Exception as e:
            logger.error(f"Database update failed: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _update_batch(self, cur, batch: List[tuple[str, List[str], str, List[str]]]) -> None:
        """Update a batch of gene data.
        
        Args:
            cur: Database cursor
            batch: List of (gene_symbol, classifications, features_json, molecular_functions) tuples
        """
        # Insert into temp table
        cur.executemany(
            "INSERT INTO temp_gene_data VALUES (%s, %s, %s::jsonb, %s)",
            batch
        )
        
        # Update main table from temp table
        cur.execute("""
            UPDATE cancer_transcript_base cb
            SET 
                product_type = tgd.product_type,
                features = tgd.features,
                molecular_functions = tgd.molecular_functions
            FROM temp_gene_data tgd
            WHERE cb.gene_symbol = tgd.gene_symbol
        """)
        
        # Clear temp table
        cur.execute("TRUNCATE temp_gene_data")

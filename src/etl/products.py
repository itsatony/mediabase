"""Gene product classification module for cancer transcriptome base."""

# Standard library imports
import logging
import gzip
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any

# Third party imports
import pandas as pd
from psycopg2.extras import execute_batch

# Local imports
from ..utils import validate_gene_symbol
from ..db.database import get_db_manager

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
        db_manager = get_db_manager(self.db_config)
        try:
            if not db_manager.cursor:
                raise RuntimeError("No database connection")
            
            # Get valid gene symbols first
            db_manager.cursor.execute(r"""
                SELECT DISTINCT gene_symbol 
                FROM cancer_transcript_base 
                WHERE gene_symbol ~ '^[A-Z][A-Z0-9\-]{0,254}$'
            """)
            genes = [row[0] for row in db_manager.cursor.fetchall()]
            logger.info(f"Processing {len(genes)} genes for classification")
            
            # Process in batches
            batch_size = self.config.get('batch_size', 100)
            total_batches = (len(genes) + batch_size - 1) // batch_size
            
            # Create the temp table outside the batch loop
            if db_manager.conn:
                db_manager.conn.rollback()  # Clean slate
                
            db_manager.cursor.execute("""
                DROP TABLE IF EXISTS temp_gene_data;
                CREATE TEMP TABLE temp_gene_data (
                    gene_symbol TEXT PRIMARY KEY,
                    product_type TEXT[],
                    features JSONB,
                    molecular_functions TEXT[]
                );
            """)
            
            for batch_idx in range(total_batches):
                start_idx = batch_idx * batch_size
                end_idx = min((batch_idx + 1) * batch_size, len(genes))
                batch_genes = genes[start_idx:end_idx]
                
                try:
                    # Clear temp table for this batch
                    db_manager.cursor.execute("TRUNCATE TABLE temp_gene_data")
                    
                    # Process genes in current batch
                    batch_data = []
                    for gene in batch_genes:
                        try:
                            data = self._data.get(gene, {})
                            classifications = self.classify_product(gene)
                            
                            # Process features
                            features = {}
                            for idx, feature in enumerate(data.get('features', [])):
                                parts = feature.split(None, 2)
                                if len(parts) >= 2:
                                    feature_type = parts[0]
                                    feature_id = f"{feature_type}_{idx}"
                                    features[feature_id] = {
                                        "type": feature_type,
                                        "description": parts[1],
                                        "evidence": "UniProt",
                                    }
                                    if len(parts) > 2:
                                        features[feature_id]["additional_info"] = parts[2]
                            
                            # Process molecular functions
                            molecular_functions = []
                            for go_term in data.get('go_terms', []):
                                if 'molecular_function' in go_term.get('aspect', '').lower():
                                    molecular_functions.append(go_term['term'])
                            
                            if classifications or features or molecular_functions:
                                batch_data.append((
                                    gene,
                                    classifications,
                                    json.dumps(features) if features else '{}',
                                    molecular_functions
                                ))
                                
                        except Exception as e:
                            logger.error(f"Error processing gene {gene}: {e}")
                            continue
                    
                    # Insert batch data into temp table
                    if batch_data:
                        execute_batch(
                            db_manager.cursor,
                            "INSERT INTO temp_gene_data VALUES (%s, %s, %s::jsonb, %s)",
                            batch_data,
                            page_size=1000
                        )
                        
                        # Update main table from temp table
                        db_manager.cursor.execute("""
                            UPDATE cancer_transcript_base cb
                            SET 
                                product_type = tgd.product_type,
                                features = tgd.features,
                                molecular_functions = tgd.molecular_functions
                            FROM temp_gene_data tgd
                            WHERE cb.gene_symbol = tgd.gene_symbol
                        """)
                        
                        # Commit the batch
                        if db_manager.conn:
                            db_manager.conn.commit()
                            
                    logger.info(f"Processed batch {batch_idx + 1}/{total_batches} ({len(batch_data)} genes)")
                    
                except Exception as e:
                    logger.error(f"Error processing batch {batch_idx + 1}: {e}")
                    if db_manager.conn:
                        db_manager.conn.rollback()
                    continue
                    
            logger.info("Database update completed successfully")
            
        except Exception as e:
            logger.error(f"Database update failed: {e}")
            if db_manager.conn:
                db_manager.conn.rollback()
            raise
        finally:
            # Clean up
            if db_manager.cursor:
                db_manager.cursor.execute("DROP TABLE IF EXISTS temp_gene_data")
            db_manager.close()

class ProductProcessor:
    """Process and load product classifications into the database."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize product processor with configuration."""
        self.config = config
        self.db_manager = get_db_manager(config)
        self.batch_size = config.get('batch_size', 1000)
        self.classifier = ProductClassifier(config)

    def run(self) -> None:
        """Run the complete product classification pipeline.
        
        This method orchestrates:
        1. Product classification
        2. Database updates
        3. Feature extraction
        """
        try:
            logger.info("Starting product classification pipeline...")
            
            # Run classification
            self.classifier.update_database_classifications()
            
            # Verify results
            if not self.db_manager.cursor:
                raise RuntimeError("No database connection")
                
            self.db_manager.cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN product_type IS NOT NULL 
                              AND array_length(product_type, 1) > 0 
                         THEN 1 END) as classified,
                    COUNT(CASE WHEN features IS NOT NULL 
                              AND features != '{}'::jsonb 
                         THEN 1 END) as with_features
                FROM cancer_transcript_base
                WHERE gene_type = 'protein_coding'
            """)
            
            stats = self.db_manager.cursor.fetchone()
            if stats:
                logger.info(
                    f"Classification completed:\n"
                    f"- Total genes processed: {stats[0]:,}\n"
                    f"- Genes classified: {stats[1]:,}\n"
                    f"- Genes with features: {stats[2]:,}"
                )
            
            logger.info("Product classification pipeline completed successfully")
            
        except Exception as e:
            logger.error(f"Product classification pipeline failed: {e}")
            if self.db_manager.conn is not None:
                self.db_manager.conn.rollback()
            raise
        finally:
            if self.db_manager.conn is not None:
                self.db_manager.conn.close()

    def load_classifications(self, records: List[tuple]) -> None:
        """Load product classification records into database."""
        try:
            if not self.db_manager.cursor:
                raise RuntimeError("No database connection")
                
            execute_batch(
                self.db_manager.cursor,
                """
                UPDATE cancer_transcript_base
                SET product_type = %s
                WHERE gene_symbol = %s
                """,
                records,
                page_size=self.batch_size
            )
            
            if self.db_manager.conn:
                self.db_manager.conn.commit()
                
        except Exception as e:
            if self.db_manager.conn:
                self.db_manager.conn.rollback()
            logger.error(f"Error loading classifications: {e}")
            raise

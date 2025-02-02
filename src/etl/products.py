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
    """Classifies gene products based on UniProt data dump."""

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
        """Determine product types for a gene."""
        if not validate_gene_symbol(gene_symbol):
            logger.warning(f"Invalid gene symbol: {gene_symbol}")
            return []
            
        data = self._data.get(gene_symbol)
        if not data:
            return []

        classifications = set()

        # Feature-based classification
        features = data.get('features', [])
        for feature in features:
            if 'DOMAIN' in feature and 'Kinase' in feature:
                classifications.add('kinase')
            if 'DNA_BIND' in feature:
                classifications.add('dna_binding')
                classifications.add('transcription_factor')

        # Keyword-based classification
        keywords = data.get('keywords', [])
        for kw in keywords:
            kw_lower = kw.lower()
            if 'transcription' in kw_lower:
                classifications.add('transcription_factor')
            if 'receptor' in kw_lower:
                classifications.add('receptor')
            if 'kinase' in kw_lower:
                classifications.add('kinase')

        # GO term based classification
        for term in data.get('go_terms', []):
            go_id = term['id']
            if go_id == 'GO:0016301':  # kinase activity
                classifications.add('kinase')
            elif go_id == 'GO:0003700':  # DNA-binding transcription factor activity
                classifications.add('transcription_factor')
            elif go_id == 'GO:0004888':  # transmembrane signaling receptor activity
                classifications.add('receptor')

        # Function description based classification
        for func in data.get('functions', []):
            func_lower = func.lower()
            if 'transcription factor' in func_lower:
                classifications.add('transcription_factor')
            if 'kinase' in func_lower:
                classifications.add('kinase')
            if 'receptor' in func_lower:
                classifications.add('receptor')

        return list(classifications)

    def update_database_classifications(self) -> None:
        """Update product classifications in the database."""
        conn = get_db_connection(self.db_config)
        try:
            with conn.cursor() as cur:
                # First create a temporary table for batch updates
                cur.execute("""
                    CREATE TEMP TABLE temp_classifications (
                        gene_symbol TEXT PRIMARY KEY,
                        product_type TEXT[]
                    ) ON COMMIT DROP
                """)
                
                # Only fetch valid gene symbols
                cur.execute(r"""
                    SELECT DISTINCT gene_symbol 
                    FROM cancer_transcript_base 
                    WHERE gene_symbol ~ '^[A-Z][A-Z0-9\-]{0,254}$'
                """)
                genes = [row[0] for row in cur.fetchall()]  # Fixed: Assign query results
                
                logger.info(f"Processing {len(genes)} genes for classification")
                
                # Process in batches for better performance
                batch = []
                batch_size = self.config.get('batch_size', 100)
                
                for gene in genes:
                    try:
                        classifications = self.classify_product(gene)
                        if classifications:
                            batch.append((gene, classifications))
                            
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
    
    def _update_batch(self, cur, batch: List[tuple[str, List[str]]]) -> None:
        """Update a batch of gene classifications.
        
        Args:
            cur: Database cursor
            batch: List of (gene_symbol, classifications) tuples
        """
        # Insert into temp table
        cur.executemany(
            "INSERT INTO temp_classifications VALUES (%s, %s)",
            batch
        )
        
        # Update main table from temp table
        cur.execute("""
            UPDATE cancer_transcript_base cb
            SET product_type = tc.product_type
            FROM temp_classifications tc
            WHERE cb.gene_symbol = tc.gene_symbol
        """)
        
        # Clear temp table
        cur.execute("TRUNCATE temp_classifications")

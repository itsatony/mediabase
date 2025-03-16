"""DrugCentral integration module for Cancer Transcriptome Base."""

import logging
import gzip
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple
import pandas as pd
import requests
from tqdm import tqdm
from psycopg2.extras import execute_batch
from ..db.database import get_db_manager
from datetime import datetime, timedelta
import hashlib
from rich.console import Console
from rich.table import Table
from ..etl.publications import Publication, PublicationsProcessor
from ..utils.publication_utils import extract_pmid_from_text, extract_pmids_from_text

logger = logging.getLogger(__name__)

# Constants
DEFAULT_CACHE_TTL = 86400  # 24 hours in seconds
DEFAULT_BATCH_SIZE = 100
GO_TERM_WEIGHT_FACTOR = 0.5  # GO terms weighted at 50% of pathway weight
DEFAULT_CACHE_DIR = '/tmp/mediabase/cache'

class DrugProcessor:
    """Process drug data from DrugCentral and integrate with transcript data."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize drug processor with configuration.
        
        Args:
            config: Configuration dictionary containing:
                - drugcentral_url: URL to DrugCentral PostgreSQL dump
                - cache_dir: Directory to store downloaded files
                - cache_ttl: Time-to-live for cached files in seconds
                - batch_size: Size of batches for database operations
        """
        self.config = config
        self.cache_dir = Path(config.get('cache_dir', DEFAULT_CACHE_DIR))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.drug_dir = self.cache_dir / 'drugcentral'
        self.drug_dir.mkdir(exist_ok=True)
        
        self.batch_size = config.get('batch_size', DEFAULT_BATCH_SIZE)
        self.cache_ttl = config.get('cache_ttl', DEFAULT_CACHE_TTL)
        self.drugcentral_url = config.get('drugcentral_url', '')
        if not self.drugcentral_url:
            raise ValueError("DrugCentral URL not configured")
        self.db_manager = get_db_manager(config)

    def _get_cache_key(self, url: str) -> str:
        """Generate a cache key from URL."""
        return hashlib.sha256(url.encode()).hexdigest()

    def download_drugcentral(self) -> Path:
        """Download and extract DrugCentral data."""
        cache_key = self._get_cache_key(self.drugcentral_url)
        file_path = self.drug_dir / f"drugcentral_{cache_key}.tsv.gz"
        meta_path = self.drug_dir / "meta.json"

        # Check cache validity
        if file_path.exists() and meta_path.exists():
            try:
                with open(meta_path, 'r') as f:
                    meta = json.load(f)
                if cache_key in meta:
                    cache_time = datetime.fromisoformat(meta[cache_key]['timestamp'])
                    if datetime.now() - cache_time < timedelta(seconds=self.cache_ttl):
                        logger.info(f"Using cached DrugCentral data: {file_path}")
                        return file_path
            except (json.JSONDecodeError, KeyError) as e:
                logger.debug(f"Cache metadata error: {e}")

        logger.info("Downloading DrugCentral data...")
        response = requests.get(self.drugcentral_url, stream=True)
        total_size = int(response.headers.get('content-length', 0))

        with open(file_path, 'wb') as f, tqdm(
            desc="Downloading",
            total=total_size,
            unit='iB',
            unit_scale=True
        ) as pbar:
            for data in response.iter_content(chunk_size=1024):
                size = f.write(data)
                pbar.update(size)

        # Update metadata
        with open(meta_path, 'w') as f:
            json.dump({
                cache_key: {
                    'timestamp': datetime.now().isoformat(),
                    'file_path': str(file_path)
                }
            }, f)

        return file_path

    def process_drug_targets(self, drug_data_path: Path) -> pd.DataFrame:
        """Process drug target information from DrugCentral."""
        logger.info("Processing DrugCentral target data...")
        
        # First inspect the file format
        try:
            # Read first few lines to determine format
            with gzip.open(drug_data_path, 'rt') as f:
                header = f.readline().strip()
                sample_line = f.readline().strip()
                
                # Clean up quotation marks from header
                header = header.replace('"', '')
                
                # Always print header and sample for debugging
                console = Console()
                
                # Create a table for better visualization
                table = Table(title="DrugCentral Data Sample")
                table.add_column("Type")
                table.add_column("Content")
                
                table.add_row("Header (cleaned)", header)
                table.add_row("Sample", sample_line)
                console.print(table)
                
                # Split and analyze columns
                header_cols = [col.strip() for col in header.split('\t')]
                sample_cols = sample_line.split('\t')
                
                table = Table(title="Column Analysis")
                table.add_column("Index")
                table.add_column("Column Name")
                table.add_column("Sample Value")
                
                for idx, (col, val) in enumerate(zip(header_cols, sample_cols)):
                    table.add_row(str(idx), col, val.replace('"', ''))
                console.print(table)
                
                # Count expected columns
                expected_columns = len(header_cols)
                logger.info(f"Found {expected_columns} columns in data file")
                
                # Map columns to our expected schema
                column_mapping = {}
                for idx, col in enumerate(header_cols):
                    col_clean = col.strip().upper()
                    # Map drug ID
                    if col_clean == 'STRUCT_ID':
                        column_mapping['drug_id'] = col
                    # Map gene symbol
                    elif col_clean == 'GENE':
                        column_mapping['gene_symbol'] = col
                    # Map drug name
                    elif col_clean == 'DRUG_NAME':
                        column_mapping['drug_name'] = col
                    # Map action type
                    elif col_clean == 'ACTION_TYPE':
                        column_mapping['action_type'] = col
                    # Map evidence type
                    elif col_clean == 'ACT_TYPE':
                        column_mapping['evidence_type'] = col
                    # Map evidence score
                    elif col_clean == 'ACT_VALUE':
                        column_mapping['evidence_score'] = col
                    # Map references
                    elif col_clean == 'ACT_SOURCE':
                        column_mapping['references'] = col
                    # Map mechanism (if available)
                    elif col_clean == 'MOA':
                        column_mapping['mechanism'] = col
                
                logger.info("Column mapping found:")
                for our_col, file_col in column_mapping.items():
                    logger.info(f"  {our_col} -> {file_col}")
                
                required_cols = ['drug_id', 'gene_symbol']
                missing = [col for col in required_cols if col not in column_mapping]
                if missing:
                    raise ValueError(
                        f"Missing required columns: {missing}\n"
                        f"Current mapping: {column_mapping}"
                    )
        
        except Exception as e:
            logger.error(f"Error inspecting drug data file: {e}")
            raise
            
        df = pd.DataFrame()  # Initialize df to avoid unbound error
        
        try:
            # Read with pandas, using our mapped columns
            df = pd.read_csv(
                drug_data_path,
                sep='\t',
                compression='gzip',
                on_bad_lines='warn',
                quoting=3,  # QUOTE_NONE
                dtype=str,  # Read all as strings initially
                na_values=['', 'NA', 'null', 'None'],
                keep_default_na=True
            )
            
            # Remove quotes from column names and values
            df.columns = [col.strip('"') for col in df.columns]
            for col in df.columns:
                if df[col].dtype == 'object':
                    df[col] = df[col].str.strip('"')
            
            # Rename columns according to our mapping
            df = df.rename(columns={v: k for k, v in column_mapping.items()})
            
            # Clean and standardize data
            required_cols = ['drug_id', 'gene_symbol']
            if not all(col in df.columns for col in required_cols):
                raise ValueError(
                    f"Missing required columns. Available columns: {df.columns.tolist()}\n"
                    f"Mapping used: {column_mapping}"
                )
            
            df = df.dropna(subset=['drug_id', 'gene_symbol'])
            df['gene_symbol'] = df['gene_symbol'].str.upper()
            df['drug_name'] = df['drug_name'].str.strip() if 'drug_name' in df.columns else df['drug_id']
            
            # Convert evidence score to float where possible
            if 'evidence_score' in df.columns:
                df['evidence_score'] = pd.to_numeric(df['evidence_score'], errors='coerce')
            
            # Fill missing values with defaults using get() to avoid KeyError
            df['mechanism'] = df.get('mechanism', pd.Series('unknown')).fillna('unknown')
            df['action_type'] = df.get('action_type', pd.Series('unknown')).fillna('unknown')
            df['evidence_type'] = df.get('evidence_type', pd.Series('experimental')).fillna('experimental')
            df['evidence_score'] = df.get('evidence_score', pd.Series(1.0)).fillna(1.0)
            df['references'] = df.get('references', pd.Series('')).fillna('')
            
            # Process and validate each row
            processed_data = []
            for _, row in tqdm(df.iterrows(), total=len(df), desc="Processing drug targets"):
                try:
                    processed_row = {
                        'drug_id': str(row['drug_id']),
                        'drug_name': str(row.get('drug_name', row['drug_id'])),
                        'gene_symbol': str(row['gene_symbol']).upper(),
                        'mechanism': str(row.get('mechanism', 'unknown')),
                        'action_type': str(row.get('action_type', 'unknown')),
                        'evidence_type': str(row.get('evidence_type', 'experimental')),
                        'evidence_score': float(row.get('evidence_score', 1.0)),
                        'reference_ids': str(row.get('references', '')).split('|') if row.get('references') else []
                    }
                    
                    # Extract publication references if available
                    references = []
                    if 'references' in row and row['references']:
                        references = self.extract_publication_references(row['references'])
                    
                    # Add publication references if found
                    if references:
                        processed_row['publications'] = [dict(ref) for ref in references]
                    
                    processed_data.append(processed_row)
                except Exception as e:
                    logger.debug(f"Error processing row: {e}\nRow data: {row}")
                    continue

            result_df = pd.DataFrame(processed_data)
            
            # Additional validation and logging
            if result_df.empty:
                raise ValueError("No valid drug target relationships found after processing")
                
            logger.info(f"Successfully processed {len(result_df):,} valid drug-target relationships")
            logger.info(f"Found {result_df['drug_id'].nunique():,} unique drugs")
            logger.info(f"Found {result_df['gene_symbol'].nunique():,} unique genes")
            
            # Sample validation with better formatting
            logger.debug("\nSample of processed data:")
            sample_data = result_df.head()
            for idx, row in sample_data.iterrows():
                logger.debug(f"\nRow {idx}:")
                for col in row.index:
                    logger.debug(f"  {col}: {row[col]}")
            
            return result_df
            
        except pd.errors.ParserError as e:
            logger.error(f"Error parsing drug data file: {e}")
            logger.error("This might indicate a corrupted download or wrong file format.")
            logger.error("Please check the DrugCentral URL and try downloading again.")
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing drug data: {e}")
            logger.error(f"Available columns: {list(df.columns) if 'df' in locals() else 'No DataFrame available'}")
            raise

    def integrate_drugs(self, drug_targets: pd.DataFrame) -> None:
        """Integrate drug information into transcript database."""
        if not self.db_manager.cursor:
            raise RuntimeError("No database connection")
            
        try:
            if self.db_manager.conn:
                # Set appropriate isolation level for DDL operations
                old_isolation_level = self.db_manager.conn.isolation_level
                self.db_manager.conn.set_isolation_level(0)  # AUTOCOMMIT for temp table creation
                
                # Create temporary table with enhanced reference support
                self.db_manager.cursor.execute("""
                    CREATE TEMP TABLE IF NOT EXISTS temp_drug_data (
                        gene_symbol TEXT,
                        drug_data JSONB,
                        drug_references JSONB
                    ) ON COMMIT PRESERVE ROWS
                """)
                
                # Reset isolation level for transaction
                if self.db_manager.conn:
                    self.db_manager.conn.set_isolation_level(old_isolation_level)
                
                # Start transaction for data processing
                self.db_manager.cursor.execute("BEGIN")
                
                # Clear any existing data in temp table
                self.db_manager.cursor.execute("TRUNCATE temp_drug_data")
                
                # Process drugs by gene
                updates = []
                processed = 0
                matched = 0
                
                for gene, group in drug_targets.groupby('gene_symbol'):
                    drug_info = {}
                    references = []
                    
                    for _, row in group.iterrows():
                        drug_info[row.get('drug_id')] = {
                            'name': row.get('drug_name', ''),
                            'mechanism': row.get('mechanism', 'unknown'),
                            'action_type': row.get('action_type', 'unknown'),
                            'evidence': {
                                'type': row.get('evidence_type', 'experimental'),
                                'score': float(row.get('evidence_score', 1.0))
                            }
                        }
                        
                        # Process references
                        if row.get('reference_ids'):
                            for ref_id in row.get('reference_ids', []):
                                if ref_id and isinstance(ref_id, str):
                                    ref_id = ref_id.strip()
                                    
                                    # Skip non-PMID references but log them
                                    if not ref_id.isdigit():
                                        # logger.debug(f"Skipping non-PMID reference: {ref_id}")
                                        continue
                                        
                                    # Drug-specific reference
                                    references.append({
                                        'pmid': ref_id,
                                        'year': None,  # Would need PubMed lookup
                                        'evidence_type': row.get('evidence_type', 'experimental'),
                                        'citation_count': None,
                                        'source_db': 'DrugCentral',
                                        'drug_id': row.get('drug_id', '')
                                    })
                    
                    updates.append((
                        gene,
                        json.dumps(drug_info),
                        json.dumps(references)
                    ))
                    
                    if len(updates) >= self.batch_size:
                        self._update_batch(self.db_manager.cursor, updates)
                        updates = []
                        
                        # Commit each batch to avoid memory issues
                        if self.db_manager.conn:
                            self.db_manager.conn.commit()
                            self.db_manager.cursor.execute("BEGIN")
                
                # Process remaining updates
                if updates:
                    self._update_batch(self.db_manager.cursor, updates)
                
                # Update main table from temp table with enhanced reference handling
                logger.debug("Updating main table from temporary table...")
                self.db_manager.cursor.execute("""
                    UPDATE cancer_transcript_base cb
                    SET 
                        drugs = COALESCE(cb.drugs, '{}'::jsonb) || tdd.drug_data,
                        source_references = jsonb_set(
                            COALESCE(cb.source_references, '{
                                "go_terms": [],
                                "uniprot": [],
                                "drugs": [],
                                "pathways": []
                            }'::jsonb),
                            '{drugs}',
                            tdd.drug_references,
                            true
                        )
                    FROM temp_drug_data tdd
                    WHERE cb.gene_symbol = tdd.gene_symbol
                """)
                
                if self.db_manager.conn:
                    self.db_manager.conn.commit()
                    
                # Drop temporary table
                self.db_manager.cursor.execute("DROP TABLE IF EXISTS temp_drug_data")
                
                if self.db_manager.conn:
                    self.db_manager.conn.commit()
                    
        except Exception as e:
            if self.db_manager.conn:
                self.db_manager.conn.rollback()
            logger.error(f"Drug data integration failed: {e}")
            raise
        finally:
            # Clean up
            try:
                if self.db_manager.cursor:
                    self.db_manager.cursor.execute("DROP TABLE IF EXISTS temp_drug_data")
                if self.db_manager.conn:
                    self.db_manager.conn.commit()
            except Exception as e:
                logger.warning(f"Cleanup failed: {e}")

    def _update_batch(self, cur, updates: List[Tuple[str, str, str]]) -> None:
        """Update a batch of drug data."""
        execute_batch(
            cur,
            """
            INSERT INTO temp_drug_data 
            (gene_symbol, drug_data, drug_references)
            VALUES (%s, %s::jsonb, %s::jsonb)
            """,
            updates,
            page_size=self.batch_size
        )

    def calculate_drug_scores(self) -> None:
        """Calculate synergy-based drug scores using pathways and GO terms."""
        if not self.db_manager.cursor:
            raise RuntimeError("No database connection")
            
        try:
            # Create temporary scoring tables
            self.db_manager.cursor.execute("""
                -- Table for storing intermediate pathway scores
                CREATE TEMP TABLE temp_pathway_scores (
                    gene_symbol TEXT,
                    drug_id TEXT,
                    pathway_score FLOAT,
                    PRIMARY KEY (gene_symbol, drug_id)
                );
                
                -- Table for storing intermediate GO term scores
                CREATE TEMP TABLE temp_go_scores (
                    gene_symbol TEXT,
                    drug_id TEXT,
                    go_score FLOAT,
                    PRIMARY KEY (gene_symbol, drug_id)
                );
                
                -- Table for final combined scores
                CREATE TEMP TABLE temp_final_scores (
                    gene_symbol TEXT,
                    drug_scores JSONB
                );
            """)
            
            # Process in batches
            batch_size = self.batch_size
            offset = 0
            total_processed = 0
            
            while True:
                # Ensure cursor is still valid
                if not self.db_manager.cursor:
                    raise RuntimeError("Database cursor is no longer valid")
                    
                # Get batch of genes with drugs
                self.db_manager.cursor.execute("""
                    SELECT gene_symbol, drugs, pathways, go_terms
                    FROM cancer_transcript_base
                    WHERE drugs IS NOT NULL
                    ORDER BY gene_symbol
                    LIMIT %s OFFSET %s
                """, (batch_size, offset))
                
                rows = self.db_manager.cursor.fetchall()
                if not rows:
                    break
                    
                logger.info(f"Processing batch of {len(rows)} genes (offset {offset})")
                
                # Process pathway scores for this batch
                self.db_manager.cursor.execute("""
                    INSERT INTO temp_pathway_scores
                    WITH batch_genes AS (
                        SELECT 
                            t1.gene_symbol,
                            t1.drugs,
                            t1.pathways as source_pathways
                        FROM cancer_transcript_base t1
                        WHERE t1.gene_symbol = ANY(%s)
                    )
                    SELECT DISTINCT
                        bg.gene_symbol,
                        d.key as drug_id,
                        COUNT(DISTINCT t2.gene_symbol)::float as pathway_score
                    FROM batch_genes bg
                    CROSS JOIN LATERAL jsonb_each(bg.drugs) d
                    JOIN cancer_transcript_base t2 
                    ON t2.pathways && bg.source_pathways
                    AND t2.gene_type = 'protein_coding'
                    GROUP BY bg.gene_symbol, d.key
                """, ([row[0] for row in rows],))
                
                # Process GO term scores for this batch
                self.db_manager.cursor.execute("""
                    INSERT INTO temp_go_scores
                    WITH batch_genes AS (
                        SELECT 
                            t1.gene_symbol,
                            t1.drugs,
                            t1.go_terms as source_terms
                        FROM cancer_transcript_base t1
                        WHERE t1.gene_symbol = ANY(%s)
                    )
                    SELECT DISTINCT
                        bg.gene_symbol,
                        d.key as drug_id,
                        COUNT(DISTINCT t2.gene_symbol)::float as go_score
                    FROM batch_genes bg
                    CROSS JOIN LATERAL jsonb_each(bg.drugs) d
                    JOIN cancer_transcript_base t2 
                    ON EXISTS (
                        SELECT 1
                        FROM jsonb_object_keys(bg.source_terms) go_id
                        WHERE t2.go_terms ? go_id
                    )
                    AND t2.gene_type = 'protein_coding'
                    GROUP BY bg.gene_symbol, d.key
                """, ([row[0] for row in rows],))
                
                # Combine scores for this batch
                pathway_weight = float(self.config.get('drug_pathway_weight', 1.0))
                go_weight = pathway_weight * GO_TERM_WEIGHT_FACTOR  # Use constant instead of magic number
                
                self.db_manager.cursor.execute("""
                    INSERT INTO temp_final_scores
                    SELECT 
                        ps.gene_symbol,
                        jsonb_object_agg(
                            ps.drug_id,
                            (COALESCE(ps.pathway_score * %s, 0) + 
                             COALESCE(gs.go_score * %s, 0))::float
                        ) as drug_scores
                    FROM temp_pathway_scores ps
                    LEFT JOIN temp_go_scores gs 
                    ON ps.gene_symbol = gs.gene_symbol 
                    AND ps.drug_id = gs.drug_id
                    WHERE ps.gene_symbol = ANY(%s)
                    GROUP BY ps.gene_symbol
                """, (pathway_weight, go_weight, [row[0] for row in rows]))
                
                # Update main table for this batch
                self.db_manager.cursor.execute("""
                    UPDATE cancer_transcript_base cb
                    SET drug_scores = fs.drug_scores
                    FROM temp_final_scores fs
                    WHERE cb.gene_symbol = fs.gene_symbol
                """)
                
                # Clear temporary tables for next batch
                self.db_manager.cursor.execute("""
                    TRUNCATE temp_pathway_scores, temp_go_scores, temp_final_scores
                """)
                
                total_processed += len(rows)
                offset += batch_size
                
                # Commit each batch
                if self.db_manager.conn:
                    self.db_manager.conn.commit()
                logger.info(f"Processed and committed {total_processed} genes so far")
            
            # Log final statistics
            logger.info(f"Drug score calculation completed. Total genes processed: {total_processed}")
            
            # Sample verification
            # Ensure cursor is still valid before executing
            if not self.db_manager.cursor:
                logger.warning("Cannot verify results - database cursor is no longer valid")
            else:
                self.db_manager.cursor.execute("""
                    SELECT gene_symbol, drug_scores 
                    FROM cancer_transcript_base 
                    WHERE drug_scores IS NOT NULL 
                    LIMIT 3
                """)
                samples = self.db_manager.cursor.fetchall() if self.db_manager.cursor else []
                if samples:
                    logger.debug("Sample drug scores:")
                    for sample in samples:
                        logger.debug(f"{sample[0]}: {sample[1]}")
            
        except Exception as e:
            logger.error(f"Drug score calculation failed: {e}")
            if self.db_manager.conn:
                self.db_manager.conn.rollback()
            raise
        finally:
            if self.db_manager.conn:
                self.db_manager.conn.close()

    def load_drugs(self, records: List[tuple]) -> None:
        """Load drug records into database."""
        try:
            if not self.db_manager.cursor:
                raise RuntimeError("No database connection")
                
            # Clear existing drug data
            self.db_manager.cursor.execute(
                "UPDATE cancer_transcript_base SET drugs = '{}'::jsonb"
            )
            
            # Insert new records
            execute_batch(
                self.db_manager.cursor,
                """
                UPDATE cancer_transcript_base
                SET drugs = drugs || %s::jsonb
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
            logger.error(f"Error loading drugs: {e}")
            raise

    def run(self) -> None:
        """Run the complete drug processing pipeline."""
        try:
            # Download and extract data
            logger.info("Starting drug processing pipeline...")
            drug_data_path = self.download_drugcentral()
            
            # Process drug targets with validation
            drug_targets = self.process_drug_targets(drug_data_path)
            if drug_targets.empty:
                raise ValueError("No valid drug target relationships found")
            
            # Log sample of processed data
            logger.info(
                f"\nProcessed drug targets sample:\n"
                f"Total relationships: {len(drug_targets):,}\n"
                f"Unique drugs: {drug_targets['drug_id'].nunique():,}\n"
                f"Unique genes: {drug_targets['gene_symbol'].nunique():,}\n"
            )
            
            # Integrate with transcript data
            logger.info("Integrating drug data with transcripts...")
            
            # Ensure we have a valid database connection before proceeding
            if not self.db_manager.ensure_connection():
                raise RuntimeError("Database connection lost before integrating drug data")
            
            self.integrate_drugs(drug_targets)
            
            # Calculate drug scores
            logger.info("Calculating drug interaction scores...")
            self.calculate_drug_scores()
            
            # Verify results
            if not self.db_manager.cursor:
                logger.warning("Cannot verify results - database cursor is no longer valid")
                return
                
            self.db_manager.cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN drugs != '{}'::jsonb THEN 1 END) as with_drugs,
                    COUNT(CASE WHEN drug_scores != '{}'::jsonb THEN 1 END) as with_scores,
                    COUNT(CASE WHEN source_references->'drugs' IS NOT NULL 
                              AND source_references->'drugs' != '[]'::jsonb 
                         THEN 1 END) as with_refs
                FROM cancer_transcript_base
            """)
            
            # Null-check before accessing fetchone
            stats = self.db_manager.cursor.fetchone() if self.db_manager.cursor else None
            if stats:
                logger.info(
                    f"Pipeline completed:\n"
                    f"- Total records: {stats[0]:,}\n"
                    f"- Records with drugs: {stats[1]:,}\n"
                    f"- Records with drug scores: {stats[2]:,}\n"
                    f"- Records with drug references: {stats[3]:,}"
                )
            
            logger.info("Drug processing pipeline completed successfully")
            
        except Exception as e:
            logger.error(f"Drug processing pipeline failed: {e}")
            raise

    def extract_publication_references(self, drug_references: str) -> List[Publication]:
        """Extract publication references from drug evidence data.
        
        Args:
            drug_references: References field from drug data
            
        Returns:
            List[Publication]: List of publication references
        """
        publications: List[Publication] = []
        
        # Skip empty references
        if not drug_references:
            return publications
            
        # Extract PMIDs from reference text
        pmids = extract_pmids_from_text(drug_references)
        
        # Create publication references for each PMID
        for pmid in pmids:
            publication = PublicationsProcessor.create_publication_reference(
                pmid=pmid,
                evidence_type="DrugCentral",
                source_db="DrugCentral"
            )
            publications.append(publication)
            
        return publications

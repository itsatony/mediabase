"""DrugCentral integration module for Cancer Transcriptome Base.

This module downloads, processes, and integrates drug data from DrugCentral
into transcript records, enhancing them with pharmacological information.
"""

# Standard library imports
import json
import gzip
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple, Union

# Third party imports
import pandas as pd
from tqdm import tqdm
from rich.console import Console
from rich.table import Table

# Local imports
from .base_processor import BaseProcessor, DownloadError, ProcessingError, DatabaseError
from .publications import Publication, PublicationsProcessor
from ..utils.publication_utils import extract_pmids_from_text, format_pmid_url, merge_publication_references
from ..utils.pandas_helpers import (
    safe_assign, 
    safe_batch_assign, 
    safe_fillna, 
    clean_dataframe, 
    PandasOperationSafe
)
from ..utils.gene_matcher import normalize_gene_symbol, match_genes_bulk, get_gene_match_stats
from ..utils.progress import track_progress

# Constants
GO_TERM_WEIGHT_FACTOR = 0.5  # GO terms weighted at 50% of pathway weight
HUMAN_SPECIES = 'Homo sapiens'

class DrugProcessor(BaseProcessor):
    """Process drug data from DrugCentral and integrate with transcript data."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize drug processor with configuration.
        
        Args:
            config: Configuration dictionary containing settings for drug processing
        """
        super().__init__(config)
        
        # Create drug-specific directory
        self.drug_dir = self.cache_dir / 'drugcentral'
        self.drug_dir.mkdir(exist_ok=True)
        
        # DrugCentral data URL
        self.drugcentral_url = config.get('drugcentral_url', '')
        if not self.drugcentral_url:
            raise ValueError("DrugCentral URL not configured")
        
        # Skip score calculation if specified
        self.skip_scores = config.get('skip_scores', False)
    
    def download_drugcentral(self) -> Path:
        """Download DrugCentral data file with caching.
        
        Returns:
            Path to the downloaded file
            
        Raises:
            DownloadError: If download fails
        """
        try:
            # Use BaseProcessor's download method
            drug_file = self.download_file(
                url=self.drugcentral_url,
                file_path=self.drug_dir / "drugcentral_data.tsv.gz"
            )
            
            return drug_file
        except Exception as e:
            raise DownloadError(f"Failed to download DrugCentral data: {e}")
    
    def process_drug_targets(self, drug_data_path: Path) -> pd.DataFrame:
        """Process drug target information from DrugCentral.
        
        Args:
            drug_data_path: Path to the DrugCentral data file
            
        Returns:
            DataFrame containing processed drug-target relationships
            
        Raises:
            ProcessingError: If drug data processing fails
        """
        try:
            self.logger.info("Processing DrugCentral target data...")
            
            # First inspect the file format
            with gzip.open(drug_data_path, 'rt') as f:
                header = f.readline().strip()
                sample_line = f.readline().strip()
                
                # Clean up quotation marks from header
                header = header.replace('"', '')
                
                # Create a table for better visualization
                console = Console()
                table = Table(title="DrugCentral Data Sample")
                table.add_column("Type")
                table.add_column("Content")
                
                table.add_row("Header (cleaned)", header)
                table.add_row("Sample", sample_line)
                console.print(table)
                
                # Split and analyze columns
                header_cols = [col.strip() for col in header.split('\t')]
                sample_cols = sample_line.split('\t')
                
                # Map columns to our expected schema
                column_mapping = self._create_column_mapping(header_cols)
                
                required_cols = ['drug_id', 'gene_symbol']
                missing = [col for col in required_cols if col not in column_mapping]
                if missing:
                    raise ValueError(
                        f"Missing required columns: {missing}\n"
                        f"Current mapping: {column_mapping}"
                    )
            
            # Read with pandas using our mapped columns
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
            df = self._clean_drug_data(df, column_mapping)
            
            # Process and validate each row
            processed_data = self._process_drug_rows(df)
            
            result_df = pd.DataFrame(processed_data)
            
            # Additional validation and logging
            if result_df.empty:
                raise ValueError("No valid drug target relationships found after processing")
                
            self.logger.info(f"Successfully processed {len(result_df):,} valid drug-target relationships")
            self.logger.info(f"Found {result_df['drug_id'].nunique():,} unique drugs")
            self.logger.info(f"Found {result_df['gene_symbol'].nunique():,} unique genes")
            
            return result_df
            
        except pd.errors.ParserError as e:
            raise ProcessingError(f"Error parsing drug data file: {e}")
        except Exception as e:
            raise ProcessingError(f"Unexpected error processing drug data: {e}")
    
    def _create_column_mapping(self, header_cols: List[str]) -> Dict[str, str]:
        """Create a mapping between expected columns and file columns.
        
        Args:
            header_cols: List of column headers from the file
            
        Returns:
            Dictionary mapping our expected column names to file column names
        """
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
        
        self.logger.info("Column mapping found:")
        for our_col, file_col in column_mapping.items():
            self.logger.info(f"  {our_col} -> {file_col}")
            
        return column_mapping
    
    def _clean_drug_data(self, df: pd.DataFrame, column_mapping: Dict[str, str]) -> pd.DataFrame:
        """Clean and standardize drug data.
        
        Args:
            df: Raw DataFrame with drug data
            column_mapping: Mapping between expected and file columns
            
        Returns:
            Cleaned DataFrame
            
        Raises:
            ValueError: If required columns are missing
        """
        # Check required columns
        required_cols = ['drug_id', 'gene_symbol']
        if not all(col in df.columns for col in required_cols):
            raise ValueError(
                f"Missing required columns. Available columns: {df.columns.tolist()}\n"
                f"Mapping used: {column_mapping}"
            )
        
        # Clean and standardize
        df = df.dropna(subset=['drug_id', 'gene_symbol'])
        df = self._normalize_drug_data(df)
        
        return df
    
    def _normalize_drug_data(self, df):
        """Normalize drug data to ensure consistent format.
        
        Args:
            df: DataFrame containing drug data
            
        Returns:
            Normalized DataFrame with consistent column values
        """
        self.logger.info("Normalizing drug data...")
        
        # First, create an explicit copy to avoid SettingWithCopyWarning
        df = df.copy()
        
        # Use safe operations from pandas_helpers.py
        with PandasOperationSafe():
            # Use .loc accessor as recommended in the warning message
            df.loc[:, 'gene_symbol'] = df['gene_symbol'].str.upper()
            df.loc[:, 'drug_name'] = df['drug_name'].str.strip() if 'drug_name' in df.columns else df['drug_id']
            
            # Convert scores to numeric
            df.loc[:, 'evidence_score'] = pd.to_numeric(df['evidence_score'], errors='coerce')
            
            # Fill missing values
            df.loc[:, 'mechanism'] = df.get('mechanism', pd.Series('unknown')).fillna('unknown')
            df.loc[:, 'action_type'] = df.get('action_type', pd.Series('unknown')).fillna('unknown')
            df.loc[:, 'evidence_type'] = df.get('evidence_type', pd.Series('experimental')).fillna('experimental')
            df.loc[:, 'evidence_score'] = df.get('evidence_score', pd.Series(1.0)).fillna(1.0)
            df.loc[:, 'references'] = df.get('references', pd.Series('')).fillna('')
        
        return df

    def _process_drug_rows(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Process each row in the drug data.
        
        Args:
            df: Cleaned DataFrame with drug data
            
        Returns:
            List of processed drug-target dictionaries
        """
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
                self.logger.debug(f"Error processing row: {e}\nRow data: {row}")
                continue
                
        return processed_data
    
    def integrate_drugs(self, drug_targets: pd.DataFrame) -> None:
        """Integrate drug information into transcript database.
        
        Args:
            drug_targets: DataFrame with processed drug-target relationships
            
        Raises:
            DatabaseError: If database operations fail
        """
        if not self.ensure_connection() or not self.db_manager.cursor:
            raise DatabaseError("Database connection failed")
            
        try:
            # Get all gene symbols from the database for matching
            self.db_manager.cursor.execute("""
                SELECT DISTINCT gene_symbol FROM cancer_transcript_base
                WHERE gene_symbol IS NOT NULL
            """)
            db_genes = [row[0] for row in self.db_manager.cursor.fetchall() if row[0]]
            
            # Create a normalized map for case-insensitive lookups
            self.logger.info(f"Building normalized gene symbol map for {len(db_genes)} database genes")
            db_gene_map = {normalize_gene_symbol(g): g for g in db_genes if g}
            
            # Get unique gene symbols from drug targets
            drug_genes = drug_targets['gene_symbol'].unique().tolist()
            
            # Match drug target genes to database genes
            matched_genes = match_genes_bulk(drug_genes, db_genes, use_fuzzy=True)
            
            # Log matching statistics
            match_stats = get_gene_match_stats(drug_genes, matched_genes)
            self.logger.info(
                f"Gene matching statistics:\n"
                f"- Total drug target genes: {match_stats['total_genes']}\n"
                f"- Matched to database: {match_stats['matched_genes']} ({match_stats['match_rate']}%)\n"
                f"- Unmatched genes: {match_stats['unmatched_genes']}"
            )
            
            # Create temporary table for batch updates
            with self.get_db_transaction() as transaction:
                # Create temporary table with enhanced reference support
                transaction.cursor.execute("""
                    CREATE TEMP TABLE IF NOT EXISTS temp_drug_data (
                        gene_symbol TEXT,
                        uniprot_ids TEXT[],
                        drug_data JSONB,
                        drug_references JSONB
                    ) ON COMMIT PRESERVE ROWS
                """)
                
            # Process drugs by gene
            updates = []
            processed = 0
            matched_count = 0
            unmatched_count = 0
            
            for gene, group in drug_targets.groupby('gene_symbol'):
                # Use matched gene symbol from our bulk matching
                db_gene = matched_genes.get(str(gene) if gene is not None else "")
                
                # If no match from bulk matching, try direct normalized lookup
                if not db_gene:
                    # Fix: Ensure gene is a string before using as a parameter
                    norm_gene = normalize_gene_symbol(str(gene) if gene is not None else "")
                    db_gene = db_gene_map.get(norm_gene)
                
                # Skip if we couldn't find a match
                if not db_gene:
                    unmatched_count += 1
                    if unmatched_count <= 10:  # Only log the first few unmatched genes
                        self.logger.debug(f"No matching gene found for drug target gene: {gene}")
                    elif unmatched_count == 11:
                        self.logger.debug("Further unmatched gene logs suppressed...")
                    continue
                    
                matched_count += 1
                drug_info = {}
                references = []
                
                for _, row in group.iterrows():
                    # Fix: Ensure drug_id is a string
                    drug_id = str(row.get('drug_id', ''))
                    drug_info[drug_id] = {
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
                
                # Get UniProt IDs for this gene if available
                uniprot_ids = []
                if self.db_manager.cursor:
                    self.db_manager.cursor.execute("""
                        SELECT uniprot_ids FROM cancer_transcript_base
                        WHERE gene_symbol = %s AND uniprot_ids IS NOT NULL
                    """, (gene,))
                    result = self.db_manager.cursor.fetchone()
                    if result and result[0]:
                        uniprot_ids = result[0]
                
                updates.append((
                    gene,
                    uniprot_ids,
                    json.dumps(drug_info),
                    json.dumps(references)
                ))
                
                if len(updates) >= self.batch_size:
                    self._update_drug_batch(updates)
                    updates = []
                    
                    # Commit each batch to avoid memory issues
                    if self.db_manager.conn and not self.db_manager.conn.closed:
                        self.db_manager.conn.commit()
            
            # Process remaining updates
            if updates:
                self._update_drug_batch(updates)
            
            # Update main table from temp table with enhanced ID mapping awareness
            with self.get_db_transaction() as transaction:
                self.logger.debug("Updating main table from temporary table...")
                transaction.cursor.execute("""
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
                
                # Add secondary mapping for UniProt IDs to ensure complete coverage
                transaction.cursor.execute("""
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
                    WHERE cb.uniprot_ids && tdd.uniprot_ids
                    AND cb.gene_symbol != tdd.gene_symbol
                    AND tdd.uniprot_ids IS NOT NULL
                    AND array_length(tdd.uniprot_ids, 1) > 0
                """)
                
                # Drop temporary table
                transaction.cursor.execute("DROP TABLE IF EXISTS temp_drug_data")
                
        except Exception as e:
            if self.db_manager.conn and not self.db_manager.conn.closed:
                self.db_manager.conn.rollback()
            raise DatabaseError(f"Drug data integration failed: {e}")
        finally:
            # Clean up
            try:
                if self.db_manager.cursor and not self.db_manager.cursor.closed:
                    self.db_manager.cursor.execute("DROP TABLE IF EXISTS temp_drug_data")
                if self.db_manager.conn and not self.db_manager.conn.closed:
                    self.db_manager.conn.commit()
            except Exception as e:
                self.logger.warning(f"Cleanup failed: {e}")

    def _update_drug_batch(self, updates: List[Tuple[str, List[str], str, str]]) -> None:
        """Update a batch of drug data.
        
        Args:
            updates: List of tuples with (gene_symbol, uniprot_ids, drug_data_json, drug_references_json)
            
        Raises:
            DatabaseError: If batch update fails
        """
        try:
            self.execute_batch(
                """
                INSERT INTO temp_drug_data 
                (gene_symbol, uniprot_ids, drug_data, drug_references)
                VALUES (%s, %s, %s::jsonb, %s::jsonb)
                """,
                updates
            )
        except Exception as e:
            raise DatabaseError(f"Failed to update drug batch: {e}")

    def calculate_drug_scores(self) -> None:
        """Calculate synergy-based drug scores using pathways and GO terms.
        
        Raises:
            DatabaseError: If drug score calculation fails
        """
        if self.skip_scores:
            self.logger.info("Skipping drug score calculation as requested")
            return
            
        if not self.ensure_connection() or not self.db_manager.cursor:
            raise DatabaseError("Database connection failed")
            
        try:
            # Create temporary scoring tables
            with self.get_db_transaction() as transaction:
                transaction.cursor.execute("""
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
            
            # Count total genes to process
            if self.db_manager.cursor:
                self.db_manager.cursor.execute("""
                    SELECT COUNT(*) 
                    FROM cancer_transcript_base 
                    WHERE drugs IS NOT NULL
                """)
                result = self.db_manager.cursor.fetchone()
                total_genes = result[0] if result is not None else 0
            else:
                total_genes = 0
                
            self.logger.info(f"Calculating drug scores for {total_genes} genes")
            
            # Process in batches
            offset = 0
            total_processed = 0
            
            # Setup progress tracking
            from ..utils.logging import get_progress_bar, complete_all_progress_bars
            
            # Create a progress bar
            progress = get_progress_bar(
                total=total_genes,
                desc="Calculating drug scores",
                module_name="drugs",
                unit="genes"
            )
            
            try:
                while True:
                    # Ensure connection is still valid
                    if not self.ensure_connection() or not self.db_manager.cursor:
                        raise DatabaseError("Database connection lost during score calculation")
                        
                    # Get batch of genes with drugs
                    self.db_manager.cursor.execute("""
                        SELECT gene_symbol, drugs, pathways, go_terms
                        FROM cancer_transcript_base
                        WHERE drugs IS NOT NULL
                        ORDER BY gene_symbol
                        LIMIT %s OFFSET %s
                    """, (self.batch_size, offset))
                    
                    rows = self.db_manager.cursor.fetchall()
                    if not rows:
                        break
                        
                    # Process scores in a transaction
                    with self.get_db_transaction() as transaction:
                        # Process pathway scores for this batch
                        transaction.cursor.execute("""
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
                        transaction.cursor.execute("""
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
                        
                        # Combine scores for this batch with proper casting to ensure numeric operations
                        pathway_weight = float(self.config.get('drug_pathway_weight', 1.0))
                        go_weight = pathway_weight * GO_TERM_WEIGHT_FACTOR
                        
                        transaction.cursor.execute("""
                            INSERT INTO temp_final_scores
                            SELECT 
                                ps.gene_symbol,
                                jsonb_object_agg(
                                    ps.drug_id,
                                    (COALESCE(ps.pathway_score * %s, 0) + 
                                     COALESCE(gs.go_score * %s, 0))::text::jsonb
                                ) as drug_scores
                            FROM temp_pathway_scores ps
                            LEFT JOIN temp_go_scores gs 
                            ON ps.gene_symbol = gs.gene_symbol 
                            AND ps.drug_id = gs.drug_id
                            WHERE ps.gene_symbol = ANY(%s)
                            GROUP BY ps.gene_symbol
                        """, (pathway_weight, go_weight, [row[0] for row in rows]))
                        
                        # Update main table for this batch
                        transaction.cursor.execute("""
                            UPDATE cancer_transcript_base cb
                            SET drug_scores = fs.drug_scores
                            FROM temp_final_scores fs
                            WHERE cb.gene_symbol = fs.gene_symbol
                        """)
                        
                        # Clear temporary tables for next batch
                        transaction.cursor.execute("""
                            TRUNCATE temp_pathway_scores, temp_go_scores, temp_final_scores
                        """)
                    
                    batch_size = len(rows)
                    total_processed += batch_size
                    offset += self.batch_size
                    
                    # Update progress
                    progress.update(batch_size)
                
                # Log final statistics
                self.logger.info(f"Drug score calculation completed. Total genes processed: {total_processed}")
            finally:
                # Ensure progress bar is completed
                progress.close()
            
        except Exception as e:
            self.logger.error(f"Drug score calculation failed: {e}")
            if self.db_manager.conn and not self.db_manager.conn.closed:
                self.db_manager.conn.rollback()
            raise DatabaseError(f"Drug score calculation failed: {e}")
        finally:
            # Clean up temporary tables
            try:
                if self.ensure_connection() and self.db_manager.cursor:
                    self.db_manager.cursor.execute("""
                        DROP TABLE IF EXISTS temp_pathway_scores;
                        DROP TABLE IF EXISTS temp_go_scores;
                        DROP TABLE IF EXISTS temp_final_scores;
                    """)
                    if self.db_manager.conn and not self.db_manager.conn.closed:
                        self.db_manager.conn.commit()
            except Exception as e:
                self.logger.warning(f"Failed to clean up temporary tables: {e}")

    def extract_publication_references(self, drug_references: str) -> List[Publication]:
        """Extract publication references from drug evidence data.
        
        Args:
            drug_references: References field from drug data
            
        Returns:
            List of publication references
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

    def extract_drug_references(self, drug_data: Dict[str, Any]) -> List[Publication]:
        """Extract publication references from drug evidence data.
        
        Args:
            drug_data: Dictionary with drug evidence data
            
        Returns:
            List of publication references
        """
        publications: List[Publication] = []
        
        # Check various evidence fields for PMIDs
        evidence_fields = [
            'clinical_evidence',
            'experimental_evidence',
            'mechanism_references'
        ]
        
        for field in evidence_fields:
            evidence_text = drug_data.get(field, '')
            pmids = extract_pmids_from_text(evidence_text)
            
            for pmid in pmids:
                publication = PublicationsProcessor.create_publication_reference(
                    pmid=pmid,
                    evidence_type=field.replace('_', ' '),
                    source_db="DrugCentral",
                    url=format_pmid_url(pmid)
                )
                publications.append(publication)
        
        return publications
    
    def run(self) -> None:
        """Run the complete drug processing pipeline.
        
        Steps:
        1. Download DrugCentral data
        2. Process drug-target relationships
        3. Integrate with transcript data
        4. Calculate synergy-based drug scores
        
        Raises:
            Various ETLError subclasses based on failure point
        """
        try:
            self.logger.info("Starting drug processing pipeline...")
            
            # Add diagnostic query to count transcripts before processing
            if not self.ensure_connection() or not self.db_manager.cursor:
                raise DatabaseError("Database connection failed")
                    
            self.db_manager.cursor.execute("""
                SELECT 
                    COUNT(*) as total_records,
                    COUNT(CASE WHEN drugs IS NOT NULL AND drugs != '{}'::jsonb THEN 1 END) as with_drugs,
                    COUNT(CASE WHEN drug_scores IS NOT NULL AND drug_scores != '{}'::jsonb THEN 1 END) as with_scores,
                    COUNT(CASE WHEN gene_symbol IS NOT NULL THEN 1 END) as with_genes,
                    COUNT(CASE WHEN uniprot_ids IS NOT NULL AND array_length(uniprot_ids, 1) > 0 THEN 1 END) as with_uniprot
                FROM cancer_transcript_base
            """)
            
            stats = self.db_manager.cursor.fetchone()
            if stats:
                self.logger.info(
                    f"Before drug processing:\n"
                    f"- Total records: {stats[0]:,}\n"
                    f"- Records with drugs: {stats[1]:,} ({stats[1]/max(1, stats[0])*100:.1f}%)\n"
                    f"- Records with drug scores: {stats[2]:,} ({stats[2]/max(1, stats[0])*100:.1f}%)\n"
                    f"- Records with gene symbols: {stats[3]:,} ({stats[3]/max(1, stats[0])*100:.1f}%)\n"
                    f"- Records with UniProt IDs: {stats[4]:,} ({stats[4]/max(1, stats[0])*100:.1f}%)"
                )
            
            # Download and extract data
            drug_data_path = self.download_drugcentral()
            
            # Process drug targets with validation
            drug_targets = self.process_drug_targets(drug_data_path)
            if drug_targets.empty:
                raise ProcessingError("No valid drug target relationships found")
            
            # Integrate with transcript data
            self.logger.info("Integrating drug data with transcripts...")
            self.integrate_drugs(drug_targets)
            
            # Calculate drug scores
            self.logger.info("Calculating drug interaction scores...")
            self.calculate_drug_scores()
            
            # Verify results
            self._verify_integration_results()
            
            self.logger.info("Drug processing pipeline completed successfully")
            
        except Exception as e:
            self.logger.error(f"Drug processing pipeline failed: {e}")
            raise
    
    def _verify_integration_results(self) -> None:
        """Verify drug integration results with database statistics."""
        if not self.ensure_connection():
            self.logger.warning("Cannot verify results - database connection unavailable")
            return
            
        try:
            # Validate cursor before using
            if not self.db_manager.cursor:
                self.logger.warning("Cannot verify results - no database cursor available")
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
            
            stats = self.db_manager.cursor.fetchone()
            if stats:
                self.logger.info(
                    f"Pipeline completed:\n"
                    f"- Total records: {stats[0]:,}\n"
                    f"- Records with drugs: {stats[1]:,}\n"
                    f"- Records with drug scores: {stats[2]:,}\n"
                    f"- Records with drug references: {stats[3]:,}"
                )
                
        except Exception as e:
            self.logger.warning(f"Failed to verify results: {e}")

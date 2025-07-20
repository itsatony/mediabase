#!/usr/bin/env python3
"""Create Patient-Specific MEDIABASE Copy.

This script creates an independent copy of the MEDIABASE database for a specific patient
and updates the expression_fold_change column with patient-specific transcriptome data
from a CSV file.

Usage:
    poetry run python scripts/create_patient_copy.py --patient-id PATIENT123 --csv-file patient_data.csv

The script will:
1. Create a new database named mediabase_patient_PATIENT123
2. Copy all schema and data from the source MEDIABASE
3. Update fold-change values from the provided CSV file
4. Validate data integrity throughout the process
"""

import argparse
import csv
import logging
import sys
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set, Any
from datetime import datetime

import pandas as pd
import psycopg2
from psycopg2.extensions import connection as pg_connection
from psycopg2.extras import execute_batch
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, TaskID
from tqdm import tqdm

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from src.db.database import get_db_manager, DatabaseManager
from src.utils.logging import setup_logging, get_progress_bar

# Constants
REQUIRED_CSV_COLUMNS = {"transcript_id", "cancer_fold"}
ALTERNATIVE_COLUMN_NAMES = {
    "transcript_id": ["transcript_id", "transcript", "id", "gene_id", "ensembl_id", "symbol"],
    "cancer_fold": ["cancer_fold", "fold_change", "expression_fold_change", "fold", "fc", "log2foldchange", "logfc"]
}

# DESeq2 specific mappings
DESEQ2_FORMAT_INDICATORS = {
    "symbol": ["symbol", "gene_symbol", "gene_name"],
    "log2_fold_change": ["log2foldchange", "log2fc", "logfc", "lfc"]
}
PATIENT_DB_PREFIX = "mediabase_patient_"
BATCH_SIZE = 1000
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

class PatientCopyError(Exception):
    """Base exception for patient copy operations."""
    pass

class CSVValidationError(PatientCopyError):
    """Exception raised when CSV validation fails."""
    pass

class DatabaseCopyError(PatientCopyError):
    """Exception raised when database copying fails."""
    pass

class FoldChangeUpdateError(PatientCopyError):
    """Exception raised when fold-change updates fail."""
    pass

class PatientDatabaseCreator:
    """Creates patient-specific copies of MEDIABASE with custom fold-change data."""
    
    def __init__(self, patient_id: str, csv_file: Path, source_db_config: Dict[str, Any]):
        """Initialize the patient database creator.
        
        Args:
            patient_id: Unique identifier for the patient
            csv_file: Path to CSV file with fold-change data
            source_db_config: Database configuration for source MEDIABASE
        """
        self.patient_id = patient_id
        self.csv_file = csv_file
        self.source_db_config = source_db_config
        self.target_db_name = f"{PATIENT_DB_PREFIX}{patient_id}"
        
        self.console = Console()
        self.logger = logging.getLogger(__name__)
        
        # Data storage
        self.csv_data: Optional[pd.DataFrame] = None
        self.column_mapping: Dict[str, str] = {}
        self.transcript_updates: Dict[str, float] = {}
        self.gene_symbol_mapping: Dict[str, str] = {}  # gene_symbol -> transcript_id
        self.is_deseq2_format: bool = False
        self.log2_fold_column: Optional[str] = None
        
        # Statistics
        self.stats = {
            "csv_rows_read": 0,
            "valid_transcripts": 0,
            "invalid_transcripts": 0,
            "updates_applied": 0,
            "transcripts_not_found": 0
        }
    
    def validate_csv_file(self) -> None:
        """Validate CSV file structure and prompt for column mapping if needed.
        
        Raises:
            CSVValidationError: If CSV validation fails
        """
        try:
            # Read CSV file
            self.console.print(f"[blue]Reading CSV file: {self.csv_file}[/blue]")
            self.csv_data = pd.read_csv(self.csv_file)
            self.stats["csv_rows_read"] = len(self.csv_data)
            
            if self.csv_data.empty:
                raise CSVValidationError("CSV file is empty")
            
            # Display CSV structure
            self._display_csv_info()
            
            # Check for required columns
            available_columns = set(self.csv_data.columns)
            found_columns = self._find_column_mapping(available_columns)
            
            if not found_columns:
                # Interactive column mapping
                self._interactive_column_mapping(available_columns)
            else:
                self.column_mapping = found_columns
                self.console.print("[green]✓ Required columns found automatically[/green]")
            
            # Validate mapped columns
            self._validate_mapped_columns()
            
        except Exception as e:
            self.logger.error(f"CSV validation failed: {e}")
            raise CSVValidationError(f"Failed to validate CSV file: {e}")
    
    def _display_csv_info(self) -> None:
        """Display information about the CSV file."""
        table = Table(title="CSV File Information")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("File Path", str(self.csv_file))
        table.add_row("Rows", str(len(self.csv_data)))
        table.add_row("Columns", str(len(self.csv_data.columns)))
        table.add_row("Available Columns", ", ".join(self.csv_data.columns))
        
        self.console.print(table)
        
        # Show first few rows
        self.console.print("\n[blue]First 5 rows:[/blue]")
        self.console.print(self.csv_data.head().to_string())
    
    def _find_column_mapping(self, available_columns: Set[str]) -> Dict[str, str]:
        """Attempt to automatically find column mapping with DESeq2 format detection.
        
        Args:
            available_columns: Set of available column names
            
        Returns:
            Dictionary mapping required columns to actual column names
        """
        mapping = {}
        
        # Check for DESeq2 format indicators
        deseq2_indicators = self._detect_deseq2_format(available_columns)
        if deseq2_indicators:
            self.is_deseq2_format = True
            self.console.print("[green]🧬 Detected DESeq2 format! Applying specialized mapping...[/green]")
            mapping = self._map_deseq2_columns(available_columns, deseq2_indicators)
        else:
            # Standard column mapping
            for required_col, alternatives in ALTERNATIVE_COLUMN_NAMES.items():
                for alt_name in alternatives:
                    if alt_name.lower() in [col.lower() for col in available_columns]:
                        # Find exact match (case-insensitive)
                        for col in available_columns:
                            if col.lower() == alt_name.lower():
                                mapping[required_col] = col
                                break
                        break
        
        return mapping if len(mapping) == len(REQUIRED_CSV_COLUMNS) else {}
    
    def _detect_deseq2_format(self, available_columns: Set[str]) -> Dict[str, str]:
        """Detect if CSV is in DESeq2 format and find key columns.
        
        Args:
            available_columns: Set of available column names
            
        Returns:
            Dictionary mapping DESeq2 column types to actual column names
        """
        deseq2_mapping = {}
        available_lower = {col.lower(): col for col in available_columns}
        
        # Check for gene symbol column
        for symbol_variant in DESEQ2_FORMAT_INDICATORS["symbol"]:
            if symbol_variant.lower() in available_lower:
                deseq2_mapping["symbol"] = available_lower[symbol_variant.lower()]
                break
        
        # Check for log2 fold change column  
        for log2_variant in DESEQ2_FORMAT_INDICATORS["log2_fold_change"]:
            if log2_variant.lower() in available_lower:
                deseq2_mapping["log2_fold_change"] = available_lower[log2_variant.lower()]
                self.log2_fold_column = available_lower[log2_variant.lower()]
                break
        
        # Must have both key columns to be considered DESeq2 format
        return deseq2_mapping if len(deseq2_mapping) == 2 else {}
    
    def _map_deseq2_columns(self, available_columns: Set[str], deseq2_indicators: Dict[str, str]) -> Dict[str, str]:
        """Map DESeq2 format columns to required format.
        
        Args:
            available_columns: Set of available column names
            deseq2_indicators: Dictionary of detected DESeq2 columns
            
        Returns:
            Dictionary mapping required columns to actual column names
        """
        mapping = {
            "transcript_id": deseq2_indicators["symbol"],  # Will be converted via gene symbol lookup
            "cancer_fold": deseq2_indicators["log2_fold_change"]  # Will be converted from log2
        }
        
        # Set the log2 fold column for later use
        self.log2_fold_column = deseq2_indicators["log2_fold_change"]
        
        self.console.print(f"[blue]📊 DESeq2 Mapping:[/blue]")
        self.console.print(f"  Gene Symbol: {deseq2_indicators['symbol']}")
        self.console.print(f"  Log2 Fold Change: {deseq2_indicators['log2_fold_change']}")
        self.console.print(f"[yellow]Note: Gene symbols will be mapped to transcript IDs, log2 values converted to linear fold change[/yellow]")
        
        return mapping
    
    def _interactive_column_mapping(self, available_columns: Set[str]) -> None:
        """Interactive column mapping when automatic detection fails.
        
        Args:
            available_columns: Set of available column names
        """
        self.console.print("\n[yellow]Could not automatically detect required columns.[/yellow]")
        self.console.print("[yellow]Please map the following columns:[/yellow]")
        
        for required_col in REQUIRED_CSV_COLUMNS:
            self.console.print(f"\n[cyan]Required column: {required_col}[/cyan]")
            self.console.print(f"Expected content: {self._get_column_description(required_col)}")
            self.console.print(f"Available columns: {', '.join(sorted(available_columns))}")
            
            while True:
                selected_col = Prompt.ask("Select column name")
                if selected_col in available_columns:
                    self.column_mapping[required_col] = selected_col
                    break
                else:
                    self.console.print(f"[red]Column '{selected_col}' not found. Please try again.[/red]")
    
    def _get_column_description(self, column: str) -> str:
        """Get description for required columns.
        
        Args:
            column: Column name
            
        Returns:
            Description of expected column content
        """
        descriptions = {
            "transcript_id": "Transcript identifier (e.g., ENST00000123456)",
            "cancer_fold": "Fold-change value for cancer expression (numeric)"
        }
        return descriptions.get(column, "Unknown column")
    
    def _validate_mapped_columns(self) -> None:
        """Validate the data in mapped columns with DESeq2 format support.
        
        Raises:
            CSVValidationError: If data validation fails
        """
        transcript_col = self.column_mapping["transcript_id"]
        fold_col = self.column_mapping["cancer_fold"]
        
        # Check for missing values
        transcript_nulls = self.csv_data[transcript_col].isnull().sum()
        fold_nulls = self.csv_data[fold_col].isnull().sum()
        
        if transcript_nulls > 0:
            self.logger.warning(f"Found {transcript_nulls} null transcript IDs")
        
        if fold_nulls > 0:
            self.logger.warning(f"Found {fold_nulls} null fold-change values")
        
        # Validate fold-change values are numeric
        try:
            fold_values = pd.to_numeric(self.csv_data[fold_col], errors='coerce')
            invalid_folds = fold_values.isnull().sum() - fold_nulls
            
            if invalid_folds > 0:
                raise CSVValidationError(f"Found {invalid_folds} non-numeric fold-change values")
            
        except Exception as e:
            raise CSVValidationError(f"Failed to validate fold-change values: {e}")
        
        # Process data based on format
        valid_data = self.csv_data.dropna(subset=[transcript_col, fold_col])
        
        if self.is_deseq2_format:
            self._process_deseq2_data(valid_data, transcript_col, fold_col)
        else:
            self._process_standard_data(valid_data, transcript_col, fold_col)
        
        self.console.print(f"[green]✓ Processed {self.stats['valid_transcripts']} transcript entries[/green]")
        if self.stats["invalid_transcripts"] > 0:
            self.console.print(f"[yellow]⚠ Skipped {self.stats['invalid_transcripts']} invalid entries[/yellow]")
    
    def _process_standard_data(self, valid_data: pd.DataFrame, transcript_col: str, fold_col: str) -> None:
        """Process standard format data (transcript_id, fold_change) with flexible ID matching.
        
        Args:
            valid_data: DataFrame with valid data rows
            transcript_col: Column name containing transcript IDs
            fold_col: Column name containing fold-change values
        """
        self.console.print("[blue]🧬 Processing standard transcript data with flexible ID matching...[/blue]")
        
        # Get available transcript IDs from database for matching
        database_transcript_ids = self._get_database_transcript_ids()
        
        transcript_updates = {}
        unmatched_ids = []
        
        for idx, (transcript_id, fold_change) in zip(valid_data.index, zip(valid_data[transcript_col], valid_data[fold_col])):
            transcript_id = str(transcript_id).strip()
            
            # Try flexible matching
            matched_id = self._match_transcript_id_flexibly(transcript_id, database_transcript_ids)
            
            if matched_id:
                transcript_updates[matched_id] = float(pd.to_numeric(fold_change))
            else:
                unmatched_ids.append(transcript_id)
        
        self.transcript_updates = transcript_updates
        
        # Update statistics
        self.stats["valid_transcripts"] = len(self.transcript_updates)
        csv_data_length = len(self.csv_data) if self.csv_data is not None else len(valid_data)
        self.stats["invalid_transcripts"] = csv_data_length - len(valid_data) + len(unmatched_ids)
        self.stats["unmatched_ids"] = len(unmatched_ids)
        self.stats["matching_success_rate"] = (len(self.transcript_updates) / len(valid_data)) * 100
        
        self.console.print(f"[blue]📊 Standard Processing Results:[/blue]")
        self.console.print(f"  Transcript IDs processed: {len(valid_data)}")
        self.console.print(f"  Successfully matched: {len(self.transcript_updates)}")
        self.console.print(f"  Unmatched IDs: {len(unmatched_ids)}")
        self.console.print(f"  Matching success rate: {self.stats['matching_success_rate']:.1f}%")
        
        if unmatched_ids and len(unmatched_ids) <= 10:
            self.console.print(f"[yellow]Unmatched IDs: {', '.join(unmatched_ids[:10])}[/yellow]")
        elif len(unmatched_ids) > 10:
            self.console.print(f"[yellow]First 10 unmatched IDs: {', '.join(unmatched_ids[:10])}... (+{len(unmatched_ids)-10} more)[/yellow]")
        
    def _process_deseq2_data(self, valid_data: pd.DataFrame, symbol_col: str, log2_col: str) -> None:
        """Process DESeq2 format data (SYMBOL, log2FoldChange).
        
        Args:
            valid_data: DataFrame with valid data rows
            symbol_col: Column name containing gene symbols
            log2_col: Column name containing log2 fold-change values
        """
        self.console.print("[blue]🧬 Processing DESeq2 data...[/blue]")
        
        # Load gene symbol to transcript ID mapping
        self._load_gene_symbol_mapping()
        
        # Convert log2 fold changes to linear fold changes
        log2_values = pd.to_numeric(valid_data[log2_col])
        linear_fold_changes = 2 ** log2_values  # Convert log2 to linear
        
        # Map gene symbols to transcript IDs
        transcript_updates = {}
        unmapped_symbols = []
        
        for idx, (symbol, fold_change) in zip(valid_data.index, zip(valid_data[symbol_col], linear_fold_changes)):
            symbol = str(symbol).strip()
            
            if symbol in self.gene_symbol_mapping:
                transcript_id = self.gene_symbol_mapping[symbol]
                transcript_updates[transcript_id] = float(fold_change)
            else:
                unmapped_symbols.append(symbol)
        
        self.transcript_updates = transcript_updates
        
        # Update statistics
        self.stats["valid_transcripts"] = len(self.transcript_updates)
        # Handle case where csv_data might be None in tests
        csv_data_length = len(self.csv_data) if self.csv_data is not None else len(valid_data)
        self.stats["invalid_transcripts"] = csv_data_length - len(valid_data) + len(unmapped_symbols)
        self.stats["unmapped_symbols"] = len(unmapped_symbols)
        self.stats["mapping_success_rate"] = (len(self.transcript_updates) / len(valid_data)) * 100
        
        self.console.print(f"[blue]📊 DESeq2 Processing Results:[/blue]")
        self.console.print(f"  Symbols processed: {len(valid_data)}")
        self.console.print(f"  Successfully mapped: {len(self.transcript_updates)}")
        self.console.print(f"  Unmapped symbols: {len(unmapped_symbols)}")
        self.console.print(f"  Mapping success rate: {self.stats['mapping_success_rate']:.1f}%")
        
        if unmapped_symbols and len(unmapped_symbols) <= 10:
            self.console.print(f"[yellow]Unmapped symbols: {', '.join(unmapped_symbols[:10])}[/yellow]")
        elif len(unmapped_symbols) > 10:
            self.console.print(f"[yellow]First 10 unmapped symbols: {', '.join(unmapped_symbols[:10])}... (+{len(unmapped_symbols)-10} more)[/yellow]")
    
    def _normalize_transcript_id(self, transcript_id: str) -> str:
        """Normalize transcript ID by removing version suffix if present.
        
        Args:
            transcript_id: Original transcript ID (e.g., 'ENST00000456328.1')
            
        Returns:
            Normalized transcript ID (e.g., 'ENST00000456328')
        """
        if not transcript_id:
            return transcript_id
            
        # Remove version suffix (everything after the last dot)
        if '.' in transcript_id and transcript_id.split('.')[-1].isdigit():
            return transcript_id.rsplit('.', 1)[0]
        
        return transcript_id
    
    def _match_transcript_id_flexibly(self, input_id: str, database_ids: Set[str]) -> Optional[str]:
        """Flexibly match transcript ID against database, handling versioned/unversioned formats.
        
        Args:
            input_id: Transcript ID from CSV (may be versioned or unversioned)
            database_ids: Set of transcript IDs from database
            
        Returns:
            Matching database transcript ID or None if no match found
        """
        if not input_id:
            return None
            
        # First try exact match
        if input_id in database_ids:
            return input_id
            
        # Try normalized version (remove version suffix)
        normalized_input = self._normalize_transcript_id(input_id)
        if normalized_input in database_ids:
            return normalized_input
            
        # Try adding common version suffixes if input has none
        if '.' not in input_id:
            for version in ['1', '2', '3', '4', '5']:
                versioned_id = f"{input_id}.{version}"
                if versioned_id in database_ids:
                    return versioned_id
        
        # Try matching any database ID that starts with normalized input
        for db_id in database_ids:
            if self._normalize_transcript_id(db_id) == normalized_input:
                return db_id
                
        return None

    def _get_database_transcript_ids(self) -> Set[str]:
        """Get set of all transcript IDs from database for flexible matching.
        
        Returns:
            Set of transcript IDs from database
        """
        try:
            # Connect to source database
            db_manager = get_db_manager(self.source_db_config)
            
            if not db_manager.ensure_connection():
                raise CSVValidationError("Failed to connect to source database")
            
            # Query for all transcript IDs
            cursor = db_manager.cursor
            cursor.execute("SELECT DISTINCT transcript_id FROM cancer_transcript_base WHERE transcript_id IS NOT NULL")
            
            transcript_ids = {row[0] for row in cursor.fetchall()}
            return transcript_ids
            
        except Exception as e:
            self.console.print(f"[yellow]Warning: Could not load transcript IDs for flexible matching: {e}[/yellow]")
            return set()
        finally:
            if 'db_manager' in locals():
                db_manager.close()

    def _load_gene_symbol_mapping(self) -> None:
        """Load gene symbol to transcript ID mapping from database.
        
        Raises:
            CSVValidationError: If mapping cannot be loaded
        """
        try:
            self.console.print("[blue]Loading gene symbol mappings from database...[/blue]")
            
            # Connect to source database
            db_manager = get_db_manager(self.source_db_config)
            
            if not db_manager.ensure_connection():
                raise CSVValidationError("Failed to connect to source database")
            
            # Query for gene symbol mappings
            cursor = db_manager.cursor
            cursor.execute("""
                SELECT DISTINCT gene_symbol, transcript_id 
                FROM cancer_transcript_base 
                WHERE gene_symbol IS NOT NULL 
                AND gene_symbol != ''
                AND transcript_id IS NOT NULL
            """)
            
            # Build mapping dictionary
            for gene_symbol, transcript_id in cursor.fetchall():
                if gene_symbol not in self.gene_symbol_mapping:
                    self.gene_symbol_mapping[gene_symbol] = transcript_id
            
            self.console.print(f"[green]✓ Loaded {len(self.gene_symbol_mapping)} gene symbol mappings[/green]")
            
        except Exception as e:
            raise CSVValidationError(f"Failed to load gene symbol mappings: {e}")
        finally:
            if 'db_manager' in locals():
                db_manager.close()
    
    def create_patient_database(self) -> None:
        """Create patient-specific database copy.
        
        Raises:
            DatabaseCopyError: If database creation fails
        """
        try:
            self.console.print(f"[blue]Creating patient database: {self.target_db_name}[/blue]")
            
            # Get source database manager
            source_db = get_db_manager(self.source_db_config)
            
            # Create target database
            self._create_target_database(source_db)
            
            # Copy schema and data
            self._copy_database_content(source_db)
            
            self.console.print(f"[green]✓ Patient database '{self.target_db_name}' created successfully[/green]")
            
        except Exception as e:
            self.logger.error(f"Database copy failed: {e}")
            raise DatabaseCopyError(f"Failed to create patient database: {e}")
    
    def _create_target_database(self, source_db: DatabaseManager) -> None:
        """Create the target database.
        
        Args:
            source_db: Source database manager
        """
        # Connect to postgres database to create new database
        postgres_config = self.source_db_config.copy()
        postgres_config['dbname'] = 'postgres'
        
        try:
            conn = psycopg2.connect(**postgres_config)
            conn.autocommit = True
            
            with conn.cursor() as cursor:
                # Check if database already exists
                cursor.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s",
                    (self.target_db_name,)
                )
                
                if cursor.fetchone():
                    if not Confirm.ask(f"Database '{self.target_db_name}' already exists. Overwrite?"):
                        raise DatabaseCopyError("Database creation cancelled by user")
                    
                    # Drop existing database
                    cursor.execute(f'DROP DATABASE "{self.target_db_name}"')
                    self.logger.info(f"Dropped existing database: {self.target_db_name}")
                
                # Create new database
                cursor.execute(f'CREATE DATABASE "{self.target_db_name}"')
                self.logger.info(f"Created database: {self.target_db_name}")
                
        finally:
            conn.close()
    
    def _copy_database_content(self, source_db: DatabaseManager) -> None:
        """Copy schema and data to target database.
        
        Args:
            source_db: Source database manager
        """
        # Use pg_dump and pg_restore for efficient copying
        source_config = self.source_db_config
        
        dump_file = f"/tmp/{self.target_db_name}_dump.sql"
        
        try:
            # Create dump
            dump_cmd = (
                f"pg_dump -h {source_config['host']} -p {source_config['port']} "
                f"-U {source_config['user']} -d {source_config['dbname']} "
                f"-f {dump_file} --no-owner --no-privileges"
            )
            
            self.logger.info("Creating database dump...")
            os.system(f"PGPASSWORD='{source_config['password']}' {dump_cmd}")
            
            # Restore to target database
            restore_cmd = (
                f"psql -h {source_config['host']} -p {source_config['port']} "
                f"-U {source_config['user']} -d {self.target_db_name} "
                f"-f {dump_file}"
            )
            
            self.logger.info("Restoring to target database...")
            os.system(f"PGPASSWORD='{source_config['password']}' {restore_cmd}")
            
        finally:
            # Cleanup dump file
            if os.path.exists(dump_file):
                os.remove(dump_file)
    
    def update_fold_changes(self) -> None:
        """Update fold-change values in the patient database.
        
        Raises:
            FoldChangeUpdateError: If updates fail
        """
        try:
            self.console.print(f"[blue]Updating fold-change values for {len(self.transcript_updates)} transcripts[/blue]")
            
            # Connect to target database
            target_config = self.source_db_config.copy()
            target_config['dbname'] = self.target_db_name
            target_db = get_db_manager(target_config)
            
            # Process updates in batches
            transcript_ids = list(self.transcript_updates.keys())
            
            # Create progress bar for batch updates
            progress_bar = get_progress_bar(
                total=len(transcript_ids),
                desc="Updating fold-changes",
                module_name="patient_copy"
            )
            
            try:
                for i in range(0, len(transcript_ids), BATCH_SIZE):
                    batch_ids = transcript_ids[i:i + BATCH_SIZE]
                    batch_updates = [
                        (self.transcript_updates[tid], tid) for tid in batch_ids
                    ]
                    
                    # Execute batch update
                    try:
                        # Ensure connection is active
                        if not target_db.ensure_connection():
                            raise Exception("Failed to connect to target database")
                        
                        # Execute batch update
                        execute_batch(
                            target_db.cursor,
                            """
                            UPDATE cancer_transcript_base 
                            SET expression_fold_change = %s 
                            WHERE transcript_id = %s
                            """,
                            batch_updates,
                            page_size=BATCH_SIZE
                        )
                        
                        # Count successful updates
                        target_db.cursor.execute(
                            """
                            SELECT COUNT(*) FROM cancer_transcript_base 
                            WHERE transcript_id = ANY(%s)
                            """,
                            (batch_ids,)
                        )
                        
                        found_count = target_db.cursor.fetchone()[0]
                        self.stats["updates_applied"] += found_count
                        self.stats["transcripts_not_found"] += len(batch_ids) - found_count
                        
                        # Commit the batch
                        target_db.conn.commit()
                        
                    except Exception as e:
                        # Rollback on error
                        if target_db.conn:
                            target_db.conn.rollback()
                        raise e
                    
                    # Update progress bar
                    progress_bar.update(len(batch_ids))
                
                # Complete the progress bar
                progress_bar.complete()
                
            finally:
                # Ensure progress bar is closed
                progress_bar.close()
            
            self._log_update_statistics()
            
        except Exception as e:
            self.logger.error(f"Fold-change update failed: {e}")
            raise FoldChangeUpdateError(f"Failed to update fold-change values: {e}")
    
    def _log_update_statistics(self) -> None:
        """Log update statistics."""
        table = Table(title="Update Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="green")
        
        table.add_row("CSV rows processed", str(self.stats["csv_rows_read"]))
        table.add_row("Valid transcript entries", str(self.stats["valid_transcripts"]))
        table.add_row("Invalid entries skipped", str(self.stats["invalid_transcripts"]))
        table.add_row("Updates applied", str(self.stats["updates_applied"]))
        table.add_row("Transcripts not found", str(self.stats["transcripts_not_found"]))
        
        self.console.print(table)
        
        if self.stats["transcripts_not_found"] > 0:
            self.console.print(
                f"[yellow]⚠ {self.stats['transcripts_not_found']} transcripts from CSV "
                f"were not found in the database[/yellow]"
            )
    
    def validate_result(self) -> None:
        """Validate the final result of the patient database creation."""
        try:
            target_config = self.source_db_config.copy()
            target_config['dbname'] = self.target_db_name
            target_db = get_db_manager(target_config)
            
            # Ensure connection is active
            if not target_db.ensure_connection():
                raise Exception("Failed to connect to target database for validation")
            
            # Check total transcript count
            target_db.cursor.execute("SELECT COUNT(*) FROM cancer_transcript_base")
            total_transcripts = target_db.cursor.fetchone()[0]
            
            # Check transcripts with non-default fold-change
            target_db.cursor.execute(
                "SELECT COUNT(*) FROM cancer_transcript_base WHERE expression_fold_change != 1.0"
            )
            modified_transcripts = target_db.cursor.fetchone()[0]
            
            # Sample some updated values
            target_db.cursor.execute(
                """
                    SELECT transcript_id, expression_fold_change 
                    FROM cancer_transcript_base 
                    WHERE expression_fold_change != 1.0 
                    LIMIT 5
                    """
                )
            samples = target_db.cursor.fetchall()
            
            self.console.print(f"[green]✓ Validation complete[/green]")
            self.console.print(f"Total transcripts: {total_transcripts:,}")
            self.console.print(f"Modified transcripts: {modified_transcripts:,}")
            
            if samples:
                self.console.print("\nSample updated transcripts:")
                for transcript_id, fold_change in samples:
                    self.console.print(f"  {transcript_id}: {fold_change:.4f}")
            
        except Exception as e:
            self.logger.error(f"Validation failed: {e}")
            raise PatientCopyError(f"Result validation failed: {e}")

def main():
    """Main entry point for the patient copy script."""
    parser = argparse.ArgumentParser(
        description="Create patient-specific MEDIABASE copy with custom fold-change data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --patient-id PATIENT123 --csv-file patient_data.csv
  %(prog)s --patient-id PATIENT123 --csv-file data.csv --source-db mediabase_dev
  %(prog)s --patient-id PATIENT123 --csv-file data.csv --log-level DEBUG
        """
    )
    
    parser.add_argument(
        "--patient-id",
        required=True,
        help="Unique identifier for the patient"
    )
    
    parser.add_argument(
        "--csv-file",
        required=True,
        type=Path,
        help="Path to CSV file with transcript fold-change data"
    )
    
    parser.add_argument(
        "--source-db",
        default="mediabase",
        help="Source database name (default: mediabase)"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate CSV and show what would be done without making changes"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(log_level=args.log_level)
    logger = logging.getLogger(__name__)
    console = Console()
    
    try:
        # Validate inputs
        if not args.csv_file.exists():
            raise PatientCopyError(f"CSV file not found: {args.csv_file}")
        
        # Get database configuration
        db_config = {
            'host': os.getenv('MB_POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('MB_POSTGRES_PORT', 5432)),
            'dbname': args.source_db,
            'user': os.getenv('MB_POSTGRES_USER', 'postgres'),
            'password': os.getenv('MB_POSTGRES_PASSWORD', 'postgres')
        }
        
        # Display operation summary
        console.print(f"[bold blue]MEDIABASE Patient Copy Operation[/bold blue]")
        console.print(f"Patient ID: {args.patient_id}")
        console.print(f"CSV File: {args.csv_file}")
        console.print(f"Source Database: {args.source_db}")
        console.print(f"Target Database: {PATIENT_DB_PREFIX}{args.patient_id}")
        console.print(f"Dry Run: {args.dry_run}")
        
        if not args.dry_run:
            if not Confirm.ask("\nProceed with database creation?"):
                console.print("[yellow]Operation cancelled by user[/yellow]")
                sys.exit(0)
        
        # Create patient database creator
        creator = PatientDatabaseCreator(args.patient_id, args.csv_file, db_config)
        
        # Execute pipeline
        console.print("\n[bold]Step 1: Validating CSV file[/bold]")
        creator.validate_csv_file()
        
        if args.dry_run:
            console.print("\n[yellow]Dry run complete. No changes made.[/yellow]")
            sys.exit(0)
        
        console.print("\n[bold]Step 2: Creating patient database[/bold]")
        creator.create_patient_database()
        
        console.print("\n[bold]Step 3: Updating fold-change values[/bold]")
        creator.update_fold_changes()
        
        console.print("\n[bold]Step 4: Validating results[/bold]")
        creator.validate_result()
        
        console.print(f"\n[bold green]✓ Patient database '{PATIENT_DB_PREFIX}{args.patient_id}' created successfully![/bold green]")
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation interrupted by user[/yellow]")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Operation failed: {e}")
        console.print(f"\n[bold red]✗ Error: {e}[/bold red]")
        sys.exit(1)

if __name__ == "__main__":
    main()
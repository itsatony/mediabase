"""ChEMBL integration module for Cancer Transcriptome Base.

This module downloads, processes, and integrates drug data from ChEMBL
into transcript records, providing comprehensive pharmacological information.
"""

# Standard library imports
import json
import gzip
import csv
import os
import shutil
import tempfile
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple, Union, Iterator
from datetime import datetime, timedelta

# Third party imports
import pandas as pd
import numpy as np
import requests
from tqdm import tqdm
from rich.console import Console
from rich.table import Table
import psycopg2
from psycopg2.extras import execute_values

# Local imports
from .base_processor import BaseProcessor, DownloadError, ProcessingError, DatabaseError
from .publications import Publication, PublicationsProcessor
from ..utils.publication_utils import extract_pmids_from_text, format_pmid_url, merge_publication_references
from ..utils.pandas_helpers import safe_assign, safe_batch_assign, safe_fillna, clean_dataframe, PandasOperationSafe
from ..utils.gene_matcher import normalize_gene_symbol, match_genes_bulk, get_gene_match_stats
from ..utils.logging import get_progress_bar, setup_logging
from ..utils.progress import track_progress

# Constants
CHEMBL_VERSION = "35"
CHEMBL_CACHE_TTL = 365 * 24 * 60 * 60  # 1 year in seconds
CHEMBL_DB_DUMP_URL = f"https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/releases/chembl_{CHEMBL_VERSION}/chembl_{CHEMBL_VERSION}_postgresql.tar.gz"
CHEMBL_MAPPING_URL = f"https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/latest/chembl_uniprot_mapping.txt"

# Target types of interest (reduces data size)
TARGET_TYPES_OF_INTEREST = {
    'SINGLE PROTEIN', 
    'PROTEIN COMPLEX', 
    'PROTEIN FAMILY', 
    'PROTEIN-PROTEIN INTERACTION'
}

class ChemblDrugProcessor(BaseProcessor):
    """Process drug data from ChEMBL and integrate with transcript data."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize ChEMBL drug processor with configuration.
        
        Args:
            config: Configuration dictionary containing settings for ChEMBL processing
        """
        super().__init__(config)
        
        # Create ChEMBL-specific directory
        self.chembl_dir = self.cache_dir / f'chembl_{CHEMBL_VERSION}'
        self.chembl_dir.mkdir(exist_ok=True)
        
        # ChEMBL data URLs
        self.chembl_db_url = config.get('chembl_db_url', CHEMBL_DB_DUMP_URL)
        self.chembl_mapping_url = config.get('chembl_mapping_url', CHEMBL_MAPPING_URL)
        
        # Configuration options
        self.skip_scores = config.get('skip_scores', False)
        self.force_download = config.get('force_download', False)
        self.use_temp_schema = config.get('use_temp_schema', True)
        self.chembl_schema = config.get('chembl_schema', 'chembl_temp')
        self.max_phase_cutoff = config.get('max_phase_cutoff', 0)  # 0 = include all, 1+ = only drugs with specified phase or higher
        
        # Path to the extracted data files
        self.extracted_dir = self.chembl_dir / 'extracted'
        self.processed_dir = self.chembl_dir / 'processed'
        
        # Enhanced ChEMBL API configuration for clinical data
        self.chembl_api_base = config.get('chembl_api_base', 'https://www.ebi.ac.uk/chembl/api/data')
        self.api_rate_limit = config.get('api_rate_limit', 0.2)  # 5 requests per second
        self.include_clinical_phases = config.get('include_clinical_phases', True)
        self.include_mechanisms = config.get('include_mechanisms', True)
        
        # Create directories
        self.extracted_dir.mkdir(exist_ok=True)
        self.processed_dir.mkdir(exist_ok=True)
        
        # Schema version tracking
        self.required_schema_version = "0.1.5"  # Minimum schema version required

    def download_chembl_data(self) -> Tuple[Path, Path]:
        """Download ChEMBL database dump and uniprot mapping with caching.
        
        Returns:
            Tuple of paths to the downloaded files (chembl_dump, uniprot_mapping)
            
        Raises:
            DownloadError: If download fails
        """
        try:
            # Check if we need to download the files
            chembl_dump = self.chembl_dir / f"chembl_{CHEMBL_VERSION}_postgresql.tar.gz"
            uniprot_mapping = self.chembl_dir / "chembl_uniprot_mapping.txt"
            
            # Download database dump if needed
            if not chembl_dump.exists() or self.force_download:
                self.logger.info(f"Downloading ChEMBL database dump from {self.chembl_db_url}")
                chembl_dump = self.download_file(
                    url=self.chembl_db_url,
                    file_path=chembl_dump
                )
            else:
                self.logger.info(f"Using cached ChEMBL database dump at {chembl_dump}")
            
            # Download uniprot mapping if needed
            if not uniprot_mapping.exists() or self.force_download:
                self.logger.info(f"Downloading ChEMBL-UniProt mapping from {self.chembl_mapping_url}")
                uniprot_mapping = self.download_file(
                    url=self.chembl_mapping_url,
                    file_path=uniprot_mapping
                )
            else:
                self.logger.info(f"Using cached ChEMBL-UniProt mapping at {uniprot_mapping}")
                
            return chembl_dump, uniprot_mapping
        
        except Exception as e:
            raise DownloadError(f"Failed to download ChEMBL data: {e}")

    def _create_temp_database(self, db_name: str) -> bool:
        """Create a temporary PostgreSQL database for ChEMBL data extraction.

        Args:
            db_name: Name of the temporary database to create

        Returns:
            True if successful, False otherwise
        """
        import subprocess

        try:
            # Use postgres connection to create new database
            host = os.environ.get('MB_POSTGRES_HOST', 'localhost')
            port = os.environ.get('MB_POSTGRES_PORT', '5432')
            user = os.environ.get('MB_POSTGRES_USER', 'postgres')
            password = os.environ.get('MB_POSTGRES_PASSWORD', '')

            # Set environment for subprocess
            env = os.environ.copy()
            env['PGPASSWORD'] = password

            # Drop database if it exists (cleanup from previous runs)
            drop_cmd = [
                'psql',
                '-h', host,
                '-p', port,
                '-U', user,
                '-d', 'postgres',
                '-c', f'DROP DATABASE IF EXISTS {db_name}'
            ]

            self.logger.info(f"Dropping existing temporary database {db_name} if present")
            subprocess.run(drop_cmd, env=env, check=False, capture_output=True)

            # Create new database
            create_cmd = [
                'psql',
                '-h', host,
                '-p', port,
                '-U', user,
                '-d', 'postgres',
                '-c', f'CREATE DATABASE {db_name}'
            ]

            self.logger.info(f"Creating temporary database {db_name}")
            result = subprocess.run(create_cmd, env=env, check=True, capture_output=True, text=True)

            self.logger.info(f"Temporary database {db_name} created successfully")
            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to create temporary database: {e.stderr}")
            return False
        except Exception as e:
            self.logger.error(f"Failed to create temporary database: {e}")
            return False

    def _restore_dump_to_temp_db(self, dump_file: Path, temp_db_name: str) -> bool:
        """Restore ChEMBL .dmp file to temporary database using pg_restore.

        Args:
            dump_file: Path to the .dmp file extracted from the archive
            temp_db_name: Name of the temporary database

        Returns:
            True if successful, False otherwise
        """
        import subprocess

        try:
            host = os.environ.get('MB_POSTGRES_HOST', 'localhost')
            port = os.environ.get('MB_POSTGRES_PORT', '5432')
            user = os.environ.get('MB_POSTGRES_USER', 'postgres')
            password = os.environ.get('MB_POSTGRES_PASSWORD', '')

            # Set environment for subprocess
            env = os.environ.copy()
            env['PGPASSWORD'] = password

            # Use pg_restore with custom format
            restore_cmd = [
                'pg_restore',
                '-h', host,
                '-p', port,
                '-U', user,
                '-d', temp_db_name,
                '--no-owner',
                '--no-privileges',
                '--clean',
                '--if-exists',
                '--verbose',
                str(dump_file)
            ]

            self.logger.info(f"Restoring ChEMBL dump {dump_file} to {temp_db_name} (this may take several minutes)")

            # Run pg_restore with progress indication
            result = subprocess.run(
                restore_cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )

            # pg_restore may return non-zero even on success due to warnings
            # Check stderr for actual errors
            if result.returncode != 0:
                stderr_lower = result.stderr.lower()
                # Only fail on actual errors, not warnings
                if 'error:' in stderr_lower or 'fatal:' in stderr_lower:
                    self.logger.error(f"pg_restore failed with errors: {result.stderr[:500]}")
                    return False
                else:
                    self.logger.warning(f"pg_restore completed with warnings: {result.stderr[:200]}")

            self.logger.info(f"ChEMBL dump restored successfully to {temp_db_name}")
            return True

        except subprocess.TimeoutExpired:
            self.logger.error(f"pg_restore timed out after 1 hour")
            return False
        except subprocess.CalledProcessError as e:
            self.logger.error(f"pg_restore failed: {e.stderr}")
            return False
        except Exception as e:
            self.logger.error(f"Failed to restore dump: {e}")
            return False

    def _query_temp_database(self, temp_db_name: str, query: str, params: Optional[tuple] = None) -> Optional[pd.DataFrame]:
        """Query the temporary ChEMBL database and return results as DataFrame.

        Args:
            temp_db_name: Name of the temporary database
            query: SQL query to execute
            params: Optional query parameters

        Returns:
            DataFrame with query results, or None if query fails
        """
        try:
            host = os.environ.get('MB_POSTGRES_HOST', 'localhost')
            port = os.environ.get('MB_POSTGRES_PORT', '5432')
            user = os.environ.get('MB_POSTGRES_USER', 'postgres')
            password = os.environ.get('MB_POSTGRES_PASSWORD', '')

            # Create connection to temporary database
            conn_str = f"postgresql://{user}:{password}@{host}:{port}/{temp_db_name}"

            # Use pandas to execute query and return DataFrame
            df = pd.read_sql_query(query, conn_str, params=params)

            return df

        except Exception as e:
            self.logger.error(f"Failed to query temporary database: {e}")
            return None

    def _drop_temp_database(self, db_name: str) -> bool:
        """Drop the temporary PostgreSQL database.

        Args:
            db_name: Name of the temporary database to drop

        Returns:
            True if successful, False otherwise
        """
        import subprocess

        try:
            host = os.environ.get('MB_POSTGRES_HOST', 'localhost')
            port = os.environ.get('MB_POSTGRES_PORT', '5432')
            user = os.environ.get('MB_POSTGRES_USER', 'postgres')
            password = os.environ.get('MB_POSTGRES_PASSWORD', '')

            # Set environment for subprocess
            env = os.environ.copy()
            env['PGPASSWORD'] = password

            # Terminate connections to the database first
            terminate_cmd = [
                'psql',
                '-h', host,
                '-p', port,
                '-U', user,
                '-d', 'postgres',
                '-c', f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db_name}'"
            ]

            subprocess.run(terminate_cmd, env=env, check=False, capture_output=True)

            # Drop database
            drop_cmd = [
                'psql',
                '-h', host,
                '-p', port,
                '-U', user,
                '-d', 'postgres',
                '-c', f'DROP DATABASE IF EXISTS {db_name}'
            ]

            self.logger.info(f"Dropping temporary database {db_name}")
            subprocess.run(drop_cmd, env=env, check=True, capture_output=True)

            self.logger.info(f"Temporary database {db_name} dropped successfully")
            return True

        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to drop temporary database: {e.stderr}")
            return False
        except Exception as e:
            self.logger.warning(f"Failed to drop temporary database: {e}")
            return False

    def extract_chembl_dump(self, dump_file: Path) -> Path:
        """Extract the necessary tables from the ChEMBL database dump using pg_restore.

        ChEMBL v35 changed from SQL files to PostgreSQL custom dump format (.dmp).
        This method creates a temporary database, restores the dump, queries the tables,
        and saves the results as CSV files for further processing.

        Args:
            dump_file: Path to the downloaded ChEMBL database dump (tar.gz containing .dmp)

        Returns:
            Path to the directory containing extracted table data (CSV files)

        Raises:
            ProcessingError: If extraction fails
        """
        try:
            # Check if extraction has already been done
            extraction_marker = self.extracted_dir / ".extraction_complete"
            if extraction_marker.exists() and not self.force_download:
                self.logger.info("Using previously extracted ChEMBL data.")
                return self.extracted_dir

            # Clear previous extraction if force_download is True
            if self.force_download and self.extracted_dir.exists():
                self.logger.info(f"Clearing previous extractions at {self.extracted_dir}")
                for file in self.extracted_dir.glob("*.csv"):
                    file.unlink()
                for file in self.extracted_dir.glob("*.parquet"):
                    file.unlink()

            # Extract the tar.gz file to find the .dmp file
            self.logger.info(f"Extracting ChEMBL database dump from {dump_file}")

            # Tables of interest for drug data extraction
            tables_of_interest = {
                "molecule_dictionary": ["molregno", "chembl_id", "pref_name", "max_phase", "molecule_type", "therapeutic_flag"],
                "compound_structures": ["molregno", "canonical_smiles", "standard_inchi", "standard_inchi_key"],
                "compound_properties": ["molregno", "mw_freebase", "alogp", "hba", "hbd", "psa", "rtb", "ro3_pass", "num_ro5_violations"],
                "target_dictionary": ["tid", "chembl_id", "pref_name", "target_type", "organism"],
                "target_components": ["tid", "component_id"],
                "component_sequences": ["component_id", "accession", "component_type", "description", "organism"],
                "drug_mechanism": ["mec_id", "molregno", "mechanism_of_action", "action_type", "tid"],
                "drug_indication": ["drugind_id", "molregno", "efo_id", "mesh_id", "max_phase_for_ind"],
                "activities": ["activity_id", "molregno", "toid", "standard_type", "standard_value", "standard_units"],
                "docs": ["doc_id", "pubmed_id", "doi", "title", "year", "journal"],
                "molecule_synonyms": ["molregno", "synonyms"],
                "atc_classification": ["level1", "level2", "level3", "level4", "level5"]
            }

            # Create a temporary directory for extraction
            with tempfile.TemporaryDirectory() as temp_dir:
                # Extract the main archive first
                self.logger.info(f"Extracting main archive to {temp_dir}")
                try:
                    shutil.unpack_archive(dump_file, temp_dir)
                except Exception as e:
                    raise ProcessingError(f"Failed to extract ChEMBL archive: {e}")

                # Find the .dmp file in the extracted archive
                dmp_files = list(Path(temp_dir).glob("**/*.dmp"))

                if not dmp_files:
                    raise ProcessingError("No .dmp file found in ChEMBL archive. Expected PostgreSQL custom format dump.")

                dmp_file = dmp_files[0]
                self.logger.info(f"Found ChEMBL dump file: {dmp_file}")

                # Create temporary database name
                temp_db_name = f"chembl_temp_{CHEMBL_VERSION}_{int(datetime.now().timestamp())}"

                try:
                    # Create temporary database
                    if not self._create_temp_database(temp_db_name):
                        raise ProcessingError("Failed to create temporary database for ChEMBL extraction")

                    # Restore dump to temporary database
                    if not self._restore_dump_to_temp_db(dmp_file, temp_db_name):
                        raise ProcessingError("Failed to restore ChEMBL dump to temporary database")

                    # Create target directory if it doesn't exist
                    self.extracted_dir.mkdir(exist_ok=True, parents=True)

                    # Extract each table from temporary database
                    self.logger.info(f"Extracting {len(tables_of_interest)} tables from temporary database")

                    for table_name, columns in tables_of_interest.items():
                        try:
                            # Build query to extract table data
                            column_list = ", ".join(columns) if columns else "*"
                            query = f"SELECT {column_list} FROM {table_name}"

                            # Query and save as CSV
                            df = self._query_temp_database(temp_db_name, query)

                            if df is not None and not df.empty:
                                output_file = self.extracted_dir / f"{table_name}.csv"
                                df.to_csv(output_file, index=False)
                                self.logger.info(f"Extracted {table_name}: {len(df)} rows → {output_file}")
                            else:
                                self.logger.warning(f"Table {table_name} is empty or query failed")

                        except Exception as e:
                            self.logger.warning(f"Failed to extract {table_name}: {e}")
                            continue

                finally:
                    # Clean up temporary database
                    self._drop_temp_database(temp_db_name)

            # Create a marker file indicating extraction is complete
            with open(extraction_marker, 'w') as f:
                f.write(f"Extraction completed at {datetime.now().isoformat()}\n")
                f.write(f"ChEMBL version: {CHEMBL_VERSION}\n")
                f.write(f"Extraction method: pg_restore to temporary database\n")

            self.logger.info(f"ChEMBL data extraction completed successfully")
            return self.extracted_dir

        except Exception as e:
            raise ProcessingError(f"Failed to extract ChEMBL dump: {e}")

    def process_uniprot_mapping(self, mapping_file: Path) -> Dict[str, Set[str]]:
        """Process ChEMBL-UniProt mapping file to create lookup dictionaries.
        
        Args:
            mapping_file: Path to the ChEMBL-UniProt mapping file
            
        Returns:
            Dictionary mapping UniProt IDs to ChEMBL target IDs
            
        Raises:
            ProcessingError: If processing fails
        """
        try:
            # Check if processed mapping exists
            mapping_cache = self.processed_dir / "uniprot_mapping.json"
            
            if mapping_cache.exists() and not self.force_download:
                self.logger.info(f"Loading cached UniProt mapping from {mapping_cache}")
                with open(mapping_cache, 'r') as f:
                    # Convert back from JSON format (sets are stored as lists)
                    mapping_data = json.load(f)
                    uniprot_to_chembl = {k: set(v) for k, v in mapping_data.items()}
                return uniprot_to_chembl
            
            self.logger.info(f"Processing ChEMBL-UniProt mapping from {mapping_file}")
            
            # Process the mapping file
            uniprot_to_chembl: Dict[str, Set[str]] = {}
            
            # Read mapping file and count lines first for progress bar
            with open(mapping_file, 'r') as f:
                total_lines = sum(1 for _ in f)
            
            # Create a progress bar using our centralized system
            progress = get_progress_bar(
                total=total_lines,
                desc="Processing UniProt mapping",
                module_name="chembl_drugs",
                unit="entries"
            )
            
            # Process the file
            with open(mapping_file, 'r') as f:
                csv_reader = csv.reader(f, delimiter='\t')
                next(csv_reader)  # Skip header
                progress.update(1)  # Account for header
                
                for row in csv_reader:
                    if len(row) >= 2:
                        uniprot_id = row[0].strip()
                        chembl_id = row[1].strip()
                        
                        if uniprot_id and chembl_id:
                            if uniprot_id not in uniprot_to_chembl:
                                uniprot_to_chembl[uniprot_id] = set()
                            uniprot_to_chembl[uniprot_id].add(chembl_id)
                    progress.update(1)
            
            # Save the processed mapping for future use
            with open(mapping_cache, 'w') as f:
                # Convert sets to lists for JSON serialization
                json.dump({k: list(v) for k, v in uniprot_to_chembl.items()}, f)
            
            self.logger.info(f"Processed {len(uniprot_to_chembl)} UniProt IDs mapped to ChEMBL targets")
            return uniprot_to_chembl
            
        except Exception as e:
            raise ProcessingError(f"Failed to process UniProt mapping: {e}")

    def create_optimized_tables(self) -> None:
        """Create optimized tables for ChEMBL data processing.
        
        Raises:
            DatabaseError: If table creation fails
        """
        if not self.ensure_connection() or not self.db_manager.cursor:
            raise DatabaseError("Database connection failed")
            
        try:
            schema_name = self.chembl_schema
            
            # Check if schema exists, drop if needed
            exists_result = self._safe_execute(f"SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname = '{schema_name}')")
            schema_exists = exists_result[0] if exists_result else False
            
            if schema_exists and self.force_download:
                self.logger.info(f"Dropping existing ChEMBL schema '{schema_name}'")
                self._safe_execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE")
                self._safe_commit()
                schema_exists = False
            
            # Create schema if it doesn't exist
            if not schema_exists:
                self.logger.info(f"Creating ChEMBL schema '{schema_name}'")
                self.db_manager.cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")
                
                # Create optimized tables
                self.logger.info("Creating optimized ChEMBL tables")
                
                # Table for basic drug information
                self.db_manager.cursor.execute(f"""
                CREATE TABLE {schema_name}.drugs (
                    chembl_id TEXT PRIMARY KEY,
                    name TEXT,
                    synonyms TEXT[],
                    max_phase FLOAT,
                    drug_type TEXT,
                    molecular_weight FLOAT,
                    atc_codes TEXT[],
                    structure_info JSONB,
                    properties JSONB,
                    external_links JSONB
                )
                """)
                
                # Table for drug-target mapping
                self.db_manager.cursor.execute(f"""
                CREATE TABLE {schema_name}.drug_targets (
                    id SERIAL PRIMARY KEY,
                    chembl_id TEXT,
                    target_id TEXT,
                    target_type TEXT,
                    target_name TEXT,
                    gene_symbol TEXT,
                    uniprot_id TEXT,
                    action_type TEXT,
                    mechanism_of_action TEXT,
                    binding_site TEXT,
                    confidence_score INTEGER,
                    UNIQUE (chembl_id, target_id, gene_symbol, uniprot_id)
                )
                """)
                
                # Table for drug indications
                self.db_manager.cursor.execute(f"""
                CREATE TABLE {schema_name}.drug_indications (
                    id SERIAL PRIMARY KEY,
                    chembl_id TEXT,
                    indication TEXT,
                    max_phase_for_ind FLOAT,
                    mesh_id TEXT,
                    efo_id TEXT
                )
                """)
                
                # Table for publication references
                self.db_manager.cursor.execute(f"""
                CREATE TABLE {schema_name}.drug_publications (
                    id SERIAL PRIMARY KEY,
                    chembl_id TEXT,
                    doc_id TEXT,
                    pubmed_id TEXT,
                    doi TEXT,
                    title TEXT,
                    abstract TEXT,
                    year INTEGER,
                    journal TEXT,
                    authors TEXT,
                    volume TEXT,
                    issue TEXT,
                    first_page TEXT,
                    last_page TEXT,
                    patent_id TEXT,
                    journal_full_title TEXT,
                    UNIQUE (doc_id)
                )
                """)
                
                # Create indexes for faster lookups
                self.db_manager.cursor.execute(f"""
                CREATE INDEX idx_{schema_name}_drug_targets_gene ON {schema_name}.drug_targets (gene_symbol);
                CREATE INDEX idx_{schema_name}_drug_targets_uniprot ON {schema_name}.drug_targets (uniprot_id);
                CREATE INDEX idx_{schema_name}_drug_publications_chembl ON {schema_name}.drug_publications (chembl_id);
                """)
                
                self._safe_commit()
                self.logger.info("ChEMBL optimized tables created successfully")
            else:
                self.logger.info(f"Using existing ChEMBL schema '{schema_name}'")
                
        except Exception as e:
            if self.db_manager and self.db_manager.conn and not getattr(self.db_manager.conn, 'closed', True):
                self.db_manager.conn.rollback()
            raise DatabaseError(f"Failed to create ChEMBL tables: {e}")

    def _process_molecule_dictionary(self, extracted_dir: Path) -> None:
        """Process molecule_dictionary table from extracted CSV files.

        Reads molecule_dictionary.csv, compound_structures.csv, compound_properties.csv
        and merges them to create comprehensive drug records.

        Args:
            extracted_dir: Path to directory containing extracted CSV files

        Raises:
            ProcessingError: If processing fails
        """
        schema_name = self.chembl_schema
        self.logger.info("Processing ChEMBL molecule_dictionary from CSV files")

        try:
            if not self.ensure_connection() or not self.db_manager.cursor:
                raise DatabaseError("Database connection failed")

            # Count existing drugs to check if we need to process
            existing_count = self._safe_fetch_count("drugs", schema_name)

            if existing_count > 0 and not self.force_download:
                self.logger.info(f"Found {existing_count} existing drugs. Use force_download=True to reimport.")
                return

            # Read CSV files
            molecule_dict_path = extracted_dir / "molecule_dictionary.csv"
            if not molecule_dict_path.exists():
                self.logger.warning("molecule_dictionary.csv not found, skipping drug processing")
                return

            self.logger.info(f"Reading molecule_dictionary from {molecule_dict_path}")
            df_molecules = pd.read_csv(molecule_dict_path)

            # Filter by max_phase if configured
            if self.max_phase_cutoff > 0:
                initial_count = len(df_molecules)
                df_molecules = df_molecules[df_molecules['max_phase'] >= self.max_phase_cutoff]
                self.logger.info(f"Filtered to {len(df_molecules)} molecules with max_phase >= {self.max_phase_cutoff} (from {initial_count})")

            # Read and merge compound structures
            structures_path = extracted_dir / "compound_structures.csv"
            if structures_path.exists():
                self.logger.info("Merging compound structures")
                df_structures = pd.read_csv(structures_path)
                df_molecules = df_molecules.merge(df_structures, on='molregno', how='left')

            # Read and merge compound properties
            properties_path = extracted_dir / "compound_properties.csv"
            if properties_path.exists():
                self.logger.info("Merging compound properties")
                df_properties = pd.read_csv(properties_path)
                df_molecules = df_molecules.merge(df_properties, on='molregno', how='left')

            # Read molecule synonyms for drug names
            synonyms_path = extracted_dir / "molecule_synonyms.csv"
            synonyms_dict = {}
            if synonyms_path.exists():
                self.logger.info("Processing molecule synonyms")
                df_synonyms = pd.read_csv(synonyms_path)
                # Group synonyms by molregno
                for molregno, group in df_synonyms.groupby('molregno'):
                    synonyms_dict[molregno] = group['synonyms'].dropna().tolist()

            self.logger.info(f"Processing {len(df_molecules)} molecules for insertion")

            # Process molecules in batches
            batch_size = 1000
            inserted_count = 0

            progress = get_progress_bar(
                total=len(df_molecules),
                desc="Inserting molecules",
                module_name="chembl_drugs",
                unit="molecules"
            )

            try:
                for start_idx in range(0, len(df_molecules), batch_size):
                    batch = df_molecules.iloc[start_idx:start_idx + batch_size]

                    # Prepare batch data
                    batch_data = []
                    for _, row in batch.iterrows():
                        # Build structure_info JSON
                        structure_info = {}
                        if 'canonical_smiles' in row and pd.notna(row['canonical_smiles']):
                            structure_info['smiles'] = str(row['canonical_smiles'])
                        if 'standard_inchi' in row and pd.notna(row['standard_inchi']):
                            structure_info['inchi'] = str(row['standard_inchi'])
                        if 'standard_inchi_key' in row and pd.notna(row['standard_inchi_key']):
                            structure_info['inchi_key'] = str(row['standard_inchi_key'])

                        # Build properties JSON
                        properties = {}
                        property_cols = ['mw_freebase', 'alogp', 'hba', 'hbd', 'psa', 'rtb', 'ro3_pass', 'num_ro5_violations']
                        for col in property_cols:
                            if col in row and pd.notna(row[col]):
                                properties[col] = float(row[col]) if isinstance(row[col], (int, float)) else str(row[col])

                        # Get synonyms
                        molregno = row['molregno']
                        synonyms = synonyms_dict.get(molregno, [])
                        if pd.notna(row.get('pref_name')):
                            synonyms.insert(0, str(row['pref_name']))

                        batch_data.append({
                            'chembl_id': str(row['chembl_id']) if pd.notna(row['chembl_id']) else None,
                            'name': str(row['pref_name']) if pd.notna(row.get('pref_name')) else None,
                            'synonyms': synonyms[:10],  # Limit to first 10 synonyms
                            'max_phase': float(row['max_phase']) if pd.notna(row.get('max_phase')) else None,
                            'drug_type': str(row['molecule_type']) if pd.notna(row.get('molecule_type')) else None,
                            'molecular_weight': float(row['mw_freebase']) if 'mw_freebase' in row and pd.notna(row['mw_freebase']) else None,
                            'atc_codes': [],  # Will be populated later if needed
                            'structure_info': json.dumps(structure_info) if structure_info else None,
                            'properties': json.dumps(properties) if properties else None,
                            'external_links': None  # Can be populated from other sources later
                        })

                    # Insert batch
                    if batch_data:
                        self.db_manager.cursor.executemany(f"""
                            INSERT INTO {schema_name}.drugs (
                                chembl_id, name, synonyms, max_phase, drug_type, molecular_weight, atc_codes,
                                structure_info, properties, external_links
                            ) VALUES (
                                %(chembl_id)s, %(name)s, %(synonyms)s, %(max_phase)s, %(drug_type)s, %(molecular_weight)s, %(atc_codes)s,
                                %(structure_info)s::jsonb, %(properties)s::jsonb, %(external_links)s::jsonb
                            )
                            ON CONFLICT (chembl_id) DO NOTHING
                        """, batch_data)

                        inserted_count += len(batch_data)

                    progress.update(len(batch))

                self._safe_commit()
                self.logger.info(f"Processed molecule_dictionary: inserted {inserted_count} drugs")

            finally:
                progress.close()

        except Exception as e:
            if self.db_manager and self.db_manager.conn and not getattr(self.db_manager.conn, 'closed', True):
                self.db_manager.conn.rollback()
            raise ProcessingError(f"Failed to process molecule_dictionary: {e}")

    def _process_drug_targets(self, extracted_dir: Path) -> None:
        """Process drug_targets table from extracted CSV files.

        Reads target_dictionary.csv, target_components.csv, component_sequences.csv,
        and drug_mechanism.csv to build comprehensive drug-target relationships.

        Args:
            extracted_dir: Path to directory containing extracted CSV files

        Raises:
            ProcessingError: If processing fails
        """
        schema_name = self.chembl_schema
        self.logger.info("Processing ChEMBL drug_targets from CSV files")

        try:
            if not self.ensure_connection() or not self.db_manager.cursor:
                raise DatabaseError("Database connection failed")

            # Count existing targets to check if we need to process
            existing_count = self._safe_fetch_count("drug_targets", schema_name)

            if existing_count > 0 and not self.force_download:
                self.logger.info(f"Found {existing_count} existing targets. Use force_download=True to reimport.")
                return

            # Read required CSV files
            target_dict_path = extracted_dir / "target_dictionary.csv"
            if not target_dict_path.exists():
                self.logger.warning("target_dictionary.csv not found, skipping target processing")
                return

            self.logger.info(f"Reading target_dictionary from {target_dict_path}")
            df_targets = pd.read_csv(target_dict_path)

            # Filter by target type if configured
            if TARGET_TYPES_OF_INTEREST:
                initial_count = len(df_targets)
                df_targets = df_targets[df_targets['target_type'].isin(TARGET_TYPES_OF_INTEREST)]
                self.logger.info(f"Filtered to {len(df_targets)} targets of interest (from {initial_count})")

            # Read target components to get component IDs
            components_path = extracted_dir / "target_components.csv"
            if components_path.exists():
                self.logger.info("Merging target_components")
                df_components = pd.read_csv(components_path)
                df_targets = df_targets.merge(df_components, on='tid', how='left')

            # Read component sequences to get gene symbols and UniProt IDs
            sequences_path = extracted_dir / "component_sequences.csv"
            if sequences_path.exists():
                self.logger.info("Merging component_sequences for gene symbols")
                df_sequences = pd.read_csv(sequences_path)
                df_targets = df_targets.merge(df_sequences, on='component_id', how='left')

            # Read drug mechanisms to link targets to molecules
            mechanisms_path = extracted_dir / "drug_mechanism.csv"
            if not mechanisms_path.exists():
                self.logger.warning("drug_mechanism.csv not found, creating targets without drug links")
                df_mechanisms = pd.DataFrame()
            else:
                self.logger.info("Reading drug_mechanism")
                df_mechanisms = pd.read_csv(mechanisms_path)
                # Merge with targets
                df_targets = df_targets.merge(
                    df_mechanisms[['molregno', 'tid', 'mechanism_of_action', 'action_type']],
                    on='tid',
                    how='left'
                )

            # Get molecule ChEMBL IDs from the drugs table we already populated
            self.logger.info("Mapping molregno to chembl_id from drugs table")
            self.db_manager.cursor.execute(f"""
                SELECT molregno, chembl_id FROM (
                    SELECT
                        CAST(SUBSTRING(chembl_id FROM '[0-9]+') AS INTEGER) as molregno,
                        chembl_id
                    FROM {schema_name}.drugs
                    WHERE chembl_id ~ '^CHEMBL[0-9]+'
                ) subq
            """)
            molregno_to_chembl = {row[0]: row[1] for row in self.db_manager.cursor.fetchall()}

            self.logger.info(f"Processing {len(df_targets)} target records for insertion")

            # Process targets in batches
            batch_size = 1000
            inserted_count = 0

            progress = get_progress_bar(
                total=len(df_targets),
                desc="Inserting drug targets",
                module_name="chembl_drugs",
                unit="targets"
            )

            try:
                for start_idx in range(0, len(df_targets), batch_size):
                    batch = df_targets.iloc[start_idx:start_idx + batch_size]

                    # Prepare batch data
                    batch_data = []
                    for _, row in batch.iterrows():
                        # Get chembl_id from molregno
                        chembl_id = None
                        if 'molregno' in row and pd.notna(row['molregno']):
                            chembl_id = molregno_to_chembl.get(int(row['molregno']))

                        # Extract gene symbol (try description field patterns)
                        gene_symbol = None
                        if 'description' in row and pd.notna(row['description']):
                            desc = str(row['description'])
                            # Try to extract gene symbol from descriptions like "Gene symbol: EGFR"
                            import re
                            match = re.search(r'\b([A-Z][A-Z0-9]{1,10})\b', desc)
                            if match:
                                gene_symbol = match.group(1)

                        batch_data.append({
                            'chembl_id': chembl_id,
                            'target_id': str(row['chembl_id']) if 'chembl_id' in row and pd.notna(row['chembl_id']) else None,
                            'target_type': str(row['target_type']) if pd.notna(row.get('target_type')) else None,
                            'target_name': str(row['pref_name']) if pd.notna(row.get('pref_name')) else None,
                            'gene_symbol': gene_symbol,
                            'uniprot_id': str(row['accession']) if 'accession' in row and pd.notna(row['accession']) else None,
                            'action_type': str(row['action_type']) if 'action_type' in row and pd.notna(row['action_type']) else None,
                            'mechanism_of_action': str(row['mechanism_of_action']) if 'mechanism_of_action' in row and pd.notna(row['mechanism_of_action']) else None,
                            'binding_site': None,  # Not typically in ChEMBL exports
                            'confidence_score': None  # Can be calculated/assigned based on evidence
                        })

                    # Insert batch (filter out entries without chembl_id)
                    batch_data_valid = [d for d in batch_data if d['chembl_id'] is not None]

                    if batch_data_valid:
                        self.db_manager.cursor.executemany(f"""
                            INSERT INTO {schema_name}.drug_targets (
                                chembl_id, target_id, target_type, target_name, gene_symbol, uniprot_id,
                                action_type, mechanism_of_action, binding_site, confidence_score
                            ) VALUES (
                                %(chembl_id)s, %(target_id)s, %(target_type)s, %(target_name)s, %(gene_symbol)s, %(uniprot_id)s,
                                %(action_type)s, %(mechanism_of_action)s, %(binding_site)s, %(confidence_score)s
                            )
                            ON CONFLICT DO NOTHING
                        """, batch_data_valid)

                        inserted_count += len(batch_data_valid)

                    progress.update(len(batch))

                self._safe_commit()
                self.logger.info(f"Processed drug_targets: inserted {inserted_count} target relationships")

            finally:
                progress.close()

        except Exception as e:
            if self.db_manager and self.db_manager.conn and not getattr(self.db_manager.conn, 'closed', True):
                self.db_manager.conn.rollback()
            raise ProcessingError(f"Failed to process drug_targets: {e}")

    def _process_drug_indications(self, extracted_dir: Path) -> None:
        """Process drug_indications table from extracted CSV files.

        Reads drug_indication.csv and maps to drug ChEMBL IDs.

        Args:
            extracted_dir: Path to directory containing extracted CSV files

        Raises:
            ProcessingError: If processing fails
        """
        schema_name = self.chembl_schema
        self.logger.info("Processing ChEMBL drug_indications from CSV files")

        try:
            if not self.ensure_connection() or not self.db_manager.cursor:
                raise DatabaseError("Database connection failed")

            # Count existing indications to check if we need to process
            existing_count = self._safe_fetch_count("drug_indications", schema_name)

            if existing_count > 0 and not self.force_download:
                self.logger.info(f"Found {existing_count} existing indications. Use force_download=True to reimport.")
                return

            # Read drug_indication CSV file
            indication_path = extracted_dir / "drug_indication.csv"
            if not indication_path.exists():
                self.logger.warning("drug_indication.csv not found, skipping indication processing")
                return

            self.logger.info(f"Reading drug_indication from {indication_path}")
            df_indications = pd.read_csv(indication_path)

            # Filter by max_phase_for_ind if configured
            if self.max_phase_cutoff > 0:
                initial_count = len(df_indications)
                df_indications = df_indications[df_indications['max_phase_for_ind'] >= self.max_phase_cutoff]
                self.logger.info(f"Filtered to {len(df_indications)} indications with max_phase >= {self.max_phase_cutoff} (from {initial_count})")

            # Get molecule ChEMBL IDs from the drugs table
            self.logger.info("Mapping molregno to chembl_id from drugs table")
            self.db_manager.cursor.execute(f"""
                SELECT molregno, chembl_id FROM (
                    SELECT
                        CAST(SUBSTRING(chembl_id FROM '[0-9]+') AS INTEGER) as molregno,
                        chembl_id
                    FROM {schema_name}.drugs
                    WHERE chembl_id ~ '^CHEMBL[0-9]+'
                ) subq
            """)
            molregno_to_chembl = {row[0]: row[1] for row in self.db_manager.cursor.fetchall()}

            self.logger.info(f"Processing {len(df_indications)} indication records for insertion")

            # Process indications in batches
            batch_size = 1000
            inserted_count = 0

            progress = get_progress_bar(
                total=len(df_indications),
                desc="Inserting drug indications",
                module_name="chembl_drugs",
                unit="indications"
            )

            try:
                for start_idx in range(0, len(df_indications), batch_size):
                    batch = df_indications.iloc[start_idx:start_idx + batch_size]

                    # Prepare batch data
                    batch_data = []
                    for _, row in batch.iterrows():
                        # Get chembl_id from molregno
                        chembl_id = None
                        if 'molregno' in row and pd.notna(row['molregno']):
                            chembl_id = molregno_to_chembl.get(int(row['molregno']))

                        if chembl_id:  # Only include if we have a valid chembl_id
                            batch_data.append({
                                'chembl_id': chembl_id,
                                'indication': str(row['indication']) if 'indication' in row and pd.notna(row['indication']) else None,
                                'max_phase_for_ind': float(row['max_phase_for_ind']) if pd.notna(row.get('max_phase_for_ind')) else None,
                                'mesh_id': str(row['mesh_id']) if 'mesh_id' in row and pd.notna(row['mesh_id']) else None,
                                'efo_id': str(row['efo_id']) if 'efo_id' in row and pd.notna(row['efo_id']) else None
                            })

                    # Insert batch
                    if batch_data:
                        self.db_manager.cursor.executemany(f"""
                            INSERT INTO {schema_name}.drug_indications (
                                chembl_id, indication, max_phase_for_ind, mesh_id, efo_id
                            ) VALUES (
                                %(chembl_id)s, %(indication)s, %(max_phase_for_ind)s, %(mesh_id)s, %(efo_id)s
                            )
                        """, batch_data)

                        inserted_count += len(batch_data)

                    progress.update(len(batch))

                self._safe_commit()
                self.logger.info(f"Processed drug_indications: inserted {inserted_count} indications")

            finally:
                progress.close()

        except Exception as e:
            if self.db_manager and self.db_manager.conn and not getattr(self.db_manager.conn, 'closed', True):
                self.db_manager.conn.rollback()
            raise ProcessingError(f"Failed to process drug_indications: {e}")

    def _process_drug_publications(self, extracted_dir: Path) -> None:
        """Process drug_publications table from extracted CSV files.

        Reads docs.csv and populates publication metadata.

        Args:
            extracted_dir: Path to directory containing extracted CSV files

        Raises:
            ProcessingError: If processing fails
        """
        schema_name = self.chembl_schema
        self.logger.info("Processing ChEMBL drug_publications from CSV files")

        try:
            if not self.ensure_connection() or not self.db_manager.cursor:
                raise DatabaseError("Database connection failed")

            # Count existing publications to check if we need to process
            existing_count = self._safe_fetch_count("drug_publications", schema_name)

            if existing_count > 0 and not self.force_download:
                self.logger.info(f"Found {existing_count} existing publications. Use force_download=True to reimport.")
                return

            # Read docs CSV file
            docs_path = extracted_dir / "docs.csv"
            if not docs_path.exists():
                self.logger.warning("docs.csv not found, skipping publication processing")
                return

            self.logger.info(f"Reading docs from {docs_path}")
            df_docs = pd.read_csv(docs_path)

            # Filter to publications with PubMed IDs or DOIs
            df_docs = df_docs[df_docs['pubmed_id'].notna() | df_docs['doi'].notna()]

            self.logger.info(f"Processing {len(df_docs)} publication records for insertion")

            # Process publications in batches
            batch_size = 1000
            inserted_count = 0

            progress = get_progress_bar(
                total=len(df_docs),
                desc="Inserting publications",
                module_name="chembl_drugs",
                unit="publications"
            )

            try:
                for start_idx in range(0, len(df_docs), batch_size):
                    batch = df_docs.iloc[start_idx:start_idx + batch_size]

                    # Prepare batch data
                    batch_data = []
                    for _, row in batch.iterrows():
                        batch_data.append({
                            'chembl_id': None,  # Will be populated when linking to drugs
                            'doc_id': str(row['doc_id']) if pd.notna(row.get('doc_id')) else None,
                            'pubmed_id': str(row['pubmed_id']) if pd.notna(row.get('pubmed_id')) else None,
                            'doi': str(row['doi']) if pd.notna(row.get('doi')) else None,
                            'title': str(row['title']) if pd.notna(row.get('title')) else None,
                            'abstract': None,  # Not typically in base docs table
                            'year': int(row['year']) if pd.notna(row.get('year')) else None,
                            'journal': str(row['journal']) if pd.notna(row.get('journal')) else None,
                            'authors': None,  # Not typically in base docs table
                            'volume': None,
                            'issue': None,
                            'first_page': None,
                            'last_page': None,
                            'patent_id': None,
                            'journal_full_title': None
                        })

                    # Insert batch
                    if batch_data:
                        self.db_manager.cursor.executemany(f"""
                            INSERT INTO {schema_name}.drug_publications (
                                chembl_id, doc_id, pubmed_id, doi, title, abstract, year, journal, authors,
                                volume, issue, first_page, last_page, journal_full_title, patent_id
                            ) VALUES (
                                %(chembl_id)s, %(doc_id)s, %(pubmed_id)s, %(doi)s, %(title)s, %(abstract)s,
                                %(year)s, %(journal)s, %(authors)s, %(volume)s, %(issue)s, %(first_page)s,
                                %(last_page)s, %(journal_full_title)s, %(patent_id)s
                            )
                            ON CONFLICT (doc_id) DO UPDATE SET
                                pubmed_id = EXCLUDED.pubmed_id,
                                doi = EXCLUDED.doi,
                                title = EXCLUDED.title,
                                year = EXCLUDED.year,
                                journal = EXCLUDED.journal
                        """, batch_data)

                        inserted_count += len(batch_data)

                    progress.update(len(batch))

                self._safe_commit()
                self.logger.info(f"Processed drug_publications: inserted {inserted_count} publications")

            finally:
                progress.close()

        except Exception as e:
            if self.db_manager and self.db_manager.conn and not getattr(self.db_manager.conn, 'closed', True):
                self.db_manager.conn.rollback()
            raise ProcessingError(f"Failed to process drug_publications: {e}")

    def import_chembl_to_tables(self, extracted_dir: Path) -> None:
        """Import extracted ChEMBL data into optimized tables.
        
        Args:
            extracted_dir: Path to the directory containing extracted SQL files
            
        Raises:
            DatabaseError: If import fails
        """
        if not self.ensure_connection() or not self.db_manager.cursor:
            raise DatabaseError("Database connection failed")
            
        try:
            schema_name = self.chembl_schema
            
            # Check if data is already imported
            if self.db_manager.cursor is None:
                raise DatabaseError("No database cursor available")
                
            # Fixed: Add null checks
            self.db_manager.cursor.execute(f"SELECT count(*) FROM {schema_name}.drugs")
            count = self.db_manager.cursor.fetchone()
            if count is not None and count[0] > 0 and not self.force_download:
                self.logger.info(f"ChEMBL data already imported ({count[0]} drugs). Use force_download=True to reimport.")
                return
            
            self.logger.info("Importing ChEMBL data into optimized tables")
            
            # Process molecule_dictionary data
            self._process_molecule_dictionary(extracted_dir)
            
            # Process drug targets
            self._process_drug_targets(extracted_dir)
            
            # Process drug indications
            self._process_drug_indications(extracted_dir)
            
            # Process drug publications
            self._process_drug_publications(extracted_dir)
            
            # Fixed: Add null check before commit
            if self.db_manager.conn is not None and not getattr(self.db_manager.conn, 'closed', True):
                self.db_manager.conn.commit()
                self.logger.info("ChEMBL data import completed successfully")
            
        except Exception as e:
            # Fixed: Add null check before rollback
            if self.db_manager.conn is not None and not getattr(self.db_manager.conn, 'closed', True):
                self.db_manager.conn.rollback()
            raise DatabaseError(f"Failed to import ChEMBL data: {e}")

    def _update_drug_batch(self, updates: List[Tuple[str, List[str], str, str]]) -> None:
        """Update a batch of drug data from ChEMBL.
        
        Args:
            updates: List of tuples with (gene_symbol, uniprot_ids, drug_data_json, drug_references_json)
            
        Raises:
            DatabaseError: If batch update fails
        """
        try:
            # Use the get_db_transaction context manager for proper transaction handling
            with self.get_db_transaction() as transaction:
                # Create temp table within this transaction
                transaction.cursor.execute("""
                    CREATE TEMP TABLE IF NOT EXISTS temp_chembl_data (
                        gene_symbol TEXT PRIMARY KEY,
                        uniprot_ids TEXT[],
                        drug_data JSONB,
                        drug_references JSONB
                    ) ON COMMIT DROP
                """)
                
                # Execute batch insert
                self.execute_batch(
                    """
                    INSERT INTO temp_chembl_data 
                    (gene_symbol, uniprot_ids, drug_data, drug_references)
                    VALUES (%s, %s, %s::jsonb, %s::jsonb)
                    ON CONFLICT (gene_symbol) DO UPDATE SET
                    drug_data = temp_chembl_data.drug_data || EXCLUDED.drug_data,
                    drug_references = temp_chembl_data.drug_references || EXCLUDED.drug_references
                    """,
                    updates
                )
                
                # Update the main table from the temp table
                transaction.cursor.execute("""
                    UPDATE cancer_transcript_base AS c
                    SET 
                        drugs = COALESCE(c.drugs, '{}'::jsonb) || t.drug_data,
                        source_references = jsonb_set(
                            COALESCE(c.source_references, '{
                                "go_terms": [],
                                "uniprot": [],
                                "drugs": [],
                                "pathways": []
                            }'::jsonb),
                            '{drugs}',
                            COALESCE(c.source_references->'drugs', '[]'::jsonb) || t.drug_references,
                            true
                        )
                    FROM temp_chembl_data t
                    WHERE c.gene_symbol = t.gene_symbol
                """)
        except Exception as e:
            self.logger.error(f"ChEMBL drug batch update failed: {e}")
            raise DatabaseError(f"Failed to update ChEMBL drug batch: {e}")

    def calculate_drug_scores(self) -> None:
        """Calculate synergy-based drug scores using pathways and GO terms.
        
        This reuses the scoring logic from the DrugProcessor but applies it to ChEMBL data.
        
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
            
            # Setup progress tracking
            progress = get_progress_bar(
                total=total_genes,
                desc="Calculating drug scores",
                module_name="chembl_drugs",
                unit="genes"
            )
            
            # Process in batches
            offset = 0
            
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
                        
                        # Combine scores for this batch
                        pathway_weight = float(self.config.get('drug_pathway_weight', 1.0))
                        go_weight = pathway_weight * 0.5  # GO terms weighted at 50% of pathway weight
                        
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
                            SET drug_scores = 
                                COALESCE(cb.drug_scores, '{}'::jsonb) || fs.drug_scores
                            FROM temp_final_scores fs
                            WHERE cb.gene_symbol = fs.gene_symbol
                        """)
                        
                        # Clear temporary tables for next batch
                        transaction.cursor.execute("""
                            TRUNCATE temp_pathway_scores, temp_go_scores, temp_final_scores
                        """)
                    
                    batch_size = len(rows)
                    offset += self.batch_size
                    
                    # Update progress
                    progress.update(batch_size)
                
                # Log final statistics
                self.logger.info(f"Drug score calculation completed.")
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
                    if self.db_manager.conn and not getattr(self.db_manager.conn, 'closed', True):
                        self.db_manager.conn.commit()
            except Exception as e:
                self.logger.warning(f"Failed to clean up temporary tables: {e}")

    def _verify_integration_results(self) -> None:
        """Verify ChEMBL integration results with database statistics."""
        if not self.ensure_connection():
            self.logger.warning("Cannot verify results - database connection unavailable")
            return
            
        try:
            # Validate cursor before using
            if not self.db_manager.cursor:
                self.logger.warning("Cannot verify results - no database cursor available")
                return
                
            # Detailed verification that includes reference counts
            self.db_manager.cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN drugs != '{}'::jsonb THEN 1 END) as with_drugs,
                    COUNT(CASE WHEN drug_scores != '{}'::jsonb THEN 1 END) as with_scores,
                    COUNT(CASE WHEN source_references->'drugs' IS NOT NULL 
                              AND source_references->'drugs' != '[]'::jsonb 
                         THEN 1 END) as with_refs,
                    SUM(CASE WHEN source_references->'drugs' IS NOT NULL 
                             THEN jsonb_array_length(source_references->'drugs')
                             ELSE 0 
                        END) as total_refs,
                    COUNT(CASE WHEN 
                            EXISTS (
                                SELECT 1 FROM jsonb_each(drugs) 
                                WHERE value->>'chembl_id' IS NOT NULL
                            )
                         THEN 1 END) as with_chembl_drugs
                FROM cancer_transcript_base
            """)
            
            stats = self.db_manager.cursor.fetchone()
            if stats:
                self.logger.info(
                    f"Pipeline completed:\n"
                    f"- Total records: {stats[0]:,}\n"
                    f"- Records with drugs: {stats[1]:,}\n"
                    f"- Records with drug scores: {stats[2]:,}\n"
                    f"- Records with drug references: {stats[3]:,}\n"
                    f"- Total drug references: {stats[4]:,}\n"
                    f"- Records with ChEMBL drugs: {stats[5]:,}"
                )
                
        except Exception as e:
            self.logger.warning(f"Failed to verify results: {e}")

    def _safe_execute(self, query: str, params: Any = None) -> Optional[Any]:
        """Safely execute a database query with proper null checks.
        
        Args:
            query: SQL query to execute
            params: Optional parameters for the query
            
        Returns:
            Query result or None if execution fails
        """
        if not self.ensure_connection() or not self.db_manager.cursor:
            self.logger.warning("Cannot execute query - database connection unavailable")
            return None
            
        try:
            if params:
                self.db_manager.cursor.execute(query, params)
            else:
                self.db_manager.cursor.execute(query)
                
            # For SELECT queries, fetch the result
            if query.strip().upper().startswith("SELECT"):
                return self.db_manager.cursor.fetchone()
            return True
        except Exception as e:
            self.logger.error(f"Query execution failed: {e}")
            return None

    def _safe_commit(self) -> bool:
        """Safely commit database changes with proper null checks.
        
        Returns:
            True if commit was successful, False otherwise
        """
        if not self.db_manager or not self.db_manager.conn:
            self.logger.warning("Cannot commit - database connection unavailable")
            return False
            
        try:
            if not self.db_manager.conn.closed:
                self.db_manager.conn.commit()
                return True
            else:
                self.logger.warning("Cannot commit - connection is closed")
                return False
        except Exception as e:
            self.logger.error(f"Database commit failed: {e}")
            return False

    def _safe_fetch_count(self, table_name: str, schema_name: Optional[str] = None) -> int:
        """Safely fetch count from a table with proper null checks.
        
        Args:
            table_name: Name of the table
            schema_name: Optional schema name
            
        Returns:
            Count of records in the table or 0 if query fails
        """
        if not self.ensure_connection() or not self.db_manager.cursor:
            self.logger.warning(f"Cannot fetch count from {table_name} - database connection unavailable")
            return 0
        
        table_ref = f"{schema_name}.{table_name}" if schema_name else table_name
        
        try:
            self.db_manager.cursor.execute(f"SELECT COUNT(*) FROM {table_ref}")
            result = self.db_manager.cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            self.logger.error(f"Failed to fetch count from {table_ref}: {e}")
            return 0

    def query_chembl_api(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Query ChEMBL API with rate limiting.
        
        Args:
            endpoint: API endpoint (e.g., 'target', 'molecule')
            params: Query parameters
            
        Returns:
            API response as dictionary
            
        Raises:
            DownloadError: If API request fails
        """
        import time
        
        url = f"{self.chembl_api_base}/{endpoint}"
        
        try:
            # Rate limiting
            time.sleep(self.api_rate_limit)
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            return response.json()
            
        except Exception as e:
            raise DownloadError(f"ChEMBL API request failed for {endpoint}: {e}")
    
    def get_clinical_phase_data(self, gene_symbol: str) -> List[Dict[str, Any]]:
        """Get clinical phase data for a gene from ChEMBL API.
        
        Args:
            gene_symbol: Gene symbol to search
            
        Returns:
            List of drug records with clinical phase information
        """
        try:
            # Search for targets by gene symbol
            target_response = self.query_chembl_api('target', {
                'target_synonym': gene_symbol,
                'format': 'json',
                'limit': 20
            })
            
            clinical_drugs = []
            
            for target in target_response.get('targets', []):
                target_chembl_id = target.get('target_chembl_id')
                if not target_chembl_id:
                    continue
                
                # Get activities for this target
                activity_response = self.query_chembl_api('activity', {
                    'target_chembl_id': target_chembl_id,
                    'format': 'json',
                    'limit': 50
                })
                
                for activity in activity_response.get('activities', []):
                    molecule_chembl_id = activity.get('molecule_chembl_id')
                    if not molecule_chembl_id:
                        continue
                    
                    # Get molecule details including clinical phase
                    molecule_response = self.query_chembl_api('molecule', {
                        'molecule_chembl_id': molecule_chembl_id,
                        'format': 'json'
                    })
                    
                    for molecule in molecule_response.get('molecules', []):
                        max_phase = molecule.get('max_phase')
                        if max_phase is not None and max_phase >= self.max_phase_cutoff:
                            
                            drug_record = {
                                'molecule_chembl_id': molecule_chembl_id,
                                'pref_name': molecule.get('pref_name', ''),
                                'max_phase': max_phase,
                                'therapeutic_flag': molecule.get('therapeutic_flag', False),
                                'target_chembl_id': target_chembl_id,
                                'target_pref_name': target.get('pref_name', ''),
                                'activity_type': activity.get('standard_type', ''),
                                'activity_value': activity.get('standard_value'),
                                'activity_units': activity.get('standard_units', '')
                            }
                            
                            # Get mechanism of action if available
                            if self.include_mechanisms:
                                moa_response = self.query_chembl_api('mechanism', {
                                    'molecule_chembl_id': molecule_chembl_id,
                                    'format': 'json'
                                })
                                
                                mechanisms = []
                                for moa in moa_response.get('mechanisms', []):
                                    mechanisms.append({
                                        'mechanism_of_action': moa.get('mechanism_of_action', ''),
                                        'action_type': moa.get('action_type', ''),
                                        'target_chembl_id': moa.get('target_chembl_id', '')
                                    })
                                
                                drug_record['mechanisms'] = mechanisms
                            
                            clinical_drugs.append(drug_record)
            
            self.logger.debug(f"Found {len(clinical_drugs)} clinical drug records for {gene_symbol}")
            return clinical_drugs
            
        except Exception as e:
            self.logger.warning(f"Failed to get clinical phase data for {gene_symbol}: {e}")
            return []
    
    def enhance_existing_drug_data(self) -> None:
        """Enhance existing drug data with clinical phases and mechanisms from ChEMBL API.
        
        This method queries the ChEMBL API to enrich drug records with:
        - Clinical trial phases
        - Mechanisms of action
        - Therapeutic flags
        - Activity data
        """
        try:
            self.logger.info("Enhancing drug data with clinical phases and mechanisms")
            
            if not self.ensure_connection():
                raise DatabaseError("Database connection failed")
            
            # Get all genes with existing drug data
            self.db_manager.cursor.execute("""
                SELECT DISTINCT gene_symbol 
                FROM cancer_transcript_base 
                WHERE drugs IS NOT NULL 
                  AND drugs != '{}'::jsonb
                ORDER BY gene_symbol
            """)
            
            genes_with_drugs = [row[0] for row in self.db_manager.cursor.fetchall()]
            self.logger.info(f"Found {len(genes_with_drugs)} genes with existing drug data")
            
            # Process genes in batches with progress tracking
            enhanced_drugs = {}
            
            progress_bar = get_progress_bar(
                total=len(genes_with_drugs),
                desc="Enhancing drug data with clinical info",
                module_name="chembl_drugs"
            )
            
            try:
                for gene_symbol in genes_with_drugs:
                    clinical_data = self.get_clinical_phase_data(gene_symbol)
                    
                    if clinical_data:
                        # Convert to format compatible with existing schema
                        enhanced_drug_records = {}
                        
                        for drug in clinical_data:
                            drug_id = drug['molecule_chembl_id']
                            enhanced_drug_records[drug_id] = {
                                'name': drug['pref_name'],
                                'score': drug.get('activity_value', 0),
                                'mechanism': drug.get('mechanisms', [{}])[0].get('mechanism_of_action', ''),
                                'max_phase': drug['max_phase'],
                                'therapeutic_flag': drug['therapeutic_flag'],
                                'activity_type': drug['activity_type'],
                                'activity_units': drug.get('activity_units', ''),
                                'target_name': drug['target_pref_name']
                            }
                        
                        if enhanced_drug_records:
                            enhanced_drugs[gene_symbol] = enhanced_drug_records
                    
                    progress_bar.update(1)
                    
            finally:
                progress_bar.close()
            
            # Update database with enhanced drug data
            if enhanced_drugs:
                self._update_enhanced_drug_data(enhanced_drugs)
                
            self.logger.info(f"Enhanced drug data for {len(enhanced_drugs)} genes")
            
        except Exception as e:
            self.logger.error(f"Failed to enhance drug data: {e}")
            raise ProcessingError(f"Drug data enhancement failed: {e}")
    
    def _update_enhanced_drug_data(self, enhanced_drugs: Dict[str, Dict[str, Any]]) -> None:
        """Update database with enhanced drug data.
        
        Args:
            enhanced_drugs: Dictionary mapping gene symbols to enhanced drug records
        """
        try:
            self.logger.info(f"Updating database with enhanced drug data for {len(enhanced_drugs)} genes")
            
            updates = []
            for gene_symbol, drug_records in enhanced_drugs.items():
                updates.append((json.dumps(drug_records), gene_symbol))
            
            # Update in batches
            batch_size = 100
            for i in range(0, len(updates), batch_size):
                batch = updates[i:i + batch_size]
                
                self.db_manager.cursor.executemany("""
                    UPDATE cancer_transcript_base 
                    SET drugs = %s::jsonb
                    WHERE gene_symbol = %s
                """, batch)
                
                if self.db_manager.conn:
                    self.db_manager.conn.commit()
            
            self.logger.info("Enhanced drug data updates completed")
            
        except Exception as e:
            if self.db_manager.conn:
                self.db_manager.conn.rollback()
            raise DatabaseError(f"Failed to update enhanced drug data: {e}")

    def _populate_publications_from_docs(self) -> None:
        """Populate ChEMBL publications table from docs data if available.
        
        This method attempts to extract publication data from the ChEMBL docs table
        or similar source and populate the drug_publications table.
        """
        try:
            schema_name = self.chembl_schema
            self.logger.info("Attempting to populate publications from ChEMBL docs data")
            
            # Check if we have access to a docs table (could be from SQL dumps or a separate import)
            docs_table_candidates = [
                f"{schema_name}.docs",
                "chembl.docs", 
                "public.docs",
                "docs"
            ]
            
            docs_table = None
            for candidate in docs_table_candidates:
                try:
                    self.db_manager.cursor.execute(f"SELECT COUNT(*) FROM {candidate} LIMIT 1")
                    docs_table = candidate
                    self.logger.info(f"Found docs table: {docs_table}")
                    break
                except Exception:
                    continue
            
            if not docs_table:
                self.logger.info("No ChEMBL docs table found, skipping docs-based population")
                return
            
            # First, check what columns are available in the docs table
            self.db_manager.cursor.execute(f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = '{docs_table.split('.')[-1]}' 
                AND table_schema = '{docs_table.split('.')[0] if '.' in docs_table else 'public'}'
            """)
            
            available_columns = [row[0] for row in self.db_manager.cursor.fetchall()]
            self.logger.info(f"Available columns in {docs_table}: {available_columns}")
            
            # Define required and optional columns
            required_columns = ['doc_id']
            important_columns = ['pubmed_id', 'doi', 'title', 'year', 'journal', 'authors']
            optional_columns = ['abstract', 'volume', 'issue', 'first_page', 'last_page', 'journal_full_title', 'patent_id']
            
            # Build SELECT clause with available columns
            select_columns = []
            column_mapping = {}  # Maps column name to index in result
            
            for col in required_columns + important_columns + optional_columns:
                if col in available_columns:
                    select_columns.append(col)
                    column_mapping[col] = len(select_columns) - 1
                else:
                    select_columns.append(f"NULL as {col}")
                    column_mapping[col] = len(select_columns) - 1
            
            # Extract publication data from docs table with dynamic columns
            query = f"""
                SELECT DISTINCT
                    {', '.join(select_columns)}
                FROM {docs_table}
                WHERE pubmed_id IS NOT NULL 
                   OR doi IS NOT NULL
                   OR title IS NOT NULL
                ORDER BY year DESC NULLS LAST
                LIMIT 10000
            """
            
            self.logger.info(f"Executing flexible query with {len(select_columns)} columns")
            self.db_manager.cursor.execute(query)
            
            docs_data = self.db_manager.cursor.fetchall()
            
            if not docs_data:
                self.logger.info("No publication data found in docs table")
                return
            
            self.logger.info(f"Found {len(docs_data)} publication records in docs table")
            
            # Insert publication data with progress tracking
            progress_bar = get_progress_bar(
                total=len(docs_data),
                desc="Populating publications from docs",
                module_name="chembl_drugs"
            )
            
            batch_size = 100
            inserted_count = 0
            
            try:
                for i in range(0, len(docs_data), batch_size):
                    batch = docs_data[i:i + batch_size]
                    
                    # Prepare batch data
                    batch_values = []
                    for row in batch:
                        # Use column mapping to extract data safely
                        pmid = row[column_mapping['pubmed_id']] if column_mapping['pubmed_id'] < len(row) else None
                        title = row[column_mapping['title']] if column_mapping['title'] < len(row) else None
                        abstract = row[column_mapping['abstract']] if column_mapping['abstract'] < len(row) else None
                        doi = row[column_mapping['doi']] if column_mapping['doi'] < len(row) else None
                        
                        # Extract PMIDs from text fields if not directly available
                        if not pmid and title:
                            pmids = extract_pmids_from_text(title)
                            pmid = pmids[0] if pmids else None
                        if not pmid and abstract:
                            pmids = extract_pmids_from_text(abstract)
                            pmid = pmids[0] if pmids else None
                        
                        # Only include records with valid identifiers
                        if pmid or doi or title:
                            batch_values.append((
                                None,  # chembl_id - will be populated later when linking to drugs
                                row[column_mapping['doc_id']],
                                pmid,
                                doi,
                                title,
                                abstract,
                                row[column_mapping['year']] if column_mapping['year'] < len(row) else None,
                                row[column_mapping['journal']] if column_mapping['journal'] < len(row) else None,
                                row[column_mapping['authors']] if column_mapping['authors'] < len(row) else None,
                                row[column_mapping['volume']] if column_mapping['volume'] < len(row) else None,
                                row[column_mapping['issue']] if column_mapping['issue'] < len(row) else None,
                                row[column_mapping['first_page']] if column_mapping['first_page'] < len(row) else None,
                                row[column_mapping['last_page']] if column_mapping['last_page'] < len(row) else None,
                                row[column_mapping['journal_full_title']] if column_mapping['journal_full_title'] < len(row) else None,
                                row[column_mapping['patent_id']] if column_mapping['patent_id'] < len(row) else None
                            ))
                    
                    if batch_values:
                        # Insert batch
                        self.db_manager.cursor.executemany(f"""
                            INSERT INTO {schema_name}.drug_publications (
                                chembl_id, doc_id, pubmed_id, doi, title, abstract, year, journal, authors,
                                volume, issue, first_page, last_page, journal_full_title, patent_id
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (doc_id) DO UPDATE SET
                                pubmed_id = EXCLUDED.pubmed_id,
                                doi = EXCLUDED.doi,
                                title = EXCLUDED.title,
                                abstract = EXCLUDED.abstract,
                                year = EXCLUDED.year,
                                journal = EXCLUDED.journal,
                                authors = EXCLUDED.authors,
                                volume = EXCLUDED.volume,
                                issue = EXCLUDED.issue,
                                first_page = EXCLUDED.first_page,
                                last_page = EXCLUDED.last_page,
                                journal_full_title = EXCLUDED.journal_full_title,
                                patent_id = EXCLUDED.patent_id
                        """, batch_values)
                        
                        inserted_count += len(batch_values)
                    
                    progress_bar.update(len(batch))
                
                self._safe_commit()
                self.logger.info(f"Successfully populated {inserted_count} publications from docs table")
                
            finally:
                progress_bar.close()
            
        except Exception as e:
            self.logger.warning(f"Failed to populate publications from docs: {e}")
            # Don't raise an exception here as this is an optional enhancement

    def extract_publication_references(self) -> List[Publication]:
        """Extract publication references from ChEMBL drug data.
        
        Returns:
            List of Publication objects extracted from ChEMBL publications
        """
        publications = []
        
        try:
            if not self.ensure_connection() or not self.db_manager.cursor:
                self.logger.warning("Cannot extract publication references - database connection unavailable")
                return publications
            
            schema_name = self.chembl_schema
            
            # First, check what columns are available in the drug_publications table
            self.db_manager.cursor.execute(f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'drug_publications' 
                AND table_schema = '{schema_name}'
            """)
            
            available_columns = [row[0] for row in self.db_manager.cursor.fetchall()]
            self.logger.info(f"Available columns in {schema_name}.drug_publications: {available_columns}")
            
            # Define required and optional columns
            required_columns = ['doc_id']
            important_columns = ['pubmed_id', 'doi', 'title', 'year', 'journal', 'authors', 'chembl_id']
            optional_columns = ['abstract', 'volume', 'issue', 'first_page', 'last_page', 'journal_full_title', 'patent_id']
            
            # Build SELECT clause with available columns
            select_columns = []
            column_mapping = {}  # Maps column name to index in result
            
            for col in required_columns + important_columns + optional_columns:
                if col in available_columns:
                    select_columns.append(col)
                    column_mapping[col] = len(select_columns) - 1
                else:
                    select_columns.append(f"NULL as {col}")
                    column_mapping[col] = len(select_columns) - 1
            
            # Extract publications from the drug_publications table with dynamic columns
            query = f"""
                SELECT DISTINCT
                    {', '.join(select_columns)}
                FROM {schema_name}.drug_publications
                WHERE pubmed_id IS NOT NULL
                   OR doi IS NOT NULL
            """
            
            self.logger.info(f"Executing flexible publication extraction query with {len(select_columns)} columns")
            self.db_manager.cursor.execute(query)
            
            publication_rows = self.db_manager.cursor.fetchall()
            
            self.logger.info(f"Extracting publication references from {len(publication_rows)} ChEMBL publications")
            
            for row in publication_rows:
                # Use column mapping to extract data safely
                pmid = row[column_mapping['pubmed_id']] if column_mapping['pubmed_id'] < len(row) else None
                doi = row[column_mapping['doi']] if column_mapping['doi'] < len(row) else None
                title = row[column_mapping['title']] if column_mapping['title'] < len(row) else None
                abstract = row[column_mapping['abstract']] if column_mapping['abstract'] < len(row) else None
                year = row[column_mapping['year']] if column_mapping['year'] < len(row) else None
                journal = row[column_mapping['journal']] if column_mapping['journal'] < len(row) else None
                authors = row[column_mapping['authors']] if column_mapping['authors'] < len(row) else None
                chembl_id = row[column_mapping['chembl_id']] if column_mapping['chembl_id'] < len(row) else None
                doc_id = row[column_mapping['doc_id']] if column_mapping['doc_id'] < len(row) else None
                
                # Create publication reference
                pub_ref = {
                    'source_db': 'ChEMBL',
                    'evidence_type': 'drug_publication',
                    'doc_id': doc_id,
                    'chembl_id': chembl_id
                }
                
                # Add PMID if available
                if pmid:
                    pub_ref['pmid'] = str(pmid)
                    pub_ref['url'] = format_pmid_url(str(pmid))
                
                # Add DOI if available
                if doi:
                    pub_ref['doi'] = doi
                    if not pub_ref.get('url'):
                        pub_ref['url'] = f"https://doi.org/{doi}"
                
                # Add other metadata
                if title:
                    pub_ref['title'] = title
                if abstract:
                    pub_ref['abstract'] = abstract[:500] + '...' if len(abstract) > 500 else abstract
                if year:
                    pub_ref['year'] = int(year)
                if journal:
                    pub_ref['journal'] = journal
                if authors:
                    # Split authors and take first few
                    author_list = [a.strip() for a in authors.split(',')][:5]
                    pub_ref['authors'] = author_list
                
                publications.append(pub_ref)
            
            self.logger.info(f"Extracted {len(publications)} publication references from ChEMBL")
            return publications
            
        except Exception as e:
            self.logger.error(f"Failed to extract ChEMBL publication references: {e}")
            return publications

    def run(self) -> None:
        """Run the ChEMBL drug processing pipeline.
        
        This processes drug information from ChEMBL and integrates it with the transcript database.
        """
        try:
            self.logger.info("Starting ChEMBL drug processing")
            
            # Check schema version compatibility
            if not self.ensure_schema_version('v0.1.5'):
                raise DatabaseError(f"Database schema version incompatible. Required: v0.1.5")
            
            # Download ChEMBL data
            chembl_dump, uniprot_mapping = self.download_chembl_data()
            
            # Extract ChEMBL dump
            extracted_dir = self.extract_chembl_dump(chembl_dump)
            
            # Process UniProt mapping
            uniprot_to_chembl = self.process_uniprot_mapping(uniprot_mapping)
            
            # Create optimized tables for ChEMBL data
            self.create_optimized_tables()
            
            # Import ChEMBL data into tables
            self.import_chembl_to_tables(extracted_dir)
            
            # Extract and process publication references
            publications = self.extract_publication_references()
            if publications:
                self.logger.info(f"Processing {len(publications)} ChEMBL publication references")
                publications_processor = PublicationsProcessor(self.config)
                publications_processor.enrich_publications_bulk(publications)
            
            # Calculate drug scores
            if not self.skip_scores:
                self.calculate_drug_scores()
            
            # Enhance with clinical phase data and mechanisms from ChEMBL API
            if self.include_clinical_phases or self.include_mechanisms:
                self.logger.info("Enhancing drug data with clinical phases and mechanisms")
                self.enhance_existing_drug_data()
            
            # Verify results
            self._verify_integration_results()
            
            self.logger.info("ChEMBL drug processing completed successfully with clinical enhancements")
            
        except Exception as e:
            self.logger.error(f"ChEMBL drug processing failed: {e}")
            raise

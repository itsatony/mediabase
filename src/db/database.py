"""Database management module for Cancer Transcriptome Base.

This module consolidates all database-related functionality including:
- Connection management
- Schema definition and versioning
- Migrations
- Custom type adapters
"""

import json
import logging
from pathlib import Path
import os
from typing import Dict, Any, Optional, List, Tuple, cast
import psycopg2
from psycopg2.extensions import (
    connection as pg_connection,
    cursor as pg_cursor,
    register_adapter,
    AsIs,
    ISOLATION_LEVEL_AUTOCOMMIT
)
from rich.console import Console
from rich.table import Table

# Import our centralized logging
from ..utils.logging import setup_logging

# Create logger with the module name
logger = setup_logging(module_name=__name__)
console = Console()

# Schema version history with migrations
SCHEMA_VERSIONS = {
    "v0.1.0": """
        CREATE TABLE cancer_transcript_base (
            transcript_id TEXT PRIMARY KEY,
            gene_symbol TEXT,
            gene_id TEXT,
            gene_type TEXT,
            chromosome TEXT,
            coordinates JSONB
        );
        CREATE INDEX idx_gene_symbol ON cancer_transcript_base(gene_symbol);
        CREATE INDEX idx_gene_id ON cancer_transcript_base(gene_id);
    """,
    "v0.1.1": """
        ALTER TABLE cancer_transcript_base
        ADD COLUMN product_type TEXT[] DEFAULT '{}',
        ADD COLUMN go_terms JSONB DEFAULT '{}'::jsonb,
        ADD COLUMN pathways TEXT[] DEFAULT '{}',
        ADD COLUMN drugs JSONB DEFAULT '{}'::jsonb,
        ADD COLUMN publications JSONB DEFAULT '[]'::jsonb,
        ADD COLUMN expression_fold_change FLOAT DEFAULT 1.0,
        ADD COLUMN expression_freq JSONB DEFAULT '{"high": [], "low": []}'::jsonb,
        ADD COLUMN cancer_types TEXT[] DEFAULT '{}';
        
        CREATE INDEX idx_product_type ON cancer_transcript_base USING GIN(product_type);
        CREATE INDEX idx_pathways ON cancer_transcript_base USING GIN(pathways);
        CREATE INDEX idx_drugs ON cancer_transcript_base USING GIN(drugs);
    """,
    "v0.1.2": """
        ALTER TABLE cancer_transcript_base
        ADD COLUMN features JSONB DEFAULT '{}'::jsonb,
        ADD COLUMN molecular_functions TEXT[] DEFAULT '{}';
        
        CREATE INDEX idx_features ON cancer_transcript_base USING GIN(features);
        CREATE INDEX idx_molecular_functions ON cancer_transcript_base USING GIN(molecular_functions);
    """,
    "v0.1.3": """
        ALTER TABLE cancer_transcript_base
        ADD COLUMN cellular_location TEXT[] DEFAULT '{}',
        ADD COLUMN drug_scores JSONB DEFAULT '{}'::jsonb;
        
        CREATE INDEX idx_cellular_location ON cancer_transcript_base USING GIN(cellular_location);
    """,
    "v0.1.4": """
        -- Add new ID columns
        ALTER TABLE cancer_transcript_base
        ADD COLUMN alt_transcript_ids JSONB DEFAULT '{}'::jsonb,  -- {source: id}
        ADD COLUMN alt_gene_ids JSONB DEFAULT '{}'::jsonb,        -- {source: id}
        ADD COLUMN uniprot_ids TEXT[] DEFAULT '{}',
        ADD COLUMN ncbi_ids TEXT[] DEFAULT '{}',
        ADD COLUMN refseq_ids TEXT[] DEFAULT '{}';

        -- Add source-specific publication references
        ALTER TABLE cancer_transcript_base
        ADD COLUMN source_references JSONB DEFAULT '{
            "go_terms": [],
            "uniprot": [],
            "drugs": [],
            "pathways": []
        }'::jsonb;

        -- Reference format in arrays:
        -- {
        --   "pmid": "12345678",
        --   "year": 2020,
        --   "evidence_type": "experimental",
        --   "citation_count": 42,
        --   "source_db": "drugcentral"
        -- }

        -- Add indices for new columns
        CREATE INDEX idx_alt_transcript_ids ON cancer_transcript_base USING GIN(alt_transcript_ids);
        CREATE INDEX idx_alt_gene_ids ON cancer_transcript_base USING GIN(alt_gene_ids);
        CREATE INDEX idx_uniprot_ids ON cancer_transcript_base USING GIN(uniprot_ids);
        CREATE INDEX idx_ncbi_ids ON cancer_transcript_base USING GIN(ncbi_ids);
        CREATE INDEX idx_refseq_ids ON cancer_transcript_base USING GIN(refseq_ids);
        CREATE INDEX idx_source_references ON cancer_transcript_base USING GIN(source_references);

        -- Drop old publications column as it's replaced by source_references
        ALTER TABLE cancer_transcript_base DROP COLUMN IF EXISTS publications;
    """,
    "v0.1.5": """
        -- Set proper default for source_references
        ALTER TABLE cancer_transcript_base
        ALTER COLUMN source_references SET DEFAULT jsonb_build_object(
            'go_terms', jsonb_build_array(),
            'uniprot', jsonb_build_array(),
            'drugs', jsonb_build_array(),
            'pathways', jsonb_build_array()
        );

        -- Update any existing NULL source_references to the proper default structure
        UPDATE cancer_transcript_base
        SET source_references = jsonb_build_object(
            'go_terms', jsonb_build_array(),
            'uniprot', jsonb_build_array(),
            'drugs', jsonb_build_array(),
            'pathways', jsonb_build_array()
        )
        WHERE source_references IS NULL;

        -- Create publication_reference type for better structure
        DO $$ BEGIN
            CREATE TYPE publication_reference AS (
                pmid text,
                evidence_type text,
                source_db text,
                title text,
                abstract text,
                year integer,
                journal text,
                authors text[],
                citation_count integer,
                doi text,
                url text
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """,
    "v0.1.6": """
        -- Add PDB IDs array for protein structure references
        ALTER TABLE cancer_transcript_base
        ADD COLUMN IF NOT EXISTS pdb_ids TEXT[] DEFAULT '{}';

        -- Add cross-reference index
        CREATE INDEX IF NOT EXISTS idx_cross_ref_ids ON cancer_transcript_base 
        USING GIN(uniprot_ids, ncbi_ids, refseq_ids, pdb_ids);

        -- Update source_references to include all reference types
        ALTER TABLE cancer_transcript_base
        ALTER COLUMN source_references SET DEFAULT jsonb_build_object(
            'go_terms', jsonb_build_array(),
            'uniprot', jsonb_build_array(),
            'drugs', jsonb_build_array(),
            'pathways', jsonb_build_array(),
            'publications', jsonb_build_array()
        );

        -- Update existing rows to include publications array if missing
        UPDATE cancer_transcript_base
        SET source_references = source_references || '{"publications": []}'::jsonb
        WHERE NOT (source_references ? 'publications');

        -- Create optimized view for ID lookups
        CREATE OR REPLACE VIEW gene_id_lookup AS
        SELECT 
            transcript_id,
            gene_symbol,
            gene_id,
            uniprot_ids,
            ncbi_ids,
            refseq_ids,
            alt_gene_ids,
            alt_transcript_ids
        FROM cancer_transcript_base;
    """,
    "v0.1.7": """
        -- Add PharmGKB pathway data for drug-specific metabolic pathways
        ALTER TABLE cancer_transcript_base
        ADD COLUMN IF NOT EXISTS pharmgkb_pathways JSONB DEFAULT '{}'::jsonb;

        -- Update source_references to include PharmGKB pathway references
        ALTER TABLE cancer_transcript_base
        ALTER COLUMN source_references SET DEFAULT jsonb_build_object(
            'go_terms', jsonb_build_array(),
            'uniprot', jsonb_build_array(),
            'drugs', jsonb_build_array(),
            'pathways', jsonb_build_array(),
            'publications', jsonb_build_array(),
            'pharmgkb_pathways', jsonb_build_array()
        );

        -- Update existing rows to include pharmgkb_pathways array if missing
        UPDATE cancer_transcript_base
        SET source_references = source_references || '{"pharmgkb_pathways": []}'::jsonb
        WHERE NOT (source_references ? 'pharmgkb_pathways');

        -- Add GIN index for efficient PharmGKB pathway queries
        CREATE INDEX IF NOT EXISTS idx_pharmgkb_pathways ON cancer_transcript_base USING GIN(pharmgkb_pathways);

        -- Add composite index for drug-pathway queries
        CREATE INDEX IF NOT EXISTS idx_drugs_pharmgkb ON cancer_transcript_base USING GIN(drugs, pharmgkb_pathways);

        -- Update gene_id_lookup view to be more comprehensive
        DROP VIEW IF EXISTS gene_id_lookup;
        CREATE OR REPLACE VIEW gene_id_lookup AS
        SELECT 
            transcript_id,
            gene_symbol,
            gene_id,
            uniprot_ids,
            ncbi_ids,
            refseq_ids,
            alt_gene_ids,
            alt_transcript_ids,
            CASE 
                WHEN pharmgkb_pathways != '{}'::jsonb THEN TRUE 
                ELSE FALSE 
            END as has_pharmgkb_data
        FROM cancer_transcript_base;
    """,
    "v0.1.8": """
        -- Enhanced evidence scoring system with multi-dimensional analysis
        
        -- Add evidence scoring metadata table
        CREATE TABLE IF NOT EXISTS evidence_scoring_metadata (
            id SERIAL PRIMARY KEY,
            gene_symbol TEXT NOT NULL,
            drug_id TEXT,
            evidence_score JSONB NOT NULL,
            use_case TEXT NOT NULL DEFAULT 'therapeutic_target',
            confidence_lower FLOAT,
            confidence_upper FLOAT,
            evidence_count INTEGER,
            evidence_quality FLOAT,
            last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            scoring_version TEXT DEFAULT '1.0',
            UNIQUE(gene_symbol, drug_id, use_case)
        );

        -- Create indexes for evidence scoring queries
        CREATE INDEX IF NOT EXISTS idx_evidence_scoring_gene ON evidence_scoring_metadata(gene_symbol);
        CREATE INDEX IF NOT EXISTS idx_evidence_scoring_drug ON evidence_scoring_metadata(drug_id);
        CREATE INDEX IF NOT EXISTS idx_evidence_scoring_use_case ON evidence_scoring_metadata(use_case);
        CREATE INDEX IF NOT EXISTS idx_evidence_scoring_quality ON evidence_scoring_metadata(evidence_quality);

        -- Add evidence quality metrics column
        ALTER TABLE cancer_transcript_base
        ADD COLUMN IF NOT EXISTS evidence_quality_metrics JSONB DEFAULT jsonb_build_object(
            'overall_confidence', 0.0,
            'evidence_count', 0,
            'source_diversity', 0,
            'clinical_evidence_ratio', 0.0,
            'publication_support_ratio', 0.0,
            'last_assessment', CURRENT_TIMESTAMP
        );

        -- Update source_references to include evidence scoring references
        UPDATE cancer_transcript_base
        SET source_references = source_references || '{"evidence_scoring": []}'::jsonb
        WHERE NOT (source_references ? 'evidence_scoring');
    """,
    "v0.1.9": """
        -- Add PharmGKB variant annotations support for pharmacogenomics
        
        -- Add variant annotations column to main table
        ALTER TABLE cancer_transcript_base
        ADD COLUMN IF NOT EXISTS pharmgkb_variants JSONB DEFAULT '{}'::jsonb;
        
        -- GIN index for efficient variant queries on main table
        CREATE INDEX IF NOT EXISTS idx_pharmgkb_variants_jsonb ON cancer_transcript_base USING GIN(pharmgkb_variants);
        
        -- Update source_references to include PharmGKB variant references
        UPDATE cancer_transcript_base
        SET source_references = source_references || '{"pharmgkb_variants": []}'::jsonb
        WHERE NOT (source_references ? 'pharmgkb_variants');
    """
}

# Minimum supported version constant
MIN_SUPPORTED_VERSION = "v0.1.8"

class DatabaseManager:
    """Manages database operations including connection, schema, and migrations."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize database manager with configuration.
        
        Args:
            config: Database configuration dictionary with connection parameters
        """
        # Set up instance logger using our centralized logger
        self.logger = setup_logging(module_name=f"{__name__}.DatabaseManager")
        
        # Ensure we have the required database configuration
        self.db_config = {
            'host': config.get('host', 'localhost'),
            'port': config.get('port', 5432),
            'dbname': config.get('dbname', 'mediabase'),
            'user': config.get('user', 'postgres'),
            'password': config.get('password', 'postgres')
        }
        # Store other config options separately
        self.config = {k: v for k, v in config.items() 
                      if k not in self.db_config}
        self.print_config()
        self.conn: Optional[pg_connection] = None
        self.cursor: Optional[pg_cursor] = None
        self._register_adapters()
    
    def _register_adapters(self) -> None:
        """Register custom PostgreSQL adapters."""
        def adapt_dict(dict_value: dict) -> AsIs:
            """Adapt Python dict to PostgreSQL JSON."""
            return AsIs(f"'{json.dumps(dict_value)}'::jsonb")
        
        # Register the dict adapter
        register_adapter(dict, adapt_dict)
    
    def connect(self, db_name: Optional[str] = None) -> bool:
        """Establish database connection."""
        try:
            params = self.db_config.copy()
            if db_name:
                params['dbname'] = db_name
            
            # Only close if connection exists and is open
            if self.conn and not self.conn.closed:
                self.close()
            
            # Create new connection
            conn = cast(pg_connection, psycopg2.connect(**params))
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            self.conn = conn
            self.cursor = self.conn.cursor()
            return True
            
        except psycopg2.Error as e:
            logger.error(f"Connection failed: {e}")
            return False
    
    def close(self) -> None:
        """Close database connection and cursor."""
        if self.cursor is not None:
            self.cursor.close()
        if self.conn is not None:
            self.conn.close()
            self.conn = None
        self.cursor = None

    def create_database(self) -> bool:
        """Create the database if it doesn't exist."""
        dbname = self.config.get('dbname', 'mediabase')
        try:
            if not self.cursor:
                if not self.connect():
                    return False
            if not self.cursor:  # Double check after connect attempt
                return False
                
            self.cursor.execute(
                f"CREATE DATABASE {dbname}"
            )
            return True
        except psycopg2.Error as e:
            logger.error(f"Database creation failed: {e}")
            return False

    def drop_database(self) -> bool:
        """Drop the database with connection handling."""
        dbname = self.config.get('dbname', 'mediabase')
        try:
            # Connect to postgres database
            if not self.connect() or not self.cursor:
                return False

            # Force close other connections
            self.cursor.execute(f"""
                SELECT pg_terminate_backend(pid) 
                FROM pg_stat_activity 
                WHERE datname = %s AND pid != pg_backend_pid()
            """, (dbname,))
            
            # Small delay to ensure connections are closed
            import time
            time.sleep(1)
            
            # Drop the database
            self.cursor.execute(f"DROP DATABASE IF EXISTS {dbname}")
            return True
            
        except psycopg2.Error as e:
            if "ERROR: database" in str(e) and "does not exist" in str(e):
                return True
            logger.error(f"Database drop failed: {e}")
            return False

    def get_current_version(self) -> Optional[str]:
        """Get current schema version."""
        try:
            if self.cursor is None:
                return None
                
            # First check if schema_version table exists at all
            self.cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'schema_version'
                )
            """)
            
            # Add null check before accessing result
            result = self.cursor.fetchone()
            if result is None:
                return None
            
            if not result[0]:
                self.logger.info("Schema version table doesn't exist. Creating it...")
                
                # Create the schema_version table with the correct columns
                self.cursor.execute("""
                    CREATE TABLE schema_version (
                        version_name TEXT PRIMARY KEY,
                        applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        description TEXT
                    )
                """)
                
                # Apply the initial version
                self.cursor.execute("""
                    INSERT INTO schema_version (version_name) VALUES ('v0.1.0')
                """)
                
                return 'v0.1.0'
            
            # Next check which version of the schema_version table we have
            # It could have different column names depending on how it was created
            self.cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'schema_version'
            """)
            
            # Add null check for columns
            columns_result = self.cursor.fetchall()
            if columns_result is None:
                return None
            
            columns = [row[0] for row in columns_result if row is not None]
            
            # Handle different column name possibilities
            version_column = 'version_name' if 'version_name' in columns else 'version'
            order_column = 'applied_at' if 'applied_at' in columns else 'id'
            order_direction = 'DESC' if order_column == 'applied_at' else 'DESC'
            
            query = f"SELECT {version_column} FROM schema_version ORDER BY {order_column} {order_direction} LIMIT 1"
            self.cursor.execute(query)
            
            result = self.cursor.fetchone()
            return result[0] if result is not None else None
            
        except psycopg2.Error as e:
            self.logger.error(f"Version check failed: {e}")
            return None

    def get_current_schemaversion_number(self) -> Optional[int]:
        """Get current schema version number - we extract and 4-digit each major, minor, patch to return 1 comparable number."""
        current_version = self.get_current_version()
        if current_version:
            # Extract major, minor, patch from version string
            parts = current_version.split('.')
            if len(parts) == 3:
                major = int(parts[0][1:])
                minor = int(parts[1])
                patch = int(parts[2])
                # Convert to a single integer
                # Examples for v0.1.3: 0.1.3 -> 0*10000 + 1*100 + 3 = 103
                # Examples for v1.0.0: 1.0.0 -> 1*10000 + 0*100 + 0 = 10000
                # Examples for v0.10.3: 0.10.3 -> 0*10000 + 10*100 + 3 = 1003
                # Examples for v0.1.10: 0.1.10 -> 0*10000 + 1*100 + 10 = 110
                # Examples for v1.2.3: 1.2.3 -> 1*10000 + 2*100 + 3 = 10203
                return major * 10000 + minor * 100 + patch
            else:
                logger.error(f"Invalid version format: {current_version}")
        return None

    def migrate_to_version(self, target_version: str) -> bool:
        """Migrate schema to target version.
        
        This method has been simplified to only support migrations from v0.1.5 onwards.
        For older versions, use reset_database() to create a fresh schema.
        
        Args:
            target_version: Target schema version
            
        Returns:
            bool: True if migration successful
        """
        try:
            current_version = self.get_current_version()
            
            # If current version is below minimum supported, recommend reset
            if not current_version or current_version < MIN_SUPPORTED_VERSION:
                self.logger.error(f"Current version {current_version} is below minimum supported version {MIN_SUPPORTED_VERSION}")
                self.logger.error("Please use reset_database() to create a fresh schema")
                return False
            
            if current_version == target_version:
                self.logger.info(f"Already at version {target_version}")
                return True
                
            # Get ordered list of versions
            versions = list(SCHEMA_VERSIONS.keys())
            
            if current_version not in versions:
                self.logger.error(f"Current version {current_version} not in known versions")
                return False
                
            if target_version not in versions:
                self.logger.error(f"Target version {target_version} not in known versions")
                return False
                
            current_idx = versions.index(current_version)
            target_idx = versions.index(target_version)
            
            if current_idx >= target_idx:
                self.logger.info(f"No migration needed: current {current_version} >= target {target_version}")
                return True
            
            # Start a transaction for the migration
            if self.conn:
                self.conn.autocommit = False
                
            # Apply all migrations between current and target
            for i in range(current_idx + 1, target_idx + 1):
                version = versions[i]
                self.logger.info(f"Migrating to {version}")
                
                if self.cursor:
                    # Execute each statement in the migration
                    statements = SCHEMA_VERSIONS[version].strip().split(';')
                    for stmt in statements:
                        if stmt.strip():  # Skip empty statements
                            try:
                                self.cursor.execute(stmt + ';')
                            except psycopg2.Error as e:
                                if "already exists" in str(e):
                                    self.logger.warning(f"Ignoring 'already exists' error: {e}")
                                else:
                                    raise
                    
                    # Record the applied migration
                    self.cursor.execute(
                        """
                        INSERT INTO schema_version (version_name) 
                        VALUES (%s)
                        ON CONFLICT (version_name) DO NOTHING
                        """,
                        (version,)
                    )
            
            # Commit the transaction
            if self.conn:
                self.conn.commit()
                self.conn.autocommit = True
                
            self.logger.info(f"Successfully migrated from {current_version} to {target_version}")
            return True
            
        except Exception as e:
            self.logger.error(f"Migration failed: {e}")
            if self.conn:
                self.conn.rollback()
                self.conn.autocommit = True
            return False

    def get_table_stats(self) -> Dict[str, Any]:
        """Get statistics about the main table."""
        try:
            if self.cursor is None:
                return {"row_count": 0, "size_mb": 0}
            
            # Get row count
            self.cursor.execute(
                "SELECT COUNT(*) FROM cancer_transcript_base"
            )
            # Add null check
            result = self.cursor.fetchone()
            row_count = result[0] if result is not None else 0

            # Get table size
            self.cursor.execute("""
                SELECT pg_size_pretty(pg_total_relation_size('cancer_transcript_base')),
                       pg_total_relation_size('cancer_transcript_base') / 1024.0 / 1024.0
                FROM pg_catalog.pg_tables
                WHERE tablename = 'cancer_transcript_base'
            """)
            # Add null check
            result = self.cursor.fetchone()
            size_mb = result[1] if result is not None else 0

            return {
                "row_count": row_count,
                "size_mb": round(size_mb, 2)
            }
        except psycopg2.Error:
            return {"row_count": 0, "size_mb": 0}

    def reset(self) -> bool:
        """Reset database tables according to the latest schema version.
        
        Instead of dropping and recreating the entire database, this method:
        1. Drops the tables if they exist
        2. Creates the schema version table
        3. Applies the latest schema version to create tables
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Ensure we have a valid connection
            if not self.conn or self.conn.closed:
                if not self.connect():
                    return False
            
            if not self.cursor:
                logger.error("No database cursor available")
                return False
            
            # Drop tables if they exist
            logger.info("Dropping existing tables...")
            try:
                self.cursor.execute("""
                    DROP TABLE IF EXISTS cancer_transcript_base CASCADE;
                    DROP TABLE IF EXISTS schema_version CASCADE;
                """)
                if self.conn:  # Add check before accessing commit
                    self.conn.commit()
            except Exception as e:
                logger.error(f"Error dropping tables: {e}")
                if self.conn:  # Add check before accessing rollback
                    self.conn.rollback()
                # Continue anyway - we'll try to create the tables
                
            # Create schema_version table
            logger.info("Creating schema_version table")
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    id SERIAL PRIMARY KEY,
                    version TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            if self.conn:  # Add check before accessing commit
                self.conn.commit()
            
            # Apply latest schema version
            latest_version = list(SCHEMA_VERSIONS.keys())[-1]
            logger.info(f"Applying schema version {latest_version}")
            
            # Apply all schema versions in order
            for version in SCHEMA_VERSIONS.keys():
                logger.info(f"Applying schema version {version}")
                self.cursor.execute(SCHEMA_VERSIONS[version])
                self.cursor.execute(
                    "INSERT INTO schema_version (version) VALUES (%s)",
                    (version,)
                )
                if self.conn:  # Add check before accessing commit
                    self.conn.commit()
            
            logger.info("Database tables reset successfully")
            return True
            
        except Exception as e:
            logger.error(f"Reset failed: {e}")
            if self.conn:  # Add check before accessing rollback
                self.conn.rollback()
            return False

    def display_status(self) -> None:
        """Display database status using rich tables."""
        current_version = self.get_current_version()
        stats = self.get_table_stats()
        
        table = Table(title="Database Status")
        table.add_column("Component")
        table.add_column("Status")
        
        table.add_row(
            "Connection",
            "[green]Connected[/green]" if self.conn else "[red]Disconnected[/red]"
        )
        table.add_row(
            "Schema Version",
            str(current_version) if current_version else "[yellow]Unknown[/yellow]"
        )
        table.add_row("Records", f"{stats['row_count']:,}")
        table.add_row("Table Size", f"{stats['size_mb']} MB")
        
        console.print(table)

    def check_db_exists(self) -> bool:
        """Check if database exists."""
        dbname = self.config.get('dbname', 'mediabase')
        try:
            if self.cursor is None:
                return False
            self.cursor.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (dbname,)
            )
            result = self.cursor.fetchone()
            # Add null check before accessing result
            return bool(result is not None and result[0] == 1)
        except psycopg2.Error as e:
            logger.error(f"Database check failed: {e}")
            return False

    def dump_database(self, output_file: str) -> bool:
        """Dump database to a file using pg_dump.
        
        Args:
            output_file: Path to output file
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            import subprocess
            
            # Create environment with PGPASSWORD
            env = os.environ.copy()
            env['PGPASSWORD'] = self.db_config['password']
            
            # Construct pg_dump command
            cmd = [
                'pg_dump',
                '-h', self.db_config['host'],
                '-p', str(self.db_config['port']),
                '-U', self.db_config['user'],
                '-F', 'c',  # Custom format
                '-f', output_file,
                self.db_config['dbname']
            ]
            
            # Run pg_dump with password in environment
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                logger.info(f"Database successfully backed up to {output_file}")
                return True
            
            logger.error(f"Dump failed: {result.stderr}")
            return False
                
        except Exception as e:
            logger.error(f"Dump failed: {e}")
            return False

    def restore_database(self, input_file: str) -> bool:
        """Restore database from a dump file."""
        dbname = self.config.get('dbname', 'mediabase')
        dbhost = self.config.get('host', 'localhost')
        dbport = self.config.get('port', 5432)
        dbuser = self.config.get('user', 'postgres')
        dbpass = self.config.get('password', 'postgres')
        try:
            # First ensure we're starting fresh
            if not self.connect():
                return False
                
            self.drop_database()
            self.create_database()
            
            import subprocess
            
            env = os.environ.copy()
            env['PGPASSWORD'] = dbpass
            
            cmd = [
                'pg_restore',
                '-h', dbhost,
                '-p', str(dbport),
                '-U', dbuser,
                '-d', dbname,
                input_file
            ]
            
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
            
            if result.returncode == 0:
                return True
            logger.error(f"Restore failed: {result.stderr}")
            return False
                
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            return False

    def check_column_exists(self, table: str, column: str) -> bool:
        """Check if a column exists in the specified table.
        
        Args:
            table: Name of the table
            column: Name of the column
            
        Returns:
            bool: True if column exists, False otherwise
        """
        try:
            if not self.cursor:
                self.cursor = self.conn.cursor() if self.conn else None
                if not self.cursor:
                    raise RuntimeError("Could not create database cursor")
                    
            self.cursor.execute("""
                SELECT EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_schema = 'public'
                    AND table_name = %s 
                    AND column_name = %s
                );
            """, (table, column))
            
            result = self.cursor.fetchone()
            return bool(result and result[0])
            
        except Exception as e:
            logger.error(f"Error checking column existence: {e}")
            return False

    def print_config(self) -> None:
        """Print database configuration."""
        table = Table(title="Database Configuration")
        table.add_column("Parameter")
        table.add_column("Value")
        
        for key, value in self.db_config.items():
            table.add_row(key, str(value))
        
        console.print(table)

    def ensure_connection(self) -> bool:
        """Ensure database connection is active and reconnect if needed.
        
        Returns:
            bool: True if a valid connection is available, False otherwise
        """
        try:
            # Check if connection exists
            if not self.conn:
                logger.info("No connection exists. Creating new connection.")
                return self.connect()
            
            # Check if connection is closed
            if self.conn.closed:
                logger.info("Connection is closed. Reconnecting...")
                return self.connect()
            
            # Test if connection is still valid
            try:
                # Create a new cursor if needed
                if not self.cursor or self.cursor.closed:
                    self.cursor = self.conn.cursor()
                
                # Simple query to test connection - with timeout to prevent hanging
                self.conn.set_isolation_level(0)  # Set to AUTOCOMMIT to avoid transaction blocks
                self.cursor.execute("SET statement_timeout = 3000")  # 3 second timeout
                self.cursor.execute("SELECT 1")
                result = self.cursor.fetchone()
                self.cursor.execute("RESET statement_timeout")  # Reset timeout
                self.conn.set_isolation_level(2)  # Reset to normal transaction isolation
                
                return bool(result and result[0] == 1)
            except psycopg2.Error as e:
                logger.warning(f"Connection test failed: {e}. Reconnecting...")
                try:
                    self.close()  # Close the invalid connection
                except:
                    pass  # Ignore errors on closing
                return self.connect()  # Try to reconnect
                
        except Exception as e:
            logger.error(f"Error ensuring database connection: {e}")
            # Try one more time with a fresh connection
            try:
                self.close()
            except:
                pass
            return self.connect()

    def execute_safely(self, query: str, params: Optional[Tuple] = None, 
                       commit: bool = True) -> Optional[pg_cursor]:
        """Execute a query safely with proper error handling and transaction management.
        
        Args:
            query: SQL query to execute
            params: Optional parameters for the query
            commit: Whether to commit after execution
            
        Returns:
            Optional[pg_cursor]: Database cursor or None if operation failed
        """
        # Ensure we have a valid connection first
        if not self.ensure_connection():
            logger.error("Failed to establish database connection")
            return None
            
        try:
            if not self.cursor:
                logger.error("Cursor is None, cannot execute query.")
                return None

            if params:
                self.cursor.execute(query, params)
            else:
                self.cursor.execute(query)
                
            if commit and self.conn:
                self.conn.commit()
                
            return self.cursor
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            if self.conn:
                self.conn.rollback()
            return None

    def get_version_sequence(self) -> List[str]:
        """Get the sequence of schema versions."""
        return [
            'v0.1.1',
            'v0.1.2',
            'v0.1.3',
            'v0.1.4',
            'v0.1.5',  # Add new version
            'v0.1.6'
        ]

    def reset_database(self) -> bool:
        """Reset the database to the latest schema version directly.
        
        This method drops all tables and applies the full v0.1.6 schema in one step,
        without going through incremental migrations.
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.ensure_connection():
            self.logger.error("Cannot reset database: no connection")
            return False
            
        try:
            self.logger.warning("Resetting database - all data will be lost!")
            
            # Start a fresh transaction
            if self.conn:
                self.conn.autocommit = False
                
            # Drop all database objects in a clean sweep
            if self.cursor:
                # Drop everything first
                self.cursor.execute("""
                    DO $$ 
                    DECLARE
                        r RECORD;
                    BEGIN
                        -- Disable triggers
                        FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = current_schema()) LOOP
                            EXECUTE 'ALTER TABLE IF EXISTS ' || quote_ident(r.tablename) || ' DISABLE TRIGGER ALL';
                        END LOOP;
                        
                        -- Drop tables with cascade
                        FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = current_schema()) LOOP
                            EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
                        END LOOP;
                        
                        -- Drop custom types
                        FOR r IN (SELECT typname FROM pg_type WHERE typtype = 'c' AND typnamespace = current_schema()::regnamespace) LOOP
                            EXECUTE 'DROP TYPE IF EXISTS ' || quote_ident(r.typname) || ' CASCADE';
                        END LOOP;
                        
                        -- Drop views
                        FOR r IN (SELECT viewname FROM pg_views WHERE schemaname = current_schema()) LOOP
                            EXECUTE 'DROP VIEW IF EXISTS ' || quote_ident(r.viewname) || ' CASCADE';
                        END LOOP;
                    END $$;
                """)
                
                self.logger.info("Successfully dropped all database objects")
                
                # Create the target database structure in one go
                # First, create the base structure for v0.1.0
                self.logger.info("Creating base database schema (v0.1.0)")
                self.cursor.execute(SCHEMA_VERSIONS["v0.1.0"])
                
                # Add the schema v0.1.1 changes
                self.logger.info("Applying schema changes for v0.1.1")
                self.cursor.execute(SCHEMA_VERSIONS["v0.1.1"])
                
                # Add the schema v0.1.2 changes
                self.logger.info("Applying schema changes for v0.1.2")
                self.cursor.execute(SCHEMA_VERSIONS["v0.1.2"])
                
                # Add the schema v0.1.3 changes
                self.logger.info("Applying schema changes for v0.1.3")
                self.cursor.execute(SCHEMA_VERSIONS["v0.1.3"])
                
                # Add the schema v0.1.4 changes
                self.logger.info("Applying schema changes for v0.1.4")
                self.cursor.execute(SCHEMA_VERSIONS["v0.1.4"])
                
                # Add the schema v0.1.5 changes, handling the DO block separately
                self.logger.info("Applying schema changes for v0.1.5")
                
                # Apply standard SQL statements first
                self.cursor.execute("""
                    -- Set proper default for source_references
                    ALTER TABLE cancer_transcript_base
                    ALTER COLUMN source_references SET DEFAULT jsonb_build_object(
                        'go_terms', jsonb_build_array(),
                        'uniprot', jsonb_build_array(),
                        'drugs', jsonb_build_array(),
                        'pathways', jsonb_build_array()
                    );

                    -- Update any existing NULL source_references to the proper default structure
                    UPDATE cancer_transcript_base
                    SET source_references = jsonb_build_object(
                        'go_terms', jsonb_build_array(),
                        'uniprot', jsonb_build_array(),
                        'drugs', jsonb_build_array(),
                        'pathways', jsonb_build_array()
                    )
                    WHERE source_references IS NULL;
                """)
                
                # Apply the DO block separately since it contains exception handling
                self.cursor.execute("""
                    DO $$ BEGIN
                        CREATE TYPE publication_reference AS (
                            pmid text,
                            evidence_type text,
                            source_db text,
                            title text,
                            abstract text,
                            year integer,
                            journal text,
                            authors text[],
                            citation_count integer,
                            doi text,
                            url text
                        );
                    EXCEPTION
                        WHEN duplicate_object THEN null;
                    END $$;
                """)
                
                # Apply the schema v0.1.6 changes
                self.logger.info("Applying schema changes for v0.1.6")
                self.cursor.execute(SCHEMA_VERSIONS["v0.1.6"])
                
                # Apply the schema v0.1.7 changes (PharmGKB pathways)
                self.logger.info("Applying schema changes for v0.1.7")
                self.cursor.execute(SCHEMA_VERSIONS["v0.1.7"])
                
                # Create schema_version table and record that we're at v0.1.7
                self.logger.info("Creating schema_version table with v0.1.7")
                self.cursor.execute("""
                    CREATE TABLE schema_version (
                        version_name TEXT PRIMARY KEY,
                        applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        description TEXT
                    );
                    
                    -- Insert the schema version record directly as v0.1.7
                    INSERT INTO schema_version (version_name, description) 
                    VALUES ('v0.1.7', 'Direct schema reset to v0.1.7 with PharmGKB pathways');
                """)
                
                # Commit all changes
                if self.conn:
                    self.conn.commit()
                    self.conn.autocommit = True
                    
                # Verify the schema is correctly set up
                current_version = self.get_current_version()
                if current_version != "v0.1.7":
                    self.logger.error(f"Schema version mismatch after reset: {current_version} != v0.1.7")
                    return False
                    
                self.logger.info("Database reset completed successfully with schema v0.1.7")
                return True
            else:
                self.logger.error("Database cursor is None, cannot reset database")
                return False
                    
        except Exception as e:
            self.logger.error(f"Database reset failed: {e}")
            if self.conn:
                self.conn.rollback()
                self.conn.autocommit = True
            return False

    def apply_full_schema(self) -> bool:
        """Apply the full schema in one step up to the latest version.
        
        Instead of applying migrations incrementally, this method applies
        the entire schema in one go to ensure consistency.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not self.cursor:
                self.logger.error("No database cursor available")
                return False
                
            self.logger.info(f"Applying full schema up to {MIN_SUPPORTED_VERSION}")
            
            # Apply each schema statement one by one
            # We'll build a combined schema SQL by concatenating all schema versions
            full_schema = ""
            versions = sorted(SCHEMA_VERSIONS.keys())
            
            for version in versions:
                full_schema += f"\n-- Schema version: {version}\n"
                full_schema += SCHEMA_VERSIONS[version]
            
            # Split the combined schema into individual statements
            statements = []
            current_statement = []
            in_do_block = False
            
            for line in full_schema.strip().split('\n'):
                # Check if we're entering a DO block
                if 'DO $$' in line and not in_do_block:
                    in_do_block = True
                    
                # Add current line to the statement
                current_statement.append(line)
                
                # Check if we're exiting a DO block
                if '$$;' in line and in_do_block:
                    in_do_block = False
                    statements.append('\n'.join(current_statement))
                    current_statement = []
                    continue
                    
                # For normal statements, split by semicolon
                if ';' in line and not in_do_block and '$$;' not in line:
                    statements.append('\n'.join(current_statement))
                    current_statement = []
            
            # Add any remaining statement
            if current_statement:
                statements.append('\n'.join(current_statement))
            
            # Execute each statement, ignoring "already exists" errors
            # These can happen when applying parts of schema more than once
            for stmt in statements:
                if stmt.strip():  # Skip empty statements
                    try:
                        self.cursor.execute(stmt)
                    except psycopg2.Error as e:
                        if "already exists" in str(e):
                            self.logger.warning(f"Ignoring 'already exists' error: {e}")
                        else:
                            raise
            
            # Record all schema versions as applied
            for version in versions:
                self.cursor.execute("""
                    INSERT INTO schema_version (version_name)
                    VALUES (%s)
                    ON CONFLICT (version_name) DO UPDATE 
                    SET applied_at = CURRENT_TIMESTAMP
                """, (version,))
            
            # Validate schema to make sure all required columns exist
            if not self.validate_schema():
                raise Exception("Schema validation failed after applying full schema")
                
            self.logger.info(f"Successfully applied full schema up to {MIN_SUPPORTED_VERSION}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to apply full schema: {e}")
            return False
    
    def validate_schema(self) -> bool:
        """Validate that the schema matches the expected structure.
        
        This checks if all expected tables, columns, and indices exist.
        
        Returns:
            bool: True if schema is valid, False otherwise
        """
        try:
            if not self.cursor:
                return False
                
            # Check if cancer_transcript_base table exists
            self.cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'cancer_transcript_base'
                )
            """)
            result = self.cursor.fetchone()
            if not result or not result[0]:
                self.logger.error("cancer_transcript_base table does not exist")
                return False
                
            # Check if all expected columns exist
            expected_columns = [
                'transcript_id', 'gene_symbol', 'gene_id', 'gene_type', 'chromosome', 
                'coordinates', 'product_type', 'go_terms', 'pathways', 'drugs',
                'expression_fold_change', 'expression_freq', 'cancer_types',
                'features', 'molecular_functions', 'cellular_location', 'drug_scores',
                'alt_transcript_ids', 'alt_gene_ids', 'uniprot_ids', 'ncbi_ids', 
                'refseq_ids', 'source_references', 'pdb_ids'
            ]
            
            missing_columns = []
            for column in expected_columns:
                self.cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_name = 'cancer_transcript_base' 
                        AND column_name = %s
                    )
                """, (column,))
                result = self.cursor.fetchone()
                if not result or not result[0]:
                    missing_columns.append(column)
            
            if missing_columns:
                self.logger.error(f"Missing columns in cancer_transcript_base: {', '.join(missing_columns)}")
                return False
                
            # Check if schema_version table exists
            self.cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'schema_version'
                )
            """)
            result = self.cursor.fetchone()
            if not result or not result[0]:
                self.logger.error("schema_version table does not exist")
                return False
                
            # Check if latest version is recorded
            current_version = self.get_current_version()
            if not current_version or current_version < MIN_SUPPORTED_VERSION:
                self.logger.error(f"Schema version {current_version} is below minimum required {MIN_SUPPORTED_VERSION}")
                return False
                
            self.logger.info(f"Schema validation successful - version {current_version}")
            return True
            
        except Exception as e:
            self.logger.error(f"Schema validation failed: {e}")
            return False

    def ensure_schema_version(self, required_version: str) -> bool:
        """Ensure the database schema is at least at the required version.
        
        If the schema is older than the required version, attempt to migrate.
        If migration fails or the version is below v0.1.5, return False.
        
        Args:
            required_version: Minimum required schema version
            
        Returns:
            bool: True if schema version is at or above required version
        """
        try:
            current_version = self.get_current_version()
            
            # Handle case where we can't determine the version
            if not current_version:
                self.logger.error("Could not determine current schema version")
                return False
                
            # Check if current version is below minimum supported
            if current_version < MIN_SUPPORTED_VERSION:
                self.logger.error(f"Current schema version {current_version} is below minimum supported version {MIN_SUPPORTED_VERSION}")
                self.logger.error("Please use reset_database() to create a fresh schema")
                return False
            
            # Compare versions
            versions = list(SCHEMA_VERSIONS.keys())
            
            if current_version not in versions:
                self.logger.error(f"Unknown schema version: {current_version}")
                return False
                
            if required_version not in versions:
                self.logger.error(f"Unknown required version: {required_version}")
                return False
                
            current_idx = versions.index(current_version)
            required_idx = versions.index(required_version)
            
            # If current version is already at or above required, we're good
            if current_idx >= required_idx:
                self.logger.info(f"Schema version check passed: {current_version} >= {required_version}")
                return True
                
            # Try to migrate to the required version
            self.logger.warning(f"Current schema version {current_version} is below required {required_version}")
            self.logger.info(f"Attempting to migrate schema to {required_version}")
            
            if self.migrate_to_version(required_version):
                self.logger.info(f"Migration to {required_version} succeeded")
                return True
            else:
                self.logger.error(f"Failed to migrate database schema to {required_version}")
                return False
                
        except Exception as e:
            self.logger.error(f"Schema version check failed: {e}")
            return False

    def display_config(self) -> None:
        """Alias for print_config for backward compatibility."""
        self.print_config()

def get_db_manager(config: Dict[str, Any]) -> DatabaseManager:
    """Create and initialize a database manager instance.
    
    Args:
        config: Database configuration dictionary
        
    Returns:
            DatabaseManager: Initialized database manager
    """
    manager = DatabaseManager(config)
    manager.connect()
    return manager
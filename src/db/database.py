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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
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
        ALTER TABLE cancer_transcript_base DROP COLUMN publications;
    """
}

class DatabaseManager:
    """Manages database operations including connection, schema, and migrations."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize database manager with configuration.
        
        Args:
            config: Database configuration dictionary with connection parameters
        """
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
                
            # Create version table if it doesn't exist
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    id SERIAL PRIMARY KEY,
                    version TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Get current version
            self.cursor.execute(
                "SELECT version FROM schema_version ORDER BY id DESC LIMIT 1"
            )
            result = self.cursor.fetchone()
            return result[0] if result else None
            
        except psycopg2.Error as e:
            logger.error(f"Version check failed: {e}")
            return None

    def migrate_to_version(self, target_version: str) -> bool:
        """Migrate schema to target version.
        
        Args:
            target_version: Target schema version
            
        Returns:
            bool: True if migration successful
        """
        try:
            current_version = self.get_current_version()
            if current_version == target_version:
                logger.info(f"Already at version {target_version}")
                return True
                
            versions = list(SCHEMA_VERSIONS.keys())
            current_idx = versions.index(current_version) if current_version else -1
            target_idx = versions.index(target_version)
            
            # Apply all migrations between current and target
            for version in versions[current_idx + 1:target_idx + 1]:
                logger.info(f"Migrating to {version}")
                if self.cursor:
                    self.cursor.execute(SCHEMA_VERSIONS[version])
                else:
                    logger.error("Cursor is None, cannot execute migration.")
                    return False
                self.cursor.execute(
                    "INSERT INTO schema_version (version) VALUES (%s)",
                    (version,)
                )
            
            return True
            
        except psycopg2.Error as e:
            logger.error(f"Migration failed: {e}")
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
            result = self.cursor.fetchone()
            row_count = result[0] if result else 0

            # Get table size
            self.cursor.execute("""
                SELECT pg_size_pretty(pg_total_relation_size('cancer_transcript_base')),
                       pg_total_relation_size('cancer_transcript_base') / 1024.0 / 1024.0
                FROM pg_catalog.pg_tables
                WHERE tablename = 'cancer_transcript_base'
            """)
            result = self.cursor.fetchone()
            size_mb = result[1] if result else 0

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
            return bool(self.cursor.fetchone())
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
                
                # Simple query to test connection
                self.cursor.execute("SELECT 1")
                result = self.cursor.fetchone()
                return bool(result and result[0] == 1)
            except psycopg2.Error as e:
                logger.warning(f"Connection test failed: {e}. Reconnecting...")
                self.close()  # Close the invalid connection
                return self.connect()  # Try to reconnect
                
        except Exception as e:
            logger.error(f"Error ensuring database connection: {e}")
            return False
    
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
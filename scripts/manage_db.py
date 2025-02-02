#!/usr/bin/env python3
"""
Database management script for Cancer Transcriptome Base.
Handles connection, schema validation, and migrations.
"""
import sys
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Any, cast
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT, connection as pg_connection, cursor as pg_cursor
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table
import os

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
console = Console()

class DatabaseManager:
    def __init__(self, db_params: Dict[str, Any]):
        self.db_params = db_params
        self.conn: Optional[pg_connection] = None
        self.cursor: Optional[pg_cursor] = None
        
    def connect(self, db_name: Optional[str] = None) -> bool:
        """Establish database connection."""
        try:
            params = self.db_params.copy()
            if db_name:
                params['dbname'] = db_name
            
            # Close existing connection if any
            if self.cursor is not None:
                self.cursor.close()
            if self.conn is not None:
                self.conn.close()

            # Create new connection
            conn = cast(pg_connection, psycopg2.connect(
                host=params['host'],
                port=params['port'],
                user=params['user'],
                password=params['password'],
                dbname=params.get('dbname', 'postgres')
            ))
            
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            self.conn = conn
            self.cursor = self.conn.cursor()
            return True
            
        except psycopg2.Error as e:
            logger.error(f"Connection failed: {e}")
            return False

    def check_db_exists(self) -> bool:
        """Check if database exists."""
        try:
            if self.cursor is None:
                return False
            self.cursor.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (self.db_params['dbname'],)
            )
            return bool(self.cursor.fetchone())
        except psycopg2.Error as e:
            logger.error(f"Database check failed: {e}")
            return False

    def create_database(self) -> bool:
        """Create the database if it doesn't exist."""
        try:
            if self.cursor is None:
                return False
            self.cursor.execute(
                f"CREATE DATABASE {self.db_params['dbname']}"
            )
            return True
        except psycopg2.Error as e:
            logger.error(f"Database creation failed: {e}")
            return False

    def drop_database(self) -> bool:
        """Drop the database."""
        try:
            if self.cursor is None:
                return False
            self.cursor.execute(
                f"DROP DATABASE IF EXISTS {self.db_params['dbname']}"
            )
            return True
        except psycopg2.Error as e:
            logger.error(f"Database drop failed: {e}")
            return False

    def get_current_schema_version(self) -> Optional[str]:
        """Get current schema version from database."""
        try:
            if self.cursor is None:
                return None
            self.cursor.execute(
                "SELECT version FROM schema_version ORDER BY id DESC LIMIT 1"
            )
            result = self.cursor.fetchone()
            return result[0] if result else None
        except psycopg2.Error:
            return None

    def create_schema(self, version: str) -> bool:
        """Create schema for specified version."""
        try:
            if self.cursor is None:
                return False
                
            # Create version tracking table
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    id SERIAL PRIMARY KEY,
                    version TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create main table based on README schema
            self.cursor.execute("""
                CREATE TABLE cancer_transcript_base (
                    transcript_id TEXT PRIMARY KEY,
                    gene_symbol TEXT,
                    gene_id TEXT,
                    gene_type TEXT,
                    chromosome TEXT,
                    coordinates JSONB,
                    product_type TEXT[],
                    cellular_location TEXT[],
                    go_terms JSONB,
                    pathways TEXT[],
                    drugs JSONB,
                    drug_scores JSONB,
                    publications JSONB,
                    expression_fold_change FLOAT DEFAULT 1.0,
                    expression_freq JSONB DEFAULT '{"high": [], "low": []}',
                    cancer_types TEXT[] DEFAULT '{}'
                )
            """)

            # Create indices
            self.cursor.execute(
                "CREATE INDEX idx_gene_symbol ON cancer_transcript_base(gene_symbol)"
            )
            self.cursor.execute(
                "CREATE INDEX idx_gene_id ON cancer_transcript_base(gene_id)"
            )
            self.cursor.execute(
                "CREATE INDEX idx_drugs ON cancer_transcript_base USING GIN(drugs)"
            )
            self.cursor.execute(
                "CREATE INDEX idx_product_type ON cancer_transcript_base USING GIN(product_type)"
            )
            self.cursor.execute(
                "CREATE INDEX idx_pathways ON cancer_transcript_base USING GIN(pathways)"
            )

            # Record schema version
            self.cursor.execute(
                "INSERT INTO schema_version (version) VALUES (%s)",
                (version,)
            )
            return True
        except psycopg2.Error as e:
            logger.error(f"Schema creation failed: {e}")
            return False

def load_config() -> Dict[str, Any]:
    """Load database configuration from environment variables."""
    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "dbname": os.getenv("POSTGRES_DB", "mediabase"),
        "user": os.getenv("POSTGRES_USER", "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", "postgres")
    }

def interactive_setup(db_manager: DatabaseManager) -> None:
    """Interactive database setup flow."""
    console.print("[bold]Cancer Transcriptome Base - Database Setup[/bold]\n")

    # Check initial connection
    if not db_manager.connect():
        console.print("[red]Failed to connect to PostgreSQL. Please check credentials.[/red]")
        return

    # Check if database exists
    db_exists = db_manager.check_db_exists()
    current_version = None

    if db_exists:
        if db_manager.connect(db_manager.db_params['dbname']):
            current_version = db_manager.get_current_schema_version()
            
        table = Table(title="Database Status")
        table.add_column("Component")
        table.add_column("Status")
        table.add_row("Database", "[green]Exists[/green]" if db_exists else "[red]Missing[/red]")
        table.add_row("Schema Version", str(current_version) if current_version else "[yellow]Unknown[/yellow]")
        console.print(table)
        
        if Confirm.ask("Database exists. Do you want to reset it?"):
            if db_manager.drop_database():
                console.print("[green]Database dropped successfully[/green]")
                db_exists = False
            else:
                console.print("[red]Failed to drop database[/red]")
                return

    if not db_exists:
        if db_manager.create_database():
            console.print("[green]Database created successfully[/green]")
            if db_manager.connect(db_manager.db_params['dbname']):
                if db_manager.create_schema("v0.1.1"):
                    console.print("[green]Schema created successfully[/green]")
                else:
                    console.print("[red]Schema creation failed[/red]")
        else:
            console.print("[red]Database creation failed[/red]")

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Database management tool")
    parser.add_argument("--non-interactive", action="store_true", help="Run in non-interactive mode")
    args = parser.parse_args()

    config = load_config()
    db_manager = DatabaseManager(config)

    if args.non_interactive:
        if not db_manager.connect() or not db_manager.check_db_exists():
            sys.exit(1)
        sys.exit(0)
    else:
        interactive_setup(db_manager)

if __name__ == "__main__":
    main()

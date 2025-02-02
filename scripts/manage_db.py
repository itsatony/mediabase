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
from dotenv import load_dotenv

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

    def _ensure_default_connection(self) -> bool:
        """Ensure connection to default postgres database."""
        try:
            # Close any existing connection
            if self.cursor is not None:
                self.cursor.close()
            if self.conn is not None:
                self.conn.close()
                self.conn = None
            self.cursor = None
            
            # Connect to default postgres database
            conn = cast(pg_connection, psycopg2.connect(
                host=self.db_params['host'],
                port=self.db_params['port'],
                user=self.db_params['user'],
                password=self.db_params['password'],
                dbname='postgres'
            ))
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            self.conn = conn
            self.cursor = self.conn.cursor()
            return True
        except psycopg2.Error as e:
            logger.error(f"Failed to connect to default database: {e}")
            return False

    def drop_database(self) -> bool:
        """Drop the database with improved connection handling."""
        try:
            # First ensure we're connected to postgres database
            if not self._ensure_default_connection():
                return False

            if self.cursor is None:
                return False

            # Force close other connections
            self.cursor.execute(f"""
                SELECT pg_terminate_backend(pid) 
                FROM pg_stat_activity 
                WHERE datname = %s AND pid != pg_backend_pid()
            """, (self.db_params['dbname'],))
            
            # Small delay to ensure connections are closed
            import time
            time.sleep(1)
            
            # Try to drop the database
            self.cursor.execute(f"DROP DATABASE IF EXISTS {self.db_params['dbname']}")
            return True
            
        except psycopg2.Error as e:
            if "ERROR: database" in str(e) and "does not exist" in str(e):
                # If database doesn't exist, that's fine
                return True
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
            
            # Create main table based on latest schema (v0.1.2)
            self.cursor.execute("""
                CREATE TABLE cancer_transcript_base (
                    transcript_id TEXT PRIMARY KEY,
                    gene_symbol TEXT,
                    gene_id TEXT,
                    gene_type TEXT,
                    chromosome TEXT,
                    coordinates JSONB,
                    product_type TEXT[],
                    features JSONB DEFAULT '{}'::jsonb,
                    molecular_functions TEXT[] DEFAULT '{}',
                    cellular_location TEXT[],
                    go_terms JSONB,
                    pathways TEXT[],
                    drugs JSONB,
                    drug_scores JSONB,
                    publications JSONB,
                    expression_fold_change FLOAT DEFAULT 1.0,
                    expression_freq JSONB DEFAULT '{"high": [], "low": []}'::jsonb,
                    cancer_types TEXT[] DEFAULT '{}'
                )
            """)

            # Create all indices
            self.cursor.execute("""
                CREATE INDEX idx_gene_symbol ON cancer_transcript_base(gene_symbol);
                CREATE INDEX idx_gene_id ON cancer_transcript_base(gene_id);
                CREATE INDEX idx_drugs ON cancer_transcript_base USING GIN(drugs);
                CREATE INDEX idx_product_type ON cancer_transcript_base USING GIN(product_type);
                CREATE INDEX idx_pathways ON cancer_transcript_base USING GIN(pathways);
                CREATE INDEX idx_features ON cancer_transcript_base USING GIN(features);
                CREATE INDEX idx_molecular_functions ON cancer_transcript_base USING GIN(molecular_functions)
            """)

            # Record schema version
            self.cursor.execute(
                "INSERT INTO schema_version (version) VALUES (%s)",
                ('v0.1.2',)
            )
            return True
            
        except psycopg2.Error as e:
            logger.error(f"Schema creation failed: {e}")
            return False

    def update_schema_to_v012(self) -> bool:
        """Update schema to version 0.1.2."""
        try:
            if self.cursor is None:
                return False
                
            # Add new columns and modify existing ones
            self.cursor.execute("""
                ALTER TABLE cancer_transcript_base
                ADD COLUMN IF NOT EXISTS features JSONB DEFAULT '{}'::jsonb,
                ADD COLUMN IF NOT EXISTS molecular_functions TEXT[] DEFAULT '{}';
                
                -- Create new indices
                CREATE INDEX IF NOT EXISTS idx_features 
                ON cancer_transcript_base USING GIN(features);
                CREATE INDEX IF NOT EXISTS idx_molecular_functions 
                ON cancer_transcript_base USING GIN(molecular_functions);
            """)
            
            # Update schema version
            self.cursor.execute(
                "INSERT INTO schema_version (version) VALUES (%s)",
                ('v0.1.2',)
            )
            return True
            
        except psycopg2.Error as e:
            logger.error(f"Schema update failed: {e}")
            return False

    def reset_database(self) -> bool:
        """Reset database to latest schema version."""
        try:
            if self.drop_database() and self.create_database():
                if self.connect(self.db_params['dbname']):
                    return self.create_schema('v0.1.2')
            return False
        except Exception as e:
            logger.error(f"Reset failed: {e}")
            return False

    def dump_database(self, output_file: str) -> bool:
        """Dump database to a file."""
        try:
            import subprocess
            
            env = os.environ.copy()
            env['PGPASSWORD'] = self.db_params['password']
            
            cmd = [
                'pg_dump',
                '-h', self.db_params['host'],
                '-p', str(self.db_params['port']),
                '-U', self.db_params['user'],
                '-F', 'c',  # Custom format
                '-f', output_file,
                self.db_params['dbname']
            ]
            
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
            
            if result.returncode == 0:
                return True
            else:
                logger.error(f"Dump failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Dump failed: {e}")
            return False

    def restore_database(self, input_file: str) -> bool:
        """Restore database from a dump file."""
        try:
            # First ensure we're starting fresh
            self._ensure_default_connection()
            self.drop_database()
            self.create_database()
            
            import subprocess
            
            env = os.environ.copy()
            env['PGPASSWORD'] = self.db_params['password']
            
            cmd = [
                'pg_restore',
                '-h', self.db_params['host'],
                '-p', str(self.db_params['port']),
                '-U', self.db_params['user'],
                '-d', self.db_params['dbname'],
                input_file
            ]
            
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
            
            if result.returncode == 0:
                return True
            else:
                logger.error(f"Restore failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Restore failed: {e}")
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

            # Get table size in MB
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

class DatabaseMenu:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.choices = {
            '1': ('Check database status', self.check_status),
            '2': ('Reset database', self.reset_database),
            '3': ('Backup database', self.backup_database),
            '4': ('Restore database', self.restore_database),
            '5': ('Exit', self.exit_program)
        }

    def display_menu(self):
        console.clear()
        console.print("[bold]Cancer Transcriptome Base - Database Management[/bold]\n")
        for key, (option, _) in self.choices.items():
            console.print(f"[bold]{key}[/bold]. {option}")
        return console.input("\n[bold]Choose an option:[/bold] ")

    def check_status(self):
        if not self.db_manager.connect():
            console.print("[red]Failed to connect to PostgreSQL.[/red]")
            return

        db_exists = self.db_manager.check_db_exists()
        current_version = None
        table_stats = {"row_count": 0, "size_mb": 0}

        if db_exists and self.db_manager.connect(self.db_manager.db_params['dbname']):
            current_version = self.db_manager.get_current_schema_version()
            table_stats = self.db_manager.get_table_stats()

        table = Table(title="Database Status")
        table.add_column("Component")
        table.add_column("Status")
        table.add_row("Database", "[green]Exists[/green]" if db_exists else "[red]Missing[/red]")
        table.add_row("Schema Version", str(current_version) if current_version else "[yellow]Unknown[/yellow]")
        table.add_row("Records", f"{table_stats['row_count']:,}")
        table.add_row("Table Size", f"{table_stats['size_mb']} MB")
        console.print(table)
        input("\nPress Enter to continue...")

    def reset_database(self):
        if Confirm.ask("Are you sure you want to reset the database? This will delete all data!"):
            if self.db_manager.drop_database():
                console.print("[green]Database dropped successfully[/green]")
                if self.db_manager.create_database():
                    console.print("[green]Database created successfully[/green]")
                    if self.db_manager.connect(self.db_manager.db_params['dbname']):
                        if self.db_manager.create_schema("v0.1.1"):
                            console.print("[green]Schema created successfully[/green]")
        input("\nPress Enter to continue...")

    def backup_database(self):
        output_file = console.input("Enter backup file path (default: backup.dump): ").strip() or "backup.dump"
        if self.db_manager.dump_database(output_file):
            console.print(f"[green]Database backed up successfully to {output_file}[/green]")
        else:
            console.print("[red]Backup failed[/red]")
        input("\nPress Enter to continue...")

    def restore_database(self):
        input_file = console.input("Enter backup file path: ").strip()
        if not input_file or not os.path.exists(input_file):
            console.print("[red]Invalid backup file[/red]")
        elif Confirm.ask("This will overwrite the current database. Continue?"):
            if self.db_manager.restore_database(input_file):
                console.print("[green]Database restored successfully[/green]")
            else:
                console.print("[red]Restore failed[/red]")
        input("\nPress Enter to continue...")

    def exit_program(self):
        console.print("[bold]Goodbye![/bold]")
        sys.exit(0)

    def run(self):
        # Run status check on startup
        self.check_status()
        
        while True:
            choice = self.display_menu()
            if choice in self.choices:
                self.choices[choice][1]()
            else:
                console.print("[red]Invalid choice[/red]")
                input("\nPress Enter to continue...")

def load_config() -> Dict[str, Any]:
    """Load database configuration from environment variables."""
    # Attempt to load .env file from project root
    project_root = Path(__file__).parent.parent
    env_path = project_root / '.env'
    load_dotenv(env_path)

    # Check if required environment variables are set
    required_vars = ['MB_POSTGRES_HOST', 'MB_POSTGRES_PORT', 'MB_POSTGRES_NAME', 
                    'MB_POSTGRES_USER', 'MB_POSTGRES_PASSWORD']
    missing_vars = [var for var in required_vars if var not in os.environ]
    if missing_vars:
        console.print(f"[red]Missing required environment variables: {', '.join(missing_vars)}[/red]")
        sys.exit(1)

    # Now get environment variables with fallbacks
    return {
        "host": os.environ.get("MB_POSTGRES_HOST", "localhost"),
        "port": int(os.environ.get("MB_POSTGRES_PORT", "5432")),
        "dbname": os.environ.get("MB_POSTGRES_NAME", "mediabase"),
        "user": os.environ.get("MB_POSTGRES_USER", "postgres"),
        "password": os.environ.get("MB_POSTGRES_PASSWORD", "postgres")
    }

def interactive_setup(db_manager: DatabaseManager) -> None:
    """Interactive database management interface."""
    menu = DatabaseMenu(db_manager)
    menu.run()

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Database management tool")
    parser.add_argument("--non-interactive", action="store_true", help="Run in non-interactive mode")
    parser.add_argument("--backup", help="Backup database to specified file")
    parser.add_argument("--restore", help="Restore database from specified file")
    args = parser.parse_args()

    config = load_config()
    db_manager = DatabaseManager(config)

    if args.backup:
        if db_manager.dump_database(args.backup):
            console.print(f"[green]Database backed up to {args.backup}[/green]")
            sys.exit(0)
        sys.exit(1)
    elif args.restore:
        if db_manager.restore_database(args.restore):
            console.print(f"[green]Database restored from {args.restore}[/green]")
            sys.exit(0)
        sys.exit(1)
    elif args.non_interactive:
        if not db_manager.connect() or not db_manager.check_db_exists():
            sys.exit(1)
        sys.exit(0)
    else:
        interactive_setup(db_manager)

if __name__ == "__main__":
    main()

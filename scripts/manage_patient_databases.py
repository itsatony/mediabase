#!/usr/bin/env python3
"""Manage Patient Database Copies.

This script provides functionality to list, inspect, and delete patient-specific
MEDIABASE database copies created by the patient copy system.

Usage:
    poetry run python scripts/manage_patient_databases.py --list
    poetry run python scripts/manage_patient_databases.py --delete PATIENT123
    poetry run python scripts/manage_patient_databases.py --info PATIENT123
    poetry run python scripts/manage_patient_databases.py --cleanup --older-than 30

The script will:
1. Connect to PostgreSQL and identify patient databases
2. Display database information including size and creation date
3. Provide safe deletion with confirmation prompts
4. Support bulk cleanup operations
"""

import argparse
import logging
import sys
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timedelta

import psycopg2
from psycopg2.extensions import connection as pg_connection
from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm
from rich.panel import Panel
from rich.text import Text

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from src.db.database import get_db_manager, DatabaseManager
from src.utils.logging import setup_logging

# Constants
PATIENT_DB_PREFIX = "mediabase_patient_"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

class PatientDatabaseManager:
    """Manages patient-specific database copies."""
    
    def __init__(self, db_config: Dict[str, Any]):
        """Initialize the patient database manager.
        
        Args:
            db_config: Database configuration for PostgreSQL connection
        """
        self.db_config = db_config
        self.console = Console()
        self.logger = logging.getLogger(__name__)
    
    def list_patient_databases(self, show_details: bool = True) -> List[Dict[str, Any]]:
        """List all patient databases.
        
        Args:
            show_details: Whether to fetch detailed information
            
        Returns:
            List of patient database information dictionaries
        """
        try:
            # Connect to postgres database to query all databases
            postgres_config = self.db_config.copy()
            postgres_config['dbname'] = 'postgres'
            
            conn = psycopg2.connect(**postgres_config)
            
            with conn.cursor() as cursor:
                # Query for patient databases with details
                query = """
                SELECT 
                    datname,
                    pg_size_pretty(pg_database_size(datname)) as size,
                    datcollate,
                    datconnlimit,
                    (SELECT count(*) FROM pg_stat_activity WHERE datname = d.datname) as connections
                FROM pg_database d
                WHERE datname LIKE %s
                ORDER BY datname
                """
                
                cursor.execute(query, (f"{PATIENT_DB_PREFIX}%",))
                databases = cursor.fetchall()
                
                # Process results
                patient_dbs = []
                for db_name, size, collate, conn_limit, active_conns in databases:
                    patient_id = db_name[len(PATIENT_DB_PREFIX):]
                    
                    db_info = {
                        'database_name': db_name,
                        'patient_id': patient_id,
                        'size': size,
                        'collate': collate,
                        'connection_limit': conn_limit,
                        'active_connections': active_conns
                    }
                    
                    if show_details:
                        # Get additional details by connecting to the database
                        try:
                            detail_info = self._get_database_details(db_name)
                            db_info.update(detail_info)
                        except Exception as e:
                            self.logger.warning(f"Could not get details for {db_name}: {e}")
                            db_info['transcript_count'] = 'Unknown'
                            db_info['modified_transcripts'] = 'Unknown'
                            db_info['schema_version'] = 'Unknown'
                    
                    patient_dbs.append(db_info)
                
                return patient_dbs
                
        except Exception as e:
            self.logger.error(f"Failed to list patient databases: {e}")
            raise
        finally:
            if 'conn' in locals():
                conn.close()
    
    def _get_database_details(self, db_name: str) -> Dict[str, Any]:
        """Get detailed information about a patient database.
        
        Args:
            db_name: Name of the patient database
            
        Returns:
            Dictionary with detailed database information
        """
        patient_config = self.db_config.copy()
        patient_config['dbname'] = db_name
        
        try:
            patient_db = get_db_manager(patient_config)
            
            with patient_db.transaction() as cursor:
                # Get transcript count
                cursor.execute("SELECT COUNT(*) FROM cancer_transcript_base")
                total_transcripts = cursor.fetchone()[0]
                
                # Get modified transcripts (non-default fold change)
                cursor.execute(
                    "SELECT COUNT(*) FROM cancer_transcript_base WHERE expression_fold_change != 1.0"
                )
                modified_transcripts = cursor.fetchone()[0]
                
                # Get schema version
                try:
                    cursor.execute("SELECT version_name FROM schema_version ORDER BY applied_at DESC LIMIT 1")
                    schema_version = cursor.fetchone()[0]
                except:
                    schema_version = "Unknown"
                
                # Get creation/modification time (approximate)
                cursor.execute("""
                    SELECT pg_stat_file('base/' || oid || '/PG_VERSION')
                    FROM pg_database WHERE datname = %s
                """, (db_name,))
                
                try:
                    stat_info = cursor.fetchone()
                    if stat_info and stat_info[0]:
                        # Parse the stat tuple (size, access_time, modify_time, change_time, creation_time, isdir)
                        creation_time = datetime.fromtimestamp(stat_info[0][4])
                    else:
                        creation_time = None
                except:
                    creation_time = None
                
                return {
                    'transcript_count': total_transcripts,
                    'modified_transcripts': modified_transcripts,
                    'schema_version': schema_version,
                    'creation_time': creation_time
                }
                
        except Exception as e:
            self.logger.warning(f"Could not get details for {db_name}: {e}")
            return {
                'transcript_count': 'Error',
                'modified_transcripts': 'Error',
                'schema_version': 'Error',
                'creation_time': None
            }
    
    def display_patient_databases(self, patient_dbs: List[Dict[str, Any]]) -> None:
        """Display patient databases in a formatted table.
        
        Args:
            patient_dbs: List of patient database information
        """
        if not patient_dbs:
            self.console.print("[yellow]No patient databases found.[/yellow]")
            return
        
        table = Table(title="Patient Database Copies")
        table.add_column("Patient ID", style="cyan", no_wrap=True)
        table.add_column("Database", style="blue", no_wrap=True)
        table.add_column("Size", style="green", justify="right")
        table.add_column("Transcripts", style="yellow", justify="right")
        table.add_column("Modified", style="magenta", justify="right")
        table.add_column("Schema", style="white", no_wrap=True)
        table.add_column("Active Conn.", style="red", justify="right")
        table.add_column("Created", style="dim", no_wrap=True)
        
        for db_info in patient_dbs:
            creation_str = "Unknown"
            if db_info.get('creation_time'):
                creation_str = db_info['creation_time'].strftime("%Y-%m-%d %H:%M")
            
            table.add_row(
                db_info['patient_id'],
                db_info['database_name'],
                str(db_info['size']),
                str(db_info['transcript_count']),
                str(db_info['modified_transcripts']),
                str(db_info['schema_version']),
                str(db_info['active_connections']),
                creation_str
            )
        
        self.console.print(table)
        
        # Summary statistics
        total_size = sum(1 for db in patient_dbs)  # Count of databases
        total_modified = sum(
            int(db['modified_transcripts']) 
            for db in patient_dbs 
            if isinstance(db['modified_transcripts'], int)
        )
        
        self.console.print(f"\n[bold]Summary:[/bold] {total_size} patient databases found")
        if total_modified > 0:
            self.console.print(f"Total modified transcripts across all patients: {total_modified:,}")
    
    def get_database_info(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific patient database.
        
        Args:
            patient_id: The patient identifier
            
        Returns:
            Database information dictionary or None if not found
        """
        patient_dbs = self.list_patient_databases(show_details=True)
        
        for db_info in patient_dbs:
            if db_info['patient_id'] == patient_id:
                return db_info
        
        return None
    
    def display_database_info(self, patient_id: str) -> None:
        """Display detailed information about a specific patient database.
        
        Args:
            patient_id: The patient identifier
        """
        db_info = self.get_database_info(patient_id)
        
        if not db_info:
            self.console.print(f"[red]Patient database '{patient_id}' not found.[/red]")
            return
        
        # Create detailed info panel
        info_text = Text()
        info_text.append(f"Patient ID: ", style="bold cyan")
        info_text.append(f"{db_info['patient_id']}\n")
        
        info_text.append(f"Database Name: ", style="bold cyan")
        info_text.append(f"{db_info['database_name']}\n")
        
        info_text.append(f"Size: ", style="bold cyan")
        info_text.append(f"{db_info['size']}\n")
        
        info_text.append(f"Schema Version: ", style="bold cyan")
        info_text.append(f"{db_info['schema_version']}\n")
        
        info_text.append(f"Total Transcripts: ", style="bold cyan")
        info_text.append(f"{db_info['transcript_count']:,}\n")
        
        info_text.append(f"Modified Transcripts: ", style="bold cyan")
        info_text.append(f"{db_info['modified_transcripts']:,}\n")
        
        info_text.append(f"Active Connections: ", style="bold cyan")
        info_text.append(f"{db_info['active_connections']}\n")
        
        if db_info.get('creation_time'):
            info_text.append(f"Created: ", style="bold cyan")
            info_text.append(f"{db_info['creation_time'].strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        panel = Panel(info_text, title=f"Patient Database: {patient_id}", border_style="blue")
        self.console.print(panel)
        
        # Show sample of modified transcripts
        if isinstance(db_info['modified_transcripts'], int) and db_info['modified_transcripts'] > 0:
            self._display_sample_transcripts(db_info['database_name'])
    
    def _display_sample_transcripts(self, db_name: str, limit: int = 10) -> None:
        """Display sample of modified transcripts.
        
        Args:
            db_name: Name of the patient database
            limit: Number of sample transcripts to show
        """
        try:
            patient_config = self.db_config.copy()
            patient_config['dbname'] = db_name
            
            patient_db = get_db_manager(patient_config)
            
            with patient_db.transaction() as cursor:
                cursor.execute("""
                    SELECT transcript_id, gene_symbol, expression_fold_change
                    FROM cancer_transcript_base 
                    WHERE expression_fold_change != 1.0 
                    ORDER BY ABS(expression_fold_change - 1.0) DESC
                    LIMIT %s
                """, (limit,))
                
                samples = cursor.fetchall()
                
                if samples:
                    table = Table(title=f"Sample Modified Transcripts (Top {len(samples)})")
                    table.add_column("Transcript ID", style="cyan")
                    table.add_column("Gene Symbol", style="yellow")
                    table.add_column("Fold Change", style="green", justify="right")
                    
                    for transcript_id, gene_symbol, fold_change in samples:
                        table.add_row(
                            transcript_id,
                            gene_symbol or "N/A",
                            f"{fold_change:.4f}"
                        )
                    
                    self.console.print(table)
                    
        except Exception as e:
            self.logger.warning(f"Could not display sample transcripts: {e}")
    
    def delete_patient_database(self, patient_id: str, force: bool = False) -> bool:
        """Delete a patient database with confirmation.
        
        Args:
            patient_id: The patient identifier
            force: Skip confirmation prompt
            
        Returns:
            True if deletion was successful, False otherwise
        """
        db_name = f"{PATIENT_DB_PREFIX}{patient_id}"
        
        # Check if database exists
        db_info = self.get_database_info(patient_id)
        if not db_info:
            self.console.print(f"[red]Patient database '{patient_id}' not found.[/red]")
            return False
        
        # Display database info before deletion
        self.console.print(f"\n[bold yellow]Database to be deleted:[/bold yellow]")
        self.display_database_info(patient_id)
        
        # Confirmation prompt
        if not force:
            if not Confirm.ask(
                f"\n[bold red]Are you sure you want to delete patient database '{patient_id}'?[/bold red]\n"
                f"This action cannot be undone."
            ):
                self.console.print("[yellow]Deletion cancelled.[/yellow]")
                return False
        
        try:
            # Connect to postgres database to drop the patient database
            postgres_config = self.db_config.copy()
            postgres_config['dbname'] = 'postgres'
            
            conn = psycopg2.connect(**postgres_config)
            conn.autocommit = True
            
            with conn.cursor() as cursor:
                # Terminate any active connections to the database
                cursor.execute("""
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = %s AND pid <> pg_backend_pid()
                """, (db_name,))
                
                # Drop the database
                cursor.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
                
            self.console.print(f"[green]✓ Patient database '{patient_id}' deleted successfully.[/green]")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to delete patient database '{patient_id}': {e}")
            self.console.print(f"[red]✗ Failed to delete database: {e}[/red]")
            return False
        finally:
            if 'conn' in locals():
                conn.close()
    
    def cleanup_old_databases(self, days_old: int, dry_run: bool = False) -> int:
        """Clean up patient databases older than specified days.
        
        Args:
            days_old: Delete databases older than this many days
            dry_run: Show what would be deleted without actually deleting
            
        Returns:
            Number of databases deleted (or would be deleted in dry run)
        """
        cutoff_date = datetime.now() - timedelta(days=days_old)
        patient_dbs = self.list_patient_databases(show_details=True)
        
        old_databases = []
        for db_info in patient_dbs:
            if db_info.get('creation_time') and db_info['creation_time'] < cutoff_date:
                old_databases.append(db_info)
        
        if not old_databases:
            self.console.print(f"[green]No patient databases older than {days_old} days found.[/green]")
            return 0
        
        # Display databases to be deleted
        self.console.print(f"\n[bold yellow]Patient databases older than {days_old} days:[/bold yellow]")
        self.display_patient_databases(old_databases)
        
        if dry_run:
            self.console.print(f"\n[yellow]Dry run: {len(old_databases)} databases would be deleted.[/yellow]")
            return len(old_databases)
        
        # Confirmation for bulk deletion
        if not Confirm.ask(
            f"\n[bold red]Delete {len(old_databases)} patient databases?[/bold red]\n"
            f"This action cannot be undone."
        ):
            self.console.print("[yellow]Cleanup cancelled.[/yellow]")
            return 0
        
        # Delete databases
        deleted_count = 0
        for db_info in old_databases:
            if self.delete_patient_database(db_info['patient_id'], force=True):
                deleted_count += 1
        
        self.console.print(f"\n[green]✓ Cleanup complete: {deleted_count}/{len(old_databases)} databases deleted.[/green]")
        return deleted_count

def main():
    """Main entry point for the patient database management script."""
    parser = argparse.ArgumentParser(
        description="Manage patient-specific MEDIABASE database copies",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --list                          # List all patient databases
  %(prog)s --info PATIENT123              # Show details for specific patient
  %(prog)s --delete PATIENT123            # Delete patient database with confirmation
  %(prog)s --delete PATIENT123 --force    # Delete without confirmation
  %(prog)s --cleanup --older-than 30      # Delete databases older than 30 days
  %(prog)s --cleanup --older-than 7 --dry-run  # Preview cleanup without deleting
        """
    )
    
    # Main actions (mutually exclusive)
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument(
        "--list",
        action="store_true",
        help="List all patient databases"
    )
    
    action_group.add_argument(
        "--info",
        metavar="PATIENT_ID",
        help="Show detailed information for specific patient database"
    )
    
    action_group.add_argument(
        "--delete",
        metavar="PATIENT_ID",
        help="Delete specific patient database"
    )
    
    action_group.add_argument(
        "--cleanup",
        action="store_true",
        help="Clean up old patient databases (use with --older-than)"
    )
    
    # Optional arguments
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompts (use with --delete)"
    )
    
    parser.add_argument(
        "--older-than",
        type=int,
        metavar="DAYS",
        help="Days threshold for cleanup (use with --cleanup)"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes (use with --cleanup)"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)"
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.cleanup and not args.older_than:
        parser.error("--cleanup requires --older-than DAYS")
    
    if args.force and not args.delete:
        parser.error("--force can only be used with --delete")
    
    if args.dry_run and not args.cleanup:
        parser.error("--dry-run can only be used with --cleanup")
    
    # Setup logging
    setup_logging(log_level=args.log_level)
    logger = logging.getLogger(__name__)
    console = Console()
    
    try:
        # Get database configuration
        db_config = {
            'host': os.getenv('MB_POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('MB_POSTGRES_PORT', 5435)),
            'dbname': 'postgres',  # We connect to postgres to manage other databases
            'user': os.getenv('MB_POSTGRES_USER', 'mbase_user'),
            'password': os.getenv('MB_POSTGRES_PASSWORD', 'mbase_secret')
        }
        
        # Create patient database manager
        manager = PatientDatabaseManager(db_config)
        
        # Execute requested action
        if args.list:
            console.print("[bold blue]MEDIABASE Patient Database Management[/bold blue]")
            patient_dbs = manager.list_patient_databases()
            manager.display_patient_databases(patient_dbs)
            
        elif args.info:
            console.print(f"[bold blue]Patient Database Information[/bold blue]")
            manager.display_database_info(args.info)
            
        elif args.delete:
            console.print(f"[bold blue]Delete Patient Database[/bold blue]")
            success = manager.delete_patient_database(args.delete, force=args.force)
            sys.exit(0 if success else 1)
            
        elif args.cleanup:
            console.print(f"[bold blue]Patient Database Cleanup[/bold blue]")
            deleted_count = manager.cleanup_old_databases(args.older_than, dry_run=args.dry_run)
            if not args.dry_run:
                console.print(f"[green]Cleanup completed: {deleted_count} databases deleted.[/green]")
            
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation interrupted by user[/yellow]")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Operation failed: {e}")
        console.print(f"\n[bold red]✗ Error: {e}[/bold red]")
        sys.exit(1)

if __name__ == "__main__":
    main()
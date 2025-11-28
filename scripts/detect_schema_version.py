#!/usr/bin/env python3
"""
Schema Version Detection Utility for MEDIABASE

Automatically detects whether a database uses:
- v0.5.0 architecture (database-per-patient)
- v0.6.0 architecture (schema-per-patient with shared core)

Usage:
    poetry run python scripts/detect_schema_version.py --database mbase
    poetry run python scripts/detect_schema_version.py --host localhost --port 5435 --database mbase --user mbase_user
    poetry run python scripts/detect_schema_version.py --all-databases

Author: MEDIABASE Development Team
Version: 0.6.0
"""

import argparse
import os
import sys
from typing import Dict, List, Tuple, Optional
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2
from psycopg2 import sql
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()


class SchemaVersionDetector:
    """Detects MEDIABASE schema version and architecture type."""

    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str
    ):
        """
        Initialize detector with database connection parameters.

        Args:
            host: PostgreSQL host
            port: PostgreSQL port
            database: Database name to analyze
            user: Database user
            password: Database password
        """
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.conn = None
        self.cursor = None

    def connect(self) -> bool:
        """
        Establish database connection.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password
            )
            self.cursor = self.conn.cursor()
            return True
        except psycopg2.Error as e:
            console.print(f"[red]ERROR:[/red] Failed to connect to database: {e}")
            return False

    def close(self) -> None:
        """Close database connection."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()

    def detect_version(self) -> Tuple[str, Dict]:
        """
        Detect schema version and architecture type.

        Returns:
            Tuple of (version_string, metadata_dict)
        """
        # Check for v0.6.0 indicators
        has_public_genes = self._check_table_exists('public', 'genes')
        has_public_transcripts = self._check_table_exists('public', 'transcripts')
        patient_schemas = self._find_patient_schemas()

        # Check for v0.5.0 indicators
        has_cancer_transcript_base = self._check_table_exists('public', 'cancer_transcript_base')

        metadata = {
            'database_name': self.database,
            'patient_schemas': patient_schemas,
            'has_public_genes': has_public_genes,
            'has_public_transcripts': has_public_transcripts,
            'has_cancer_transcript_base': has_cancer_transcript_base,
            'total_patient_schemas': len(patient_schemas)
        }

        # Determine version
        if patient_schemas and has_public_genes and has_public_transcripts:
            # v0.6.0: Schema-per-patient with shared core
            version = "v0.6.0"
            metadata['architecture'] = "Shared Core (Schema-per-Patient)"
            metadata['storage_model'] = "Sparse (only fold_change != 1.0)"

            # Validate patient schema structure
            if patient_schemas:
                sample_schema = patient_schemas[0]
                has_expression_data = self._check_table_exists(sample_schema, 'expression_data')
                has_metadata = self._check_table_exists(sample_schema, 'metadata')
                metadata['patient_schema_valid'] = has_expression_data and has_metadata

        elif has_cancer_transcript_base and not patient_schemas:
            # v0.5.0: Database-per-patient OR single patient database
            version = "v0.5.0"
            metadata['architecture'] = "Database-per-Patient (Legacy)"
            metadata['storage_model'] = "Full (all transcripts stored)"
            metadata['migration_recommended'] = True

        else:
            # Unknown or incomplete
            version = "Unknown"
            metadata['architecture'] = "Unknown"
            metadata['storage_model'] = "Unknown"
            metadata['migration_recommended'] = None

        return version, metadata

    def _check_table_exists(self, schema: str, table: str) -> bool:
        """
        Check if a table exists in the specified schema.

        Args:
            schema: Schema name
            table: Table name

        Returns:
            True if table exists, False otherwise
        """
        query = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = %s
                AND table_name = %s
            );
        """
        try:
            self.cursor.execute(query, (schema, table))
            return self.cursor.fetchone()[0]
        except psycopg2.Error:
            return False

    def _find_patient_schemas(self) -> List[str]:
        """
        Find all patient schemas (schemas matching 'patient_*' pattern).

        Returns:
            List of patient schema names
        """
        query = """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name LIKE 'patient_%'
            ORDER BY schema_name;
        """
        try:
            self.cursor.execute(query)
            return [row[0] for row in self.cursor.fetchall()]
        except psycopg2.Error:
            return []

    def get_patient_schema_stats(self, schema_name: str) -> Dict:
        """
        Get statistics for a patient schema.

        Args:
            schema_name: Patient schema name

        Returns:
            Dictionary with schema statistics
        """
        stats = {
            'schema_name': schema_name,
            'expression_data_count': 0,
            'metadata_records': 0,
            'last_updated': None
        }

        # Count expression data records
        try:
            query = sql.SQL("SELECT COUNT(*) FROM {}.expression_data").format(
                sql.Identifier(schema_name)
            )
            self.cursor.execute(query)
            stats['expression_data_count'] = self.cursor.fetchone()[0]
        except psycopg2.Error:
            pass

        # Get metadata
        try:
            query = sql.SQL("SELECT upload_date FROM {}.metadata ORDER BY upload_date DESC LIMIT 1").format(
                sql.Identifier(schema_name)
            )
            self.cursor.execute(query)
            result = self.cursor.fetchone()
            if result:
                stats['last_updated'] = result[0]
        except psycopg2.Error:
            pass

        return stats

    def print_report(self, version: str, metadata: Dict) -> None:
        """
        Print formatted detection report.

        Args:
            version: Detected version string
            metadata: Detection metadata
        """
        # Header panel
        title = f"MEDIABASE Schema Version Detection: {self.database}"
        console.print(Panel(title, style="bold cyan", box=box.DOUBLE))
        console.print()

        # Version information
        version_color = "green" if version == "v0.6.0" else "yellow" if version == "v0.5.0" else "red"
        console.print(f"[bold]Database:[/bold] {metadata['database_name']}")
        console.print(f"[bold]Schema Version:[/bold] [{version_color}]{version}[/{version_color}]")
        console.print(f"[bold]Architecture:[/bold] {metadata.get('architecture', 'Unknown')}")
        console.print(f"[bold]Storage Model:[/bold] {metadata.get('storage_model', 'Unknown')}")
        console.print()

        # Patient schemas
        if metadata['patient_schemas']:
            console.print(f"[bold cyan]Patient Schemas Found:[/bold cyan] {metadata['total_patient_schemas']}")

            # Create table for patient schemas
            table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
            table.add_column("Schema Name", style="cyan")
            table.add_column("Expression Records", justify="right", style="green")
            table.add_column("Last Updated", style="yellow")

            for schema in metadata['patient_schemas']:
                stats = self.get_patient_schema_stats(schema)
                table.add_row(
                    stats['schema_name'],
                    str(stats['expression_data_count']),
                    str(stats['last_updated']) if stats['last_updated'] else "Unknown"
                )

            console.print(table)
            console.print()
        else:
            console.print("[yellow]No patient schemas found[/yellow]")
            console.print()

        # Migration recommendation
        if metadata.get('migration_recommended'):
            console.print(Panel(
                "[bold yellow]⚠️  Migration Recommended[/bold yellow]\n\n"
                "This database uses the v0.5.0 architecture (database-per-patient).\n"
                "Consider migrating to v0.6.0 for:\n"
                "  • 99.75% storage reduction (sparse storage)\n"
                "  • Simplified query patterns (single database connection)\n"
                "  • Better multi-patient support\n\n"
                "See: docs/QUERY_MIGRATION_GUIDE_v0.6.0.md",
                style="yellow",
                box=box.ROUNDED
            ))
            console.print()

        # v0.6.0 validation
        if version == "v0.6.0":
            validation_status = "✓ Valid" if metadata.get('patient_schema_valid', False) else "✗ Invalid"
            validation_color = "green" if metadata.get('patient_schema_valid', False) else "red"
            console.print(f"[bold]Patient Schema Validation:[/bold] [{validation_color}]{validation_status}[/{validation_color}]")

            if not metadata.get('patient_schema_valid', False):
                console.print("[red]Patient schemas missing required tables (expression_data, metadata)[/red]")
            console.print()


def find_all_databases(
    host: str,
    port: int,
    user: str,
    password: str
) -> List[str]:
    """
    Find all databases on the PostgreSQL server.

    Args:
        host: PostgreSQL host
        port: PostgreSQL port
        user: Database user
        password: Database password

    Returns:
        List of database names
    """
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            database='postgres',  # Connect to default database
            user=user,
            password=password
        )
        cursor = conn.cursor()

        query = """
            SELECT datname
            FROM pg_database
            WHERE datistemplate = false
            AND datname NOT IN ('postgres', 'template0', 'template1')
            ORDER BY datname;
        """
        cursor.execute(query)
        databases = [row[0] for row in cursor.fetchall()]

        cursor.close()
        conn.close()

        return databases
    except psycopg2.Error as e:
        console.print(f"[red]ERROR:[/red] Failed to list databases: {e}")
        return []


def main():
    """Main entry point for schema version detection."""
    parser = argparse.ArgumentParser(
        description='Detect MEDIABASE schema version and architecture type',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Detect version for specific database
  poetry run python scripts/detect_schema_version.py --database mbase

  # Detect with custom connection parameters
  poetry run python scripts/detect_schema_version.py --host localhost --port 5435 --database mbase --user mbase_user

  # Scan all databases on server
  poetry run python scripts/detect_schema_version.py --all-databases

  # Use environment variables for connection
  export MB_POSTGRES_HOST=localhost
  export MB_POSTGRES_PORT=5435
  export MB_POSTGRES_USER=mbase_user
  export MB_POSTGRES_PASSWORD=mbase_secret
  poetry run python scripts/detect_schema_version.py --database mbase
        """
    )

    parser.add_argument(
        '--database',
        help='Database name to analyze'
    )
    parser.add_argument(
        '--all-databases',
        action='store_true',
        help='Scan all databases on the server'
    )
    parser.add_argument(
        '--host',
        default=os.getenv('MB_POSTGRES_HOST', 'localhost'),
        help='PostgreSQL host (default: MB_POSTGRES_HOST or localhost)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=int(os.getenv('MB_POSTGRES_PORT', '5432')),
        help='PostgreSQL port (default: MB_POSTGRES_PORT or 5432)'
    )
    parser.add_argument(
        '--user',
        default=os.getenv('MB_POSTGRES_USER', 'postgres'),
        help='Database user (default: MB_POSTGRES_USER or postgres)'
    )
    parser.add_argument(
        '--password',
        default=os.getenv('MB_POSTGRES_PASSWORD', ''),
        help='Database password (default: MB_POSTGRES_PASSWORD)'
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.all_databases and not args.database:
        parser.error("Must specify either --database or --all-databases")

    if args.all_databases and args.database:
        parser.error("Cannot specify both --database and --all-databases")

    # Determine databases to scan
    if args.all_databases:
        databases = find_all_databases(args.host, args.port, args.user, args.password)
        if not databases:
            console.print("[red]No databases found[/red]")
            return 1
        console.print(f"[cyan]Found {len(databases)} database(s) to scan[/cyan]\n")
    else:
        databases = [args.database]

    # Scan each database
    for i, database in enumerate(databases):
        if len(databases) > 1:
            console.print(f"[bold]Scanning database {i+1}/{len(databases)}[/bold]\n")

        detector = SchemaVersionDetector(
            host=args.host,
            port=args.port,
            database=database,
            user=args.user,
            password=args.password
        )

        if not detector.connect():
            continue

        try:
            version, metadata = detector.detect_version()
            detector.print_report(version, metadata)
        except Exception as e:
            console.print(f"[red]ERROR:[/red] Failed to detect version: {e}")
        finally:
            detector.close()

        if i < len(databases) - 1:
            console.print("\n" + "="*70 + "\n")

    return 0


if __name__ == '__main__':
    sys.exit(main())

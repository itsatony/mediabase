#!/usr/bin/env python3
"""
Database Export Script for MEDIABASE

This script exports all MEDIABASE databases (main + patient databases) using pg_dump
with compression and creates a complete package for sharing with colleagues.

Usage:
    poetry run python scripts/export_databases.py
    poetry run python scripts/export_databases.py --output-dir ./exports
    poetry run python scripts/export_databases.py --compress-level 6
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Optional
import tempfile
import zipfile
from datetime import datetime

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from rich.console import Console
from rich.progress import Progress, TaskID, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.table import Table

console = Console()


class DatabaseExporter:
    """Export MEDIABASE databases with compression and packaging."""

    def __init__(self, output_dir: str, compress_level: int = 6):
        """Initialize exporter with configuration."""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.compress_level = compress_level

        # Database connection parameters
        self.db_config = {
            "host": os.getenv("MB_POSTGRES_HOST", "localhost"),
            "port": os.getenv("MB_POSTGRES_PORT", "5435"),
            "user": os.getenv("MB_POSTGRES_USER", "mbase_user"),
            "password": os.getenv("MB_POSTGRES_PASSWORD", "mbase_secret"),
        }

    def get_available_databases(self) -> List[str]:
        """Get list of all MEDIABASE-related databases."""
        try:
            cmd = [
                "psql",
                "-h",
                self.db_config["host"],
                "-p",
                self.db_config["port"],
                "-U",
                self.db_config["user"],
                "-d",
                "postgres",
                "-t",
                "-c",
                "SELECT datname FROM pg_database WHERE datname IN ('mbase', 'mediabase') OR datname LIKE 'mediabase_patient_%' ORDER BY datname;",
            ]

            env = os.environ.copy()
            env["PGPASSWORD"] = self.db_config["password"]

            result = subprocess.run(
                cmd, env=env, capture_output=True, text=True, check=True
            )

            databases = [
                db.strip() for db in result.stdout.strip().split("\n") if db.strip()
            ]
            return databases

        except subprocess.CalledProcessError as e:
            console.print(f"[red]Error listing databases: {e}[/red]")
            return []

    def export_database(self, database_name: str, output_file: Path) -> bool:
        """Export a single database using pg_dump with compression."""
        try:
            cmd = [
                "pg_dump",
                "-h",
                self.db_config["host"],
                "-p",
                self.db_config["port"],
                "-U",
                self.db_config["user"],
                "-d",
                database_name,
                "--no-password",
                "--verbose",
                "--clean",
                "--if-exists",
                "--create",
                f"--compress={self.compress_level}",
                "-f",
                str(output_file),
            ]

            env = os.environ.copy()
            env["PGPASSWORD"] = self.db_config["password"]

            result = subprocess.run(cmd, env=env, capture_output=True, text=True)

            if result.returncode == 0:
                # Check if file was created and has reasonable size
                if output_file.exists() and output_file.stat().st_size > 1000:
                    return True
                else:
                    console.print(
                        f"[yellow]Warning: {database_name} dump file is suspiciously small[/yellow]"
                    )
                    return False
            else:
                console.print(
                    f"[red]pg_dump failed for {database_name}: {result.stderr}[/red]"
                )
                return False

        except Exception as e:
            console.print(f"[red]Exception exporting {database_name}: {e}[/red]")
            return False

    def get_database_stats(self, database_name: str) -> Dict[str, int]:
        """Get basic statistics for a database."""
        try:
            # For normalized schema databases
            if database_name in ["mbase", "mediabase"]:
                queries = [
                    (
                        "Tables",
                        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'",
                    ),
                    ("Genes", "SELECT COUNT(*) FROM genes"),
                    ("Transcripts", "SELECT COUNT(*) FROM transcripts"),
                    (
                        "Drug Interactions",
                        "SELECT COUNT(*) FROM gene_drug_interactions",
                    ),
                    ("Pathways", "SELECT COUNT(*) FROM gene_pathways"),
                ]
            else:
                # For patient databases with old schema
                queries = [
                    (
                        "Tables",
                        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'",
                    ),
                    ("Transcripts", "SELECT COUNT(*) FROM cancer_transcript_base"),
                    (
                        "Changed Expression",
                        "SELECT COUNT(*) FROM cancer_transcript_base WHERE expression_fold_change != 1.0",
                    ),
                ]

            stats = {}
            for name, query in queries:
                try:
                    cmd = [
                        "psql",
                        "-h",
                        self.db_config["host"],
                        "-p",
                        self.db_config["port"],
                        "-U",
                        self.db_config["user"],
                        "-d",
                        database_name,
                        "-t",
                        "-c",
                        query,
                    ]

                    env = os.environ.copy()
                    env["PGPASSWORD"] = self.db_config["password"]

                    result = subprocess.run(
                        cmd, env=env, capture_output=True, text=True
                    )
                    if result.returncode == 0:
                        stats[name] = int(result.stdout.strip())
                    else:
                        stats[name] = 0
                except:
                    stats[name] = 0

            return stats

        except Exception as e:
            console.print(
                f"[yellow]Could not get stats for {database_name}: {e}[/yellow]"
            )
            return {}

    def create_documentation(self, databases: List[str], export_info: Dict) -> str:
        """Create comprehensive documentation for the export."""
        doc_content = f"""# MEDIABASE Database Export Package

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Version:** {export_info.get('version', 'v0.3.0')}

## Package Contents

This package contains complete database exports for MEDIABASE, a comprehensive cancer transcriptomics database system.

### Databases Included

"""

        for db_name in databases:
            stats = export_info.get("database_stats", {}).get(db_name, {})
            doc_content += f"**{db_name}**\n"
            if "patient" in db_name:
                doc_content += f"- Cancer-specific patient database\n"
                doc_content += f"- Schema: Legacy (cancer_transcript_base table)\n"
            else:
                doc_content += f"- Main MEDIABASE database\n"
                doc_content += (
                    f"- Schema: Normalized (genes, transcripts, enrichment tables)\n"
                )

            for stat_name, value in stats.items():
                doc_content += f"- {stat_name}: {value:,}\n"
            doc_content += "\n"

        doc_content += """
## Setup Instructions

### Prerequisites
- PostgreSQL 12+ installed and running
- Access to create databases
- `pg_restore` command available

### Database Restoration

1. **Create target databases:**
```bash
createdb mediabase_main
createdb mediabase_patient_demo_breast_her2
# ... (create other patient databases as needed)
```

2. **Restore databases:**
```bash
# Main database
pg_restore -d mediabase_main mbase.sql.gz

# Patient databases
pg_restore -d mediabase_patient_demo_breast_her2 mediabase_patient_DEMO_BREAST_HER2.sql.gz
# ... (restore other patient databases)
```

### Testing the Installation

Run the provided query examples to verify the databases are working correctly:

```bash
# Test normalized schema queries on main database
python query_examples_normalized.py --db-name mediabase_main --example all

# Test cancer-specific queries on patient databases
# (Use the provided cancer_specific_queries.sql file)
```

## Query Examples

### Normalized Schema Queries (Main Database)

The main database supports advanced queries using the normalized schema:

1. **Oncogene Discovery**: Find upregulated genes with therapeutic potential
2. **Drug Target Analysis**: Identify druggable targets with existing compounds
3. **Pathway Enrichment**: Analyze pathway-level expression changes
4. **Database Statistics**: Get comprehensive data coverage metrics

### Cancer-Specific Queries (Patient Databases)

Patient databases contain cancer-specific expression data for:

- **Breast Cancer HER2+**: Targeted therapy selection, resistance analysis
- **Breast Cancer TNBC**: PARP inhibitors, immunotherapy targets
- **Lung Adenocarcinoma**: EGFR targeting, resistance mechanisms
- **Colorectal Cancer**: Microsatellite instability analysis
- **Pancreatic Cancer**: Aggressive phenotype characterization
- **Pan-Cancer**: Comprehensive multi-cancer analysis

## File Structure

```
mediabase_export/
├── README.md                           # This file
├── databases/                          # Database dumps
│   ├── mbase.sql.gz                   # Main database
│   ├── mediabase_patient_*.sql.gz     # Patient databases
├── queries/                           # Example queries
│   ├── query_examples_normalized.py   # Python query examples
│   ├── cancer_specific_queries.sql    # Cancer-specific SQL queries
└── documentation/                     # Additional docs
    └── schema_reference.md           # Database schema reference
```

## Support

For questions about this export package or MEDIABASE:
- Check the query examples for usage patterns
- Review the schema reference for table structures
- Test queries on sample data before production use

**Database Version:** {export_info.get('schema_version', 'Unknown')}
**Export Tool Version:** 1.0.0
"""

        return doc_content

    def create_export_package(self) -> Optional[Path]:
        """Create complete export package with databases and documentation."""

        # Get list of databases to export
        databases = self.get_available_databases()
        if not databases:
            console.print("[red]No MEDIABASE databases found![/red]")
            return None

        console.print(f"[blue]Found {len(databases)} databases to export[/blue]")

        # Create export directory structure
        export_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_dir = self.output_dir / f"mediabase_export_{export_timestamp}"
        export_dir.mkdir(exist_ok=True)

        databases_dir = export_dir / "databases"
        queries_dir = export_dir / "queries"
        docs_dir = export_dir / "documentation"

        for dir_path in [databases_dir, queries_dir, docs_dir]:
            dir_path.mkdir(exist_ok=True)

        export_info = {
            "timestamp": export_timestamp,
            "version": "v0.3.0",
            "database_stats": {},
        }

        # Export databases with progress tracking
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            successful_exports = []
            failed_exports = []

            for db_name in databases:
                task = progress.add_task(f"Exporting {db_name}...", total=None)

                # Get database statistics
                stats = self.get_database_stats(db_name)
                export_info["database_stats"][db_name] = stats

                # Export database
                output_file = databases_dir / f"{db_name}.sql.gz"
                success = self.export_database(db_name, output_file)

                if success:
                    successful_exports.append(db_name)
                    file_size_mb = output_file.stat().st_size / (1024 * 1024)
                    progress.update(
                        task, description=f"✓ {db_name} ({file_size_mb:.1f} MB)"
                    )
                else:
                    failed_exports.append(db_name)
                    progress.update(task, description=f"✗ {db_name} (failed)")

        # Copy query examples
        query_files = [
            project_root / "scripts" / "query_examples_normalized.py",
            project_root / "cancer_specific_sota_queries.sql",
            project_root / "normalized_cancer_specific_sota_queries.sql",
        ]

        for query_file in query_files:
            if query_file.exists():
                import shutil

                shutil.copy2(query_file, queries_dir)

        # Create documentation
        readme_content = self.create_documentation(successful_exports, export_info)
        (export_dir / "README.md").write_text(readme_content)

        # Create summary table
        table = Table(title="Database Export Summary")
        table.add_column("Database", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Size (MB)", justify="right")
        table.add_column("Tables", justify="right")

        for db_name in databases:
            if db_name in successful_exports:
                file_path = databases_dir / f"{db_name}.sql.gz"
                size_mb = file_path.stat().st_size / (1024 * 1024)
                stats = export_info["database_stats"].get(db_name, {})
                table_count = stats.get("Tables", 0)
                table.add_row(db_name, "✓ Success", f"{size_mb:.1f}", str(table_count))
            else:
                table.add_row(db_name, "✗ Failed", "-", "-")

        console.print("\n")
        console.print(table)
        console.print(f"\n[bold green]Export completed![/bold green]")
        console.print(f"[blue]Location: {export_dir}[/blue]")
        console.print(
            f"[blue]Successful: {len(successful_exports)} | Failed: {len(failed_exports)}[/blue]"
        )

        return export_dir

    def create_zip_archive(self, export_dir: Path) -> Path:
        """Create compressed zip archive of the export package."""
        zip_path = export_dir.with_suffix(".zip")

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for file_path in export_dir.rglob("*"):
                if file_path.is_file():
                    arcname = file_path.relative_to(export_dir.parent)
                    zipf.write(file_path, arcname)

        zip_size_mb = zip_path.stat().st_size / (1024 * 1024)
        console.print(f"\n[bold green]Zip archive created![/bold green]")
        console.print(f"[blue]File: {zip_path}[/blue]")
        console.print(f"[blue]Size: {zip_size_mb:.1f} MB[/blue]")

        return zip_path


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Export MEDIABASE databases for sharing"
    )
    parser.add_argument(
        "--output-dir", default="./exports", help="Output directory for exports"
    )
    parser.add_argument(
        "--compress-level", type=int, default=6, help="Compression level (1-9)"
    )
    parser.add_argument(
        "--create-zip", action="store_true", help="Create zip archive of export"
    )

    args = parser.parse_args()

    console.print("[bold blue]MEDIABASE Database Exporter[/bold blue]")
    console.print("Creating comprehensive database export package for colleagues\n")

    # Initialize exporter
    exporter = DatabaseExporter(args.output_dir, args.compress_level)

    # Create export package
    export_dir = exporter.create_export_package()
    if not export_dir:
        console.print("[red]Export failed![/red]")
        return 1

    # Create zip archive if requested
    if args.create_zip:
        zip_path = exporter.create_zip_archive(export_dir)
        console.print(f"\n[bold]Final deliverable: {zip_path}[/bold]")

    console.print(
        "\n[bold green]✓ Database export package ready for sharing![/bold green]"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

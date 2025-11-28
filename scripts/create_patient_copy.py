#!/usr/bin/env python3
"""
Create patient-specific schema in MEDIABASE shared core database.

MEDIABASE v0.6.0 Shared Core Architecture:
- Single mbase database with public schema (core transcriptome data)
- Patient-specific schemas: patient_<PATIENT_ID>
- Sparse storage: Only stores expression_fold_change != 1.0

This script:
1. Creates patient schema from template
2. Imports expression data from CSV
3. Populates metadata table with import statistics
4. Validates data integrity

Usage:
    poetry run python scripts/create_patient_copy.py \
        --patient-id PATIENT123 \
        --csv-file patient_transcriptome.csv

CSV Format:
    Required columns: transcript_id, <fold_change_column>
    Fold change column auto-detected (supports multiple formats):
    - cancer_fold, expression_fold_change, fold_change, log2FoldChange, etc.

Example:
    poetry run python scripts/create_patient_copy.py \
        --patient-id DEMO_HER2 \
        --csv-file examples/synthetic/her2_patient.csv \
        --cancer-type "Breast Cancer" \
        --cancer-subtype "HER2+"
"""

import argparse
import csv
import logging
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

import pandas as pd
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.table import Table

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.database import get_db_manager
from src.db.patient_schema import (
    create_patient_schema,
    insert_metadata,
    validate_patient_schema,
    get_patient_statistics,
    schema_exists,
    get_schema_name,
    InvalidPatientIDError,
    SchemaExistsError,
)
from src.utils.logging import setup_logging

console = Console()
logger = logging.getLogger(__name__)


# Column name mappings for fold change detection
FOLD_CHANGE_COLUMNS = [
    "cancer_fold",
    "expression_fold_change",
    "fold_change",
    "fc",
    "linear_fc",
    "foldchange",
]

LOG2_FOLD_CHANGE_COLUMNS = [
    "log2FoldChange",
    "log2fc",
    "log2_fold_change",
    "log2_fc",
    "l2fc",
]


class CSVValidationError(Exception):
    """Raised when CSV validation fails."""

    pass


class PatientDataImporter:
    """Import patient transcriptome data into patient schema."""

    def __init__(
        self,
        patient_id: str,
        csv_file: Path,
        cancer_type: Optional[str] = None,
        cancer_subtype: Optional[str] = None,
        dry_run: bool = False,
        overwrite: bool = False,
    ):
        """Initialize patient data importer.

        Args:
            patient_id: Unique patient identifier
            csv_file: Path to CSV file with expression data
            cancer_type: Optional cancer type (e.g., "Breast Cancer")
            cancer_subtype: Optional cancer subtype (e.g., "HER2+")
            dry_run: If True, validate only without making changes
            overwrite: If True, drop existing schema and recreate
        """
        self.patient_id = patient_id
        self.csv_file = Path(csv_file)
        self.cancer_type = cancer_type
        self.cancer_subtype = cancer_subtype
        self.dry_run = dry_run
        self.overwrite = overwrite

        # Initialize database manager
        self.db_manager = get_db_manager(config={})

        # Schema name
        self.schema_name = get_schema_name(patient_id)

        # CSV data
        self.csv_data: pd.DataFrame = None
        self.transcript_id_column: str = None
        self.fold_change_column: str = None
        self.is_log2: bool = False

        # Import statistics
        self.stats = {
            "total_rows": 0,
            "transcripts_matched": 0,
            "transcripts_unmatched": 0,
            "transcripts_stored": 0,  # Only != 1.0
            "transcripts_baseline": 0,  # = 1.0 (not stored)
            "matching_success_rate": 0.0,
            "storage_efficiency": 0.0,  # % not stored
        }

    def validate_csv(self) -> None:
        """Validate CSV file format and detect columns.

        Raises:
            CSVValidationError: If CSV is invalid
        """
        console.print(f"\n[bold]Validating CSV file:[/bold] {self.csv_file}")

        # Check file exists
        if not self.csv_file.exists():
            raise CSVValidationError(f"CSV file not found: {self.csv_file}")

        # Read CSV
        try:
            self.csv_data = pd.read_csv(self.csv_file)
        except Exception as e:
            raise CSVValidationError(f"Failed to read CSV: {e}")

        console.print(f"  Rows: {len(self.csv_data):,}")
        console.print(f"  Columns: {', '.join(self.csv_data.columns)}")

        # Detect transcript_id column
        transcript_id_candidates = [
            col
            for col in self.csv_data.columns
            if "transcript" in col.lower() and "id" in col.lower()
        ]

        if not transcript_id_candidates:
            raise CSVValidationError(
                "No transcript_id column found. Expected column name containing "
                "'transcript' and 'id' (e.g., 'transcript_id', 'transcript_ID')"
            )

        self.transcript_id_column = transcript_id_candidates[0]
        console.print(
            f"  ✓ Transcript ID column: [cyan]{self.transcript_id_column}[/cyan]"
        )

        # Detect fold change column
        fold_change_candidates = []

        # Check linear fold change columns
        for col in self.csv_data.columns:
            col_lower = col.lower().replace("_", "").replace(" ", "")
            for fc_col in FOLD_CHANGE_COLUMNS:
                fc_col_normalized = fc_col.lower().replace("_", "")
                if fc_col_normalized in col_lower:
                    fold_change_candidates.append((col, False))  # (column, is_log2)
                    break

        # Check log2 fold change columns
        for col in self.csv_data.columns:
            for log2_col in LOG2_FOLD_CHANGE_COLUMNS:
                if log2_col.lower() == col.lower():
                    fold_change_candidates.append((col, True))  # (column, is_log2)
                    break

        if not fold_change_candidates:
            raise CSVValidationError(
                f"No fold change column found. Expected one of: "
                f"{', '.join(FOLD_CHANGE_COLUMNS + LOG2_FOLD_CHANGE_COLUMNS)}"
            )

        self.fold_change_column, self.is_log2 = fold_change_candidates[0]
        fc_type = "log2 fold change" if self.is_log2 else "linear fold change"
        console.print(
            f"  ✓ Fold change column: [cyan]{self.fold_change_column}[/cyan] ({fc_type})"
        )

        # Validate data types
        if not pd.api.types.is_numeric_dtype(self.csv_data[self.fold_change_column]):
            raise CSVValidationError(
                f"Fold change column '{self.fold_change_column}' must be numeric"
            )

        # Check for missing values
        missing_transcripts = self.csv_data[self.transcript_id_column].isna().sum()
        missing_fc = self.csv_data[self.fold_change_column].isna().sum()

        if missing_transcripts > 0:
            console.print(
                f"  ⚠ Warning: {missing_transcripts} rows with missing transcript_id"
            )

        if missing_fc > 0:
            console.print(f"  ⚠ Warning: {missing_fc} rows with missing fold_change")

        # Remove rows with missing values
        before_count = len(self.csv_data)
        self.csv_data = self.csv_data.dropna(
            subset=[self.transcript_id_column, self.fold_change_column]
        )
        after_count = len(self.csv_data)

        if before_count != after_count:
            console.print(
                f"  Removed {before_count - after_count} rows with missing values"
            )

        # Show fold change distribution
        fc_values = self.csv_data[self.fold_change_column]
        table = Table(title="Fold Change Distribution")
        table.add_column("Statistic", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Count", f"{len(fc_values):,}")
        table.add_row("Mean", f"{fc_values.mean():.3f}")
        table.add_row("Median", f"{fc_values.median():.3f}")
        table.add_row("Min", f"{fc_values.min():.3f}")
        table.add_row("Max", f"{fc_values.max():.3f}")

        console.print(table)

        console.print("[bold green]✓ CSV validation passed[/bold green]\n")

    def create_schema(self) -> None:
        """Create patient schema in database."""
        console.print(f"\n[bold]Creating patient schema:[/bold] {self.schema_name}")

        if self.dry_run:
            console.print("[yellow]  (Dry run - skipping schema creation)[/yellow]")
            return

        try:
            # Check if schema exists
            if schema_exists(self.patient_id, self.db_manager):
                if self.overwrite:
                    console.print(f"  [yellow]Schema exists - will overwrite[/yellow]")
                else:
                    raise SchemaExistsError(
                        f"Schema {self.schema_name} already exists. "
                        f"Use --overwrite to replace it."
                    )

            # Create schema
            metadata = {
                "source_file": str(self.csv_file.name),
                "file_format": "csv",
            }

            if self.cancer_type:
                metadata["cancer_type"] = self.cancer_type
            if self.cancer_subtype:
                metadata["cancer_subtype"] = self.cancer_subtype

            result = create_patient_schema(
                patient_id=self.patient_id,
                db_manager=self.db_manager,
                metadata=metadata,
                overwrite=self.overwrite,
            )

            console.print(f"[bold green]✓ Schema created successfully[/bold green]")

        except Exception as e:
            console.print(f"[bold red]✗ Schema creation failed:[/bold red] {e}")
            raise

    def match_transcripts(self) -> pd.DataFrame:
        """Match CSV transcripts to database transcripts.

        Returns:
            DataFrame with matched transcripts and their linear fold changes
        """
        console.print(f"\n[bold]Matching transcripts to database...[/bold]")

        # Get all transcript IDs from CSV
        csv_transcript_ids = self.csv_data[self.transcript_id_column].tolist()

        # Convert log2 fold change to linear if needed
        if self.is_log2:
            console.print("  Converting log2 fold change to linear...")
            fold_changes = (
                self.csv_data[self.fold_change_column]
                .apply(lambda x: 2 ** x if pd.notna(x) else None)
                .tolist()
            )
        else:
            fold_changes = self.csv_data[self.fold_change_column].tolist()

        # Query database for matching transcripts
        if not self.db_manager.cursor:
            self.db_manager.connect()
        cursor = self.db_manager.cursor

        # Build parameterized query
        placeholders = ",".join(["%s"] * len(csv_transcript_ids))
        query = f"""
            SELECT transcript_id
            FROM public.transcripts
            WHERE transcript_id IN ({placeholders})
        """

        cursor.execute(query, csv_transcript_ids)
        db_transcript_ids = {row[0] for row in cursor.fetchall()}

        # Match transcripts
        matched_data = []
        for transcript_id, fold_change in zip(csv_transcript_ids, fold_changes):
            if transcript_id in db_transcript_ids:
                matched_data.append(
                    {"transcript_id": transcript_id, "fold_change": fold_change}
                )

        matched_df = pd.DataFrame(matched_data)

        # Update statistics
        self.stats["total_rows"] = len(csv_transcript_ids)
        self.stats["transcripts_matched"] = len(matched_df)
        self.stats["transcripts_unmatched"] = len(csv_transcript_ids) - len(matched_df)
        self.stats["matching_success_rate"] = (
            len(matched_df) / len(csv_transcript_ids)
            if len(csv_transcript_ids) > 0
            else 0.0
        )

        # Show matching results
        table = Table(title="Transcript Matching Results")
        table.add_column("Category", style="cyan")
        table.add_column("Count", style="green")
        table.add_column("Percentage", style="yellow")

        total = self.stats["total_rows"]
        matched = self.stats["transcripts_matched"]
        unmatched = self.stats["transcripts_unmatched"]

        table.add_row("Total transcripts in CSV", f"{total:,}", "100%")
        table.add_row(
            "Matched to database", f"{matched:,}", f"{(matched/total*100):.1f}%"
        )
        table.add_row(
            "Not found in database", f"{unmatched:,}", f"{(unmatched/total*100):.1f}%"
        )

        console.print(table)

        if unmatched > 0:
            console.print(
                f"\n[yellow]⚠ {unmatched:,} transcripts not found in database "
                f"(may be outdated IDs or non-protein-coding)[/yellow]"
            )

        return matched_df

    def import_expression_data(self, matched_df: pd.DataFrame) -> None:
        """Import expression data into patient schema.

        Only stores fold_change != 1.0 (sparse storage).

        Args:
            matched_df: DataFrame with matched transcript_id and fold_change
        """
        console.print(f"\n[bold]Importing expression data...[/bold]")

        if self.dry_run:
            console.print("[yellow]  (Dry run - skipping import)[/yellow]")
            # Still calculate statistics for dry run
            non_default = matched_df[matched_df["fold_change"] != 1.0]
            self.stats["transcripts_stored"] = len(non_default)
            self.stats["transcripts_baseline"] = len(matched_df) - len(non_default)
            self.stats["storage_efficiency"] = (
                self.stats["transcripts_baseline"] / len(matched_df) * 100
                if len(matched_df) > 0
                else 0.0
            )
            return

        # Filter for sparse storage (only != 1.0)
        non_default_df = matched_df[matched_df["fold_change"] != 1.0].copy()

        self.stats["transcripts_stored"] = len(non_default_df)
        self.stats["transcripts_baseline"] = len(matched_df) - len(non_default_df)
        self.stats["storage_efficiency"] = (
            self.stats["transcripts_baseline"] / len(matched_df) * 100
            if len(matched_df) > 0
            else 0.0
        )

        console.print(
            f"  Transcripts to store: {self.stats['transcripts_stored']:,} "
            f"(excluding {self.stats['transcripts_baseline']:,} baseline values)"
        )
        console.print(
            f"  Storage efficiency: {self.stats['storage_efficiency']:.1f}% "
            f"reduction vs. storing all values"
        )

        if len(non_default_df) == 0:
            console.print(
                "[yellow]  No non-baseline expression values to store[/yellow]"
            )
            return

        # Batch insert expression data
        if not self.db_manager.cursor:
            self.db_manager.connect()
        cursor = self.db_manager.cursor

        insert_query = f"""
            INSERT INTO {self.schema_name}.expression_data
                (transcript_id, expression_fold_change)
            VALUES (%s, %s)
            ON CONFLICT (transcript_id) DO UPDATE SET
                expression_fold_change = EXCLUDED.expression_fold_change,
                updated_at = CURRENT_TIMESTAMP
        """

        batch_size = 5000
        total_batches = (len(non_default_df) + batch_size - 1) // batch_size

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console,
        ) as progress:
            task = progress.add_task(
                "Inserting expression data...", total=len(non_default_df)
            )

            for i in range(0, len(non_default_df), batch_size):
                batch = non_default_df.iloc[i : i + batch_size]
                values = [
                    (row["transcript_id"], float(row["fold_change"]))
                    for _, row in batch.iterrows()
                ]

                cursor.executemany(insert_query, values)
                progress.update(task, advance=len(batch))

        console.print(
            f"[bold green]✓ Imported {len(non_default_df):,} expression values[/bold green]"
        )

    def update_metadata(self) -> None:
        """Update patient metadata with import statistics."""
        if self.dry_run:
            console.print("\n[yellow](Dry run - skipping metadata update)[/yellow]")
            return

        console.print(f"\n[bold]Updating metadata...[/bold]")

        metadata = {
            "total_transcripts_uploaded": self.stats["total_rows"],
            "transcripts_matched": self.stats["transcripts_matched"],
            "transcripts_unmatched": self.stats["transcripts_unmatched"],
            "matching_success_rate": self.stats["matching_success_rate"],
        }

        if self.cancer_type:
            metadata["cancer_type"] = self.cancer_type
        if self.cancer_subtype:
            metadata["cancer_subtype"] = self.cancer_subtype

        insert_metadata(
            patient_id=self.patient_id, metadata=metadata, db_manager=self.db_manager
        )

        console.print("[bold green]✓ Metadata updated[/bold green]")

    def validate_import(self) -> None:
        """Validate imported data."""
        console.print(f"\n[bold]Validating imported data...[/bold]")

        if self.dry_run:
            console.print("[yellow]  (Dry run - skipping validation)[/yellow]")
            return

        # Run patient schema validation
        validation = validate_patient_schema(
            patient_id=self.patient_id, db_manager=self.db_manager
        )

        # Display validation results
        table = Table(title="Validation Results")
        table.add_column("Check", style="cyan")
        table.add_column("Status", style="green")

        for check_name, result in validation["checks"].items():
            status = "✓ PASS" if "PASS" in str(result) else f"✗ {result}"
            table.add_row(check_name, status)

        console.print(table)

        if validation["valid"]:
            console.print("[bold green]✓ Validation passed[/bold green]")
        else:
            console.print("[bold red]✗ Validation failed[/bold red]")
            raise RuntimeError(f"Validation failed: {validation}")

        # Get patient statistics
        stats = get_patient_statistics(
            patient_id=self.patient_id, db_manager=self.db_manager
        )

        # Display statistics
        stats_table = Table(title="Patient Expression Statistics")
        stats_table.add_column("Metric", style="cyan")
        stats_table.add_column("Value", style="green")

        stats_table.add_row(
            "Total transcripts stored", f"{stats['total_transcripts']:,}"
        )
        stats_table.add_row("Overexpressed (>2.0)", f"{stats['overexpressed_count']:,}")
        stats_table.add_row(
            "Underexpressed (<0.5)", f"{stats['underexpressed_count']:,}"
        )
        stats_table.add_row("Min fold change", f"{stats['min_fold_change']:.3f}")
        stats_table.add_row("Max fold change", f"{stats['max_fold_change']:.3f}")
        stats_table.add_row("Mean fold change", f"{stats['avg_fold_change']:.3f}")
        stats_table.add_row("Median fold change", f"{stats['median_fold_change']:.3f}")

        console.print(stats_table)

    def run(self) -> None:
        """Run complete patient data import workflow."""
        try:
            console.print(
                "\n[bold blue]MEDIABASE v0.6.0 - Patient Data Import[/bold blue]"
            )
            console.print(f"Patient ID: [cyan]{self.patient_id}[/cyan]")
            console.print(f"Schema: [cyan]{self.schema_name}[/cyan]")
            console.print(f"CSV file: [cyan]{self.csv_file}[/cyan]")

            if self.dry_run:
                console.print(
                    "\n[yellow]DRY RUN MODE - No changes will be made[/yellow]"
                )

            # Step 1: Validate CSV
            self.validate_csv()

            # Step 2: Create schema
            self.create_schema()

            # Step 3: Match transcripts
            matched_df = self.match_transcripts()

            if len(matched_df) == 0:
                console.print(
                    "\n[bold red]✗ No transcripts matched - aborting[/bold red]"
                )
                return

            # Step 4: Import expression data
            self.import_expression_data(matched_df)

            # Step 5: Update metadata
            self.update_metadata()

            # Step 6: Validate
            self.validate_import()

            # Success summary
            console.print(
                "\n[bold green]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold green]"
            )
            console.print(
                "[bold green]✓ Patient data import completed successfully![/bold green]"
            )
            console.print(
                "[bold green]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold green]"
            )

            # Final statistics
            final_table = Table(title="Import Summary")
            final_table.add_column("Metric", style="cyan")
            final_table.add_column("Value", style="green")

            final_table.add_row("Patient ID", self.patient_id)
            final_table.add_row("Schema", self.schema_name)
            final_table.add_row("CSV rows", f"{self.stats['total_rows']:,}")
            final_table.add_row(
                "Transcripts matched", f"{self.stats['transcripts_matched']:,}"
            )
            final_table.add_row(
                "Match rate", f"{self.stats['matching_success_rate']:.1%}"
            )
            final_table.add_row(
                "Transcripts stored", f"{self.stats['transcripts_stored']:,}"
            )
            final_table.add_row(
                "Baseline (not stored)", f"{self.stats['transcripts_baseline']:,}"
            )
            final_table.add_row(
                "Storage reduction", f"{self.stats['storage_efficiency']:.1f}%"
            )

            console.print(final_table)

            # Usage examples
            console.print("\n[bold]Query examples:[/bold]")
            console.print(
                f"  SELECT * FROM {self.schema_name}.expression_data LIMIT 10;"
            )
            console.print(f"  SELECT * FROM {self.schema_name}.metadata;")
            console.print(
                f"\n  # Join with public schema:\n"
                f"  SELECT g.gene_symbol, pe.expression_fold_change\n"
                f"  FROM {self.schema_name}.expression_data pe\n"
                f"  JOIN public.transcripts t ON pe.transcript_id = t.transcript_id\n"
                f"  JOIN public.genes g ON t.gene_id = g.gene_id\n"
                f"  WHERE pe.expression_fold_change > 2.0\n"
                f"  LIMIT 20;"
            )

        except Exception as e:
            console.print(f"\n[bold red]✗ Import failed:[/bold red] {e}")
            logger.exception("Import failed")
            raise


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Import patient transcriptome data into MEDIABASE v0.6.0 shared core database"
    )
    parser.add_argument(
        "--patient-id",
        type=str,
        required=True,
        help="Unique patient identifier (e.g., PATIENT123, DEMO_HER2)",
    )
    parser.add_argument(
        "--csv-file",
        type=Path,
        required=True,
        help="Path to CSV file with expression data",
    )
    parser.add_argument(
        "--cancer-type",
        type=str,
        help='Cancer type (e.g., "Breast Cancer", "Lung Adenocarcinoma")',
    )
    parser.add_argument(
        "--cancer-subtype",
        type=str,
        help='Cancer molecular subtype (e.g., "HER2+", "TNBC", "EGFR-mutant")',
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate CSV without making changes"
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing patient schema if it exists",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(log_level=args.log_level)

    # Run import
    try:
        importer = PatientDataImporter(
            patient_id=args.patient_id,
            csv_file=args.csv_file,
            cancer_type=args.cancer_type,
            cancer_subtype=args.cancer_subtype,
            dry_run=args.dry_run,
            overwrite=args.overwrite,
        )
        importer.run()
        return 0

    except InvalidPatientIDError as e:
        console.print(f"\n[bold red]Invalid patient ID:[/bold red] {e}")
        return 1
    except SchemaExistsError as e:
        console.print(f"\n[bold red]Schema exists:[/bold red] {e}")
        console.print("Use --overwrite to replace existing schema")
        return 1
    except CSVValidationError as e:
        console.print(f"\n[bold red]CSV validation failed:[/bold red] {e}")
        return 1
    except Exception as e:
        console.print(f"\n[bold red]Import failed:[/bold red] {e}")
        logger.exception("Unexpected error")
        return 1


if __name__ == "__main__":
    sys.exit(main())

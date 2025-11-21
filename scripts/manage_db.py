#!/usr/bin/env python3
"""
Database management CLI for MEDIABASE v0.6.0.
Provides interactive and non-interactive database management interface.
Supports both core database and patient schema management.
"""
import sys
import logging
import argparse
from pathlib import Path
from typing import Dict, Any, List
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table
from dotenv import load_dotenv
import os
from src.db.database import get_db_manager
from src.db.patient_schema import (
    list_patient_schemas,
    validate_patient_schema,
    get_patient_statistics,
    drop_patient_schema,
    schema_exists,
    get_schema_name,
)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
console = Console()


class DatabaseMenu:
    """Interactive menu for database management (v0.6.0)."""

    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.choices = {
            "1": ("Check database status", self.check_status),
            "2": ("Reset database", self.reset_database),
            "3": ("Backup database", self.backup_database),
            "4": ("Restore database", self.restore_database),
            "5": ("List patient schemas", self.list_schemas),
            "6": ("Validate patient schema", self.validate_schema),
            "7": ("View patient schema statistics", self.view_schema_stats),
            "8": ("Delete patient schema", self.delete_schema),
            "9": ("Exit", self.exit_program),
        }

    def display_menu(self):
        """Display the interactive menu."""
        console.clear()
        console.print("[bold]MEDIABASE v0.6.0 - Database Management[/bold]\n")
        console.print("[dim]Core Database + Patient Schema Management[/dim]\n")
        for key, (option, _) in self.choices.items():
            console.print(f"[bold]{key}[/bold]. {option}")
        return console.input("\n[bold]Choose an option:[/bold] ")

    def check_status(self):
        """Display database status."""
        self.db_manager.display_status()
        input("\nPress Enter to continue...")

    def reset_database(self):
        """Reset the database after confirmation."""
        if Confirm.ask(
            "Are you sure you want to reset the database? This will delete all data!"
        ):
            if self.db_manager.reset():
                console.print("[green]Database reset successfully[/green]")
            else:
                console.print("[red]Database reset failed[/red]")
        input("\nPress Enter to continue...")

    def backup_database(self):
        """Backup the database to a file."""
        output_file = (
            console.input("Enter backup file path (default: backup.dump): ").strip()
            or "backup.dump"
        )
        if self.db_manager.dump_database(output_file):
            console.print(
                f"[green]Database backed up successfully to {output_file}[/green]"
            )
        else:
            console.print("[red]Backup failed[/red]")
        input("\nPress Enter to continue...")

    def restore_database(self):
        """Restore the database from a backup file."""
        input_file = console.input("Enter backup file path: ").strip()
        if not input_file or not os.path.exists(input_file):
            console.print("[red]Invalid backup file[/red]")
        elif Confirm.ask("This will overwrite the current database. Continue?"):
            if self.db_manager.restore_database(input_file):
                console.print("[green]Database restored successfully[/green]")
            else:
                console.print("[red]Restore failed[/red]")
        input("\nPress Enter to continue...")

    def list_schemas(self):
        """List all patient schemas in the database."""
        try:
            schemas = list_patient_schemas(self.db_manager)

            if not schemas:
                console.print("\n[yellow]No patient schemas found[/yellow]")
                input("\nPress Enter to continue...")
                return

            table = Table(title=f"Patient Schemas ({len(schemas)} total)")
            table.add_column("Patient ID", style="cyan")
            table.add_column("Schema Name", style="green")
            table.add_column("Expression Data", justify="right", style="yellow")
            table.add_column("Created", style="dim")

            for schema in schemas:
                table.add_row(
                    schema["patient_id"],
                    schema["schema_name"],
                    f"{schema['expression_count']:,}",
                    schema["created_at"].strftime("%Y-%m-%d %H:%M")
                    if schema["created_at"]
                    else "N/A",
                )

            console.print()
            console.print(table)

        except Exception as e:
            console.print(f"[red]Error listing schemas: {e}[/red]")

        input("\nPress Enter to continue...")

    def validate_schema(self):
        """Validate a specific patient schema."""
        patient_id = Prompt.ask("\n[bold]Enter patient ID to validate[/bold]")

        if not patient_id:
            console.print("[red]Patient ID required[/red]")
            input("\nPress Enter to continue...")
            return

        try:
            console.print(f"\n[bold]Validating schema for patient:[/bold] {patient_id}")

            if not schema_exists(patient_id, self.db_manager):
                console.print(
                    f"[red]Schema {get_schema_name(patient_id)} does not exist[/red]"
                )
                input("\nPress Enter to continue...")
                return

            result = validate_patient_schema(patient_id, self.db_manager)

            console.print(f"\n[bold green]✓ Validation complete[/bold green]")
            console.print(f"Schema name: [cyan]{result['schema_name']}[/cyan]")
            console.print(
                f"Valid: [{'green' if result['is_valid'] else 'red'}]{result['is_valid']}[/]"
            )

            if result["errors"]:
                console.print(f"\n[red]Errors found:[/red]")
                for error in result["errors"]:
                    console.print(f"  • {error}")
            else:
                console.print(f"\n[green]No errors found[/green]")

            console.print(f"\nExpression data count: {result['expression_count']:,}")
            console.print(f"Metadata records: {result['metadata_count']}")

        except Exception as e:
            console.print(f"[red]Error validating schema: {e}[/red]")

        input("\nPress Enter to continue...")

    def view_schema_stats(self):
        """View statistics for a patient schema."""
        patient_id = Prompt.ask("\n[bold]Enter patient ID[/bold]")

        if not patient_id:
            console.print("[red]Patient ID required[/red]")
            input("\nPress Enter to continue...")
            return

        try:
            if not schema_exists(patient_id, self.db_manager):
                console.print(
                    f"[red]Schema {get_schema_name(patient_id)} does not exist[/red]"
                )
                input("\nPress Enter to continue...")
                return

            stats = get_patient_statistics(patient_id, self.db_manager)

            console.print(f"\n[bold]Patient Expression Statistics[/bold]")
            console.print(f"Patient ID: [cyan]{patient_id}[/cyan]")
            console.print(f"Schema: [green]{get_schema_name(patient_id)}[/green]\n")

            table = Table(title="Expression Distribution")
            table.add_column("Category", style="cyan")
            table.add_column("Count", justify="right", style="yellow")
            table.add_column("Percentage", justify="right", style="green")

            total_stored = stats["total_expression_values"]

            table.add_row("Total stored expressions", f"{total_stored:,}", "100.0%")
            table.add_row(
                "Overexpressed (>2.0)",
                f"{stats['overexpressed_count']:,}",
                f"{stats['overexpressed_pct']:.1f}%",
            )
            table.add_row(
                "Underexpressed (<0.5)",
                f"{stats['underexpressed_count']:,}",
                f"{stats['underexpressed_pct']:.1f}%",
            )
            table.add_row(
                "Baseline (=1.0)",
                f"{stats['baseline_count']:,}",
                f"{stats['baseline_pct']:.1f}%",
            )

            console.print(table)

            if stats["top_overexpressed"]:
                console.print(f"\n[bold]Top 10 Overexpressed Genes[/bold]")
                for i, (gene, fc) in enumerate(stats["top_overexpressed"], 1):
                    console.print(f"  {i}. {gene}: {fc:.2f}x")

            if stats["top_underexpressed"]:
                console.print(f"\n[bold]Top 10 Underexpressed Genes[/bold]")
                for i, (gene, fc) in enumerate(stats["top_underexpressed"], 1):
                    console.print(f"  {i}. {gene}: {fc:.3f}x")

        except Exception as e:
            console.print(f"[red]Error retrieving statistics: {e}[/red]")

        input("\nPress Enter to continue...")

    def delete_schema(self):
        """Delete a patient schema."""
        patient_id = Prompt.ask("\n[bold]Enter patient ID to delete[/bold]")

        if not patient_id:
            console.print("[red]Patient ID required[/red]")
            input("\nPress Enter to continue...")
            return

        try:
            if not schema_exists(patient_id, self.db_manager):
                console.print(
                    f"[red]Schema {get_schema_name(patient_id)} does not exist[/red]"
                )
                input("\nPress Enter to continue...")
                return

            schema_name = get_schema_name(patient_id)
            console.print(
                f"\n[yellow]WARNING: This will permanently delete schema: {schema_name}[/yellow]"
            )

            if not Confirm.ask(
                f"Are you sure you want to delete patient schema for '{patient_id}'?"
            ):
                console.print("[dim]Deletion cancelled[/dim]")
                input("\nPress Enter to continue...")
                return

            if drop_patient_schema(patient_id, self.db_manager, cascade=True):
                console.print(
                    f"[green]✓ Schema {schema_name} deleted successfully[/green]"
                )
            else:
                console.print(f"[red]Failed to delete schema {schema_name}[/red]")

        except Exception as e:
            console.print(f"[red]Error deleting schema: {e}[/red]")

        input("\nPress Enter to continue...")

    def exit_program(self):
        """Exit the program."""
        console.print("[bold]Goodbye![/bold]")
        sys.exit(0)

    def run(self):
        """Run the interactive menu loop."""
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
    project_root = Path(__file__).parent.parent
    env_path = project_root / ".env"
    load_dotenv(env_path)

    required_vars = [
        "MB_POSTGRES_HOST",
        "MB_POSTGRES_PORT",
        "MB_POSTGRES_NAME",
        "MB_POSTGRES_USER",
        "MB_POSTGRES_PASSWORD",
    ]
    missing_vars = [var for var in required_vars if var not in os.environ]
    if missing_vars:
        console.print(
            f"[red]Missing required environment variables: {', '.join(missing_vars)}[/red]"
        )
        sys.exit(1)

    return {
        "host": os.environ.get("MB_POSTGRES_HOST", "localhost"),
        "port": int(os.environ.get("MB_POSTGRES_PORT", "5435")),
        "dbname": os.environ.get("MB_POSTGRES_NAME", "mediabase"),
        "user": os.environ.get("MB_POSTGRES_USER", "mbase_user"),
        "password": os.environ.get("MB_POSTGRES_PASSWORD", "mbase_secret"),
    }


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="MEDIABASE v0.6.0 Database Management Tool",
        epilog="For interactive mode, run without arguments.",
    )

    # Core database operations
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run in non-interactive mode (check database status)",
    )
    parser.add_argument(
        "--backup", metavar="FILE", help="Backup database to specified file"
    )
    parser.add_argument(
        "--restore", metavar="FILE", help="Restore database from specified file"
    )

    # Patient schema operations
    schema_group = parser.add_argument_group("Patient Schema Operations")
    schema_group.add_argument(
        "--list-schemas", action="store_true", help="List all patient schemas"
    )
    schema_group.add_argument(
        "--validate-schema",
        metavar="PATIENT_ID",
        help="Validate specified patient schema",
    )
    schema_group.add_argument(
        "--schema-stats",
        metavar="PATIENT_ID",
        help="Show statistics for specified patient schema",
    )
    schema_group.add_argument(
        "--delete-schema",
        metavar="PATIENT_ID",
        help="Delete specified patient schema (requires confirmation)",
    )
    schema_group.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompts (use with --delete-schema)",
    )

    args = parser.parse_args()

    config = load_config()
    db_manager = get_db_manager(config)

    # Core database operations
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

    # Patient schema operations
    elif args.list_schemas:
        try:
            schemas = list_patient_schemas(db_manager)
            if not schemas:
                console.print("[yellow]No patient schemas found[/yellow]")
                sys.exit(0)

            table = Table(title=f"Patient Schemas ({len(schemas)} total)")
            table.add_column("Patient ID", style="cyan")
            table.add_column("Schema Name", style="green")
            table.add_column("Expression Data", justify="right", style="yellow")
            table.add_column("Created", style="dim")

            for schema in schemas:
                table.add_row(
                    schema["patient_id"],
                    schema["schema_name"],
                    f"{schema['expression_count']:,}",
                    schema["created_at"].strftime("%Y-%m-%d %H:%M")
                    if schema["created_at"]
                    else "N/A",
                )

            console.print(table)
            sys.exit(0)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            sys.exit(1)

    elif args.validate_schema:
        try:
            patient_id = args.validate_schema
            if not schema_exists(patient_id, db_manager):
                console.print(
                    f"[red]Schema {get_schema_name(patient_id)} does not exist[/red]"
                )
                sys.exit(1)

            result = validate_patient_schema(patient_id, db_manager)
            console.print(f"\n[bold]Validation Results for {patient_id}[/bold]")
            console.print(f"Schema: [cyan]{result['schema_name']}[/cyan]")
            console.print(
                f"Valid: [{'green' if result['is_valid'] else 'red'}]{result['is_valid']}[/]"
            )

            if result["errors"]:
                console.print(f"\n[red]Errors:[/red]")
                for error in result["errors"]:
                    console.print(f"  • {error}")
                sys.exit(1)
            else:
                console.print(f"[green]✓ Schema is valid[/green]")
                console.print(f"Expression data count: {result['expression_count']:,}")
                sys.exit(0)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            sys.exit(1)

    elif args.schema_stats:
        try:
            patient_id = args.schema_stats
            if not schema_exists(patient_id, db_manager):
                console.print(
                    f"[red]Schema {get_schema_name(patient_id)} does not exist[/red]"
                )
                sys.exit(1)

            stats = get_patient_statistics(patient_id, db_manager)

            console.print(f"\n[bold]Statistics for {patient_id}[/bold]")
            console.print(f"Schema: [green]{get_schema_name(patient_id)}[/green]\n")

            table = Table(title="Expression Distribution")
            table.add_column("Category", style="cyan")
            table.add_column("Count", justify="right", style="yellow")
            table.add_column("Percentage", justify="right", style="green")

            table.add_row(
                "Total stored", f"{stats['total_expression_values']:,}", "100.0%"
            )
            table.add_row(
                "Overexpressed (>2.0)",
                f"{stats['overexpressed_count']:,}",
                f"{stats['overexpressed_pct']:.1f}%",
            )
            table.add_row(
                "Underexpressed (<0.5)",
                f"{stats['underexpressed_count']:,}",
                f"{stats['underexpressed_pct']:.1f}%",
            )
            table.add_row(
                "Baseline (=1.0)",
                f"{stats['baseline_count']:,}",
                f"{stats['baseline_pct']:.1f}%",
            )

            console.print(table)
            sys.exit(0)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            sys.exit(1)

    elif args.delete_schema:
        try:
            patient_id = args.delete_schema
            if not schema_exists(patient_id, db_manager):
                console.print(
                    f"[red]Schema {get_schema_name(patient_id)} does not exist[/red]"
                )
                sys.exit(1)

            schema_name = get_schema_name(patient_id)

            if not args.force:
                console.print(
                    f"\n[yellow]WARNING: This will permanently delete schema: {schema_name}[/yellow]"
                )
                if not Confirm.ask(f"Are you sure you want to delete '{patient_id}'?"):
                    console.print("[dim]Deletion cancelled[/dim]")
                    sys.exit(0)

            if drop_patient_schema(patient_id, db_manager, cascade=True):
                console.print(
                    f"[green]✓ Schema {schema_name} deleted successfully[/green]"
                )
                sys.exit(0)
            else:
                console.print(f"[red]Failed to delete schema {schema_name}[/red]")
                sys.exit(1)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            sys.exit(1)

    elif args.non_interactive:
        if not db_manager.connect() or not db_manager.check_db_exists():
            sys.exit(1)
        sys.exit(0)

    # Interactive mode
    else:
        DatabaseMenu(db_manager).run()


if __name__ == "__main__":
    main()

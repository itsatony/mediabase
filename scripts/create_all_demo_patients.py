#!/usr/bin/env python3
"""
Create All Demo Patient Databases

This script creates all demo patient databases using the enhanced datasets.
"""

import os
import sys
import subprocess
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from rich.console import Console
from rich.progress import Progress, TaskID

console = Console()

# Demo datasets to process
DEMO_DATASETS = [
    {
        "patient_id": "DEMO_BREAST_HER2",
        "csv_file": "examples/enhanced/demo_breast_her2_enhanced.csv",
        "description": "Breast Cancer HER2-Positive (500 genes)",
    },
    {
        "patient_id": "DEMO_BREAST_TNBC",
        "csv_file": "examples/enhanced/demo_breast_tnbc_enhanced.csv",
        "description": "Breast Cancer Triple-Negative (400 genes)",
    },
    {
        "patient_id": "DEMO_LUNG_EGFR",
        "csv_file": "examples/enhanced/demo_lung_egfr_enhanced.csv",
        "description": "Lung Adenocarcinoma EGFR-Mutant (300 genes)",
    },
    {
        "patient_id": "DEMO_COLORECTAL_MSI",
        "csv_file": "examples/enhanced/demo_colorectal_msi_enhanced.csv",
        "description": "Colorectal Adenocarcinoma MSI-High (400 genes)",
    },
    {
        "patient_id": "DEMO_PANCREATIC_PDAC",
        "csv_file": "examples/enhanced/demo_pancreatic_pdac_enhanced.csv",
        "description": "Pancreatic Ductal Adenocarcinoma (350 genes)",
    },
    {
        "patient_id": "DEMO_COMPREHENSIVE",
        "csv_file": "examples/enhanced/demo_comprehensive_enhanced.csv",
        "description": "Comprehensive Pan-Cancer Dataset (1000 genes)",
    },
]


def setup_environment():
    """Set up environment variables for database connection."""
    os.environ["MB_POSTGRES_HOST"] = "localhost"
    os.environ["MB_POSTGRES_PORT"] = "5435"
    os.environ["MB_POSTGRES_USER"] = "mbase_user"
    os.environ["MB_POSTGRES_PASSWORD"] = "mbase_secret"


def create_patient_database(patient_id: str, csv_file: str, description: str) -> bool:
    """Create a patient database using the create_patient_copy.py script.

    Args:
        patient_id: Patient ID for the database
        csv_file: Path to CSV file with fold-change data
        description: Description of the dataset

    Returns:
        True if successful, False otherwise
    """
    console.print(f"[blue]Creating {description}...[/blue]")
    console.print(f"  Patient ID: {patient_id}")
    console.print(f"  Dataset: {csv_file}")

    try:
        # Prepare the command
        cmd = [
            "poetry",
            "run",
            "python",
            "scripts/create_patient_copy.py",
            "--patient-id",
            patient_id,
            "--csv-file",
            csv_file,
            "--source-db",
            "mbase",
        ]

        # Run with auto-confirmation
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Send 'y' to confirm database creation
        stdout, stderr = process.communicate(input="y\n")

        if process.returncode == 0:
            console.print(f"[green]✓ Successfully created {patient_id}[/green]")
            return True
        else:
            console.print(f"[red]✗ Failed to create {patient_id}[/red]")
            console.print(f"Error: {stderr}")
            return False

    except Exception as e:
        console.print(f"[red]✗ Exception creating {patient_id}: {e}[/red]")
        return False


def list_created_databases():
    """List all created demo patient databases."""
    console.print("\n[blue]Checking created databases...[/blue]")

    try:
        cmd = [
            "psql",
            "-h",
            "localhost",
            "-p",
            "5435",
            "-U",
            "mbase_user",
            "-d",
            "postgres",
            "-c",
            "SELECT datname FROM pg_database WHERE datname LIKE 'mediabase_patient_DEMO_%' ORDER BY datname;",
        ]

        env = os.environ.copy()
        env["PGPASSWORD"] = "mbase_secret"

        result = subprocess.run(cmd, env=env, capture_output=True, text=True)

        if result.returncode == 0:
            console.print("\n[green]Created Demo Patient Databases:[/green]")
            console.print(result.stdout)
        else:
            console.print(f"[yellow]Could not list databases: {result.stderr}[/yellow]")

    except Exception as e:
        console.print(f"[yellow]Could not list databases: {e}[/yellow]")


def main():
    """Main execution function."""
    console.print("[bold blue]Creating All Demo Patient Databases[/bold blue]")
    console.print(
        "This will create 6 comprehensive patient databases with realistic expression data.\n"
    )

    # Set up environment
    setup_environment()

    # Track results
    successful = []
    failed = []

    # Create each database
    with Progress() as progress:
        task = progress.add_task("Creating databases...", total=len(DEMO_DATASETS))

        for dataset in DEMO_DATASETS:
            if create_patient_database(
                dataset["patient_id"], dataset["csv_file"], dataset["description"]
            ):
                successful.append(dataset["patient_id"])
            else:
                failed.append(dataset["patient_id"])

            progress.update(task, advance=1)

    # Summary
    console.print(f"\n[bold]Summary:[/bold]")
    console.print(f"[green]Successful: {len(successful)}[/green]")
    if successful:
        for db in successful:
            console.print(f"  ✓ {db}")

    if failed:
        console.print(f"[red]Failed: {len(failed)}[/red]")
        for db in failed:
            console.print(f"  ✗ {db}")

    # List created databases
    list_created_databases()

    if successful:
        console.print(
            "\n[bold green]Demo patient databases are ready for SOTA query testing![/bold green]"
        )
        console.print("\nNext steps:")
        console.print("1. Test SOTA queries on these databases")
        console.print("2. Create cancer-specific query examples")
        console.print("3. Update README with working workflows")


if __name__ == "__main__":
    main()

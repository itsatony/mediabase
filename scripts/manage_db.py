#!/usr/bin/env python3
"""
Database management CLI for Cancer Transcriptome Base.
Provides interactive and non-interactive database management interface.
"""
import sys
import logging
import argparse
from pathlib import Path
from typing import Dict, Any
from rich.console import Console
from rich.prompt import Confirm
from dotenv import load_dotenv
import os
from src.db.database import get_db_manager

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
console = Console()

class DatabaseMenu:
    """Interactive menu for database management."""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.choices = {
            '1': ('Check database status', self.check_status),
            '2': ('Reset database', self.reset_database),
            '3': ('Backup database', self.backup_database),
            '4': ('Restore database', self.restore_database),
            '5': ('Exit', self.exit_program)
        }

    def display_menu(self):
        """Display the interactive menu."""
        console.clear()
        console.print("[bold]Cancer Transcriptome Base - Database Management[/bold]\n")
        for key, (option, _) in self.choices.items():
            console.print(f"[bold]{key}[/bold]. {option}")
        return console.input("\n[bold]Choose an option:[/bold] ")

    def check_status(self):
        """Display database status."""
        self.db_manager.display_status()
        input("\nPress Enter to continue...")

    def reset_database(self):
        """Reset the database after confirmation."""
        if Confirm.ask("Are you sure you want to reset the database? This will delete all data!"):
            if self.db_manager.reset():
                console.print("[green]Database reset successfully[/green]")
            else:
                console.print("[red]Database reset failed[/red]")
        input("\nPress Enter to continue...")

    def backup_database(self):
        """Backup the database to a file."""
        output_file = console.input("Enter backup file path (default: backup.dump): ").strip() or "backup.dump"
        if self.db_manager.dump_database(output_file):
            console.print(f"[green]Database backed up successfully to {output_file}[/green]")
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
    env_path = project_root / '.env'
    load_dotenv(env_path)

    required_vars = ['MB_POSTGRES_HOST', 'MB_POSTGRES_PORT', 'MB_POSTGRES_NAME', 
                    'MB_POSTGRES_USER', 'MB_POSTGRES_PASSWORD']
    missing_vars = [var for var in required_vars if var not in os.environ]
    if missing_vars:
        console.print(f"[red]Missing required environment variables: {', '.join(missing_vars)}[/red]")
        sys.exit(1)

    return {
        "host": os.environ.get("MB_POSTGRES_HOST", "localhost"),
        "port": int(os.environ.get("MB_POSTGRES_PORT", "5432")),
        "dbname": os.environ.get("MB_POSTGRES_NAME", "mediabase"),
        "user": os.environ.get("MB_POSTGRES_USER", "postgres"),
        "password": os.environ.get("MB_POSTGRES_PASSWORD", "postgres")
    }

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Database management tool")
    parser.add_argument("--non-interactive", action="store_true", 
                       help="Run in non-interactive mode")
    parser.add_argument("--backup", help="Backup database to specified file")
    parser.add_argument("--restore", help="Restore database from specified file")
    args = parser.parse_args()

    config = load_config()
    db_manager = get_db_manager(config)

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
        DatabaseMenu(db_manager).run()

if __name__ == "__main__":
    main()

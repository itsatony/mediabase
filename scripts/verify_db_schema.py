"""Verify database schema for Cancer Transcriptome Base."""

import sys
import os
from pathlib import Path

# Add src to Python path
src_path = Path(__file__).resolve().parent.parent
sys.path.append(str(src_path))

from src.utils.logging import setup_logging, console
from src.db.database import get_db_manager, SCHEMA_VERSIONS
from rich.table import Table

# Use centralized logging with proper module name
logger = setup_logging(module_name=__name__)

def main() -> int:
    """Verify database schema and show status.
    
    Returns:
        int: 0 for success, 1 for error
    """
    # Use environment variables for database configuration
    config = {
        'host': os.getenv('MB_POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('MB_POSTGRES_PORT', '5432')),
        'dbname': os.getenv('MB_POSTGRES_NAME', 'mediabase'),
        'user': os.getenv('MB_POSTGRES_USER', 'postgres'),
        'password': os.getenv('MB_POSTGRES_PASSWORD', 'postgres')
    }
    
    try:
        # Connect to database
        db_manager = get_db_manager(config)
        db_manager.display_config()
        
        # Get current version
        current_version = db_manager.get_current_version()
        
        # Check if we're at or above minimum supported version
        if current_version and current_version < "v0.1.5":
            console.print(f"[yellow]Warning:[/yellow] Current schema version {current_version} is below minimum supported version v0.1.5")
            console.print("[yellow]You should reset the database to get a fresh v0.1.5 schema[/yellow]")
        
        # Create status table
        table = Table(title="Database Schema Status")
        table.add_column("Version", style="cyan")
        table.add_column("Status", style="green")
        
        # Check all schema versions
        for version in SCHEMA_VERSIONS.keys():
            if current_version and current_version >= version:
                table.add_row(version, "[green]Applied[/green] ✓")
            else:
                table.add_row(version, "[yellow]Pending[/yellow] ⚠")
        
        console.print(table)
        
        # Validate schema
        if db_manager.validate_schema():
            console.print("[green]Schema validation passed successfully[/green]")
        else:
            console.print("[red]Schema validation failed - database may need reset[/red]")
            return 1
        
        # Check the cancer_transcript_base table
        if db_manager.cursor:
            db_manager.cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'cancer_transcript_base'
                )
            """)
            
            result = db_manager.cursor.fetchone()
            if result and result[0]:  # Add None check before indexing
                # Get column information
                db_manager.cursor.execute("""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = 'cancer_transcript_base'
                """)
                
                # Create table structure view
                table = Table(title="Cancer Transcript Base Table Structure")
                table.add_column("Column", style="cyan")
                table.add_column("Type", style="green")
                
                for col in db_manager.cursor.fetchall():
                    table.add_row(col[0], col[1])
                
                console.print(table)
                
                # Get row count
                db_manager.cursor.execute("SELECT COUNT(*) FROM cancer_transcript_base")
                result = db_manager.cursor.fetchone()
                row_count = result[0] if result else 0  # Safe access with None check
                logger.info(f"Table has {row_count} rows")
            else:
                logger.error("cancer_transcript_base table does not exist!")
                return 1
                
        return 0
        
    except Exception as e:
        logger.error(f"Database verification failed: {e}")
        return 1
        
if __name__ == "__main__":
    sys.exit(main())

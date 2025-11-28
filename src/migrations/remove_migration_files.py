"""
Script to remove legacy migration files.

This script helps identify and optionally remove migration files
that are no longer needed since we only support v0.1.5+.
"""
import os
import logging
from typing import List, Optional
from pathlib import Path

# Setup logging
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    level=logging.INFO,
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def find_migration_files(base_dir: str = "src/migrations") -> List[Path]:
    """Find migration files that handle pre-0.1.5 versions.

    Args:
        base_dir: Directory to search for migration files

    Returns:
        List of Path objects for migration files to be removed
    """
    migration_path = Path(base_dir)
    if not migration_path.exists():
        logger.warning(f"Migration directory {base_dir} not found")
        return []

    # Identify migration files for versions before 0.1.5
    # Adjust the pattern as needed for your naming convention
    files_to_remove = []
    for file in migration_path.glob("*.py"):
        # Skip __init__.py and this script
        if file.name in ["__init__.py", "remove_migration_files.py"]:
            continue

        # Check if file is for pre-0.1.5 migrations
        # Adjust this logic based on your file naming convention
        if "pre_v0_1_5" in file.name or "legacy" in file.name:
            files_to_remove.append(file)

    return files_to_remove


def remove_files(files: List[Path], dry_run: bool = True) -> None:
    """Remove the specified files.

    Args:
        files: List of files to remove
        dry_run: If True, only print files that would be removed
    """
    for file in files:
        if dry_run:
            logger.info(f"Would remove: {file}")
        else:
            logger.info(f"Removing: {file}")
            file.unlink()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Remove legacy migration files")
    parser.add_argument(
        "--dir", default="src/migrations", help="Directory containing migration files"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually remove files (default is dry run)",
    )

    args = parser.parse_args()

    files = find_migration_files(args.dir)
    if not files:
        logger.info("No migration files found to remove")
    else:
        logger.info(f"Found {len(files)} migration files to remove")
        remove_files(files, not args.execute)

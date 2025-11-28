#!/usr/bin/env python3
"""
MEDIABASE Migration Script

This script orchestrates the complete migration from the corrupted current system
to the new normalized architecture with comprehensive error handling, validation,
and rollback capability.

Usage:
    poetry run python scripts/run_migration.py [--test-only] [--skip-confirmation] [--config-file CONFIG]

Options:
    --test-only         Run comprehensive tests without executing migration
    --skip-confirmation Skip user confirmation prompts (use with caution)
    --config-file       Path to custom configuration file
    --dry-run          Validate and plan migration without execution
    --rollback         Rollback to previous backup (requires migration ID)
"""

import sys
import json
import argparse
import os
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.db.database import get_db_manager
from src.utils.logging import get_logger
from src.migration import (
    ControlledMigration,
    MigrationTestFramework,
    MigrationController,
    PerformanceOptimizer,
)

logger = get_logger(__name__)


def load_db_config() -> Dict[str, Any]:
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
        logger.error(
            f"Missing required environment variables: {', '.join(missing_vars)}"
        )
        sys.exit(1)

    return {
        "host": os.environ.get("MB_POSTGRES_HOST", "localhost"),
        "port": int(os.environ.get("MB_POSTGRES_PORT", "5435")),
        "dbname": os.environ.get("MB_POSTGRES_NAME", "mediabase"),
        "user": os.environ.get("MB_POSTGRES_USER", "mbase_user"),
        "password": os.environ.get("MB_POSTGRES_PASSWORD", "mbase_secret"),
    }


def load_migration_config(config_file: str = None) -> Dict[str, Any]:
    """Load migration configuration from file or use defaults.

    Args:
        config_file: Path to configuration file

    Returns:
        Migration configuration dictionary
    """
    default_config = {
        "checkpoints_dir": "./migration_checkpoints",
        "require_user_confirmation": True,
        "validation": {
            "max_gene_symbol_length": 50,
            "required_gene_fields": ["gene_id", "gene_symbol", "gene_type"],
            "drug_name_min_length": 2,
            "cross_reference_databases": ["UniProt", "RefSeq", "Ensembl"],
            "go_categories": [
                "molecular_function",
                "biological_process",
                "cellular_component",
            ],
        },
        "performance": {
            "batch_size": 10000,
            "index_creation_parallel": True,
            "materialized_view_refresh_interval": 3600,
        },
        "testing": {
            "test_unit": True,
            "test_integration": True,
            "test_performance": True,
            "test_data_validation": True,
            "generate_report": True,
            "test_timeout": 300,
        },
    }

    if config_file and Path(config_file).exists():
        try:
            with open(config_file, "r") as f:
                user_config = json.load(f)

            # Merge user config with defaults
            config = {**default_config, **user_config}
            logger.info(f"📄 Loaded configuration from {config_file}")

        except Exception as e:
            logger.error(f"Failed to load config file {config_file}: {e}")
            logger.info("Using default configuration")
            config = default_config
    else:
        config = default_config
        logger.info("Using default migration configuration")

    return config


def run_comprehensive_tests(db_manager, config: Dict[str, Any]) -> bool:
    """Run comprehensive migration tests.

    Args:
        db_manager: Database manager instance
        config: Migration configuration

    Returns:
        True if all tests pass, False otherwise
    """
    logger.info("🧪 Running comprehensive migration tests...")

    try:
        test_framework = MigrationTestFramework(db_manager, config)
        results = test_framework.run_comprehensive_tests()

        # Print summary
        summary = results["summary"]
        logger.info(f"\n{'='*60}")
        logger.info("TESTING RESULTS SUMMARY")
        logger.info(f"{'='*60}")
        logger.info(f"Total tests: {summary['total_tests']}")
        logger.info(f"Passed: {summary['tests_passed']}")
        logger.info(f"Failed: {summary['tests_failed']}")
        logger.info(f"Errors: {summary['tests_errors']}")
        logger.info(f"Success rate: {summary['success_rate_percent']}%")
        logger.info(f"Overall status: {summary['overall_status']}")
        logger.info(f"Total time: {results['total_time']}s")

        if "report_path" in results:
            logger.info(f"Report saved to: {results['report_path']}")

        return summary["overall_status"] == "PASS"

    except Exception as e:
        logger.error(f"Testing failed catastrophically: {e}")
        return False


def execute_migration(db_manager, config: Dict[str, Any]) -> bool:
    """Execute the complete migration process.

    Args:
        db_manager: Database manager instance
        config: Migration configuration

    Returns:
        True if migration successful, False otherwise
    """
    logger.info("🚀 Starting MEDIABASE pipeline restructuring migration...")

    try:
        # Initialize controlled migration
        migration = ControlledMigration(db_manager, config)

        # Execute full migration
        success = migration.execute_full_migration()

        if success:
            logger.info("✅ Migration completed successfully!")
            logger.info("The new normalized system is now ready for use.")
        else:
            logger.error("❌ Migration failed!")
            logger.error("Check the logs and consider rollback if necessary.")

        return success

    except Exception as e:
        logger.error(f"Migration execution failed: {e}")
        return False


def rollback_migration(db_manager, migration_id: str, config: Dict[str, Any]) -> bool:
    """Rollback migration to previous state.

    Args:
        db_manager: Database manager instance
        migration_id: Migration ID to rollback
        config: Migration configuration

    Returns:
        True if rollback successful, False otherwise
    """
    logger.warning(f"⏪ Rolling back migration: {migration_id}")

    try:
        controller = MigrationController(db_manager, config)
        controller.migration_id = migration_id

        success = controller.rollback_to_backup()

        if success:
            logger.info("✅ Rollback completed successfully!")
        else:
            logger.error("❌ Rollback failed!")

        return success

    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        return False


def show_migration_status(db_manager) -> None:
    """Show current migration status and system information."""
    logger.info("📊 MEDIABASE System Status")
    logger.info(f"{'='*50}")

    try:
        # Check current system
        db_manager.cursor.execute("SELECT COUNT(*) FROM cancer_transcript_base")
        current_records = db_manager.cursor.fetchone()[0]
        logger.info(f"Current system records: {current_records:,}")

        # Check if new schema exists
        db_manager.cursor.execute(
            """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name IN ('genes', 'transcripts', 'drug_interactions')
        """
        )
        new_tables = db_manager.cursor.fetchone()[0]

        if new_tables >= 3:
            logger.info("✅ New normalized schema detected")

            # Check materialized views
            db_manager.cursor.execute(
                """
                SELECT COUNT(*) FROM information_schema.views
                WHERE table_name LIKE '%_view'
            """
            )
            views = db_manager.cursor.fetchone()[0]
            logger.info(f"Materialized views: {views}")

        else:
            logger.info("⚠️  New normalized schema not found")

        # Check backup schemas
        db_manager.cursor.execute(
            """
            SELECT COUNT(*) FROM information_schema.schemata
            WHERE schema_name LIKE 'mediabase_backup_%'
        """
        )
        backups = db_manager.cursor.fetchone()[0]
        logger.info(f"Available backups: {backups}")

    except Exception as e:
        logger.error(f"Status check failed: {e}")


def main():
    """Main script execution."""
    parser = argparse.ArgumentParser(
        description="MEDIABASE Pipeline Migration Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--test-only",
        action="store_true",
        help="Run comprehensive tests without executing migration",
    )

    parser.add_argument(
        "--skip-confirmation",
        action="store_true",
        help="Skip user confirmation prompts (use with caution)",
    )

    parser.add_argument(
        "--config-file", type=str, help="Path to custom configuration file"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and plan migration without execution",
    )

    parser.add_argument(
        "--rollback",
        type=str,
        metavar="MIGRATION_ID",
        help="Rollback to previous backup (requires migration ID)",
    )

    parser.add_argument(
        "--status", action="store_true", help="Show current migration status"
    )

    args = parser.parse_args()

    # Load configuration
    config = load_migration_config(args.config_file)

    # Apply command line overrides
    if args.skip_confirmation:
        config["require_user_confirmation"] = False

    # Initialize database manager
    try:
        db_config = load_db_config()
        db_manager = get_db_manager(db_config)
        logger.info("✅ Database connection established")
    except Exception as e:
        logger.error(f"❌ Failed to connect to database: {e}")
        return False

    # Execute requested operation
    try:
        if args.status:
            show_migration_status(db_manager)
            return True

        elif args.rollback:
            return rollback_migration(db_manager, args.rollback, config)

        elif args.test_only:
            return run_comprehensive_tests(db_manager, config)

        elif args.dry_run:
            logger.info("🔍 Dry run mode - validation only")
            # Run tests and validation without migration
            tests_passed = run_comprehensive_tests(db_manager, config)
            if tests_passed:
                logger.info(
                    "✅ Migration validation passed - system ready for migration"
                )
            else:
                logger.error(
                    "❌ Migration validation failed - resolve issues before migration"
                )
            return tests_passed

        else:
            # Full migration workflow
            logger.info("🚀 Starting full migration workflow")

            # Step 1: Run comprehensive tests
            logger.info("Step 1: Running comprehensive tests...")
            tests_passed = run_comprehensive_tests(db_manager, config)

            if not tests_passed:
                logger.error("❌ Tests failed - migration aborted")
                return False

            logger.info("✅ All tests passed - proceeding with migration")

            # Step 2: Execute migration
            logger.info("Step 2: Executing migration...")
            migration_success = execute_migration(db_manager, config)

            if migration_success:
                logger.info("🎉 MEDIABASE migration completed successfully!")
                logger.info(
                    "The system has been transformed to the new normalized architecture."
                )
                logger.info(
                    "Performance improvements and data quality enhancements are now active."
                )
                return True
            else:
                logger.error("❌ Migration failed - check logs for details")
                return False

    except KeyboardInterrupt:
        logger.warning("⚠️  Migration interrupted by user")
        return False

    except Exception as e:
        logger.error(f"💥 Unexpected error: {e}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

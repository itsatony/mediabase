"""Migration Controller for MEDIABASE Pipeline Restructuring.

This module provides comprehensive migration management with rollback capability,
checkpoint creation, and error handling for the transition from the corrupted
current system to the new normalized architecture.
"""

import json
import time
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from contextlib import contextmanager

from ..db.database import DatabaseManager
from ..utils.logging import get_logger

logger = get_logger(__name__)


class MigrationError(Exception):
    """Custom exception for migration-related errors."""

    pass


class MigrationController:
    """Manages database schema migrations with full rollback support."""

    def __init__(self, db_manager: DatabaseManager, config: Dict[str, Any]):
        """Initialize migration controller.

        Args:
            db_manager: Database manager instance
            config: Configuration dictionary with migration settings
        """
        self.db_manager = db_manager
        self.config = config
        self.migration_log = []
        self.backup_tables = []
        self.checkpoints_dir = Path(
            config.get("checkpoints_dir", "./migration_checkpoints")
        )
        self.checkpoints_dir.mkdir(exist_ok=True)

        # Migration metadata
        self.migration_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.backup_schema = None
        self.current_stage = None

    def create_backup_schema(self) -> str:
        """Create backup of current schema before migration.

        Returns:
            Name of the backup schema created

        Raises:
            MigrationError: If backup creation fails
        """
        try:
            backup_schema = f"mediabase_backup_{self.migration_id}"
            logger.info(f"Creating backup schema: {backup_schema}")

            with self.db_manager.transaction():
                # Create backup schema
                self.db_manager.cursor.execute(
                    f"CREATE SCHEMA IF NOT EXISTS {backup_schema}"
                )

                # Backup current table with all data
                self.db_manager.cursor.execute(
                    f"""
                    CREATE TABLE {backup_schema}.cancer_transcript_base AS
                    SELECT * FROM cancer_transcript_base
                """
                )

                # Backup indexes (store as metadata)
                self.db_manager.cursor.execute(
                    """
                    SELECT indexname, indexdef
                    FROM pg_indexes
                    WHERE tablename = 'cancer_transcript_base'
                      AND schemaname = 'public'
                """
                )

                index_definitions = self.db_manager.cursor.fetchall()

                # Save index definitions for potential restore
                backup_metadata = {
                    "backup_schema": backup_schema,
                    "original_table": "cancer_transcript_base",
                    "backup_timestamp": datetime.now().isoformat(),
                    "index_definitions": [
                        {"name": idx[0], "definition": idx[1]}
                        for idx in index_definitions
                    ],
                }

                # Save backup metadata
                backup_file = (
                    self.checkpoints_dir / f"backup_metadata_{self.migration_id}.json"
                )
                with open(backup_file, "w") as f:
                    json.dump(backup_metadata, f, indent=2)

                self.backup_schema = backup_schema
                logger.info(f"✅ Backup created successfully: {backup_schema}")

                return backup_schema

        except Exception as e:
            logger.error(f"Failed to create backup schema: {e}")
            raise MigrationError(f"Backup creation failed: {e}")

    def validate_migration_prerequisites(self) -> bool:
        """Validate system state before migration.

        Returns:
            True if all prerequisites are met, False otherwise
        """
        try:
            logger.info("Validating migration prerequisites...")

            checks = [
                ("disk_space", self._check_disk_space),
                ("database_connections", self._check_database_connections),
                ("current_data_integrity", self._check_current_data_integrity),
                ("backup_space", self._check_backup_space),
                ("permissions", self._check_permissions),
            ]

            all_passed = True
            failed_checks = []

            for check_name, check_func in checks:
                try:
                    result = check_func()
                    if result:
                        logger.info(f"✅ {check_name}: PASSED")
                    else:
                        logger.error(f"❌ {check_name}: FAILED")
                        all_passed = False
                        failed_checks.append(check_name)

                except Exception as e:
                    logger.error(f"❌ {check_name}: ERROR - {e}")
                    all_passed = False
                    failed_checks.append(check_name)

            if not all_passed:
                logger.error(f"Migration prerequisites failed: {failed_checks}")
                return False

            logger.info("✅ All migration prerequisites passed")
            return True

        except Exception as e:
            logger.error(f"Error validating prerequisites: {e}")
            return False

    def execute_phase(self, phase_func: Callable, phase_name: str) -> Any:
        """Execute migration phase with error handling and logging.

        Args:
            phase_func: Function to execute for this phase
            phase_name: Name of the migration phase

        Returns:
            Result from the phase function

        Raises:
            MigrationError: If the phase fails
        """
        try:
            logger.info(f"🔄 Starting migration phase: {phase_name}")
            self.current_stage = phase_name
            start_time = time.time()

            # Execute the phase
            result = phase_func()

            elapsed = time.time() - start_time
            logger.info(f"✅ Completed {phase_name} in {elapsed:.2f}s")

            # Log successful phase
            phase_log = {
                "phase": phase_name,
                "status": "success",
                "elapsed_seconds": round(elapsed, 2),
                "timestamp": datetime.now().isoformat(),
                "result_summary": self._summarize_result(result),
            }

            self.migration_log.append(phase_log)
            return result

        except Exception as e:
            elapsed = time.time() - start_time if "start_time" in locals() else 0
            logger.error(f"❌ Migration phase {phase_name} failed: {e}")

            # Log failed phase
            phase_log = {
                "phase": phase_name,
                "status": "failed",
                "error": str(e),
                "elapsed_seconds": round(elapsed, 2),
                "timestamp": datetime.now().isoformat(),
            }

            self.migration_log.append(phase_log)
            raise MigrationError(f"Phase {phase_name} failed: {e}")

    def create_checkpoint(
        self, stage_name: str, additional_data: Optional[Dict] = None
    ) -> Path:
        """Create recovery checkpoint after each stage.

        Args:
            stage_name: Name of the completed stage
            additional_data: Additional data to include in checkpoint

        Returns:
            Path to the checkpoint file created
        """
        try:
            checkpoint_data = {
                "migration_id": self.migration_id,
                "stage": stage_name,
                "timestamp": datetime.now().isoformat(),
                "backup_schema": self.backup_schema,
                "database_state": self._capture_database_state(),
                "migration_log": self.migration_log,
                "additional_data": additional_data or {},
            }

            checkpoint_file = (
                self.checkpoints_dir
                / f"checkpoint_{self.migration_id}_{stage_name}.json"
            )

            with open(checkpoint_file, "w") as f:
                json.dump(checkpoint_data, f, indent=2)

            logger.info(f"📋 Checkpoint created: {checkpoint_file}")
            return checkpoint_file

        except Exception as e:
            logger.error(f"Failed to create checkpoint: {e}")
            raise

    def rollback_to_backup(self) -> bool:
        """Rollback database to backup state.

        Returns:
            True if rollback successful, False otherwise
        """
        try:
            if not self.backup_schema:
                logger.error("No backup schema available for rollback")
                return False

            logger.warning(f"🔄 Rolling back to backup schema: {self.backup_schema}")

            with self.db_manager.transaction():
                # Drop current table
                self.db_manager.cursor.execute(
                    "DROP TABLE IF EXISTS cancer_transcript_base CASCADE"
                )

                # Restore from backup
                self.db_manager.cursor.execute(
                    f"""
                    CREATE TABLE cancer_transcript_base AS
                    SELECT * FROM {self.backup_schema}.cancer_transcript_base
                """
                )

                # Restore primary key
                self.db_manager.cursor.execute(
                    """
                    ALTER TABLE cancer_transcript_base
                    ADD CONSTRAINT cancer_transcript_base_pkey PRIMARY KEY (transcript_id)
                """
                )

                # Restore indexes (from backup metadata)
                backup_file = (
                    self.checkpoints_dir / f"backup_metadata_{self.migration_id}.json"
                )
                if backup_file.exists():
                    with open(backup_file) as f:
                        backup_metadata = json.load(f)

                    for idx_info in backup_metadata.get("index_definitions", []):
                        try:
                            # Modify index definition to work with restored table
                            idx_def = idx_info["definition"].replace(
                                "cancer_transcript_base", "cancer_transcript_base"
                            )
                            self.db_manager.cursor.execute(idx_def)
                        except Exception as e:
                            logger.warning(
                                f"Failed to restore index {idx_info['name']}: {e}"
                            )

                logger.info("✅ Rollback completed successfully")
                return True

        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return False

    def cleanup_migration_artifacts(self):
        """Clean up temporary migration artifacts."""
        try:
            logger.info("🧹 Cleaning up migration artifacts...")

            # Keep backup schema but remove temporary tables/schemas
            cleanup_commands = [
                "DROP SCHEMA IF EXISTS migration_temp CASCADE",
                "DROP SCHEMA IF EXISTS validation_temp CASCADE",
            ]

            for cmd in cleanup_commands:
                try:
                    self.db_manager.cursor.execute(cmd)
                except Exception as e:
                    logger.warning(f"Cleanup command failed: {cmd} - {e}")

            # Archive old checkpoint files (keep for reference)
            archive_dir = self.checkpoints_dir / "archived" / self.migration_id
            archive_dir.mkdir(parents=True, exist_ok=True)

            for checkpoint_file in self.checkpoints_dir.glob(
                f"*_{self.migration_id}_*.json"
            ):
                if checkpoint_file.is_file():
                    shutil.move(
                        str(checkpoint_file), str(archive_dir / checkpoint_file.name)
                    )

            logger.info("✅ Migration artifacts cleaned up")

        except Exception as e:
            logger.warning(f"Cleanup partially failed: {e}")

    # Private helper methods

    def _check_disk_space(self) -> bool:
        """Check if sufficient disk space is available."""
        try:
            # Get current database size
            self.db_manager.cursor.execute(
                """
                SELECT pg_size_pretty(pg_database_size(current_database()))
            """
            )

            db_size_pretty = self.db_manager.cursor.fetchone()[0]
            logger.info(f"Current database size: {db_size_pretty}")

            # Get actual size in bytes for calculation
            self.db_manager.cursor.execute(
                """
                SELECT pg_database_size(current_database())
            """
            )

            db_size_bytes = self.db_manager.cursor.fetchone()[0]

            # Check available disk space (simplified check)
            import shutil

            total, used, free = shutil.disk_usage("/")

            # Require at least 3x database size free (for backup + migration + safety)
            required_space = db_size_bytes * 3

            if free < required_space:
                logger.error(
                    f"Insufficient disk space. Need {required_space//1024//1024//1024}GB, have {free//1024//1024//1024}GB"
                )
                return False

            logger.info(
                f"Disk space check passed. Free: {free//1024//1024//1024}GB, Required: {required_space//1024//1024//1024}GB"
            )
            return True

        except Exception as e:
            logger.error(f"Disk space check failed: {e}")
            return False

    def _check_database_connections(self) -> bool:
        """Check database connections and permissions."""
        try:
            # Test basic connection
            self.db_manager.cursor.execute("SELECT 1")

            # Test transaction capability
            with self.db_manager.transaction():
                self.db_manager.cursor.execute("SELECT 1")

            # Check if we can create schemas
            self.db_manager.cursor.execute(
                "SELECT has_database_privilege(current_user, current_database(), 'CREATE')"
            )
            can_create = self.db_manager.cursor.fetchone()[0]

            if not can_create:
                logger.error("User does not have CREATE privileges")
                return False

            return True

        except Exception as e:
            logger.error(f"Database connection check failed: {e}")
            return False

    def _check_current_data_integrity(self) -> bool:
        """Check integrity of current data."""
        try:
            # Basic table existence and structure check
            self.db_manager.cursor.execute(
                """
                SELECT COUNT(*) FROM cancer_transcript_base
            """
            )

            record_count = self.db_manager.cursor.fetchone()[0]

            if record_count == 0:
                logger.error("Current table has no records")
                return False

            # Check for critical columns
            self.db_manager.cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'cancer_transcript_base'
                  AND column_name IN ('transcript_id', 'gene_symbol', 'gene_id')
            """
            )

            critical_columns = [row[0] for row in self.db_manager.cursor.fetchall()]

            if len(critical_columns) < 3:
                logger.error(f"Missing critical columns: {critical_columns}")
                return False

            logger.info(f"Data integrity check passed. Records: {record_count:,}")
            return True

        except Exception as e:
            logger.error(f"Data integrity check failed: {e}")
            return False

    def _check_backup_space(self) -> bool:
        """Check if we have space for backup."""
        # This is covered by disk space check
        return True

    def _check_permissions(self) -> bool:
        """Check database permissions for migration."""
        try:
            # Check schema creation
            test_schema = f"permission_test_{int(time.time())}"

            self.db_manager.cursor.execute(f"CREATE SCHEMA {test_schema}")
            self.db_manager.cursor.execute(f"DROP SCHEMA {test_schema}")

            return True

        except Exception as e:
            logger.error(f"Permission check failed: {e}")
            return False

    def _capture_database_state(self) -> Dict[str, Any]:
        """Capture current database state for checkpoint."""
        try:
            state = {}

            # Table sizes
            self.db_manager.cursor.execute(
                """
                SELECT
                    schemaname,
                    tablename,
                    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
                FROM pg_tables
                WHERE schemaname IN ('public')
                  AND tablename LIKE '%cancer%'
            """
            )

            state["table_sizes"] = [
                {"schema": row[0], "table": row[1], "size": row[2]}
                for row in self.db_manager.cursor.fetchall()
            ]

            # Record counts
            self.db_manager.cursor.execute(
                "SELECT COUNT(*) FROM cancer_transcript_base"
            )
            state["cancer_transcript_base_count"] = self.db_manager.cursor.fetchone()[0]

            # Index count
            self.db_manager.cursor.execute(
                """
                SELECT COUNT(*) FROM pg_indexes
                WHERE tablename = 'cancer_transcript_base'
            """
            )
            state["index_count"] = self.db_manager.cursor.fetchone()[0]

            return state

        except Exception as e:
            logger.warning(f"Failed to capture database state: {e}")
            return {"error": str(e)}

    def _summarize_result(self, result: Any) -> str:
        """Create summary of phase result."""
        if isinstance(result, dict):
            if "count" in result:
                return f"Processed {result['count']} items"
            elif "success" in result:
                return f"Success: {result['success']}"

        return str(type(result).__name__)


@contextmanager
def migration_transaction(db_manager: DatabaseManager, migration_name: str):
    """Context manager for migration transactions with automatic rollback."""
    try:
        logger.info(f"Starting migration transaction: {migration_name}")
        with db_manager.transaction():
            yield
        logger.info(f"Migration transaction completed: {migration_name}")
    except Exception as e:
        logger.error(f"Migration transaction failed: {migration_name} - {e}")
        raise

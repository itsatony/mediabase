"""Migration package for MEDIABASE pipeline restructuring."""

from .migration_controller import (
    MigrationController,
    MigrationError,
    migration_transaction,
)
from .data_extractor import RobustDataExtractor
from .data_validator import DataValidationFramework
from .controlled_migration import ControlledMigration
from .performance_optimizer import PerformanceOptimizer
from .test_framework import MigrationTestFramework
from .config_manager import ConfigurationManager, MigrationConfig
from .monitoring_dashboard import MigrationMonitor
from .post_migration_validator import PostMigrationValidator
from .patient_compatibility import PatientDataMigrator

__all__ = [
    "MigrationController",
    "MigrationError",
    "migration_transaction",
    "RobustDataExtractor",
    "DataValidationFramework",
    "ControlledMigration",
    "PerformanceOptimizer",
    "MigrationTestFramework",
    "ConfigurationManager",
    "MigrationConfig",
    "MigrationMonitor",
    "PostMigrationValidator",
    "PatientDataMigrator",
]

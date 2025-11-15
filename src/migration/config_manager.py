"""Configuration Management System for MEDIABASE Migration.

This module provides comprehensive configuration management with validation,
environment-specific settings, and dynamic configuration updates for the
migration system.
"""

import os
import json
import yaml
from typing import Dict, Any, Optional, List, Union
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime

from ..utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DatabaseConfig:
    """Database configuration settings."""
    host: str = "localhost"
    port: int = 5432
    database: str = "mbase"
    user: str = "mbase_user"
    password: str = "mbase_secret"
    connection_timeout: int = 30
    max_connections: int = 10
    backup_database: Optional[str] = None


@dataclass
class ValidationConfig:
    """Data validation configuration."""
    max_gene_symbol_length: int = 50
    required_gene_fields: List[str] = None
    drug_name_min_length: int = 2
    cross_reference_databases: List[str] = None
    go_categories: List[str] = None
    enable_strict_validation: bool = True
    validation_timeout: int = 300
    max_validation_errors: int = 1000

    def __post_init__(self):
        if self.required_gene_fields is None:
            self.required_gene_fields = ['gene_id', 'gene_symbol', 'gene_type']

        if self.cross_reference_databases is None:
            self.cross_reference_databases = ['UniProt', 'RefSeq', 'Ensembl']

        if self.go_categories is None:
            self.go_categories = ['molecular_function', 'biological_process', 'cellular_component']


@dataclass
class PerformanceConfig:
    """Performance and optimization configuration."""
    batch_size: int = 10000
    index_creation_parallel: bool = True
    materialized_view_refresh_interval: int = 3600
    query_timeout: int = 300
    memory_limit_mb: int = 2048
    parallel_workers: int = 4
    enable_query_optimization: bool = True
    cache_size_mb: int = 512


@dataclass
class TestingConfig:
    """Testing framework configuration."""
    test_unit: bool = True
    test_integration: bool = True
    test_performance: bool = True
    test_data_validation: bool = True
    generate_report: bool = True
    test_timeout: int = 300
    mock_data_size: int = 1000
    performance_threshold_ms: int = 1000
    coverage_threshold_percent: float = 80.0


@dataclass
class MigrationConfig:
    """Main migration configuration."""
    # Directories and paths
    checkpoints_dir: str = "./migration_checkpoints"
    backup_dir: str = "./migration_backups"
    temp_dir: str = "./migration_temp"
    log_dir: str = "./migration_logs"

    # Migration behavior
    require_user_confirmation: bool = True
    auto_cleanup: bool = False
    max_retry_attempts: int = 3
    stage_timeout_minutes: int = 60
    enable_rollback: bool = True

    # Component configurations
    database: DatabaseConfig = None
    validation: ValidationConfig = None
    performance: PerformanceConfig = None
    testing: TestingConfig = None

    # Environment settings
    environment: str = "development"
    debug_mode: bool = False
    verbose_logging: bool = True

    def __post_init__(self):
        if self.database is None:
            self.database = DatabaseConfig()
        if self.validation is None:
            self.validation = ValidationConfig()
        if self.performance is None:
            self.performance = PerformanceConfig()
        if self.testing is None:
            self.testing = TestingConfig()


class ConfigurationManager:
    """Manages migration configuration with validation and environment support."""

    def __init__(self, config_file: Optional[str] = None, environment: str = "development"):
        """Initialize configuration manager.

        Args:
            config_file: Path to configuration file
            environment: Target environment (development, testing, production)
        """
        self.environment = environment
        self.config_file = config_file
        self.config = MigrationConfig()
        self._load_configuration()

    def _load_configuration(self) -> None:
        """Load configuration from file, environment variables, and defaults."""
        logger.info(f"Loading configuration for environment: {self.environment}")

        # Step 1: Load from default configuration
        self._load_defaults()

        # Step 2: Load from configuration file if provided
        if self.config_file:
            self._load_from_file(self.config_file)

        # Step 3: Override with environment variables
        self._load_from_environment()

        # Step 4: Apply environment-specific overrides
        self._apply_environment_overrides()

        # Step 5: Validate configuration
        self._validate_configuration()

        logger.info("✅ Configuration loaded and validated successfully")

    def _load_defaults(self) -> None:
        """Load default configuration values."""
        self.config = MigrationConfig()
        self.config.environment = self.environment

    def _load_from_file(self, config_file: str) -> None:
        """Load configuration from file (JSON or YAML).

        Args:
            config_file: Path to configuration file
        """
        try:
            config_path = Path(config_file)

            if not config_path.exists():
                logger.warning(f"Configuration file not found: {config_file}")
                return

            with open(config_path, 'r') as f:
                if config_path.suffix.lower() in ['.yml', '.yaml']:
                    file_config = yaml.safe_load(f)
                else:
                    file_config = json.load(f)

            self._merge_config(file_config)
            logger.info(f"📄 Loaded configuration from: {config_file}")

        except Exception as e:
            logger.error(f"Failed to load configuration file {config_file}: {e}")
            raise

    def _load_from_environment(self) -> None:
        """Load configuration from environment variables."""
        env_mappings = {
            # Database settings
            'MB_POSTGRES_HOST': 'database.host',
            'MB_POSTGRES_PORT': 'database.port',
            'MB_POSTGRES_DB': 'database.database',
            'MB_POSTGRES_USER': 'database.user',
            'MB_POSTGRES_PASSWORD': 'database.password',

            # Migration settings
            'MB_MIGRATION_CHECKPOINTS_DIR': 'checkpoints_dir',
            'MB_MIGRATION_BACKUP_DIR': 'backup_dir',
            'MB_MIGRATION_TEMP_DIR': 'temp_dir',
            'MB_MIGRATION_LOG_DIR': 'log_dir',

            # Behavior settings
            'MB_MIGRATION_AUTO_CLEANUP': 'auto_cleanup',
            'MB_MIGRATION_DEBUG': 'debug_mode',
            'MB_MIGRATION_VERBOSE': 'verbose_logging',

            # Performance settings
            'MB_MIGRATION_BATCH_SIZE': 'performance.batch_size',
            'MB_MIGRATION_PARALLEL_WORKERS': 'performance.parallel_workers',
            'MB_MIGRATION_MEMORY_LIMIT': 'performance.memory_limit_mb',
        }

        for env_var, config_path in env_mappings.items():
            env_value = os.getenv(env_var)
            if env_value is not None:
                try:
                    self._set_nested_value(config_path, self._convert_env_value(env_value))
                    logger.debug(f"Set {config_path} from {env_var}")
                except Exception as e:
                    logger.warning(f"Failed to set {config_path} from {env_var}: {e}")

    def _apply_environment_overrides(self) -> None:
        """Apply environment-specific configuration overrides."""
        if self.environment == "production":
            self.config.debug_mode = False
            self.config.testing.test_unit = False
            self.config.testing.test_integration = False
            self.config.validation.enable_strict_validation = True
            self.config.require_user_confirmation = True

        elif self.environment == "testing":
            self.config.debug_mode = True
            self.config.require_user_confirmation = False
            self.config.testing.mock_data_size = 100  # Smaller for testing
            self.config.auto_cleanup = True

        elif self.environment == "development":
            self.config.debug_mode = True
            self.config.verbose_logging = True
            self.config.testing.generate_report = True

        logger.debug(f"Applied {self.environment} environment overrides")

    def _validate_configuration(self) -> None:
        """Validate configuration settings."""
        errors = []

        # Validate database configuration
        if not self.config.database.host:
            errors.append("Database host is required")

        if not (1 <= self.config.database.port <= 65535):
            errors.append("Database port must be between 1 and 65535")

        # Validate directory paths
        for dir_attr in ['checkpoints_dir', 'backup_dir', 'temp_dir', 'log_dir']:
            dir_path = getattr(self.config, dir_attr)
            try:
                Path(dir_path).mkdir(parents=True, exist_ok=True)
            except Exception as e:
                errors.append(f"Cannot create {dir_attr} '{dir_path}': {e}")

        # Validate performance settings
        if self.config.performance.batch_size <= 0:
            errors.append("Performance batch_size must be positive")

        if self.config.performance.parallel_workers <= 0:
            errors.append("Performance parallel_workers must be positive")

        # Validate testing settings
        if not (0 <= self.config.testing.coverage_threshold_percent <= 100):
            errors.append("Testing coverage threshold must be between 0 and 100")

        if errors:
            error_message = "Configuration validation failed:\n" + "\n".join(f"  - {error}" for error in errors)
            raise ValueError(error_message)

    def _merge_config(self, new_config: Dict[str, Any]) -> None:
        """Merge new configuration with existing configuration.

        Args:
            new_config: Configuration dictionary to merge
        """
        def merge_dict(base: Dict[str, Any], overlay: Dict[str, Any]) -> None:
            for key, value in overlay.items():
                if isinstance(value, dict) and key in base and isinstance(base[key], dict):
                    merge_dict(base[key], value)
                else:
                    base[key] = value

        # Convert config to dict, merge, and convert back
        config_dict = asdict(self.config)
        merge_dict(config_dict, new_config)

        # Reconstruct config object
        self.config = self._dict_to_config(config_dict)

    def _dict_to_config(self, config_dict: Dict[str, Any]) -> MigrationConfig:
        """Convert dictionary to MigrationConfig object.

        Args:
            config_dict: Configuration dictionary

        Returns:
            MigrationConfig object
        """
        # Extract nested configs
        db_config = DatabaseConfig(**config_dict.pop('database', {}))
        val_config = ValidationConfig(**config_dict.pop('validation', {}))
        perf_config = PerformanceConfig(**config_dict.pop('performance', {}))
        test_config = TestingConfig(**config_dict.pop('testing', {}))

        # Create main config
        main_config = MigrationConfig(**config_dict)
        main_config.database = db_config
        main_config.validation = val_config
        main_config.performance = perf_config
        main_config.testing = test_config

        return main_config

    def _set_nested_value(self, path: str, value: Any) -> None:
        """Set nested configuration value using dot notation.

        Args:
            path: Dot-separated path (e.g., 'database.host')
            value: Value to set
        """
        parts = path.split('.')
        target = self.config

        for part in parts[:-1]:
            target = getattr(target, part)

        setattr(target, parts[-1], value)

    def _convert_env_value(self, value: str) -> Union[str, int, float, bool]:
        """Convert environment variable string to appropriate type.

        Args:
            value: String value from environment variable

        Returns:
            Converted value
        """
        # Boolean conversion
        if value.lower() in ('true', 'false'):
            return value.lower() == 'true'

        # Integer conversion
        try:
            if '.' not in value:
                return int(value)
        except ValueError:
            pass

        # Float conversion
        try:
            return float(value)
        except ValueError:
            pass

        # String (default)
        return value

    def get_database_config(self) -> DatabaseConfig:
        """Get database configuration.

        Returns:
            DatabaseConfig object
        """
        return self.config.database

    def get_migration_config(self) -> MigrationConfig:
        """Get complete migration configuration.

        Returns:
            MigrationConfig object
        """
        return self.config

    def save_configuration(self, output_file: str, format: str = "yaml") -> None:
        """Save current configuration to file.

        Args:
            output_file: Output file path
            format: Output format ('yaml' or 'json')
        """
        try:
            config_dict = asdict(self.config)

            with open(output_file, 'w') as f:
                if format.lower() == 'yaml':
                    yaml.dump(config_dict, f, default_flow_style=False, indent=2)
                else:
                    json.dump(config_dict, f, indent=2)

            logger.info(f"📄 Configuration saved to: {output_file}")

        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
            raise

    def create_environment_config(self, environment: str, output_dir: str) -> None:
        """Create environment-specific configuration files.

        Args:
            environment: Target environment
            output_dir: Output directory for configuration files
        """
        try:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            # Create base config for environment
            env_config = MigrationConfig()
            env_config.environment = environment

            # Apply environment-specific settings
            if environment == "production":
                env_config.debug_mode = False
                env_config.require_user_confirmation = True
                env_config.validation.enable_strict_validation = True
                env_config.auto_cleanup = False
                env_config.performance.parallel_workers = 8
                env_config.performance.memory_limit_mb = 4096

            elif environment == "testing":
                env_config.debug_mode = True
                env_config.require_user_confirmation = False
                env_config.auto_cleanup = True
                env_config.testing.mock_data_size = 100
                env_config.performance.parallel_workers = 2

            elif environment == "development":
                env_config.debug_mode = True
                env_config.verbose_logging = True
                env_config.testing.generate_report = True

            # Save configuration
            config_file = output_path / f"migration_config_{environment}.yaml"
            config_dict = asdict(env_config)

            with open(config_file, 'w') as f:
                yaml.dump(config_dict, f, default_flow_style=False, indent=2)

            logger.info(f"✅ Created {environment} configuration: {config_file}")

        except Exception as e:
            logger.error(f"Failed to create environment config: {e}")
            raise

    def get_config_summary(self) -> Dict[str, Any]:
        """Get configuration summary for logging/display.

        Returns:
            Configuration summary dictionary
        """
        return {
            'environment': self.config.environment,
            'database_host': self.config.database.host,
            'database_port': self.config.database.port,
            'database_name': self.config.database.database,
            'checkpoints_dir': self.config.checkpoints_dir,
            'require_confirmation': self.config.require_user_confirmation,
            'debug_mode': self.config.debug_mode,
            'batch_size': self.config.performance.batch_size,
            'parallel_workers': self.config.performance.parallel_workers,
            'testing_enabled': {
                'unit': self.config.testing.test_unit,
                'integration': self.config.testing.test_integration,
                'performance': self.config.testing.test_performance,
                'validation': self.config.testing.test_data_validation
            }
        }

    def update_runtime_config(self, updates: Dict[str, Any]) -> None:
        """Update configuration at runtime.

        Args:
            updates: Dictionary of configuration updates
        """
        try:
            self._merge_config(updates)
            self._validate_configuration()
            logger.info("✅ Runtime configuration updated successfully")

        except Exception as e:
            logger.error(f"Failed to update runtime configuration: {e}")
            raise
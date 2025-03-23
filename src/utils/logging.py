"""Centralized logging utilities for MediaBase ETL processes.

This module provides standardized logging setup with both console (rich) and
file logging capabilities, integrated progress tracking, and consistent
formatting across all application components.
"""

import logging
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Union, Dict, Any, Callable, List
from logging.handlers import RotatingFileHandler

import tqdm
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn

# Constants for log configuration
DEFAULT_LOG_LEVEL = logging.INFO
DEFAULT_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DEFAULT_LOG_DATE_FORMAT = "%H:%M:%S"
DEFAULT_LOG_DIR = "logs"
DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_BACKUP_COUNT = 5

# Global console object for rich output
console = Console()

class TqdmLoggingHandler(logging.Handler):
    """Logging handler that writes through tqdm to avoid breaking progress bars."""
    
    def emit(self, record: logging.LogRecord) -> None:
        """Write log record using tqdm.write to avoid breaking progress bars.
        
        Args:
            record: The log record to emit
        """
        try:
            msg = self.format(record)
            tqdm.tqdm.write(msg)
            self.flush()
        except Exception:
            self.handleError(record)


class ETLProgressBar:
    """Progress bar manager with tqdm integration and rich formatting."""
    
    def __init__(
        self, 
        total: int, 
        desc: str = "Processing", 
        unit: str = "items",
        log_interval: int = 1000
    ) -> None:
        """Initialize progress bar.
        
        Args:
            total: Total number of items to process
            desc: Description for the progress bar
            unit: Unit of items being processed
            log_interval: Log progress every N items
        """
        self.total = total
        self.desc = desc
        self.unit = unit
        self.log_interval = log_interval
        self.pbar = None
        self.logger = logging.getLogger("etl.progress")
        self.start_time = None
        
    def __enter__(self) -> tqdm.tqdm:
        """Start progress tracking and return the progress bar object.
        
        Returns:
            The tqdm progress bar instance
        """
        self.start_time = datetime.now()
        self.pbar = tqdm.tqdm(
            total=self.total,
            desc=self.desc,
            unit=self.unit,
            dynamic_ncols=True,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]"
        )
        
        self.logger.info(f"Started {self.desc} with {self.total:,} {self.unit}")
        return self.pbar
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Close the progress bar and log completion time."""
        items_processed = 0
        if self.pbar:
            items_processed = self.pbar.n
            self.pbar.close()
            
        elapsed = datetime.now() - self.start_time if self.start_time else None
        if elapsed:
            self.logger.info(
                f"Completed {self.desc}: processed {items_processed:,}/{self.total:,} "
                f"{self.unit} in {elapsed.total_seconds():.2f}s"
            )


def setup_logging(
    log_level: Union[int, str] = DEFAULT_LOG_LEVEL,
    log_file: Optional[str] = None,
    module_name: str = "mediabase",
    console_output: bool = True,
    rich_output: bool = True,
) -> logging.Logger:
    """Set up logging with both file and console handlers.
    
    Args:
        log_level: The logging level (DEBUG, INFO, etc.)
        log_file: Path to log file (if None, no file logging)
        module_name: Name of the module for logger
        console_output: Whether to enable console output
        rich_output: Whether to use rich formatting for console output
        
    Returns:
        The configured logger instance
    """
    # Convert string log level to numeric if needed
    if isinstance(log_level, str):
        log_level = getattr(logging, log_level.upper(), DEFAULT_LOG_LEVEL)
        
    # Create logger
    logger = logging.getLogger(module_name)
    logger.setLevel(log_level)
    
    # Remove existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    
    # Add file handler if log_file is specified
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=DEFAULT_MAX_BYTES,
            backupCount=DEFAULT_BACKUP_COUNT
        )
        file_formatter = logging.Formatter(DEFAULT_LOG_FORMAT, DEFAULT_LOG_DATE_FORMAT)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    # Add console handler if console_output is True
    if console_output:
        if rich_output and "pytest" not in sys.modules:
            # Use Rich formatter for console if rich_output is True and not in pytest
            console_handler = RichHandler(
                rich_tracebacks=True,
                show_time=True,
                show_path=False,
                markup=False,
                console=console
            )
        else:
            # Use tqdm-compatible handler for progress bar compatibility
            console_handler = TqdmLoggingHandler()
            console_formatter = logging.Formatter(
                f"%(asctime)s %(levelname)s %(name)s - %(message)s",
                DEFAULT_LOG_DATE_FORMAT
            )
            console_handler.setFormatter(console_formatter)
            
        logger.addHandler(console_handler)
    
    # Prevent propagation to root logger to avoid duplicate logs
    logger.propagate = False
    
    return logger


def get_etl_logger(
    module_name: str,
    log_level: Union[int, str] = DEFAULT_LOG_LEVEL,
    log_file: Optional[str] = None
) -> logging.Logger:
    """Get a logger specifically configured for ETL operations.
    
    Args:
        module_name: Name of the ETL module
        log_level: Logging level
        log_file: Optional log file path
        
    Returns:
        Configured logger for ETL operations
    """
    # Set default log file if not provided
    if log_file is None:
        log_dir = Path(DEFAULT_LOG_DIR)
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d")
        log_file = str(log_dir / f"etl_{module_name}_{timestamp}.log")
    
    # Full module name for the logger
    full_module_name = f"etl.{module_name}"
    
    return setup_logging(
        log_level=log_level,
        log_file=log_file,
        module_name=full_module_name,
        console_output=True,
        rich_output=True
    )

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

# Global logger registry to avoid duplicate setup
_loggers = {}

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

def configure_tqdm() -> None:
    """Configure tqdm for single-line updates and consistent display."""
    # Set global default format
    tqdm.tqdm.monitor_interval = 0  # Disable monitor thread
    
    # Create custom tqdm class that always updates in-place
    original_tqdm = tqdm.tqdm
    
    # Extend tqdm to always have position=0 and leave=False by default
    class SingleLineTqdm(original_tqdm):
        def __init__(self, *args, **kwargs):
            if 'position' not in kwargs:
                kwargs['position'] = 0
            if 'leave' not in kwargs:
                kwargs['leave'] = False
            if 'bar_format' not in kwargs:
                # Use a compact format that fits better with our other output
                kwargs['bar_format'] = '{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]'
            super().__init__(*args, **kwargs)
    
    # Replace the tqdm class
    tqdm.tqdm = SingleLineTqdm

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
    # Check if logger is already configured
    if module_name in _loggers:
        return _loggers[module_name]
        
    # Configure tqdm for consistent display
    configure_tqdm()
    
    # Convert string log level to numeric if needed
    if isinstance(log_level, str):
        log_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Create logger
    logger = logging.getLogger(module_name)
    logger.setLevel(log_level)
    
    # Remove existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    
    # Add file handler if log_file is specified
    if log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
            
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=DEFAULT_MAX_BYTES,
            backupCount=DEFAULT_BACKUP_COUNT
        )
        file_formatter = logging.Formatter(
            DEFAULT_LOG_FORMAT,
            datefmt=DEFAULT_LOG_DATE_FORMAT
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    # Add console handler if console_output is True
    if console_output:
        if rich_output:
            # Use Rich for pretty console output with consistent timestamp format
            console_handler = RichHandler(
                rich_tracebacks=True,
                console=console,
                show_time=True,
                show_level=True,
                show_path=False,
                markup=True,
                log_time_format=DEFAULT_LOG_DATE_FORMAT,
                omit_repeated_times=False
            )
        else:
            # Use TqdmLoggingHandler for compatibility with progress bars
            console_handler = TqdmLoggingHandler()
            console_formatter = logging.Formatter(
                DEFAULT_LOG_FORMAT,
                datefmt=DEFAULT_LOG_DATE_FORMAT
            )
            console_handler.setFormatter(console_formatter)
            
        logger.addHandler(console_handler)
    
    # Prevent propagation to root logger to avoid duplicate logs
    logger.propagate = False
    
    # Store in registry
    _loggers[module_name] = logger
    
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
        log_dir.mkdir(exist_ok=True)
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

# Create a singleton progress instance for ETL operations
_progress_instance = None

def get_progress() -> Progress:
    """Get a shared progress instance for ETL operations.
    
    Returns:
        Progress instance for tracking ETL operations
    """
    global _progress_instance
    if _progress_instance is None:
        _progress_instance = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TextColumn("•"),
            TimeRemainingColumn(),
            console=console,
            transient=True  # Ensures progress bars disappear after completion
        )
    return _progress_instance

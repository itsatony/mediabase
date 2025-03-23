"""Centralized logging utilities for MediaBase ETL processes.

This module provides standardized logging setup with both console (rich) and
file logging capabilities, integrated progress tracking, and consistent
formatting across all application components.
"""

import logging
import sys
import os
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Union, Dict, Any, Callable, List, cast
from logging.handlers import RotatingFileHandler
import threading
import io

import tqdm
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn, TimeElapsedColumn

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

# Global progress instance
_progress_instance = None
_progress_lock = threading.Lock()

class UnifiedProgressBar:
    """A unified progress bar that works with logging and follows all formatting rules."""
    
    def __init__(self, 
                 total: int, 
                 desc: str, 
                 module_name: str = "mediabase",
                 unit: str = "it") -> None:
        """Initialize the progress bar.
        
        Args:
            total: Total number of items to process
            desc: Description of the progress
            module_name: Module name for logging prefix
            unit: Unit name for items being processed
        """
        self.total = total
        self.desc = desc
        self.module_name = module_name
        self.unit = unit
        self.n = 0
        self.start_time = time.time()
        self.last_update_time = 0
        self.min_update_interval = 0.1  # Seconds between updates
        self._last_line_length = 0
        self._is_finished = False
        # Add an attribute to track progress as float for more precise reporting
        self._progress_value = 0.0
        
        # Create format string with timestamp and module
        timestamp = datetime.now().strftime(DEFAULT_LOG_DATE_FORMAT)
        self.prefix = f"{timestamp} INFO     {self.module_name} - "
        
        # Print initial progress bar
        self._update_progress()
    
    def update(self, n: int = 1) -> None:
        """Update the progress bar.
        
        Args:
            n: Number of items to increment by
        """
        self.n += n
        self._progress_value += float(n)
        
        # Throttle updates to avoid excessive printing
        current_time = time.time()
        if current_time - self.last_update_time < self.min_update_interval:
            return
            
        self.last_update_time = current_time
        
        if not self._is_finished:
            self._update_progress()
            
    # Add a method to update progress with float values
    def update_float(self, value: float) -> None:
        """Update the progress bar with a float value.
        
        Args:
            value: Float value to update progress by
        """
        # Update internal float tracker
        self._progress_value = value
        # Update integer counter as well (rounded down)
        self.n = int(value)
        
        # Throttle updates to avoid excessive printing
        current_time = time.time()
        if current_time - self.last_update_time < self.min_update_interval:
            return
            
        self.last_update_time = current_time
        
        if not self._is_finished:
            self._update_progress()
    
    def _update_progress(self) -> None:
        """Update the progress display."""
        # Calculate progress metrics
        elapsed = time.time() - self.start_time
        pct = min(100, (self.n * 100 / self.total) if self.total > 0 else 100)
        
        # Calculate remaining time
        if self.n > 0:
            remaining = elapsed * (self.total - self.n) / self.n
        else:
            remaining = 0
            
        # Format remaining time
        if remaining > 3600:
            remaining_str = f"{int(remaining/3600):d}:{int((remaining%3600)/60):02d}:{int(remaining%60):02d}"
        else:
            remaining_str = f"{int(remaining/60):d}:{int(remaining%60):02d}"
            
        # Format elapsed time
        if elapsed > 3600:
            elapsed_str = f"{int(elapsed/3600):d}:{int((elapsed%3600)/60):02d}:{int(elapsed%60):02d}"
        else:
            elapsed_str = f"{int(elapsed/60):d}:{int(elapsed%60):02d}"
            
        # Create progress bar (30 chars wide)
        bar_width = 30
        filled = int(pct / 100 * bar_width)
        bar = '█' * filled + '░' * (bar_width - filled)
        
        # Assemble the full progress line with all required components
        # Rule 1: prefix with timestamp and module name
        # Rule 2 & 7: Single line that will be updated in place
        # Rule 3: Include count/total
        # Rule 4: Include elapsed time
        progress_line = f"{self.prefix}{self.desc}: [{bar}] {pct:.1f}% {self.n}/{self.total} [elapsed: {elapsed_str}, remaining: {remaining_str}]"
        
        # Calculate padding to overwrite previous line completely
        if len(progress_line) < self._last_line_length:
            progress_line += ' ' * (self._last_line_length - len(progress_line))
        self._last_line_length = len(progress_line)
        
        # Print the progress line
        # Using carriage return to update in place
        sys.stdout.write('\r' + progress_line)
        sys.stdout.flush()
    
    def close(self) -> None:
        """Finish the progress bar and move to a new line."""
        self._is_finished = True
        self._update_progress()
        # Rule 6: Add a newline after progress completes
        sys.stdout.write('\n')
        sys.stdout.flush()


class LoggerStreamCapture(io.StringIO):
    """Capture log output to prevent it from breaking progress bars."""
    
    def __init__(self, original_stream=None):
        """Initialize with optional original stream to tee output to."""
        super().__init__()
        self.original_stream = original_stream
        self.progress_active = False
    
    def write(self, s: str) -> int:
        """Write to the buffer and optionally to original stream.
        
        Args:
            s: String to write
            
        Returns:
            int: Number of characters written
        """
        # If a progress bar is active, first print a newline
        if self.progress_active and s.strip():
            if self.original_stream:
                self.original_stream.write('\n')
            self.progress_active = False
        
        # Write to our buffer and count characters
        chars_written = super().write(s)
        
        # Also write to original stream if provided
        if self.original_stream:
            self.original_stream.write(s)
            
        return chars_written
    
    def set_progress_active(self, active: bool = True):
        """Indicate that a progress bar is active."""
        self.progress_active = active


class CustomTqdmHandler(logging.Handler):
    """Custom logging handler that ensures tqdm progress bars work with logging."""
    
    def __init__(self, level=logging.NOTSET):
        """Initialize the handler."""
        super().__init__(level)
        self.stream_capture = LoggerStreamCapture(sys.stdout)
    
    def emit(self, record):
        """Format and emit a log record."""
        try:
            msg = self.format(record)
            # Always print a newline first to ensure we don't overwrite a progress bar
            if self.stream_capture.progress_active:
                sys.stdout.write('\n')
                
            # Write the message
            sys.stdout.write(msg + '\n')
            sys.stdout.flush()
        except Exception:
            self.handleError(record)
    
    def set_progress_active(self, active: bool = True):
        """Set whether a progress bar is currently active."""
        self.stream_capture.set_progress_active(active)


def get_progress_bar(total: int, 
                    desc: str, 
                    module_name: str = "mediabase", 
                    unit: str = "it") -> UnifiedProgressBar:
    """Get a unified progress bar that integrates with the logging system.
    
    Args:
        total: Total number of items to process
        desc: Description of the progress operation
        module_name: Module name for logging prefix
        unit: Unit label for the items
        
    Returns:
        A properly configured progress bar
    """
    return UnifiedProgressBar(total, desc, module_name, unit)


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
            # Use our custom handler for better integration with progress bars
            console_handler = CustomTqdmHandler()
            console_formatter = logging.Formatter(
                "%(asctime)s %(levelname)-8s %(name)s - %(message)s",
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
        rich_output=False  # Use the custom formatter for ETL
    )


# For backward compatibility - will be deprecated
def get_progress() -> Progress:
    """Get a shared progress instance for ETL operations (Legacy method).
    
    This is kept for backward compatibility but progress should migrate
    to using get_progress_bar() instead.
    
    Returns:
        Progress instance for tracking ETL operations
    """
    global _progress_instance
    with _progress_lock:
        if (_progress_instance is None):
            _progress_instance = Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                TextColumn("•"),
                TimeRemainingColumn(),
                console=console,
                transient=True  # Ensures progress bars disappear after completion
            )
    return _progress_instance


# Helper functions for download progress reporting
def create_download_progress_bar(desc: str, total: int, module_name: str) -> UnifiedProgressBar:
    """Create a properly formatted download progress bar.
    
    Args:
        desc: File being downloaded
        total: Total size in bytes
        module_name: Module name for logging
        
    Returns:
        UnifiedProgressBar: Configured progress bar for downloads
    """
    # Convert total to MB for display
    total_mb = total / (1024 * 1024)
    unit = "MB"
    
    # Create description with file and size
    display_desc = f"Downloading {desc} ({total_mb:.1f} {unit})"
    
    # Return properly configured progress bar
    return get_progress_bar(total, display_desc, module_name, unit)


def format_download_progress(progress_bar: UnifiedProgressBar, n: int) -> None:
    """Update download progress with proper formatting.
    
    Args:
        progress_bar: The progress bar to update
        n: Current number of bytes downloaded
    """
    # Convert to MB for more readable display
    n_mb = n / (1024 * 1024)
    
    # Use the new update_float method to handle float values
    progress_bar.update_float(n_mb)

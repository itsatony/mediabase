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

# Global progress manager instance
_progress_manager = None
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
        self.timestamp_format = DEFAULT_LOG_DATE_FORMAT
        
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
        # Create fresh timestamp for each update (Rule 1)
        timestamp = datetime.now().strftime(self.timestamp_format)
        prefix = f"{timestamp} INFO {self.module_name:10s} - "
        
        # Calculate progress metrics
        elapsed = time.time() - self.start_time
        pct = min(100, (self.n * 100 / self.total) if self.total > 0 else 100)
        
        # Calculate remaining time (Rule 4)
        if self.n > 0 and self.total > 0:
            remaining = elapsed * (self.total - self.n) / self.n
        else:
            remaining = 0
            
        # Format time strings
        def format_time(seconds):
            """Format time in appropriate units."""
            if seconds > 3600:
                return f"{int(seconds/3600):d}h{int((seconds%3600)/60):02d}m{int(seconds%60):02d}s"
            elif seconds > 60:
                return f"{int(seconds/60):d}m{int(seconds%60):02d}s"
            else:
                return f"{int(seconds):d}s"
        
        remaining_str = format_time(remaining)
        elapsed_str = format_time(elapsed)
            
        # Create progress bar (30 chars wide) (Rule 5)
        bar_width = 30
        filled = int(pct / 100 * bar_width)
        bar = '█' * filled + '░' * (bar_width - filled)
        
        # Assemble the full progress line with all required components
        # Rule 3: Include count/total
        progress_line = f"{prefix}{self.desc}: [{bar}] {pct:.1f}% {self.n}/{self.total} [elapsed: {elapsed_str}, remaining: {remaining_str}]"
        
        # Calculate padding to overwrite previous line completely (Rule 7)
        if len(progress_line) < self._last_line_length:
            progress_line += ' ' * (self._last_line_length - len(progress_line))
        self._last_line_length = len(progress_line)
        
        # Print the progress line using carriage return to update in place (Rule 2)
        sys.stdout.write('\r' + progress_line)
        sys.stdout.flush()
    
    def complete(self) -> None:
        """Force completion of the progress bar (sets to 100%)."""
        if not self._is_finished:
            self.n = self.total
            self._progress_value = float(self.total)
            self._update_progress()
            self.close()
    
    def close(self) -> None:
        """Finish the progress bar and move to a new line."""
        if not self._is_finished:
            self._is_finished = True
            self._update_progress()
            # Rule 6: Add a newline after progress completes
            sys.stdout.write('\n')
            sys.stdout.flush()
            # Add a small delay to ensure the console output is flushed
            time.sleep(0.01)


class ProgressManager:
    """Centralized manager for all progress bars throughout the application."""
    
    def __init__(self):
        """Initialize the progress manager."""
        self.active_bars = {}
        self.lock = threading.Lock()
        self.bar_id_counter = 0
    
    def create_bar(self, 
                  total: int, 
                  desc: str, 
                  module_name: str = "mediabase", 
                  unit: str = "it") -> UnifiedProgressBar:
        """Create a new progress bar with a unique ID.
        
        Args:
            total: Total number of items to process
            desc: Description of the progress
            module_name: Module name for logging prefix
            unit: Unit name for items being processed
            
        Returns:
            UnifiedProgressBar: A new unified progress bar
        """
        with self.lock:
            self.bar_id_counter += 1
            bar_id = self.bar_id_counter
            
            # Create the progress bar
            bar = UnifiedProgressBar(total, desc, module_name, unit)
            
            # Register in active bars
            self.active_bars[bar_id] = bar
            
            # Return a wrapped bar with automatic cleanup
            return self._create_tracked_bar(bar, bar_id)
    
    def _create_tracked_bar(self, bar: UnifiedProgressBar, bar_id: int) -> UnifiedProgressBar:
        """Create a wrapped progress bar that automatically unregisters itself on close.
        
        Args:
            bar: The original progress bar
            bar_id: The ID of the bar
            
        Returns:
            UnifiedProgressBar: A modified bar with automatic cleanup
        """
        # Store original close method
        original_close = bar.close
        
        # Define new close method
        def tracked_close():
            # Call original close
            if not bar._is_finished:
                original_close()
            # Unregister from active bars
            with self.lock:
                if bar_id in self.active_bars:
                    del self.active_bars[bar_id]
        
        # Replace close method
        bar.close = tracked_close
        
        return bar
    
    def complete_all_bars(self) -> None:
        """Complete all active progress bars."""
        with self.lock:
            # Create a copy of active bars to avoid modification during iteration
            bars_to_complete = list(self.active_bars.items())
            
        # Complete each bar outside the lock to prevent deadlocks
        for bar_id, bar in bars_to_complete:
            try:
                if not bar._is_finished:
                    bar.complete()
            except Exception:
                # Ignore errors during completion
                pass
    
    def create_download_bar(self, desc: str, total: int, module_name: str) -> UnifiedProgressBar:
        """Create a properly formatted download progress bar.
        
        Args:
            desc: File being downloaded
            total: Total size in bytes
            module_name: Module name for logging
            
        Returns:
            UnifiedProgressBar: Configured progress bar for downloads
        """
        # Convert total to MB for display if large enough
        if total > 1024 * 1024:
            total_mb = total / (1024 * 1024)
            size_str = f"{total_mb:.1f} MB"
        else:
            total_kb = total / 1024
            size_str = f"{total_kb:.1f} KB"
        
        # Create description with file and size
        display_desc = f"Downloading {desc} ({size_str})"
        
        # Return properly configured progress bar
        return self.create_bar(total, display_desc, module_name, "B")
    
    def get_or_create_rich_progress(self) -> Progress:
        """Get or create a Rich Progress instance for legacy support.
        
        Returns:
            Progress: Rich Progress instance
        """
        with self.lock:
            if not hasattr(self, '_rich_progress'):
                self._rich_progress = Progress(
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                    TimeElapsedColumn(),
                    TextColumn("•"),
                    TimeRemainingColumn(),
                    console=console,
                    transient=True
                )
            return self._rich_progress


# Get the global progress manager instance
def get_progress_manager() -> ProgressManager:
    """Get the global progress manager instance.
    
    Returns:
        ProgressManager: The global progress manager
    """
    global _progress_manager
    with _progress_lock:
        if (_progress_manager is None):
            _progress_manager = ProgressManager()
    return _progress_manager


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
    manager = get_progress_manager()
    return manager.create_bar(total, desc, module_name, unit)


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
    manager = get_progress_manager()
    return manager.create_download_bar(desc, total, module_name)


# Legacy support
def get_progress() -> Progress:
    """Get a shared progress instance for ETL operations (Legacy method).
    
    Returns:
        Progress instance for tracking ETL operations
    """
    manager = get_progress_manager()
    return manager.get_or_create_rich_progress()


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
                self.original_stream.flush()  # Ensure the newline is output
            self.progress_active = False
        
        # Write to our buffer and count characters
        chars_written = super().write(s)
        
        # Also write to original stream if provided
        if self.original_stream:
            self.original_stream.write(s)
            self.original_stream.flush()  # Ensure immediate output
            
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
            
            # Always ensure there's a newline before emitting a log record
            # if there might be a progress bar active
            manager = get_progress_manager()
            if manager and hasattr(manager, 'active_bars') and manager.active_bars:
                sys.stdout.write('\n')
                
            # Write the message with a newline and flush immediately
            sys.stdout.write(msg + '\n')
            sys.stdout.flush()
            
            # Add a small delay to ensure output is properly flushed
            time.sleep(0.01)
        except Exception:
            self.handleError(record)


# A simpler implementation of complete_all_progress_bars that avoids deadlocks
def complete_all_progress_bars() -> None:
    """Complete all active progress bars to ensure clean display."""
    try:
        manager = get_progress_manager()
        if manager:
            manager.complete_all_bars()
    except Exception:
        # Ignore any errors to ensure we don't crash the application
        pass


# Enhance the setup_logging function to handle progress bars better
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
    # Complete any active progress bars before setting up new logger
    complete_all_progress_bars()
    
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

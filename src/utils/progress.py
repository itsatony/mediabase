"""Progress tracking utilities with proper logging integration."""

from typing import Iterator, TypeVar, List, Optional, Callable, Any, Dict, Union, Iterable
import time
from functools import wraps
import warnings
import pandas as pd

from .logging import get_progress_bar, setup_logging, get_progress_manager

# Create module logger
logger = setup_logging(module_name=__name__)

# Generic type for iterables
T = TypeVar('T')

def track_progress(
    iterable: Iterable[T], 
    total: Optional[int] = None,
    desc: str = "Processing",
    module_name: str = "progress",
    unit: str = "items"
) -> Iterator[T]:
    """Iterate with proper progress tracking that integrates with logging.
    
    Args:
        iterable: Iterable to track progress for
        total: Total number of items (if None, attempts to determine from iterable)
        desc: Description of the operation
        module_name: Module name for logging prefix
        unit: Unit name for items
        
    Yields:
        Items from the iterable
    """
    # Try to determine total if not provided
    if total is None:
        try:
            total = len(iterable)  # type: ignore
        except (TypeError, AttributeError):
            total = 0  # Unknown
    
    # Create unified progress bar
    progress = get_progress_bar(total, desc, module_name, unit)
    items_processed = 0
    
    # Iterate and update progress
    try:
        for item in iterable:
            yield item
            items_processed += 1
            progress.update(1)
    finally:
        # Safely complete and close the progress bar
        try:
            if items_processed < total and total > 0:
                progress.n = total
                progress._update_progress()
            progress.close()
        except Exception:
            # Ignore errors during completion
            pass

# Helper function for tqdm with logging (kept for any existing code that might reference it)
def tqdm_with_logging(
    iterable: Iterable[T],
    desc: str = "Processing",
    module_name: str = "mediabase",
    total: Optional[int] = None,
    unit: str = "it"
) -> Iterator[T]:
    """Drop-in replacement for tqdm that follows our logging format rules.

    This function uses our unified logging progress bar format.

    Args:
        iterable: Iterable to track progress for
        desc: Description of the progress operation
        module_name: Module name for logging prefix
        total: Total number of items (if None, attempts to determine from iterable)
        unit: Unit name for items

    Yields:
        Items from the iterable
    """
    return track_progress(iterable, total, desc, module_name, unit)

# Pandas warning suppression context manager
class SuppressPandasWarnings:
    """Context manager to suppress pandas SettingWithCopyWarning."""
    
    def __init__(self, warning_type=None):
        """Initialize with optional specific warning type.
        
        Args:
            warning_type: Type of warning to suppress, defaults to SettingWithCopyWarning
        """
        self.warning_type = warning_type or pd.errors.SettingWithCopyWarning
        
    def __enter__(self):
        """Enter the context and start suppressing warnings."""
        warnings.filterwarnings('ignore', category=self.warning_type)
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the context and restore warnings."""
        warnings.filterwarnings('default', category=self.warning_type)

# Decorator to suppress pandas warnings for an entire function
def suppress_pandas_warnings(func):
    """Decorator to suppress pandas warnings for an entire function."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        with SuppressPandasWarnings():
            return func(*args, **kwargs)
    return wrapper

# Safe pandas operations
def safe_dataframe_assign(df: pd.DataFrame, col: str, value: Any) -> pd.DataFrame:
    """Safely assign a value to a DataFrame column without triggering warnings.
    
    Args:
        df: DataFrame to modify
        col: Column name
        value: Value to assign
        
    Returns:
        Modified DataFrame (copy)
    """
    # Create a copy to avoid the SettingWithCopyWarning
    df_copy = df.copy()
    df_copy[col] = value
    return df_copy

def batch_process(
    items: List[T],
    batch_size: int,
    process_func: Callable[[List[T]], Any],
    desc: str = "Processing batches",
    module_name: str = "batch"
) -> List[Any]:
    """Process items in batches with proper progress tracking.
    
    Args:
        items: List of items to process
        batch_size: Size of each batch
        process_func: Function to process each batch
        desc: Description of the operation
        module_name: Module name for logging prefix
        
    Returns:
        List of results from processing
    """
    total_items = len(items)
    total_batches = (total_items + batch_size - 1) // batch_size
    
    logger.info(f"Processing {total_items} items in {total_batches} batches")
    
    results = []
    batches_processed = 0
    
    # Create unified progress bar for batch tracking
    progress = get_progress_bar(total_batches, desc, module_name, "batches")
    
    try:
        for i in range(0, total_items, batch_size):
            batch = items[i:i+batch_size]
            
            # Process batch and capture result
            result = process_func(batch)
            if result is not None:
                results.append(result)
                
            # Update progress
            batches_processed += 1
            progress.update(1)
    finally:
        # Safely complete and close the progress bar
        try:
            if batches_processed < total_batches:
                progress.n = total_batches
                progress._update_progress()
            progress.close()
        except Exception:
            # Ignore errors during completion
            pass
    
    return results

def progress_decorator(
    desc: str = "Processing",
    module_name: Optional[str] = None,
    log_result: bool = True
) -> Callable:
    """Decorator to add progress logging to functions.
    
    Args:
        desc: Description of the operation
        module_name: Module name (defaults to function's module)
        log_result: Whether to log the result
        
    Returns:
        Decorated function with progress logging
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Get module name if not provided
            nonlocal module_name
            if module_name is None:
                module_name = func.__module__.split('.')[-1]
                
            # Log start of operation - no need to complete progress bars here
            func_logger = setup_logging(module_name=module_name)
            func_logger.info(f"Starting: {desc}")
            
            # Track execution time
            start_time = time.time()
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Calculate execution time
            elapsed = time.time() - start_time
            if elapsed > 60:
                elapsed_str = f"{elapsed/60:.1f} minutes"
            else:
                elapsed_str = f"{elapsed:.1f} seconds"
                
            # Log completion
            if log_result:
                func_logger.info(f"Completed: {desc} in {elapsed_str}")
            
            return result
        return wrapper
    return decorator

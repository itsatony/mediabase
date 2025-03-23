"""Base processor for ETL workflows.

This module provides a common base class for all ETL processor implementations,
standardizing configuration, logging, and database operations.
"""

# Standard library imports
import json
import os
import time
import logging
import warnings
import hashlib
import gzip
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Union, TypeVar, Callable
from datetime import datetime, timedelta

# Third party imports
import requests
from tqdm import tqdm
import psycopg2
from psycopg2.extensions import connection as pg_connection
from psycopg2.extras import execute_batch

# Local imports
from ..utils.logging import setup_logging, get_progress_bar
from ..db.database import get_db_manager, DatabaseManager

# Type variables for generic methods
T = TypeVar('T')

class ETLError(Exception):
    """Base exception class for ETL-related errors."""
    pass

class DownloadError(ETLError):
    """Exception raised when file download fails."""
    pass

class CacheError(ETLError):
    """Exception raised when cache operations fail."""
    pass

class ProcessingError(ETLError):
    """Exception raised during data processing."""
    pass

class DatabaseError(ETLError):
    """Exception raised during database operations."""
    pass

class BaseProcessor:
    """Base class for all ETL processors.
    
    Provides common functionality for:
    - Database connection management
    - File downloading with caching
    - Cache metadata management
    - Batch processing
    - Progress tracking
    """
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize base processor.
        
        Args:
            config: Configuration dictionary containing all settings
                   including nested db configuration
        """
        self.config = config
        
        # Set up module-specific logger
        module_name = self.__class__.__module__.split('.')[-1]
        self.logger = setup_logging(module_name=module_name, log_level=config.get('log_level', 'INFO'))
        
        # Extract nested db config if present
        db_config = config.get('db')
        if not db_config:
            self.logger.warning("No nested db config found, checking root level")
            # Try to extract db config from root level
            db_config = {
                'host': config.get('host', 'localhost'),
                'port': config.get('port', 5432),
                'dbname': config.get('dbname', 'mediabase'),
                'user': config.get('user', 'postgres'),
                'password': config.get('password', 'postgres')
            }
        
        self.logger.debug(f"Using database config: {db_config}")
        self.db_manager = get_db_manager(db_config)
        
        # Set up cache directory
        self.cache_dir = Path(config.get('cache_dir', '/tmp/mediabase/cache'))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Set up cache TTL (time-to-live) in seconds
        self.cache_ttl = config.get('cache_ttl', 86400)  # Default: 24 hours
        
        # Set up batch size for database operations
        self.batch_size = config.get('batch_size', 1000)
        
        # Set up force download flag
        self.force_download = config.get('force_download', False)
        
    def _get_cache_key(self, url: str, params: Optional[Dict[str, Any]] = None) -> str:
        """Generate a cache key from URL and optional parameters.
        
        Args:
            url: Source URL
            params: Optional dictionary of parameters
            
        Returns:
            Hash string to use as cache key
        """
        # Create a combined string of URL and parameters
        key_str = url
        if params:
            for k, v in sorted(params.items()):
                key_str += f"_{k}={v}"
        
        return hashlib.sha256(key_str.encode()).hexdigest()
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cache is still valid for a given cache key.
        
        Args:
            cache_key: The cache key to check
            
        Returns:
            True if cache is valid, False otherwise
        """
        meta_path = self.cache_dir / "meta.json"
        
        # Force download overrides cache validity
        if self.force_download:
            return False
            
        if not meta_path.exists():
            return False
            
        try:
            with open(meta_path, 'r') as f:
                meta = json.load(f)
                
            if cache_key not in meta:
                return False
                
            cache_time = datetime.fromisoformat(meta[cache_key]['timestamp'])
            return (datetime.now() - cache_time) < timedelta(seconds=self.cache_ttl)
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self.logger.warning(f"Cache metadata error: {e}")
            return False
    
    def _update_cache_meta(self, cache_key: str, file_path: Path, 
                         metadata: Optional[Dict[str, Any]] = None) -> None:
        """Update cache metadata.
        
        Args:
            cache_key: The cache key
            file_path: Path to the cached file
            metadata: Optional additional metadata
        """
        meta_path = self.cache_dir / "meta.json"
        meta = {}
        
        if meta_path.exists():
            try:
                with open(meta_path, 'r') as f:
                    meta = json.load(f)
            except json.JSONDecodeError:
                self.logger.warning("Invalid JSON in cache metadata, creating new")
        
        meta[cache_key] = {
            'timestamp': datetime.now().isoformat(),
            'file_path': str(file_path),
            'metadata': metadata or {}
        }
        
        with open(meta_path, 'w') as f:
            json.dump(meta, f)
    
    def download_file(self, url: str, file_path: Optional[Path] = None, 
                    params: Optional[Dict[str, Any]] = None) -> Path:
        """Download a file with caching.
        
        Args:
            url: URL to download
            file_path: Optional custom file path, if None a path is generated
            params: Optional parameters affecting cache key
            
        Returns:
            Path to the downloaded file
        
        Raises:
            DownloadError: If download fails
        """
        cache_key = self._get_cache_key(url, params)
        
        if file_path is None:
            # Extract filename from URL or use cache key
            url_path = url.split('/')[-1]
            filename = url_path if '.' in url_path else f"download_{cache_key}"
            file_path = self.cache_dir / filename
        
        # Check if cache is valid
        if file_path.exists() and self._is_cache_valid(cache_key):
            self.logger.info(f"Using cached file: {file_path}")
            return file_path
        
        self.logger.info(f"Downloading {url}")
        
        try:
            response = requests.get(url, stream=True, params=params)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            
            # Use tqdm with leave=False to ensure it updates in place
            with open(file_path, 'wb') as f, tqdm(
                desc=f"Downloading {file_path.name}",
                total=total_size,
                unit='B',
                unit_scale=True,
                position=0,
                leave=False
            ) as pbar:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        size = f.write(chunk)
                        pbar.update(size)
            
            # Update cache metadata
            self._update_cache_meta(cache_key, file_path, params)
            self.logger.info(f"Download completed: {file_path}")
            
            return file_path
            
        except Exception as e:
            # Remove partial download if it exists
            if file_path.exists():
                file_path.unlink()
                
            raise DownloadError(f"Failed to download {url}: {e}")
    
    def compress_file(self, input_path: Path, output_path: Optional[Path] = None) -> Path:
        """Compress a file using gzip.
        
        Args:
            input_path: Path to the input file
            output_path: Optional path for the compressed file
            
        Returns:
            Path to the compressed file
        """
        if output_path is None:
            output_path = Path(str(input_path) + '.gz')
            
        with open(input_path, 'rb') as f_in, gzip.open(output_path, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
            
        return output_path
    
    def decompress_file(self, input_path: Path, output_path: Optional[Path] = None) -> Path:
        """Decompress a gzipped file.
        
        Args:
            input_path: Path to the gzipped file
            output_path: Optional path for the decompressed file
            
        Returns:
            Path to the decompressed file
        """
        if output_path is None:
            output_path = input_path.with_suffix('')
            
        with gzip.open(input_path, 'rb') as f_in, open(output_path, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
            
        return output_path
    
    def ensure_connection(self) -> bool:
        """Ensure database connection is active.
        
        Returns:
            True if connection is successful, False otherwise
        """
        if not self.db_manager:
            self.logger.error("No database manager available")
            return False
            
        return self.db_manager.ensure_connection()
    
    def execute_batch(self, query: str, argslist: List[Tuple], 
                    page_size: Optional[int] = None) -> None:
        """Execute a batch query.
        
        Args:
            query: SQL query with placeholders
            argslist: List of argument tuples
            page_size: Number of items per batch, defaults to self.batch_size
            
        Raises:
            DatabaseError: If batch execution fails
        """
        if not self.ensure_connection() or not self.db_manager.cursor:
            raise DatabaseError("Cannot execute batch: no database connection")
            
        try:
            execute_batch(
                self.db_manager.cursor,
                query,
                argslist,
                page_size=page_size or self.batch_size
            )
            
            if self.db_manager.conn and not self.db_manager.conn.closed:
                self.db_manager.conn.commit()
                
        except Exception as e:
            if self.db_manager.conn and not self.db_manager.conn.closed:
                self.db_manager.conn.rollback()
            raise DatabaseError(f"Batch execution failed: {e}")
    
    def process_in_batches(self, items: List[T], processor: Callable[[List[T]], None], 
                         batch_size: Optional[int] = None, 
                         desc: str = "Processing batches") -> None:
        """Process items in batches with progress tracking.
        
        Args:
            items: List of items to process
            processor: Function that processes a batch of items
            batch_size: Size of each batch, defaults to self.batch_size
            desc: Description for the progress bar
        """
        batch_size_val = batch_size if batch_size is not None else self.batch_size
        total_batches = (len(items) + batch_size_val - 1) // batch_size_val  # Ceiling division
        
        # Use tqdm with position=0 and leave=False for in-place updates
        with tqdm(
            total=total_batches, 
            desc=desc, 
            unit="batch",
            position=0,
            leave=False
        ) as pbar:
            for i in range(0, len(items), batch_size_val):
                batch = items[i:i+batch_size_val]
                processor(batch)
                pbar.update(1)
    
    def get_db_transaction(self):
        """Get a context manager for database transaction.
        
        Returns:
            A context manager for transaction management
            
        Usage:
            with processor.get_db_transaction() as transaction:
                transaction.cursor.execute("...")
        """
        if not self.db_manager:
            raise DatabaseError("No database manager available")
            
        class TransactionContext:
            def __init__(self, db_manager):
                self.db_manager = db_manager
                self._cursor = None
                
            @property
            def cursor(self):
                """Safe access to cursor, ensuring it's not None.
                
                Returns: 
                    Database cursor
                    
                Raises: 
                    DatabaseError: If cursor is None
                """
                if not self._cursor:
                    if not self.db_manager.cursor:
                        raise DatabaseError("No database cursor available")
                    self._cursor = self.db_manager.cursor
                return self._cursor
                
            def __enter__(self):
                if not self.db_manager.ensure_connection():
                    raise DatabaseError("Cannot start transaction: no database connection")
                
                if self.db_manager.conn:
                    self.db_manager.conn.autocommit = False
                    
                # Ensure cursor is available
                if not self.db_manager.cursor:
                    raise DatabaseError("No database cursor available")
                self._cursor = self.db_manager.cursor
                    
                return self
                
            def __exit__(self, exc_type, exc_val, exc_tb):
                if not self.db_manager.conn or self.db_manager.conn.closed:
                    return
                    
                if exc_type is not None:
                    self.db_manager.conn.rollback()
                else:
                    self.db_manager.conn.commit()
                
                # Reset to autocommit mode
                if self.db_manager.conn and not self.db_manager.conn.closed:
                    self.db_manager.conn.autocommit = True
        
        return TransactionContext(self.db_manager)

    def check_schema_version(self, required_version: str) -> bool:
        """Check if database schema version meets requirements.
        
        Args:
            required_version: Minimum required schema version (e.g., 'v0.1.4')
            
        Returns:
            True if schema version is compatible, False otherwise
            
        Raises:
            DatabaseError: If schema version check fails
        """
        if not self.ensure_connection():
            raise DatabaseError("Cannot check schema version: no database connection")
        
        try:
            # Extract version number without 'v' prefix for numeric comparison
            required_num = int(required_version.lstrip('v').replace('.', ''))
            
            # Get current schema version from database
            current_version_str = self.db_manager.get_current_version()
            if not current_version_str:
                self.logger.warning(f"No current schema version found, need to migrate to {required_version}")
                return False
                
            current_num = int(current_version_str.lstrip('v').replace('.', ''))
            
            # Check if current version is sufficient
            if current_num < required_num:
                self.logger.warning(f"Current schema version {current_version_str} is below required {required_version}")
                return False
                
            return True
        except Exception as e:
            self.logger.error(f"Failed to check schema version: {e}")
            return False

    def ensure_schema_version(self, required_version: str) -> bool:
        """Ensure database schema meets version requirements or attempt migration.
        
        Args:
            required_version: Minimum required schema version (e.g., 'v0.1.4')
            
        Returns:
            True if schema is compatible (already or after migration), False if migration failed
            
        Raises:
            DatabaseError: If schema migration fails
        """
        # First check if schema is already compatible
        if self.check_schema_version(required_version):
            return True
            
        # Attempt to migrate
        self.logger.info(f"Attempting to migrate schema to {required_version}")
        if not self.db_manager.migrate_to_version(required_version):
            self.logger.error(f"Failed to migrate database schema to {required_version}")
            return False
            
        self.logger.info(f"Successfully migrated schema to {required_version}")
        return True

    def run(self) -> None:
        """Run the processor pipeline.
        
        This method should be implemented by subclasses to define the processing pipeline.
        """
        raise NotImplementedError("Subclasses must implement run()")

    def execute_batch_update(self, query: str, params_list: List[Tuple]) -> int:
        """Execute a batch update with proper transaction handling.
        
        Args:
            query: SQL query to execute
            params_list: List of parameter tuples for the query
            
        Returns:
            int: Number of rows affected
            
        Raises:
            DatabaseError: If the batch update fails
        """
        if not self.db_manager or not self.db_manager.cursor:
            raise DatabaseError("No database connection available")
            
        try:
            # Execute batch update
            self.db_manager.cursor.executemany(query, params_list)
            
            # Commit if the connection is not in autocommit mode
            if self.db_manager.conn and not self.db_manager.conn.autocommit:
                self.db_manager.conn.commit()
                
            # Return rowcount if available
            return self.db_manager.cursor.rowcount if hasattr(self.db_manager.cursor, 'rowcount') else 0
            
        except Exception as e:
            # Rollback if not in autocommit mode
            if self.db_manager.conn and not self.db_manager.conn.autocommit:
                self.db_manager.conn.rollback()
            raise DatabaseError(f"Batch update failed: {e}")

"""Utilities for downloading files with proper progress reporting."""

import os
import requests
from typing import Optional, Dict, Any, Union
from pathlib import Path
import logging
import gzip
import shutil
import time

from .logging import create_download_progress_bar, setup_logging

# Create module logger
logger = setup_logging(module_name=__name__)


def download_file(
    url: str,
    destination: Union[str, Path],
    module_name: str = "download",
    force_download: bool = False,
    headers: Optional[Dict[str, str]] = None,
) -> bool:
    """Download a file with proper progress reporting.

    Args:
        url: URL to download from
        destination: Where to save the file
        module_name: Module name for logging prefix
        force_download: Whether to download even if file exists
        headers: Optional HTTP headers

    Returns:
        bool: True if download successful, False otherwise
    """
    destination_path = Path(destination)

    # Create directory if it doesn't exist
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    # Check if file already exists
    if destination_path.exists() and not force_download:
        logger.info(f"File already exists: {destination_path}")
        return True

    # Initialize progress variable
    progress = None
    try:
        # Start the request
        logger.info(f"Downloading {url}")

        response = requests.get(url, headers=headers or {}, stream=True, timeout=120)
        response.raise_for_status()

        # Get file size if available
        total_size = int(response.headers.get("content-length", 0))
        desc = os.path.basename(destination_path)

        # Create progress bar with proper formatting
        progress = create_download_progress_bar(desc, total_size, module_name)

        # Download with progress
        with open(destination_path, "wb") as f:
            downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    progress.update(len(chunk))

        # Make sure progress is at 100% before closing
        if progress is not None:
            try:
                if downloaded < total_size and total_size > 0:
                    progress.n = total_size
                    progress._update_progress()
                progress.close()
            except Exception:
                # Ignore errors during progress bar operations
                pass

        logger.info(f"Download completed: {destination_path}")
        return True

    except Exception as e:
        # Safely close progress bar on error
        if progress is not None:
            try:
                progress.close()
            except Exception:
                pass

        logger.error(f"Download failed: {e}")
        # Remove partial downloads
        if destination_path.exists():
            os.unlink(destination_path)
        return False


def extract_gzip(
    source: Union[str, Path],
    destination: Optional[Union[str, Path]] = None,
    remove_source: bool = False,
) -> bool:
    """Extract a gzipped file with proper logging.

    Args:
        source: Source gzip file
        destination: Destination file (if None, removes .gz extension)
        remove_source: Whether to remove source file after extraction

    Returns:
        bool: True if extraction successful, False otherwise
    """
    source_path = Path(source)

    if destination is None:
        # Remove .gz extension for default destination
        destination_path = source_path.with_suffix("")
    else:
        destination_path = Path(destination)

    try:
        logger.info(f"Extracting {source_path} to {destination_path}")

        with gzip.open(source_path, "rb") as f_in:
            with open(destination_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

        if remove_source:
            os.unlink(source_path)

        logger.info(f"Extraction completed: {destination_path}")
        return True

    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        return False

"""Validation utilities for the MediaBase project."""

import logging
import re
from typing import Any, Dict, List, cast
import pandas as pd
import numpy as np
from numpy.typing import NDArray

logger = logging.getLogger(__name__)


def validate_gene_symbol(gene_symbol: str) -> bool:
    """Validate a gene symbol according to HGNC guidelines.

    Args:
        gene_symbol: Gene symbol to validate

    Returns:
        bool: True if valid, False otherwise

    Note:
        Gene symbols should:
        - Be uppercase alphanumeric
        - May contain hyphens
        - Should not start with a number
        - Should be between 1 and 255 characters
    """
    if not gene_symbol:
        return False

    # Basic pattern for gene symbols
    pattern = r"^[A-Z][A-Z0-9\-]{0,254}$"
    return bool(re.match(pattern, gene_symbol))


def validate_config(
    config: Dict[str, Any], required_keys: list[str], defaults: Dict[str, Any]
) -> Dict[str, Any]:
    """Validate configuration dictionary.

    Args:
        config: Configuration dictionary to validate
        required_keys: List of required keys
        defaults: Default values for missing keys

    Returns:
        Dict[str, Any]: Validated configuration with defaults

    Raises:
        ValueError: If required key is missing or has invalid value
    """
    validated = config.copy()

    for key in required_keys:
        if key not in validated:
            if key in defaults:
                validated[key] = defaults[key]
            else:
                raise ValueError(f"Missing required configuration key: {key}")

    return validated


def validate_db_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate database configuration.

    Args:
        config: Database configuration dictionary

    Returns:
        Dict[str, Any]: Validated database configuration

    Raises:
        ValueError: If required database configuration is missing or invalid
    """
    required = ["host", "port", "dbname", "user", "password"]
    defaults = {"host": "localhost", "port": 5432}

    config = validate_config(config, required, defaults)

    # Validate port
    if not isinstance(config["port"], int) or config["port"] < 1:
        raise ValueError("Database port must be a positive integer")

    return config


def validate_transcript_data(df: pd.DataFrame) -> bool:
    """Validate transcript data requirements.

    Args:
        df: DataFrame with transcript data

    Returns:
        bool: True if all validations pass
    """
    try:
        # Check required columns
        required_columns = [
            "transcript_id",
            "gene_symbol",
            "gene_id",
            "gene_type",
            "chromosome",
            "coordinates",
        ]
        missing_cols = [col for col in required_columns if col not in df.columns]
        if missing_cols:
            logger.error(f"Missing required columns: {missing_cols}")
            return False

        # Check for null values in key fields
        null_counts = df[required_columns].isnull().sum()
        if cast(bool, null_counts.to_numpy().any()):
            logger.error(f"Found null values:\n{null_counts[null_counts > 0]}")
            return False

        # Validate transcript_id format (ENST...)
        invalid_mask = ~df["transcript_id"].str.match(r"^ENST\d+")
        invalid_ids = df.loc[invalid_mask, "transcript_id"]
        if not invalid_ids.empty:
            logger.error(f"Found {len(invalid_ids)} invalid transcript IDs")
            return False

        # Validate gene_id format (ENSG...)
        invalid_mask = ~df["gene_id"].str.match(r"^ENSG\d+")
        invalid_genes = df.loc[invalid_mask, "gene_id"]
        if not invalid_genes.empty:
            logger.error(f"Found {len(invalid_genes)} invalid gene IDs")
            return False

        # Validate coordinates structure
        def valid_coordinates(coord: Dict[str, Any]) -> bool:
            return bool(  # explicit cast to bool
                isinstance(coord, dict)
                and "start" in coord
                and "end" in coord
                and "strand" in coord
                and isinstance(coord["start"], (int, np.integer))
                and isinstance(coord["end"], (int, np.integer))
                and coord["strand"] in (1, -1)
                and coord["start"] <= coord["end"]
            )

        invalid_coords = ~df["coordinates"].apply(valid_coordinates)
        if cast(bool, invalid_coords.any()):
            logger.error(f"Found {invalid_coords.sum()} invalid coordinate entries")
            return False

        logger.info("All transcript data validations passed")
        return True

    except Exception as e:
        logger.error(f"Validation error: {e}")
        return False

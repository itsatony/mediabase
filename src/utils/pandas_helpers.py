"""Pandas helper utilities for safe operations and proper logging."""

import warnings
import pandas as pd
from typing import Any, Optional, List, Dict, Union, Callable
from functools import wraps

from .logging import setup_logging

# Create module logger
logger = setup_logging(module_name=__name__)


class PandasOperationSafe:
    """Context manager for safe pandas operations without warnings."""

    def __init__(self, warning_type=None):
        """Initialize with optional specific warning type.

        Args:
            warning_type: Type of warning to suppress, defaults to SettingWithCopyWarning
        """
        self.warning_type = warning_type or pd.errors.SettingWithCopyWarning

    def __enter__(self):
        """Enter context and start suppressing warnings."""
        warnings.filterwarnings("ignore", category=self.warning_type)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context and restore warnings."""
        warnings.filterwarnings("default", category=self.warning_type)


def safe_operation(func):
    """Decorator for pandas operations to suppress warnings."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        with PandasOperationSafe():
            return func(*args, **kwargs)

    return wrapper


def safe_assign(df: pd.DataFrame, column: str, value: Any) -> pd.DataFrame:
    """Safely assign values to a DataFrame column.

    This prevents SettingWithCopyWarning by ensuring we're working
    with a copy of the DataFrame.

    Args:
        df: DataFrame to modify
        column: Column name to assign to
        value: Value to assign

    Returns:
        Modified DataFrame
    """
    with PandasOperationSafe():
        # Ensure we have a copy
        result = df.copy()
        result.loc[:, column] = value
        return result


def safe_batch_assign(df: pd.DataFrame, columns_dict: Dict[str, Any]) -> pd.DataFrame:
    """Safely assign multiple columns to a DataFrame.

    Args:
        df: DataFrame to modify
        columns_dict: Dictionary of column names and values

    Returns:
        Modified DataFrame
    """
    with PandasOperationSafe():
        # Ensure we have a copy
        result = df.copy()
        for column, value in columns_dict.items():
            result.loc[:, column] = value
        return result


def safe_fillna(df: pd.DataFrame, column: str, value: Any) -> pd.DataFrame:
    """Safely fill NA values in a DataFrame column.

    Args:
        df: DataFrame to modify
        column: Column to fill
        value: Value to use for filling NAs

    Returns:
        Modified DataFrame
    """
    with PandasOperationSafe():
        result = df.copy()
        if column in result.columns:
            result.loc[:, column] = result[column].fillna(value)
        else:
            result[column] = value
        return result


def get_column_safely(df: pd.DataFrame, column: str, default: Any = None) -> pd.Series:
    """Safely get a column from a DataFrame with a default if it doesn't exist.

    Args:
        df: Source DataFrame
        column: Column name to retrieve
        default: Default value if column doesn't exist

    Returns:
        Pandas Series with the column values
    """
    if column in df.columns:
        return df[column]

    # Return a Series of the default value with the same index
    return pd.Series([default] * len(df), index=df.index)


@safe_operation
def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Clean a DataFrame by standardizing column types and handling nulls.

    Args:
        df: DataFrame to clean

    Returns:
        Cleaned DataFrame
    """
    # Make a copy to avoid chained assignment warnings
    result = df.copy()

    # String columns: strip whitespace
    string_cols = result.select_dtypes(include=["object"]).columns
    for col in string_cols:
        if result[col].notna().any():  # Only process if there are non-NA values
            result.loc[:, col] = result[col].astype(str).str.strip()

    # Numeric columns: convert to float where possible
    for col in result.columns:
        if col not in string_cols:
            try:
                result.loc[:, col] = pd.to_numeric(result[col], errors="coerce")
            except:
                pass  # Keep as is if conversion fails

    return result

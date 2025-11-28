"""Tests for validation utilities."""

import pytest
from src.utils.validation import (
    validate_gene_symbol,
    validate_config,
    validate_db_config,
)


def test_validate_gene_symbol():
    """Test gene symbol validation."""
    # Valid symbols
    assert validate_gene_symbol("TP53")
    assert validate_gene_symbol("BRCA1")
    assert validate_gene_symbol("HLA-DRB1")

    # Invalid symbols
    assert not validate_gene_symbol("")
    assert not validate_gene_symbol("1TP53")
    assert not validate_gene_symbol("tp53")
    assert not validate_gene_symbol("TP53!")
    assert not validate_gene_symbol("TP 53")


def test_validate_config():
    """Test configuration validation."""
    required = ["key1", "key2"]
    defaults = {"key1": "default1", "key2": "default2"}

    # Test with complete config
    config = {"key1": "value1", "key2": "value2"}
    validated = validate_config(config, required, defaults)
    assert validated["key1"] == "value1"
    assert validated["key2"] == "value2"

    # Test with missing key (should use default)
    config = {"key1": "value1"}
    validated = validate_config(config, required, defaults)
    assert validated["key1"] == "value1"
    assert validated["key2"] == "default2"

    # Test with missing required key and no default
    with pytest.raises(ValueError):
        validate_config({}, ["required_key"], {})


def test_validate_db_config():
    """Test database configuration validation."""
    # Valid config
    config = {
        "host": "localhost",
        "port": 5432,
        "dbname": "test",
        "user": "user",
        "password": "pass",
    }
    validated = validate_db_config(config)
    assert validated == config

    # Invalid port
    with pytest.raises(ValueError):
        validate_db_config(
            {
                "host": "localhost",
                "port": -1,
                "dbname": "test",
                "user": "user",
                "password": "pass",
            }
        )

    # Missing required field
    with pytest.raises(ValueError):
        validate_db_config({"host": "localhost", "port": 5432})

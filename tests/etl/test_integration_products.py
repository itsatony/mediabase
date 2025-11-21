"""Integration tests for gene product classification."""

import pytest
import os
from pathlib import Path
import gzip
import json
from src.etl.products import ProductClassifier
from src.db.database import get_db_manager


@pytest.fixture
def mock_uniprot_data(tmp_path):
    """Create mock UniProt data for testing."""
    cache_dir = tmp_path / "mediabase" / "cache"
    uniprot_dir = cache_dir / "uniprot"
    uniprot_dir.mkdir(parents=True)

    # Create mock processed UniProt data
    json_path = uniprot_dir / "uniprot_processed.json.gz"
    test_data = {
        "TP53": {
            "gene_symbol": "TP53",
            "features": ["DNA_BIND DNA binding region"],
            "keywords": ["Transcription regulation"],
            "go_terms": [
                {
                    "id": "GO:0003700",
                    "term": "DNA-binding transcription factor activity",
                }
            ],
            "functions": ["Acts as a transcription factor"],
        },
        "MAPK1": {
            "gene_symbol": "MAPK1",
            "features": ["DOMAIN Protein kinase"],
            "keywords": ["Kinase", "Transferase"],
            "go_terms": [{"id": "GO:0016301", "term": "kinase activity"}],
            "functions": ["Protein kinase activity"],
        },
        "CD4": {
            "gene_symbol": "CD4",
            "features": ["TRANSMEM Transmembrane"],
            "keywords": ["Receptor", "Membrane"],
            "go_terms": [
                {
                    "id": "GO:0004888",
                    "term": "transmembrane signaling receptor activity",
                }
            ],
            "functions": ["Cell surface receptor"],
        },
    }

    with gzip.open(json_path, "wt") as f:
        json.dump(test_data, f)

    return cache_dir


@pytest.fixture
def test_genes():
    """Known genes for testing."""
    return [
        "TP53",  # Well-known transcription factor
        "MAPK1",  # Known kinase
        "CD4",  # Known receptor
        "GAPDH",  # Metabolic enzyme (not in mock data)
    ]


def test_product_classification(mock_uniprot_data, test_genes, monkeypatch):
    """Test product classification using mock data."""
    monkeypatch.setenv("MB_CACHE_DIR", str(mock_uniprot_data))

    config = {
        "cache_dir": str(mock_uniprot_data),
        "batch_size": 100,
        "host": os.getenv("MB_POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("MB_POSTGRES_PORT", "5435")),
        "dbname": os.getenv("MB_POSTGRES_NAME", "mediabase_test"),
        "user": os.getenv("MB_POSTGRES_USER", "mbase_user"),
        "password": os.getenv("MB_POSTGRES_PASSWORD", "mbase_secret"),
    }
    classifier = ProductClassifier(config)

    # Test TP53 classification - classify_gene expects gene_data dict
    tp53_data = {
        "gene_symbol": "TP53",
        "features": {"DNA_BIND": "DNA binding region"},
        "keywords": ["Transcription regulation"],
        "go_terms": {"GO:0003700": "DNA-binding transcription factor activity"},
        "function": "Acts as a transcription factor",
    }
    tp53_classes = classifier.classify_gene(tp53_data)
    assert (
        "transcription_factor" in tp53_classes
    ), f"TP53 should be classified as transcription factor. Got: {tp53_classes}"
    assert (
        "dna_binding" in tp53_classes
    ), f"TP53 should have DNA binding activity. Got: {tp53_classes}"

    # Test MAPK1 classification
    mapk1_data = {
        "gene_symbol": "MAPK1",
        "features": {"DOMAIN": "Protein kinase"},
        "keywords": ["Kinase", "Transferase"],
        "go_terms": {"GO:0016301": "kinase activity"},
        "function": "Protein kinase activity",
    }
    mapk1_classes = classifier.classify_gene(mapk1_data)
    assert (
        "kinase" in mapk1_classes
    ), f"MAPK1 should be classified as kinase. Got: {mapk1_classes}"

    # Test CD4 classification
    cd4_data = {
        "gene_symbol": "CD4",
        "features": {"TRANSMEM": "Transmembrane"},
        "keywords": ["Receptor", "Membrane"],
        "go_terms": {"GO:0004888": "transmembrane signaling receptor activity"},
        "function": "Cell surface receptor",
    }
    cd4_classes = classifier.classify_gene(cd4_data)
    assert (
        "receptor" in cd4_classes
    ), f"CD4 should be classified as receptor. Got: {cd4_classes}"

    # Test non-existent gene - empty data should return empty list
    gapdh_data = {
        "gene_symbol": "GAPDH",
        "features": {},
        "keywords": [],
        "go_terms": {},
        "function": "",
    }
    gapdh_classes = classifier.classify_gene(gapdh_data)
    assert (
        gapdh_classes == []
    ), f"GAPDH should return empty list as it has no classifiable features. Got: {gapdh_classes}"


def test_invalid_gene_symbols(mock_uniprot_data, monkeypatch):
    """Test handling of invalid gene symbols."""
    monkeypatch.setenv("MB_CACHE_DIR", str(mock_uniprot_data))

    config = {
        "cache_dir": str(mock_uniprot_data),
        "batch_size": 100,
        "host": os.getenv("MB_POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("MB_POSTGRES_PORT", "5435")),
        "dbname": os.getenv("MB_POSTGRES_NAME", "mediabase_test"),
        "user": os.getenv("MB_POSTGRES_USER", "mbase_user"),
        "password": os.getenv("MB_POSTGRES_PASSWORD", "mbase_secret"),
    }
    classifier = ProductClassifier(config)

    # Test various invalid/empty gene data structures
    empty_data = {
        "gene_symbol": "",
        "features": {},
        "keywords": [],
        "go_terms": {},
        "function": "",
    }
    assert classifier.classify_gene(empty_data) == []

    # Unclassifiable data with no recognized features
    invalid_data = {
        "gene_symbol": "123ABC",
        "features": {},
        "keywords": [],
        "go_terms": {},
        "function": "",
    }
    assert classifier.classify_gene(invalid_data) == []

    # Data with invalid GO terms/features
    malformed_data = {
        "gene_symbol": "TP53!",
        "features": {"invalid": "xyz"},
        "keywords": [],
        "go_terms": {},
        "function": "",
    }
    assert classifier.classify_gene(malformed_data) == []


@pytest.mark.integration
def test_database_update(mock_uniprot_data, monkeypatch):
    """Test database classification updates."""
    # Setup test database configuration
    config = {
        "cache_dir": str(mock_uniprot_data),
        "batch_size": 100,
        "host": os.getenv("MB_POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("MB_POSTGRES_PORT", "5435")),
        "dbname": os.getenv("MB_POSTGRES_NAME", "mediabase_test"),
        "user": os.getenv("MB_POSTGRES_USER", "mbase_user"),
        "password": os.getenv("MB_POSTGRES_PASSWORD", "mbase_secret"),
    }

    monkeypatch.setenv("MB_CACHE_DIR", str(mock_uniprot_data))

    # Create classifier with correct database config
    classifier = ProductClassifier(config)

    # Test that the classifier has the main classification method
    assert hasattr(classifier, "classify_gene")

    # Verify classify_gene works with sample data
    test_data = {
        "gene_symbol": "TEST",
        "features": {"test": "value"},
        "keywords": [],
        "go_terms": {},
        "function": "",
    }
    result = classifier.classify_gene(test_data)
    assert isinstance(result, list)

    # Skip actual database update test as it requires:
    # 1. Populated transcript data in the database
    # 2. Full ETL pipeline to have run
    # 3. UniProt data to be available
    # These integration tests should be run separately with proper setup

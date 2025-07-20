"""Integration tests for gene product classification."""

import pytest
import os
from pathlib import Path
import gzip
import json
from src.etl.products import ProductClassifier
from src.db.connection import get_db_connection  # Fixed import path

@pytest.fixture
def mock_uniprot_data(tmp_path):
    """Create mock UniProt data for testing."""
    cache_dir = tmp_path / "mediabase" / "cache"
    uniprot_dir = cache_dir / "uniprot"
    uniprot_dir.mkdir(parents=True)
    
    # Create mock processed UniProt data
    json_path = uniprot_dir / "uniprot_processed.json.gz"
    test_data = {
        'TP53': {
            'gene_symbol': 'TP53',
            'features': ['DNA_BIND DNA binding region'],
            'keywords': ['Transcription regulation'],
            'go_terms': [{'id': 'GO:0003700', 'term': 'DNA-binding transcription factor activity'}],
            'functions': ['Acts as a transcription factor']
        },
        'MAPK1': {
            'gene_symbol': 'MAPK1',
            'features': ['DOMAIN Protein kinase'],
            'keywords': ['Kinase', 'Transferase'],
            'go_terms': [{'id': 'GO:0016301', 'term': 'kinase activity'}],
            'functions': ['Protein kinase activity']
        },
        'CD4': {
            'gene_symbol': 'CD4',
            'features': ['TRANSMEM Transmembrane'],
            'keywords': ['Receptor', 'Membrane'],
            'go_terms': [{'id': 'GO:0004888', 'term': 'transmembrane signaling receptor activity'}],
            'functions': ['Cell surface receptor']
        }
    }
    
    with gzip.open(json_path, 'wt') as f:
        json.dump(test_data, f)
    
    return cache_dir

@pytest.fixture
def test_genes():
    """Known genes for testing."""
    return [
        "TP53",    # Well-known transcription factor
        "MAPK1",   # Known kinase
        "CD4",     # Known receptor
        "GAPDH",   # Metabolic enzyme (not in mock data)
    ]

def test_product_classification(mock_uniprot_data, test_genes, monkeypatch):
    """Test product classification using mock data."""
    monkeypatch.setenv('MB_CACHE_DIR', str(mock_uniprot_data))
    
    classifier = ProductClassifier()
    
    # Test TP53 classification
    tp53_classes = classifier.classify_product('TP53')
    assert 'transcription_factor' in tp53_classes, \
        f"TP53 should be classified as transcription factor. Got: {tp53_classes}"
    assert 'dna_binding' in tp53_classes, \
        f"TP53 should have DNA binding activity. Got: {tp53_classes}"
    
    # Test MAPK1 classification
    mapk1_classes = classifier.classify_product('MAPK1')
    assert 'kinase' in mapk1_classes, \
        f"MAPK1 should be classified as kinase. Got: {mapk1_classes}"
    
    # Test CD4 classification
    cd4_classes = classifier.classify_product('CD4')
    assert 'receptor' in cd4_classes, \
        f"CD4 should be classified as receptor. Got: {cd4_classes}"
    
    # Test non-existent gene
    gapdh_classes = classifier.classify_product('GAPDH')
    assert gapdh_classes == [], \
        f"GAPDH should return empty list as it's not in test data. Got: {gapdh_classes}"

def test_invalid_gene_symbols(mock_uniprot_data, monkeypatch):
    """Test handling of invalid gene symbols."""
    monkeypatch.setenv('MB_CACHE_DIR', str(mock_uniprot_data))
    
    classifier = ProductClassifier()
    
    # Test various invalid symbols
    assert classifier.classify_product('') == []
    assert classifier.classify_product('123ABC') == []
    assert classifier.classify_product('tp53') == []  # lowercase
    assert classifier.classify_product('TP53!') == []  # invalid character

@pytest.mark.integration
def test_database_update(mock_uniprot_data, monkeypatch):
    """Test database classification updates."""
    # Setup test database configuration
    db_config = {
        'host': os.getenv('MB_POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('MB_POSTGRES_PORT', '5432')),
        'dbname': os.getenv('MB_POSTGRES_NAME', 'mbase'),
        'user': os.getenv('MB_POSTGRES_USER', 'postgres'),
        'password': os.getenv('MB_POSTGRES_PASSWORD', 'postgres')
    }

    monkeypatch.setenv('MB_CACHE_DIR', str(mock_uniprot_data))
    
    # Create classifier with correct database config
    classifier = ProductClassifier(config={'db': db_config})
    classifier.update_database_classifications()
    
    # Verify database updates
    conn = get_db_connection(db_config)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT gene_symbol, product_type 
                FROM cancer_transcript_base 
                WHERE gene_symbol = 'TP53'
            """)
            result = cur.fetchone()
            assert result is not None, "TP53 not found in database"
            assert 'transcription_factor' in result[1], \
                f"TP53 should be classified as transcription factor. Got: {result[1]}"
    finally:
        conn.close()

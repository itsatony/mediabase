"""Tests for gene product classification."""

import pytest
import gzip
import json
from pathlib import Path
from src.etl.products import ProductClassifier

@pytest.fixture
def mock_uniprot_data(tmp_path):
    """Create mock UniProt data for testing."""
    uniprot_dir = tmp_path / 'uniprot'
    uniprot_dir.mkdir()
    json_path = uniprot_dir / 'uniprot_processed.json.gz'
    
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
        }
    }
    
    with gzip.open(json_path, 'wt') as f:
        json.dump(test_data, f)
    
    return tmp_path

def test_product_classification(mock_uniprot_data, monkeypatch):
    """Test product classification using mock data."""
    monkeypatch.setenv('MB_CACHE_DIR', str(mock_uniprot_data))
    
    classifier = ProductClassifier()
    
    # Test TP53 classification
    tp53_classes = classifier.classify_product('TP53')
    assert 'transcription_factor' in tp53_classes
    assert 'dna_binding' in tp53_classes
    
    # Test MAPK1 classification
    mapk1_classes = classifier.classify_product('MAPK1')
    assert 'kinase' in mapk1_classes

def test_invalid_gene_symbol(mock_uniprot_data, monkeypatch):
    """Test handling of invalid gene symbols."""
    monkeypatch.setenv('MB_CACHE_DIR', str(mock_uniprot_data))
    
    classifier = ProductClassifier()
    assert classifier.classify_product('invalid!') == []
    assert classifier.classify_product('123ABC') == []

@pytest.mark.integration
def test_database_update(mock_uniprot_data, monkeypatch):
    """Test database classification updates."""
    monkeypatch.setenv('MB_CACHE_DIR', str(mock_uniprot_data))
    
    classifier = ProductClassifier()
    classifier.update_database_classifications()
    # Add assertions to verify database state

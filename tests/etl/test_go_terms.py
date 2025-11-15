"""Tests for GO terms enrichment module."""

import pytest
import os
from pathlib import Path
import json
import networkx as nx
from src.etl.go_terms import GOTermProcessor
from src.db.database import get_db_manager

@pytest.fixture
def test_config():
    """Provide test configuration."""
    return {
        'go_obo_url': 'http://purl.obolibrary.org/obo/go.obo',
        'cache_dir': '/tmp/mediabase_test/cache',
        'cache_ttl': 3600,  # 1 hour cache for tests
        'batch_size': 100,
        'host': os.getenv('MB_POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('MB_POSTGRES_PORT', '5435')),
        'dbname': os.getenv('MB_POSTGRES_NAME', 'mediabase_test'),
        'user': os.getenv('MB_POSTGRES_USER', 'mbase_user'),
        'password': os.getenv('MB_POSTGRES_PASSWORD', 'mbase_secret')
    }

@pytest.fixture
def sample_obo_data(tmp_path) -> Path:
    """Create a sample OBO file for testing."""
    obo_content = """format-version: 1.2
ontology: go

[Term]
id: GO:0003674
name: molecular_function
namespace: molecular_function

[Term]
id: GO:0016301
name: kinase activity
namespace: molecular_function
is_a: GO:0003674

[Term]
id: GO:0004672
name: protein kinase activity
namespace: molecular_function
is_a: GO:0016301
"""
    obo_file = tmp_path / "test.obo"
    obo_file.write_text(obo_content)
    return obo_file

def test_load_go_graph(sample_obo_data, test_config):
    """Test GO graph loading functionality."""
    processor = GOTermProcessor(test_config)
    processor.load_go_graph(sample_obo_data)
    
    assert isinstance(processor.go_graph, nx.MultiDiGraph)
    assert len(processor.go_graph) == 3
    assert 'GO:0016301' in processor.go_graph
    
    # Check term data
    assert processor.go_graph.nodes['GO:0016301']['name'] == 'kinase activity'
    assert processor.go_graph.nodes['GO:0016301']['namespace'] == 'molecular_function'

def test_get_ancestors(sample_obo_data, test_config):
    """Test ancestor retrieval functionality."""
    processor = GOTermProcessor(test_config)
    processor.load_go_graph(sample_obo_data)
    
    ancestors = processor.get_ancestors('GO:0004672')
    assert ancestors == {'GO:0016301', 'GO:0003674'}
    
    # Test with aspect filter
    mf_ancestors = processor.get_ancestors('GO:0004672', 'molecular_function')
    assert mf_ancestors == {'GO:0016301', 'GO:0003674'}
    
    bp_ancestors = processor.get_ancestors('GO:0004672', 'biological_process')
    assert bp_ancestors == set()

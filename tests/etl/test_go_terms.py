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

@pytest.mark.integration
def test_enrich_transcripts(test_config):
    """Test transcript enrichment with GO terms.

    Requires a test database to be available with proper schema.
    """
    processor = GOTermProcessor(test_config)

    try:
        # Check if database has proper schema before running
        if not processor.ensure_connection():
            pytest.skip("Database connection not available")

        # Try to check schema version - skip if incompatible
        try:
            if not processor.ensure_schema_version('v0.1.3'):
                pytest.skip("Database schema version incompatible - requires v0.1.3+")
        except Exception:
            pytest.skip("Database schema check failed - database may not be initialized")

        processor.run()
        # Add assertions to verify database state
        # This would typically involve querying the database
        # and checking the enriched GO terms
    except Exception as e:
        pytest.fail(f"GO term enrichment failed: {e}")

@pytest.mark.skip(reason="Requires full ETL pipeline and GOA data - see integration tests")
def test_populate_initial_terms(test_config, sample_obo_data):
    """Test initial GO term population from GOA data.

    This test is skipped because populate_initial_terms requires:
    1. A fully populated transcript database with gene symbols
    2. The GOA (Gene Ontology Annotation) file to be downloaded
    3. Gene symbol matching between GOA and the database

    This is better tested as part of the full ETL pipeline integration test.
    """
    processor = GOTermProcessor(test_config)
    processor.load_go_graph(sample_obo_data)

    # Verify the method exists and is callable
    assert hasattr(processor, 'populate_initial_terms')
    assert callable(processor.populate_initial_terms)

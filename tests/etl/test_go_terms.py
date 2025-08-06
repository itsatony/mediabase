"""Tests for GO terms enrichment module."""

import pytest
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
        'host': 'localhost',
        'port': 5432,
        'dbname': 'mediabase_test',
        'user': 'postgres',
        'password': 'postgres'
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
    
    Requires a test database to be available.
    """
    processor = GOTermProcessor(test_config)
    
    try:
        processor.run()
        # Add assertions to verify database state
        # This would typically involve querying the database
        # and checking the enriched GO terms
    except Exception as e:
        pytest.fail(f"GO term enrichment failed: {e}")

def test_populate_initial_terms(test_config, sample_obo_data):
    """Test initial GO term population from UniProt features."""
    processor = GOTermProcessor(test_config)
    processor.load_go_graph(sample_obo_data)
    
    # Create test data in database
    conn = get_db_connection(test_config)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO cancer_transcript_base (
                    transcript_id, gene_symbol, features
                ) VALUES (
                    'TEST_TRANSCRIPT',
                    'TEST1',
                    '{"feature1": {"go_terms": [{"id": "GO:0016301", "evidence": "IEA"}]}}'::jsonb
                )
            """)
        conn.commit()
        
        # Run population
        processor.populate_initial_terms()
        
        # Verify results
        with conn.cursor() as cur:
            cur.execute("""
                SELECT go_terms 
                FROM cancer_transcript_base 
                WHERE gene_symbol = 'TEST1'
            """)
            result = cur.fetchone()
            assert result is not None
            go_terms = result[0]
            assert 'GO:0016301' in go_terms
            assert go_terms['GO:0016301']['evidence'] == 'IEA'
            
    finally:
        conn.close()

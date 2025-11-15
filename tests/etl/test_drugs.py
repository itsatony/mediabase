"""Tests for drug ETL pipeline."""

import pytest
import os
from pathlib import Path
import pandas as pd
import json
from src.etl.drugs import DrugProcessor

@pytest.fixture
def test_config():
    """Provide test configuration."""
    return {
        'drugcentral_url': 'https://drugcentral.org/download/current',
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
def sample_drug_data(tmp_path) -> Path:
    """Create sample drug data for testing."""
    data = {
        'drug_targets': [
            {
                'drug_id': 'DB00001',
                'drug_name': 'Test Drug',
                'gene_symbol': 'TEST1',
                'mechanism': 'inhibitor',
                'action_type': 'antagonist',
                'evidence_type': 'experimental',
                'evidence_score': 0.9,
                'reference_ids': ['PMID:12345']
            }
        ]
    }
    drug_file = tmp_path / "drug_data.json"
    with open(drug_file, 'w') as f:
        json.dump(data, f)
    return drug_file

def test_process_drug_targets(sample_drug_data, test_config):
    """Test drug target processing functionality."""
    processor = DrugProcessor(test_config)
    df = processor.process_drug_targets(sample_drug_data)
    
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert all(col in df.columns for col in [
        'drug_id', 'drug_name', 'gene_symbol',
        'mechanism', 'action_type', 'evidence_type'
    ])
    
    assert df['drug_id'].iloc[0] == 'DB00001'
    assert df['gene_symbol'].iloc[0] == 'TEST1'

@pytest.mark.integration
def test_integrate_drugs(test_config):
    """Test drug data integration.
    
    Requires a test database to be available.
    """
    processor = DrugProcessor(test_config)
    
    # Create test data
    drug_targets = pd.DataFrame({
        'drug_id': ['DB00001'],
        'drug_name': ['Test Drug'],
        'gene_symbol': ['TEST1'],
        'mechanism': ['inhibitor'],
        'action_type': ['antagonist'],
        'evidence_type': ['experimental'],
        'evidence_score': [0.9],
        'reference_ids': [['PMID:12345']]
    })
    
    try:
        processor.integrate_drugs(drug_targets)
        # Add assertions to verify database state
    except Exception as e:
        pytest.fail(f"Drug integration failed: {e}")

@pytest.mark.integration
def test_calculate_drug_scores(test_config):
    """Test drug score calculation."""
    processor = DrugProcessor(test_config)
    
    try:
        processor.calculate_drug_scores()
        # Add assertions to verify score calculation
    except Exception as e:
        pytest.fail(f"Drug score calculation failed: {e}")

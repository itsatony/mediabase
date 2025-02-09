"""Test suite for publications processing module."""

import pytest
from unittest.mock import Mock, patch
from src.etl.publications import PublicationsProcessor, Publication
from typing import Dict, Any

@pytest.fixture
def mock_config() -> Dict[str, Any]:
    """Provide test configuration."""
    return {
        'pubmed_api_key': 'test_key',
        'pubmed_email': 'test@example.com',
        'batch_size': 10,
        'host': 'localhost',
        'port': 5432,
        'dbname': 'test_db',
        'user': 'test_user',
        'password': 'test_pass'
    }

@pytest.fixture
def mock_db_manager(mock_config):
    """Mock database manager."""
    with patch('src.etl.publications.get_db_manager') as mock:
        db_manager = Mock()
        db_manager.cursor = Mock()
        db_manager.conn = Mock()
        mock.return_value = db_manager
        yield db_manager

@pytest.fixture
def processor(mock_config, mock_db_manager):
    """Create test processor instance."""
    return PublicationsProcessor(mock_config)

def test_init(processor, mock_config):
    """Test processor initialization."""
    assert processor.api_key == mock_config['pubmed_api_key']
    assert processor.email == mock_config['pubmed_email']
    assert processor.batch_size == mock_config['batch_size']

def test_fetch_pubmed_metadata(processor):
    """Test PubMed metadata fetching."""
    mock_response = {
        'result': {
            '12345': {
                'pubdate': '2020',
                'title': 'Test Article',
                'source': 'Test Journal'
            },
            'uids': ['12345']
        }
    }
    
    with patch('requests.get') as mock_get:
        mock_get.return_value.ok = True
        mock_get.return_value.json.return_value = mock_response
        
        result = processor._fetch_pubmed_metadata({'12345'})
        
        assert '12345' in result
        assert result['12345']['year'] == 2020
        assert result['12345']['title'] == 'Test Article'
        assert result['12345']['journal'] == 'Test Journal'

def test_update_batch(processor, mock_db_manager):
    """Test batch update functionality."""
    updates = [
        ('{"go_terms": [{"pmid": "12345"}]}', 'GENE1'),
        ('{"drugs": [{"pmid": "67890"}]}', 'GENE2')
    ]
    
    processor._update_batch(updates)
    
    mock_db_manager.cursor.execute.assert_called()
    mock_db_manager.conn.commit.assert_called_once()

@pytest.mark.integration
def test_enrich_references_integration(processor, mock_db_manager):
    """Test complete reference enrichment process."""
    # Mock database query results
    mock_db_manager.cursor.fetchall.side_effect = [
        [('12345',)],  # PMIDs query
        [  # Gene references query
            ('GENE1', {
                'go_terms': [{'pmid': '12345'}],
                'drugs': [{'pmid': '12345'}]
            })
        ]
    ]
    
    # Mock PubMed API response
    mock_metadata = {
        '12345': {
            'year': 2020,
            'title': 'Test Article',
            'journal': 'Test Journal'
        }
    }
    
    with patch.object(processor, '_fetch_pubmed_metadata', return_value=mock_metadata):
        processor.enrich_references()
        
        # Verify database updates
        mock_db_manager.cursor.execute.assert_called()
        mock_db_manager.conn.commit.assert_called()

def test_error_handling(processor, mock_db_manager):
    """Test error handling in enrichment process."""
    mock_db_manager.cursor.execute.side_effect = Exception("Test error")
    
    with pytest.raises(Exception):
        processor.enrich_references()
        
    mock_db_manager.conn.rollback.assert_called_once()

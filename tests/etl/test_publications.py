"""Test suite for publications processing module."""

import pytest
from unittest.mock import Mock, patch
from src.etl.publications import PublicationsProcessor, Publication
from typing import Dict, Any


@pytest.fixture
def mock_config() -> Dict[str, Any]:
    """Provide test configuration."""
    return {
        "api_key": "test_key",  # Changed from pubmed_api_key
        "email": "test@example.com",  # Changed from pubmed_email
        "batch_size": 10,
        "host": "localhost",
        "port": 5432,
        "dbname": "test_db",
        "user": "test_user",
        "password": "test_pass",
    }


@pytest.fixture
def mock_db_manager(mock_config):
    """Mock database manager."""
    with patch("src.etl.base_processor.get_db_manager") as mock:
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
    assert processor.api_key == mock_config["api_key"]
    assert processor.email == mock_config["email"]
    assert processor.batch_size == mock_config["batch_size"]


def test_fetch_pubmed_metadata(processor):
    """Test PubMed metadata fetching."""
    # Mock response for ESummary API
    mock_summary_response = {
        "result": {
            "12345": {
                "pubdate": "2020",
                "title": "Test Article",
                "fulljournalname": "Test Journal",  # Changed from 'source'
                "authors": [{"name": "Test Author"}],
                "elocationid": "doi:10.1234/test",
            },
            "uids": ["12345"],
        }
    }

    # Mock response for EFetch API (abstracts) - returns empty for simplicity
    mock_abstract_response = "<PubmedArticleSet></PubmedArticleSet>"

    with patch("requests.get") as mock_get:

        def mock_response(*args, **kwargs):
            response = Mock()
            response.ok = True
            response.raise_for_status = Mock()
            # Check if this is the summary or abstract request
            if "esummary" in args[0]:
                response.json.return_value = mock_summary_response
            else:  # efetch
                response.text = mock_abstract_response
            return response

        mock_get.side_effect = mock_response

        result = processor._fetch_pubmed_metadata(["12345"])

        assert "12345" in result
        assert result["12345"]["year"] == 2020
        assert result["12345"]["title"] == "Test Article"
        assert result["12345"]["journal"] == "Test Journal"

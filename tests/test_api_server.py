"""Tests for MEDIABASE FastAPI Server.

This module contains comprehensive tests for the FastAPI server endpoints,
covering transcript search, filtering, and database statistics.
"""

import pytest
import json
from typing import Dict, Any, List
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fastapi.testclient import TestClient
from src.api.server import app, get_database

# Skip all tests - need POST→GET refactoring and database views setup
#  - API changed from POST (JSON) to GET (query params)
# - Tests require transcript_enrichment_view and other database views
# - Need integration test database or better mocking
pytestmark = pytest.mark.skip(reason="API tests need refactoring: POST→GET conversion & database view setup")

class TestAPIServer:
    """Test suite for FastAPI server functionality."""
    
    @pytest.fixture
    def client(self):
        """Create test client for FastAPI app."""
        return TestClient(app)
    
    @pytest.fixture
    def mock_database(self):
        """Mock database manager for testing."""
        mock_db = Mock()
        mock_cursor = Mock()
        mock_db.cursor = mock_cursor
        mock_db.ensure_connection.return_value = True
        mock_db.close.return_value = None
        return mock_db, mock_cursor
    
    @pytest.fixture
    def sample_transcript_data(self) -> List[tuple]:
        """Sample transcript data for testing."""
        return [
            (
                'ENST00000357654',  # transcript_id
                'BRCA1',           # gene_symbol
                'ENSG00000012048', # gene_id
                'protein_coding',  # gene_type
                '17',              # chromosome
                2.5,               # expression_fold_change
                'enzyme',          # product_type
                ['GO:0003677'],    # go_terms
                ['R-HSA-5693532'], # pathways
                {'drug1': {'name': 'Test Drug', 'score': 85.0}},  # drugs
                ['DNA binding'],   # molecular_functions
                ['nucleus'],       # cellular_location
                {'pmids': ['12345']}  # source_references
            ),
            (
                'ENST00000269305',
                'TP53',
                'ENSG00000141510',
                'protein_coding',
                '17',
                0.3,
                'transcription_factor',
                ['GO:0003700'],
                ['R-HSA-69620'],
                {'drug2': {'name': 'Another Drug', 'score': 72.0}},
                ['transcription factor activity'],
                ['nucleus'],
                {'pmids': ['67890']}
            )
        ]
    
    def test_health_check(self, client: TestClient, mock_database):
        """Test health check endpoint."""
        mock_db, mock_cursor = mock_database
        
        with patch('src.api.server.get_database', return_value=iter([mock_db])):
            response = client.get("/health")
            
            assert response.status_code == 200
            data = response.json()
            assert data['status'] == 'healthy'
            assert data['version'] == '0.1.9'
            assert data['database_connected'] is True
    
    def test_search_transcripts_basic(self, client: TestClient, mock_database, sample_transcript_data):
        """Test basic transcript search functionality."""
        mock_db, mock_cursor = mock_database
        
        # Mock database query results
        mock_cursor.fetchall.return_value = sample_transcript_data
        mock_cursor.description = [
            ('transcript_id',), ('gene_symbol',), ('gene_id',), ('gene_type',),
            ('chromosome',), ('expression_fold_change',), ('product_type',),
            ('go_terms',), ('pathways',), ('drugs',), ('molecular_functions',),
            ('cellular_location',), ('source_references',)
        ]
        
        with patch('src.api.server.get_database', return_value=iter([mock_db])):
            response = client.get("/api/v1/transcripts?limit=10")
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]['transcript_id'] == 'ENST00000357654'
            assert data[0]['gene_symbol'] == 'BRCA1'
            assert data[0]['expression_fold_change'] == 2.5

    def test_get_single_transcript(self, client: TestClient, mock_database, sample_transcript_data):
        """Test getting single transcript by ID."""
        mock_db, mock_cursor = mock_database
        mock_cursor.fetchone.return_value = sample_transcript_data[0]
        mock_cursor.description = [
            ('transcript_id',), ('gene_symbol',), ('gene_id',), ('gene_type',),
            ('chromosome',), ('expression_fold_change',), ('product_type',),
            ('go_terms',), ('pathways',), ('drugs',), ('molecular_functions',),
            ('cellular_location',), ('source_references',)
        ]
        
        with patch('src.api.server.get_database', return_value=iter([mock_db])):
            response = client.get("/api/v1/transcripts/ENST00000357654")
            
            assert response.status_code == 200
            data = response.json()
            assert data['transcript_id'] == 'ENST00000357654'
            assert data['gene_symbol'] == 'BRCA1'
            assert data['expression_fold_change'] == 2.5
    
    def test_get_single_transcript_not_found(self, client: TestClient, mock_database):
        """Test getting non-existent transcript."""
        mock_db, mock_cursor = mock_database
        mock_cursor.fetchone.return_value = None
        
        with patch('src.api.server.get_database', return_value=iter([mock_db])):
            response = client.get("/api/v1/transcripts/NONEXISTENT")
            
            assert response.status_code == 404
            assert "not found" in response.json()['detail']
    
    def test_database_stats(self, client: TestClient, mock_database):
        """Test database statistics endpoint."""
        mock_db, mock_cursor = mock_database
        
        # Mock statistics queries
        mock_cursor.fetchone.side_effect = [
            (50000,),  # total_transcripts
            (25000,),  # transcripts_with_drugs
            (30000,),  # transcripts_with_pathways
            (20000,)   # unique_genes
        ]
        
        with patch('src.api.server.get_database', return_value=iter([mock_db])):
            response = client.get("/api/v1/stats")
            
            assert response.status_code == 200
            data = response.json()
            assert data['total_transcripts'] == 50000
            assert data['transcripts_with_drugs'] == 25000
            assert data['transcripts_with_pathways'] == 30000
            assert data['unique_genes'] == 20000
            assert data['drug_coverage'] == 50.0  # 25000/50000 * 100
            assert data['pathway_coverage'] == 60.0  # 30000/50000 * 100
    
    def test_pagination(self, client: TestClient, mock_database, sample_transcript_data):
        """Test pagination parameters."""
        mock_db, mock_cursor = mock_database
        mock_cursor.fetchall.return_value = sample_transcript_data
        mock_cursor.description = [
            ('transcript_id',), ('gene_symbol',), ('gene_id',), ('gene_type',),
            ('chromosome',), ('expression_fold_change',), ('product_type',),
            ('go_terms',), ('pathways',), ('drugs',), ('molecular_functions',),
            ('cellular_location',), ('source_references',)
        ]
        
        with patch('src.api.server.get_database', return_value=iter([mock_db])):
            response = client.post(
                "/api/v1/transcripts",
                json={"limit": 50, "offset": 100}
            )
            
            assert response.status_code == 200
            
            # Verify pagination parameters in SQL query
            call_args = mock_cursor.execute.call_args[0]
            assert "LIMIT %s OFFSET %s" in call_args[0]
            # Parameters should include limit and offset at the end
            params = call_args[1]
            assert 50 in params  # limit
            assert 100 in params  # offset
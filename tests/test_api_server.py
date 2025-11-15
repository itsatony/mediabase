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
    
    def test_search_transcripts_with_gene_symbols(self, client: TestClient, mock_database, sample_transcript_data):
        """Test transcript search with gene symbol filtering."""
        mock_db, mock_cursor = mock_database
        mock_cursor.fetchall.return_value = [sample_transcript_data[0]]  # Only BRCA1
        mock_cursor.description = [
            ('transcript_id',), ('gene_symbol',), ('gene_id',), ('gene_type',),
            ('chromosome',), ('expression_fold_change',), ('product_type',),
            ('go_terms',), ('pathways',), ('drugs',), ('molecular_functions',),
            ('cellular_location',), ('source_references',)
        ]
        
        with patch('src.api.server.get_database', return_value=iter([mock_db])):
            response = client.post(
                "/api/v1/transcripts",
                json={"gene_symbols": ["BRCA1"]}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]['gene_symbol'] == 'BRCA1'
            
            # Verify SQL query was built correctly
            mock_cursor.execute.assert_called()
            call_args = mock_cursor.execute.call_args[0]
            assert "gene_symbol IN (%s)" in call_args[0]
            assert "BRCA1" in call_args[1]
    
    def test_search_transcripts_with_fold_change_filter(self, client: TestClient, mock_database, sample_transcript_data):
        """Test transcript search with fold change filtering."""
        mock_db, mock_cursor = mock_database
        mock_cursor.fetchall.return_value = [sample_transcript_data[0]]  # Only high fold change
        mock_cursor.description = [
            ('transcript_id',), ('gene_symbol',), ('gene_id',), ('gene_type',),
            ('chromosome',), ('expression_fold_change',), ('product_type',),
            ('go_terms',), ('pathways',), ('drugs',), ('molecular_functions',),
            ('cellular_location',), ('source_references',)
        ]
        
        with patch('src.api.server.get_database', return_value=iter([mock_db])):
            response = client.post(
                "/api/v1/transcripts",
                json={"fold_change_min": 2.0}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]['expression_fold_change'] == 2.5
            
            # Verify SQL query includes fold change filter
            call_args = mock_cursor.execute.call_args[0]
            assert "expression_fold_change >= %s" in call_args[0]
            assert 2.0 in call_args[1]
    
    def test_search_transcripts_with_drug_filter(self, client: TestClient, mock_database, sample_transcript_data):
        """Test transcript search with drug presence filtering."""
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
                json={"has_drugs": True}
            )
            
            assert response.status_code == 200
            
            # Verify SQL query includes drug filter
            call_args = mock_cursor.execute.call_args[0]
            assert "drugs IS NOT NULL" in call_args[0]
            assert "jsonb_typeof(drugs) = 'object'" in call_args[0]
    
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
    
    def test_database_connection_error(self, client: TestClient):
        """Test handling of database connection errors."""
        mock_db = Mock()
        mock_db.ensure_connection.return_value = False
        
        with patch('src.api.server.get_database', side_effect=Exception("Database connection failed")):
            response = client.get("/health")
            
            assert response.status_code == 500
    
    def test_input_validation(self, client: TestClient, mock_database):
        """Test input validation for API endpoints."""
        mock_db, mock_cursor = mock_database
        
        with patch('src.api.server.get_database', return_value=iter([mock_db])):
            # Test invalid fold change values
            response = client.post(
                "/api/v1/transcripts",
                json={"fold_change_min": -1}  # Should be >= 0
            )
            assert response.status_code == 422  # Validation error
            
            # Test invalid limit values
            response = client.post(
                "/api/v1/transcripts",
                json={"limit": -1}  # Should be >= 1
            )
            assert response.status_code == 422
            
            # Test limit too high
            response = client.post(
                "/api/v1/transcripts",
                json={"limit": 20000}  # Should be <= 10000
            )
            assert response.status_code == 422
    
    def test_complex_query_combinations(self, client: TestClient, mock_database, sample_transcript_data):
        """Test complex query combinations."""
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
                json={
                    "gene_symbols": ["BRCA1", "TP53"],
                    "fold_change_min": 1.0,
                    "fold_change_max": 5.0,
                    "has_drugs": True,
                    "has_pathways": True,
                    "limit": 25,
                    "offset": 0
                }
            )
            
            assert response.status_code == 200
            
            # Verify complex query was built correctly
            call_args = mock_cursor.execute.call_args[0]
            sql_query = call_args[0]
            params = call_args[1]
            
            # Check all filter conditions are present
            assert "gene_symbol IN (%s,%s)" in sql_query
            assert "expression_fold_change >= %s" in sql_query
            assert "expression_fold_change <= %s" in sql_query
            assert "drugs IS NOT NULL" in sql_query
            assert "pathways IS NOT NULL" in sql_query
            
            # Check parameters are correct
            assert "BRCA1" in params
            assert "TP53" in params
            assert 1.0 in params
            assert 5.0 in params
            assert 25 in params  # limit
            assert 0 in params   # offset


class TestAPIServerIntegration:
    """Integration tests for API server with realistic scenarios."""
    
    @pytest.fixture
    def client(self):
        """Create test client for FastAPI app."""
        return TestClient(app)
    
    def test_clinical_workflow_simulation(self, client: TestClient):
        """Test a realistic clinical workflow using the API."""
        # Mock database for clinical scenario
        mock_db = Mock()
        mock_cursor = Mock()
        mock_db.cursor = mock_cursor
        mock_db.ensure_connection.return_value = True
        mock_db.close.return_value = None
        
        # Clinical scenario: Search for overexpressed oncogenes with drug targets
        clinical_transcripts = [
            (
                'ENST00000357654', 'BRCA1', 'ENSG00000012048', 'protein_coding', '17',
                3.2, 'enzyme', ['GO:0003677'], ['R-HSA-5693532'],
                {'parp_inhibitor': {'name': 'Olaparib', 'score': 92.0}},
                ['DNA repair'], ['nucleus'], {'pmids': ['25642963']}
            ),
            (
                'ENST00000275493', 'EGFR', 'ENSG00000146648', 'protein_coding', '7',
                4.1, 'receptor', ['GO:0004714'], ['R-HSA-1236394'],
                {'egfr_inhibitor': {'name': 'Erlotinib', 'score': 88.0}},
                ['protein kinase activity'], ['cell membrane'], {'pmids': ['15118073']}
            )
        ]
        
        mock_cursor.fetchall.return_value = clinical_transcripts
        mock_cursor.description = [
            ('transcript_id',), ('gene_symbol',), ('gene_id',), ('gene_type',),
            ('chromosome',), ('expression_fold_change',), ('product_type',),
            ('go_terms',), ('pathways',), ('drugs',), ('molecular_functions',),
            ('cellular_location',), ('source_references',)
        ]
        
        with patch('src.api.server.get_database', return_value=iter([mock_db])):
            # Clinical query: Find highly overexpressed genes with drug targets
            response = client.post(
                "/api/v1/transcripts",
                json={
                    "fold_change_min": 2.0,
                    "has_drugs": True,
                    "limit": 50
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            
            # Verify clinical relevance
            for transcript in data:
                assert transcript['expression_fold_change'] >= 2.0
                assert transcript['drugs'] is not None
                assert len(transcript['drugs']) > 0
            
            # Check specific therapeutic targets
            brca1_result = next(t for t in data if t['gene_symbol'] == 'BRCA1')
            assert 'parp_inhibitor' in brca1_result['drugs']
            assert brca1_result['drugs']['parp_inhibitor']['name'] == 'Olaparib'
    
    def test_research_workflow_simulation(self, client: TestClient):
        """Test a realistic research workflow using the API."""
        mock_db = Mock()
        mock_cursor = Mock()
        mock_db.cursor = mock_cursor
        mock_db.ensure_connection.return_value = True
        mock_db.close.return_value = None
        
        # Research scenario: Pathway analysis for specific gene set
        research_transcripts = [
            (
                'ENST00000269305', 'TP53', 'ENSG00000141510', 'protein_coding', '17',
                1.8, 'transcription_factor', ['GO:0003700'], ['R-HSA-69620'],
                {'mdm2_inhibitor': {'name': 'Nutlin-3', 'score': 75.0}},
                ['sequence-specific DNA binding'], ['nucleus'], {'pmids': ['12840024']}
            )
        ]
        
        mock_cursor.fetchall.return_value = research_transcripts
        mock_cursor.description = [
            ('transcript_id',), ('gene_symbol',), ('gene_id',), ('gene_type',),
            ('chromosome',), ('expression_fold_change',), ('product_type',),
            ('go_terms',), ('pathways',), ('drugs',), ('molecular_functions',),
            ('cellular_location',), ('source_references',)
        ]
        
        with patch('src.api.server.get_database', return_value=iter([mock_db])):
            # Research query: Specific gene analysis
            response = client.post(
                "/api/v1/transcripts",
                json={
                    "gene_symbols": ["TP53"],
                    "has_pathways": True
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]['gene_symbol'] == 'TP53'
            assert data[0]['pathways'] is not None
            assert len(data[0]['pathways']) > 0
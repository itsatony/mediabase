"""Tests for MEDIABASE FastAPI Server.

Integration tests for the FastAPI server endpoints using real database.
Tests cover transcript search, filtering, and database statistics with the
normalized schema and materialized views.
"""

import pytest
import os
from fastapi.testclient import TestClient

from src.api.server import app


@pytest.mark.integration
class TestAPIServer:
    """Integration test suite for FastAPI server functionality."""

    @pytest.fixture(autouse=True)
    def setup_db(self, test_db):
        """Ensure test database exists for all tests in this class."""
        # Set environment variables for API to use test database
        os.environ['MB_POSTGRES_HOST'] = 'localhost'
        os.environ['MB_POSTGRES_PORT'] = '5435'
        os.environ['MB_POSTGRES_NAME'] = test_db
        os.environ['MB_POSTGRES_USER'] = 'mbase_user'
        os.environ['MB_POSTGRES_PASSWORD'] = 'mbase_secret'

    @pytest.fixture
    def client(self):
        """Create test client for FastAPI app."""
        return TestClient(app)

    def test_health_check(self, client: TestClient):
        """Test health check endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'
        assert data['version'] == '0.2.1'
        assert data['database_connected'] is True

    def test_search_transcripts_basic(self, client: TestClient):
        """Test basic transcript search functionality."""
        response = client.get("/api/v1/transcripts?limit=10")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2  # We have 2 transcripts in seed data

        # Check first transcript (BRCA1)
        brca1 = next((t for t in data if t['gene_symbol'] == 'BRCA1'), None)
        assert brca1 is not None
        assert brca1['transcript_id'] == 'ENST00000357654'
        assert brca1['gene_id'] == 'ENSG00000012048'
        assert brca1['gene_type'] == 'protein_coding'
        assert brca1['chromosome'] == '17'
        assert brca1['expression_fold_change'] == 2.5

        # Check enrichment data
        assert 'enzyme' in brca1['product_type']  # From gene_annotations
        assert len(brca1['go_terms']) > 0  # From transcript_go_terms
        assert len(brca1['pathways']) > 0  # From gene_pathways
        assert len(brca1['drugs']) > 0  # From gene_drug_interactions

    def test_get_single_transcript(self, client: TestClient):
        """Test getting single transcript by ID."""
        response = client.get("/api/v1/transcripts/ENST00000357654")

        assert response.status_code == 200
        data = response.json()
        assert data['transcript_id'] == 'ENST00000357654'
        assert data['gene_symbol'] == 'BRCA1'
        assert data['gene_id'] == 'ENSG00000012048'
        assert data['expression_fold_change'] == 2.5

        # Verify enrichment data is present
        assert 'enzyme' in data['product_type']
        assert 'Olaparib' in data['drugs']

    def test_get_single_transcript_not_found(self, client: TestClient):
        """Test getting non-existent transcript."""
        response = client.get("/api/v1/transcripts/NONEXISTENT")

        assert response.status_code == 404
        assert "not found" in response.json()['detail']

    def test_database_stats(self, client: TestClient):
        """Test database statistics endpoint."""
        response = client.get("/api/v1/stats")

        assert response.status_code == 200
        data = response.json()

        # Verify we have the correct counts from seed data
        assert data['total_transcripts'] == 2
        assert data['unique_genes'] == 2
        assert data['genes_with_drugs'] == 2
        assert data['genes_with_pathways'] == 2
        assert data['genes_with_product_types'] == 2
        assert data['transcripts_with_go_terms'] == 2
        assert data['materialized_view_genes'] == 2

        # Verify coverage calculations
        assert data['drug_coverage'] == 100.0  # 2/2 * 100
        assert data['pathway_coverage'] == 100.0  # 2/2 * 100
        assert data['product_type_coverage'] == 100.0  # 2/2 * 100
        assert data['go_term_coverage'] == 100.0  # 2/2 * 100

        # Verify architecture info
        assert data['architecture'] == 'normalized_schema_v1.0'

    def test_pagination(self, client: TestClient):
        """Test pagination parameters."""
        # Test with limit=1, should return only 1 transcript
        response = client.get("/api/v1/transcripts?limit=1&offset=0")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

        # Test with offset=1, should return the second transcript
        response = client.get("/api/v1/transcripts?limit=1&offset=1")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

        # Verify we got different transcripts
        response1 = client.get("/api/v1/transcripts?limit=1&offset=0")
        response2 = client.get("/api/v1/transcripts?limit=1&offset=1")

        transcript1 = response1.json()[0]['transcript_id']
        transcript2 = response2.json()[0]['transcript_id']
        assert transcript1 != transcript2

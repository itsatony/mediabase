"""Integration tests for ETL pipeline with new schema."""

import pytest
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from src.db.database import DatabaseManager
from src.etl.transcript import TranscriptProcessor
from src.etl.publications import PublicationsProcessor
import os

@pytest.fixture(scope="session")
def test_db():
    """Create and manage test database."""
    db_params = {
        'host': os.getenv('MB_TEST_POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('MB_TEST_POSTGRES_PORT', '5432')),
        'user': os.getenv('MB_TEST_POSTGRES_USER', 'postgres'),
        'password': os.getenv('MB_TEST_POSTGRES_PASSWORD', 'postgres'),
        'dbname': 'test_mediabase'
    }
    
    # Create test database
    conn = psycopg2.connect(
        host=db_params['host'],
        port=db_params['port'],
        user=db_params['user'],
        password=db_params['password']
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    
    with conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {db_params['dbname']}")
        cur.execute(f"CREATE DATABASE {db_params['dbname']}")
    
    conn.close()
    
    # Initialize schema
    db_manager = DatabaseManager(db_params)
    db_manager.connect()
    db_manager.migrate_to_version('v0.1.4')
    
    yield db_params
    
    # Cleanup
    conn = psycopg2.connect(
        host=db_params['host'],
        port=db_params['port'],
        user=db_params['user'],
        password=db_params['password']
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    
    with conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {db_params['dbname']}")
    
    conn.close()

@pytest.mark.integration
def test_full_etl_pipeline(test_db):
    """Test complete ETL pipeline with new schema features."""
    # Initialize processors
    transcript_processor = TranscriptProcessor({
        **test_db,
        'cache_dir': '/tmp/test_mediabase'
    })
    
    publications_processor = PublicationsProcessor({
        **test_db,
        'pubmed_api_key': os.getenv('MB_TEST_PUBMED_KEY'),
        'pubmed_email': os.getenv('MB_TEST_PUBMED_EMAIL')
    })
    
    # Run pipeline
    transcript_processor.run()
    publications_processor.run()
    
    # Verify results
    with psycopg2.connect(**test_db) as conn:
        with conn.cursor() as cur:
            # Check alternative IDs
            cur.execute("""
                SELECT COUNT(*) 
                FROM cancer_transcript_base 
                WHERE alt_transcript_ids != '{}'::jsonb 
                OR alt_gene_ids != '{}'::jsonb
            """)
            assert cur.fetchone()[0] > 0, "No alternative IDs found"
            
            # Check source-specific references
            cur.execute("""
                SELECT COUNT(*) 
                FROM cancer_transcript_base 
                WHERE source_references != '{
                    "go_terms": [],
                    "uniprot": [],
                    "drugs": [],
                    "pathways": []
                }'::jsonb
            """)
            assert cur.fetchone()[0] > 0, "No source-specific references found"

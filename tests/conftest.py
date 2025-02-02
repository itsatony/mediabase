"""Test configuration and shared fixtures."""

import pytest
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

@pytest.fixture(scope="session")
def test_db():
    """Create and manage test database."""
    # Connection parameters for creating/dropping test database
    params = {
        'host': 'localhost',
        'port': 5432,
        'user': 'postgres',
        'password': 'postgres',
        'dbname': 'postgres'
    }
    
    test_db_name = 'mediabase_test'
    
    # Create test database
    conn = psycopg2.connect(**params)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    
    # Drop test database if it exists
    cur.execute(f"DROP DATABASE IF EXISTS {test_db_name}")
    cur.execute(f"CREATE DATABASE {test_db_name}")
    
    cur.close()
    conn.close()
    
    # Create schema in test database
    test_params = params.copy()
    test_params['dbname'] = test_db_name
    conn = psycopg2.connect(**test_params)
    
    with conn.cursor() as cur:
        # Create your schema here
        cur.execute("""
            CREATE TABLE cancer_transcript_base (
                transcript_id TEXT PRIMARY KEY,
                gene_symbol TEXT,
                gene_id TEXT,
                gene_type TEXT,
                chromosome TEXT,
                coordinates JSONB,
                product_type TEXT[],
                cellular_location TEXT[],
                go_terms JSONB,
                pathways TEXT[],
                drugs JSONB,
                drug_scores JSONB,
                publications JSONB,
                expression_fold_change FLOAT DEFAULT 1.0,
                expression_freq JSONB DEFAULT '{"high": [], "low": []}',
                cancer_types TEXT[] DEFAULT '{}'
            )
        """)
    
    conn.commit()
    conn.close()
    
    yield test_db_name
    
    # Cleanup
    conn = psycopg2.connect(**params)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {test_db_name}")
    cur.close()
    conn.close()

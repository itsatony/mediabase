"""Test configuration and shared fixtures."""

import os
import pytest
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv
from pathlib import Path

# Load test environment variables from .env.test
env_test_path = Path(__file__).parent.parent / '.env.test'
if env_test_path.exists():
    load_dotenv(env_test_path, override=True)
    print(f"✓ Loaded test configuration from {env_test_path}")
else:
    print(f"⚠ Warning: .env.test not found at {env_test_path}, using default values")

@pytest.fixture(scope="session")
def test_db():
    """Create and manage test database."""
    # Connection parameters from environment variables
    params = {
        'host': os.getenv('MB_POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('MB_POSTGRES_PORT', '5435')),
        'user': os.getenv('MB_POSTGRES_USER', 'mbase_user'),
        'password': os.getenv('MB_POSTGRES_PASSWORD', 'mbase_secret'),
        'dbname': 'postgres'  # Connect to postgres to create test database
    }

    test_db_name = os.getenv('MB_POSTGRES_NAME', 'mediabase_test')
    
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

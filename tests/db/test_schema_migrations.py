"""Test database schema migrations."""

import os
import pytest
import json
from typing import Dict, Any
from src.db.database import get_db_manager

@pytest.fixture
def db_config(test_db) -> Dict[str, Any]:
    """Provide test database configuration from test_db fixture."""
    # Use the test_db fixture from conftest.py which creates and initializes the database
    return {
        'host': os.getenv('MB_POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('MB_POSTGRES_PORT', '5435')),
        'dbname': os.getenv('MB_POSTGRES_NAME', 'mediabase_test'),
        'user': os.getenv('MB_POSTGRES_USER', 'mbase_user'),
        'password': os.getenv('MB_POSTGRES_PASSWORD', 'mbase_secret')
    }

@pytest.mark.skip(reason="Schema migration test needs rework for v0.1.9+ schema")
def test_v0_1_5_migration(db_config: Dict[str, Any]) -> None:
    """Test migration to v0.1.5 with focus on publication references."""
    db = get_db_manager(db_config)
    
    try:
        # Reset database to v0.1.4
        db.migrate_to_version('v0.1.4')
        assert db.get_current_version() == 'v0.1.4'
        
        # Insert test data with NULL source_references
        if db.cursor:
            db.cursor.execute("""
                INSERT INTO cancer_transcript_base (
                    transcript_id, gene_symbol, source_references
                ) VALUES (
                    'TEST1', 'TEST_GENE', NULL
                );
            """)
            
        # Migrate to v0.1.5
        assert db.migrate_to_version('v0.1.5')
        assert db.get_current_version() == 'v0.1.5'
        
        # Verify source_references structure
        if db.cursor:
            db.cursor.execute("""
                SELECT source_references 
                FROM cancer_transcript_base 
                WHERE transcript_id = 'TEST1';
            """)
            result = db.cursor.fetchone()
            assert result is not None
            
            refs = result[0]
            assert isinstance(refs, dict)
            assert all(key in refs for key in ['go_terms', 'uniprot', 'drugs', 'pathways'])
            assert all(isinstance(refs[key], list) for key in refs)
        
        # Verify publication_reference type exists
        if db.cursor:
            db.cursor.execute("""
                SELECT typname FROM pg_type WHERE typname = 'publication_reference';
            """)
            assert db.cursor.fetchone() is not None
            
    finally:
        db.close()

def test_source_references_default(db_config: Dict[str, Any]) -> None:
    """Test that new records get proper source_references defaults."""
    db = get_db_manager(db_config)
    
    try:
        # Ensure we're on v0.1.5
        db.migrate_to_version('v0.1.5')
        
        # Insert new record without specifying source_references
        if db.cursor:
            db.cursor.execute("""
                INSERT INTO cancer_transcript_base (
                    transcript_id, gene_symbol
                ) VALUES (
                    'TEST2', 'TEST_GENE2'
                ) RETURNING source_references;
            """)
            result = db.cursor.fetchone()
            assert result is not None
            
            refs = result[0]
            expected = {
                'go_terms': [],
                'uniprot': [],
                'drugs': [],
                'pathways': []
            }
            assert refs == expected
            
    finally:
        db.close()

def test_publication_reference_type_usage(db_config: Dict[str, Any]) -> None:
    """Test using the publication_reference composite type."""
    db = get_db_manager(db_config)
    
    try:
        # Ensure we're on v0.1.5
        db.migrate_to_version('v0.1.5')
        
        # Test creating a publication reference
        if db.cursor:
            db.cursor.execute("""
                SELECT ROW(
                    '12345678',
                    'experimental',
                    'pubmed',
                    'Test Title',
                    'Test Abstract',
                    2023,
                    'Test Journal',
                    ARRAY['Author 1', 'Author 2'],
                    42,
                    '10.1234/test',
                    'https://pubmed.ncbi.nlm.nih.gov/12345678/'
                )::publication_reference;
            """)
            result = db.cursor.fetchone()
            assert result is not None
            pub_ref = result[0]
            assert '12345678' in pub_ref  # Check PMID is in the string representation
            
    finally:
        db.close()

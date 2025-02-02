"""Tests for transcript ETL pipeline."""

import pytest
from pathlib import Path
import pandas as pd
from src.etl.transcript import TranscriptProcessor
import os

@pytest.fixture
def test_config():
    """Provide test configuration."""
    return {
        'gtf_url': os.getenv('MB_GENCODE_GTF_URL', 'https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_47/gencode.v47.basic.annotation.gtf.gz'),
        'cache_dir': '/tmp/mediabase_test/cache',
        'cache_ttl': 3600,  # 1 hour cache for tests
        'batch_size': 100,
        'host': os.getenv('MB_POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('MB_POSTGRES_PORT', 5432)),
        'dbname': os.getenv('MB_POSTGRES_NAME', 'mediabase_test'),
        'user': os.getenv('MB_POSTGRES_USER', 'postgres'),
        'password': os.getenv('MB_POSTGRES_PASSWORD', 'postgres')
    }

@pytest.fixture
def sample_gtf_data(tmp_path) -> Path:
    """Create a sample GTF file for testing."""
    gtf_content = """#!genome-build GRCh38.p14
#!genome-version GRCh38
#!genome-date 2013-12
#!genebuild-last-updated 2023-07
1\tHAVANA\ttranscript\t11869\t14409\t.\t+\t.\tgene_id "ENSG00000223972"; transcript_id "ENST00000456328"; gene_type "transcribed_unprocessed_pseudogene"; gene_name "DDX11L1"; transcript_type "processed_transcript";
1\tHAVANA\ttranscript\t12010\t13670\t.\t+\t.\tgene_id "ENSG00000223972"; transcript_id "ENST00000450305"; gene_type "transcribed_unprocessed_pseudogene"; gene_name "DDX11L1"; transcript_type "transcribed_unprocessed_pseudogene";
"""
    gtf_file = tmp_path / "test.gtf"
    gtf_file.write_text(gtf_content)
    return gtf_file

def test_process_gtf(sample_gtf_data, test_config):
    """Test GTF processing functionality."""
    processor = TranscriptProcessor(test_config)
    df = processor.process_gtf(sample_gtf_data)
    
    # Check basic DataFrame properties
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert all(col in df.columns for col in [
        'transcript_id', 'gene_symbol', 'gene_id',
        'gene_type', 'chromosome', 'coordinates'
    ])
    
    # Check specific values
    assert df['transcript_id'].iloc[0] == 'ENST00000456328'
    assert df['gene_symbol'].iloc[0] == 'DDX11L1'
    assert isinstance(df['coordinates'].iloc[0], dict)

def test_validate_transcript_data(test_config):
    """Test transcript data validation."""
    processor = TranscriptProcessor(test_config)
    
    # Create valid test data
    valid_data = pd.DataFrame({
        'transcript_id': ['ENST00000456328'],
        'gene_symbol': ['DDX11L1'],
        'gene_id': ['ENSG00000223972'],
        'gene_type': ['transcribed_unprocessed_pseudogene'],
        'chromosome': ['1'],
        'coordinates': [{'start': 11869, 'end': 14409, 'strand': 1}]
    })
    
    assert processor.validate_data(valid_data)
    
    # Test invalid data
    invalid_data = valid_data.copy()
    invalid_data.loc[0, 'transcript_id'] = 'invalid_id'
    assert not processor.validate_data(invalid_data)

@pytest.mark.integration
def test_full_pipeline(test_config):
    """Test the complete transcript processing pipeline.
    
    Requires a test database to be available.
    """
    processor = TranscriptProcessor(test_config)
    
    try:
        processor.run()
        # Add assertions to verify database state
        # This would typically involve querying the database
        # and checking the results
    except Exception as e:
        pytest.fail(f"Pipeline failed: {e}")

"""Tests for DESeq2 format support in patient copy functionality.

This module contains comprehensive tests for the enhanced patient database creation
script with DESeq2 format detection, gene symbol mapping, and log2 conversion.
"""

import os
import tempfile
import pytest
import pandas as pd
import numpy as np
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any, List

# Add src to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from scripts.create_patient_copy import (
    PatientDatabaseCreator,
    CSVValidationError,
    DESEQ2_FORMAT_INDICATORS
)

class TestDESeq2FormatDetection:
    """Test suite for DESeq2 format detection and parsing."""
    
    @pytest.fixture
    def deseq2_csv_data(self) -> pd.DataFrame:
        """Create DESeq2 format CSV data for testing."""
        return pd.DataFrame({
            'SYMBOL': ['BRCA1', 'TP53', 'EGFR', 'MYC', 'KRAS'],
            'baseMean': [240.0033086, 51.74567233, 1850.465789, 1329.690696, 1638.35287],
            'log2FoldChange': [0.607602249, -2.61508112, -1.047249687, 0.617431664, 0.276392428],
            'lfcSE': [0.335758132, 1.446814346, 0.416750258, 0.173353097, 0.220527243],
            'stat': [1.80964269, -1.807475249, -2.512895114, 3.561699655, 1.253325552],
            'pvalue': [0.070351215, 0.07068821, 0.011974493, 0.000368462, 0.210087253],
            'padj': [0.203820552, 0.204308384, 0.052658351, 0.002889004, 0.433380619]
        })
    
    @pytest.fixture 
    def deseq2_csv_variations(self) -> List[pd.DataFrame]:
        """Create various DESeq2 format variations for testing."""
        variations = []
        
        # Variation 1: lowercase column names
        variations.append(pd.DataFrame({
            'symbol': ['BRCA1', 'TP53'],
            'log2foldchange': [0.5, -1.2],
            'padj': [0.01, 0.05]
        }))
        
        # Variation 2: alternative column names
        variations.append(pd.DataFrame({
            'gene_symbol': ['EGFR', 'MYC'],
            'logfc': [2.1, -0.8],
            'fdr': [0.001, 0.02]
        }))
        
        # Variation 3: mixed case
        variations.append(pd.DataFrame({
            'Gene_Name': ['KRAS', 'PIK3CA'],
            'Log2FC': [1.5, -2.1],
            'adj_pvalue': [0.03, 0.001]
        }))
        
        return variations
    
    @pytest.fixture
    def standard_csv_data(self) -> pd.DataFrame:
        """Create standard format CSV data (should not trigger DESeq2 detection)."""
        return pd.DataFrame({
            'transcript_id': ['ENST00000123456', 'ENST00000789012'],
            'cancer_fold': [2.5, 0.3],
            'gene_symbol': ['GENE1', 'GENE2']
        })
    
    @pytest.fixture
    def db_config(self) -> Dict[str, Any]:
        """Database configuration for testing."""
        return {
            'host': 'localhost',
            'port': 5432,
            'dbname': 'mediabase_test',
            'user': 'postgres',
            'password': 'postgres'
        }
    
    def test_detect_deseq2_format_valid(self, tmp_path: Path, db_config: Dict[str, Any], deseq2_csv_data: pd.DataFrame):
        """Test DESeq2 format detection with valid DESeq2 data."""
        csv_file = tmp_path / "deseq2_test.csv"
        deseq2_csv_data.to_csv(csv_file, index=False)
        
        creator = PatientDatabaseCreator("TEST123", csv_file, db_config)
        creator.csv_data = deseq2_csv_data
        
        available_columns = set(deseq2_csv_data.columns)
        deseq2_indicators = creator._detect_deseq2_format(available_columns)
        
        assert len(deseq2_indicators) == 2
        assert deseq2_indicators['symbol'] == 'SYMBOL'
        assert deseq2_indicators['log2_fold_change'] == 'log2FoldChange'
    
    def test_detect_deseq2_format_variations(self, tmp_path: Path, db_config: Dict[str, Any], deseq2_csv_variations: List[pd.DataFrame]):
        """Test DESeq2 format detection with various column name formats."""
        for i, variation_data in enumerate(deseq2_csv_variations):
            csv_file = tmp_path / f"deseq2_variation_{i}.csv"
            variation_data.to_csv(csv_file, index=False)
            
            creator = PatientDatabaseCreator(f"TEST{i}", csv_file, db_config)
            creator.csv_data = variation_data
            
            available_columns = set(variation_data.columns)
            deseq2_indicators = creator._detect_deseq2_format(available_columns)
            
            # Should detect some format of gene symbol and log2 fold change
            assert len(deseq2_indicators) >= 1, f"Failed to detect DESeq2 format in variation {i}"
    
    def test_detect_deseq2_format_standard_format(self, tmp_path: Path, db_config: Dict[str, Any], standard_csv_data: pd.DataFrame):
        """Test that standard format is not detected as DESeq2."""
        csv_file = tmp_path / "standard_test.csv"
        standard_csv_data.to_csv(csv_file, index=False)
        
        creator = PatientDatabaseCreator("TEST123", csv_file, db_config)
        creator.csv_data = standard_csv_data
        
        available_columns = set(standard_csv_data.columns)
        deseq2_indicators = creator._detect_deseq2_format(available_columns)
        
        # Standard format should not be detected as DESeq2
        assert len(deseq2_indicators) < 2
    
    def test_map_deseq2_columns(self, tmp_path: Path, db_config: Dict[str, Any], deseq2_csv_data: pd.DataFrame):
        """Test DESeq2 column mapping functionality."""
        csv_file = tmp_path / "deseq2_test.csv"
        deseq2_csv_data.to_csv(csv_file, index=False)
        
        creator = PatientDatabaseCreator("TEST123", csv_file, db_config)
        creator.csv_data = deseq2_csv_data
        
        available_columns = set(deseq2_csv_data.columns)
        deseq2_indicators = {
            'symbol': 'SYMBOL',
            'log2_fold_change': 'log2FoldChange'
        }
        
        mapping = creator._map_deseq2_columns(available_columns, deseq2_indicators)
        
        assert mapping['transcript_id'] == 'SYMBOL'
        assert mapping['cancer_fold'] == 'log2FoldChange'
        assert creator.is_deseq2_format is True
        assert creator.log2_fold_column == 'log2FoldChange'
    
    def test_log2_to_linear_conversion(self, tmp_path: Path, db_config: Dict[str, Any]):
        """Test log2 fold change to linear fold change conversion."""
        # Create test data with known log2 values
        test_data = pd.DataFrame({
            'SYMBOL': ['GENE1', 'GENE2', 'GENE3', 'GENE4'],
            'log2FoldChange': [1.0, -1.0, 2.0, 0.0],  # Should convert to 2.0, 0.5, 4.0, 1.0
            'padj': [0.01, 0.02, 0.001, 0.5]
        })
        
        csv_file = tmp_path / "log2_test.csv"
        test_data.to_csv(csv_file, index=False)
        
        creator = PatientDatabaseCreator("TEST123", csv_file, db_config)
        
        # Mock gene symbol mapping to avoid database dependency
        mock_mapping = {
            'GENE1': 'ENST00000001',
            'GENE2': 'ENST00000002', 
            'GENE3': 'ENST00000003',
            'GENE4': 'ENST00000004'
        }
        creator.gene_symbol_mapping = mock_mapping
        
        # Process the DESeq2 data
        creator.csv_data = test_data
        creator.is_deseq2_format = True
        creator.log2_fold_column = 'log2FoldChange'
        
        # Call the processing function
        creator._process_deseq2_data(test_data, 'SYMBOL', 'log2FoldChange')
        
        # Check conversions
        expected_values = {
            'ENST00000001': 2.0,   # 2^1.0 = 2.0
            'ENST00000002': 0.5,   # 2^-1.0 = 0.5
            'ENST00000003': 4.0,   # 2^2.0 = 4.0
            'ENST00000004': 1.0    # 2^0.0 = 1.0
        }
        
        for transcript_id, expected_fold in expected_values.items():
            assert transcript_id in creator.transcript_updates
            assert abs(creator.transcript_updates[transcript_id] - expected_fold) < 0.001
        
        # Check statistics
        assert creator.stats['valid_transcripts'] == 4
        assert creator.stats['unmapped_symbols'] == 0
        assert creator.stats['mapping_success_rate'] == 100.0


class TestGeneSymbolMapping:
    """Test suite for gene symbol to transcript ID mapping."""
    
    @pytest.fixture
    def db_config(self) -> Dict[str, Any]:
        """Database configuration for testing."""
        return {
            'host': 'localhost',
            'port': 5432,
            'dbname': 'mediabase_test',
            'user': 'postgres',
            'password': 'postgres'
        }
    
    @pytest.fixture
    def mock_gene_mappings(self) -> List[tuple]:
        """Mock database gene symbol mappings."""
        return [
            ('BRCA1', 'ENST00000357654'),
            ('TP53', 'ENST00000269305'),
            ('EGFR', 'ENST00000275493'),
            ('MYC', 'ENST00000377970'),
            ('KRAS', 'ENST00000256078')
        ]
    
    def test_gene_symbol_mapping_success(self, tmp_path: Path, db_config: Dict[str, Any], mock_gene_mappings: List[tuple]):
        """Test successful gene symbol mapping."""
        csv_file = tmp_path / "test.csv"
        
        creator = PatientDatabaseCreator("TEST123", csv_file, db_config)
        
        # Mock database connection and query
        with patch('scripts.create_patient_copy.get_db_manager') as mock_db_manager:
            mock_manager = Mock()
            mock_cursor = Mock()
            mock_cursor.fetchall.return_value = mock_gene_mappings
            mock_manager.cursor = mock_cursor
            mock_manager.ensure_connection.return_value = True
            mock_db_manager.return_value = mock_manager
            
            # Call the mapping function
            creator._load_gene_symbol_mapping()
            
            # Verify mappings were loaded correctly
            assert len(creator.gene_symbol_mapping) == 5
            assert creator.gene_symbol_mapping['BRCA1'] == 'ENST00000357654'
            assert creator.gene_symbol_mapping['TP53'] == 'ENST00000269305'
            assert creator.gene_symbol_mapping['EGFR'] == 'ENST00000275493'
    
    def test_gene_symbol_mapping_database_error(self, tmp_path: Path, db_config: Dict[str, Any]):
        """Test gene symbol mapping with database connection error."""
        csv_file = tmp_path / "test.csv"
        creator = PatientDatabaseCreator("TEST123", csv_file, db_config)
        
        # Mock database connection failure
        with patch('scripts.create_patient_copy.get_db_manager') as mock_db_manager:
            mock_manager = Mock()
            mock_manager.ensure_connection.return_value = False
            mock_db_manager.return_value = mock_manager
            
            with pytest.raises(CSVValidationError, match="Failed to connect to source database"):
                creator._load_gene_symbol_mapping()
    
    def test_process_deseq2_data_with_unmapped_symbols(self, tmp_path: Path, db_config: Dict[str, Any]):
        """Test DESeq2 processing with some unmapped gene symbols."""
        test_data = pd.DataFrame({
            'SYMBOL': ['BRCA1', 'UNKNOWN1', 'TP53', 'UNKNOWN2'],
            'log2FoldChange': [1.0, 2.0, -1.0, 0.5],
            'padj': [0.01, 0.02, 0.001, 0.5]
        })
        
        csv_file = tmp_path / "test.csv"
        creator = PatientDatabaseCreator("TEST123", csv_file, db_config)
        
        # Mock partial gene symbol mapping (only some genes mapped)
        creator.gene_symbol_mapping = {
            'BRCA1': 'ENST00000357654',
            'TP53': 'ENST00000269305'
            # UNKNOWN1 and UNKNOWN2 not mapped
        }
        
        creator._process_deseq2_data(test_data, 'SYMBOL', 'log2FoldChange')
        
        # Should only have mappings for known genes
        assert len(creator.transcript_updates) == 2
        assert 'ENST00000357654' in creator.transcript_updates
        assert 'ENST00000269305' in creator.transcript_updates
        
        # Check statistics
        assert creator.stats['valid_transcripts'] == 2
        assert creator.stats['unmapped_symbols'] == 2
        assert creator.stats['mapping_success_rate'] == 50.0


class TestDESeq2Integration:
    """Integration tests for complete DESeq2 workflow."""
    
    @pytest.fixture
    def db_config(self) -> Dict[str, Any]:
        """Database configuration for testing."""
        return {
            'host': 'localhost',
            'port': 5432,
            'dbname': 'mediabase_test',
            'user': 'postgres',
            'password': 'postgres'
        }
    
    def test_end_to_end_deseq2_workflow(self, tmp_path: Path, db_config: Dict[str, Any]):
        """Test complete DESeq2 workflow from CSV validation to transcript updates."""
        # Create realistic DESeq2 data
        deseq2_data = pd.DataFrame({
            'SYMBOL': ['BRCA1', 'TP53', 'EGFR', 'MYC'],
            'baseMean': [240.0, 51.7, 1850.5, 1329.7],
            'log2FoldChange': [0.61, -2.62, -1.05, 0.62],
            'lfcSE': [0.34, 1.45, 0.42, 0.17],
            'stat': [1.81, -1.81, -2.51, 3.56],
            'pvalue': [0.07, 0.07, 0.01, 0.0004],
            'padj': [0.20, 0.20, 0.05, 0.003]
        })
        
        csv_file = tmp_path / "deseq2_complete.csv"
        deseq2_data.to_csv(csv_file, index=False)
        
        creator = PatientDatabaseCreator("TEST123", csv_file, db_config)
        
        # Mock gene symbol mapping
        mock_mappings = [
            ('BRCA1', 'ENST00000357654'),
            ('TP53', 'ENST00000269305'),
            ('EGFR', 'ENST00000275493'),
            ('MYC', 'ENST00000377970')
        ]
        
        with patch('scripts.create_patient_copy.get_db_manager') as mock_db_manager:
            mock_manager = Mock()
            mock_cursor = Mock()
            mock_cursor.fetchall.return_value = mock_mappings
            mock_manager.cursor = mock_cursor
            mock_manager.ensure_connection.return_value = True
            mock_db_manager.return_value = mock_manager
            
            # Run complete validation workflow
            creator.validate_csv_file()
            
            # Verify DESeq2 detection worked
            assert creator.is_deseq2_format is True
            assert creator.log2_fold_column == 'log2FoldChange'
            
            # Verify transcript updates were created with correct conversions
            assert len(creator.transcript_updates) == 4
            
            # Verify log2 conversions (approximately)
            assert abs(creator.transcript_updates['ENST00000357654'] - (2 ** 0.61)) < 0.01  # BRCA1
            assert abs(creator.transcript_updates['ENST00000269305'] - (2 ** -2.62)) < 0.01  # TP53
            
            # Verify statistics
            assert creator.stats['valid_transcripts'] == 4
            assert creator.stats['mapping_success_rate'] == 100.0
    
    def test_deseq2_vs_standard_format_detection(self, tmp_path: Path, db_config: Dict[str, Any]):
        """Test that the system correctly distinguishes DESeq2 from standard format."""
        
        # Test 1: DESeq2 format should be detected
        deseq2_data = pd.DataFrame({
            'SYMBOL': ['GENE1', 'GENE2'],
            'log2FoldChange': [1.0, -1.0],
            'padj': [0.01, 0.02]
        })
        
        csv_file1 = tmp_path / "deseq2.csv"
        deseq2_data.to_csv(csv_file1, index=False)
        
        creator1 = PatientDatabaseCreator("TEST1", csv_file1, db_config)
        creator1.csv_data = deseq2_data
        
        available_columns1 = set(deseq2_data.columns)
        mapping1 = creator1._find_column_mapping(available_columns1)
        
        assert creator1.is_deseq2_format is True
        assert len(mapping1) == 2
        
        # Test 2: Standard format should not trigger DESeq2 detection
        standard_data = pd.DataFrame({
            'transcript_id': ['ENST00000001', 'ENST00000002'],
            'cancer_fold': [2.5, 0.3],
            'gene_symbol': ['GENE1', 'GENE2']
        })
        
        csv_file2 = tmp_path / "standard.csv"
        standard_data.to_csv(csv_file2, index=False)
        
        creator2 = PatientDatabaseCreator("TEST2", csv_file2, db_config)
        creator2.csv_data = standard_data
        
        available_columns2 = set(standard_data.columns)
        mapping2 = creator2._find_column_mapping(available_columns2)
        
        assert creator2.is_deseq2_format is False
        assert len(mapping2) == 2
        assert mapping2['transcript_id'] == 'transcript_id'
        assert mapping2['cancer_fold'] == 'cancer_fold'
    
    def test_edge_cases_and_error_handling(self, tmp_path: Path, db_config: Dict[str, Any]):
        """Test edge cases and error handling in DESeq2 processing."""
        
        # Test with invalid log2 values
        invalid_data = pd.DataFrame({
            'SYMBOL': ['GENE1', 'GENE2'],
            'log2FoldChange': [float('inf'), float('nan')],
            'padj': [0.01, 0.02]
        })
        
        csv_file = tmp_path / "invalid.csv"
        invalid_data.to_csv(csv_file, index=False)
        
        creator = PatientDatabaseCreator("TEST123", csv_file, db_config)
        creator.gene_symbol_mapping = {'GENE1': 'ENST001', 'GENE2': 'ENST002'}
        
        # Should handle infinite and NaN values gracefully
        with patch('pandas.DataFrame.dropna') as mock_dropna:
            mock_dropna.return_value = pd.DataFrame({
                'SYMBOL': ['GENE1'],  # GENE2 dropped due to NaN
                'log2FoldChange': [1.0]
            })
            
            creator._process_deseq2_data(mock_dropna.return_value, 'SYMBOL', 'log2FoldChange')
            
            # Should only process valid data
            assert len(creator.transcript_updates) == 1
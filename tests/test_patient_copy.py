"""Tests for patient copy functionality.

This module contains comprehensive tests for the patient database creation script,
covering CSV validation, database copying, and fold-change updates.
"""

import os
import tempfile
import pytest
import pandas as pd
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

import psycopg2
from psycopg2.extensions import connection as pg_connection

# Add src to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from scripts.create_patient_copy import (
    PatientDatabaseCreator,
    CSVValidationError,
    DatabaseCopyError,
    FoldChangeUpdateError,
    PatientCopyError,
    REQUIRED_CSV_COLUMNS,
    ALTERNATIVE_COLUMN_NAMES
)

class TestPatientDatabaseCreator:
    """Test suite for PatientDatabaseCreator class."""

    @pytest.fixture(autouse=True)
    def setup_db(self, test_db):
        """Ensure test database exists for all tests in this class."""
        pass

    @pytest.fixture
    def valid_csv_data(self) -> pd.DataFrame:
        """Create valid CSV data for testing."""
        return pd.DataFrame({
            'transcript_id': ['ENST00000123456', 'ENST00000789012', 'ENST00000345678'],
            'cancer_fold': [2.5, 0.3, 1.8],
            'gene_symbol': ['GENE1', 'GENE2', 'GENE3']
        })
    
    @pytest.fixture
    def invalid_csv_data(self) -> pd.DataFrame:
        """Create invalid CSV data for testing."""
        return pd.DataFrame({
            'wrong_id': ['ENST00000123456', 'ENST00000789012'],
            'wrong_fold': ['not_a_number', 'also_not_a_number']
        })
    
    @pytest.fixture
    def alternative_csv_data(self) -> pd.DataFrame:
        """Create CSV data with alternative column names."""
        return pd.DataFrame({
            'transcript': ['ENST00000123456', 'ENST00000789012'],
            'fold_change': [2.5, 0.3]
        })
    
    @pytest.fixture
    def csv_file(self, tmp_path: Path, valid_csv_data: pd.DataFrame) -> Path:
        """Create temporary CSV file for testing."""
        csv_path = tmp_path / "test_data.csv"
        valid_csv_data.to_csv(csv_path, index=False)
        return csv_path
    
    @pytest.fixture
    def db_config(self) -> Dict[str, Any]:
        """Database configuration for testing."""
        return {
            'host': os.getenv('MB_POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('MB_POSTGRES_PORT', '5435')),
            'dbname': os.getenv('MB_POSTGRES_NAME', 'mediabase_test'),
            'user': os.getenv('MB_POSTGRES_USER', 'mbase_user'),
            'password': os.getenv('MB_POSTGRES_PASSWORD', 'mbase_secret')
        }
    
    @pytest.fixture
    def creator(self, csv_file: Path, db_config: Dict[str, Any]) -> PatientDatabaseCreator:
        """Create PatientDatabaseCreator instance for testing."""
        return PatientDatabaseCreator("TEST123", csv_file, db_config)
    
    def test_init(self, creator: PatientDatabaseCreator):
        """Test PatientDatabaseCreator initialization."""
        assert creator.patient_id == "TEST123"
        assert creator.target_db_name == "mediabase_patient_TEST123"
        assert creator.csv_data is None
        assert creator.column_mapping == {}
        assert creator.transcript_updates == {}
        assert creator.stats["csv_rows_read"] == 0
    
    def test_validate_csv_file_success(self, creator: PatientDatabaseCreator):
        """Test successful CSV validation."""
        creator.validate_csv_file()
        
        assert creator.csv_data is not None
        assert len(creator.csv_data) == 3
        assert creator.stats["csv_rows_read"] == 3
        assert creator.stats["valid_transcripts"] == 3
        assert creator.stats["invalid_transcripts"] == 0
        assert "transcript_id" in creator.column_mapping
        assert "cancer_fold" in creator.column_mapping
    
    def test_validate_csv_file_empty(self, tmp_path: Path, db_config: Dict[str, Any]):
        """Test CSV validation with empty file."""
        empty_csv = tmp_path / "empty.csv"
        # Create an actually empty CSV file
        with open(empty_csv, 'w') as f:
            f.write("")
        
        creator = PatientDatabaseCreator("TEST123", empty_csv, db_config)
        
        with pytest.raises(CSVValidationError, match="Failed to validate CSV file"):
            creator.validate_csv_file()
    
    def test_validate_csv_file_missing_columns(self, tmp_path: Path, db_config: Dict[str, Any], invalid_csv_data: pd.DataFrame):
        """Test CSV validation with missing required columns."""
        invalid_csv = tmp_path / "invalid.csv"
        invalid_csv_data.to_csv(invalid_csv, index=False)
        
        creator = PatientDatabaseCreator("TEST123", invalid_csv, db_config)
        
        # Mock interactive input to simulate user selecting columns
        with patch('rich.prompt.Prompt.ask', side_effect=['wrong_id', 'wrong_fold']):
            with patch('pandas.to_numeric', side_effect=ValueError("Invalid values")):
                with pytest.raises(CSVValidationError, match="Failed to validate fold-change values"):
                    creator.validate_csv_file()
    
    def test_find_column_mapping_automatic(self, creator: PatientDatabaseCreator):
        """Test automatic column mapping detection."""
        available_columns = {'transcript_id', 'cancer_fold', 'other_column'}
        mapping = creator._find_column_mapping(available_columns)
        
        assert mapping == {'transcript_id': 'transcript_id', 'cancer_fold': 'cancer_fold'}
    
    def test_find_column_mapping_alternatives(self, creator: PatientDatabaseCreator):
        """Test column mapping with alternative names."""
        available_columns = {'transcript', 'fold_change', 'other_column'}
        mapping = creator._find_column_mapping(available_columns)
        
        assert mapping == {'transcript_id': 'transcript', 'cancer_fold': 'fold_change'}
    
    def test_find_column_mapping_case_insensitive(self, creator: PatientDatabaseCreator):
        """Test case-insensitive column mapping."""
        available_columns = {'TRANSCRIPT_ID', 'Cancer_Fold', 'other_column'}
        mapping = creator._find_column_mapping(available_columns)
        
        assert mapping == {'transcript_id': 'TRANSCRIPT_ID', 'cancer_fold': 'Cancer_Fold'}
    
    def test_find_column_mapping_incomplete(self, creator: PatientDatabaseCreator):
        """Test column mapping when not all columns found."""
        available_columns = {'transcript_id', 'other_column'}  # Missing fold column
        mapping = creator._find_column_mapping(available_columns)
        
        assert mapping == {}  # Should return empty dict when incomplete
    
    def test_validate_mapped_columns_success(self, creator: PatientDatabaseCreator, valid_csv_data: pd.DataFrame):
        """Test successful column validation."""
        creator.csv_data = valid_csv_data
        creator.column_mapping = {'transcript_id': 'transcript_id', 'cancer_fold': 'cancer_fold'}
        
        creator._validate_mapped_columns()
        
        assert len(creator.transcript_updates) == 3
        assert creator.transcript_updates['ENST00000123456'] == 2.5
        assert creator.transcript_updates['ENST00000789012'] == 0.3
        assert creator.transcript_updates['ENST00000345678'] == 1.8
    
    def test_validate_mapped_columns_with_nulls(self, creator: PatientDatabaseCreator):
        """Test column validation with null values."""
        data_with_nulls = pd.DataFrame({
            'transcript_id': ['ENST00000123456', None, 'ENST00000345678'],
            'cancer_fold': [2.5, 0.3, None]
        })
        
        creator.csv_data = data_with_nulls
        creator.column_mapping = {'transcript_id': 'transcript_id', 'cancer_fold': 'cancer_fold'}
        
        creator._validate_mapped_columns()
        
        # Should only have one valid entry
        assert len(creator.transcript_updates) == 1
        assert creator.transcript_updates['ENST00000123456'] == 2.5
        assert creator.stats["valid_transcripts"] == 1
        assert creator.stats["invalid_transcripts"] == 2
    
    def test_validate_mapped_columns_invalid_numbers(self, creator: PatientDatabaseCreator):
        """Test column validation with invalid numeric values."""
        invalid_data = pd.DataFrame({
            'transcript_id': ['ENST00000123456', 'ENST00000789012'],
            'cancer_fold': ['not_a_number', 'also_invalid']
        })
        
        creator.csv_data = invalid_data
        creator.column_mapping = {'transcript_id': 'transcript_id', 'cancer_fold': 'cancer_fold'}
        
        with pytest.raises(CSVValidationError, match="non-numeric fold-change values"):
            creator._validate_mapped_columns()
    
    @patch('psycopg2.connect')
    def test_create_target_database_new(self, mock_connect: Mock, creator: PatientDatabaseCreator):
        """Test creating new target database."""
        # Mock database connection and cursor
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor_context = Mock()
        mock_cursor_context.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor_context.__exit__ = Mock(return_value=None)
        mock_conn.cursor.return_value = mock_cursor_context
        mock_connect.return_value = mock_conn
        
        # Mock database doesn't exist
        mock_cursor.fetchone.return_value = None
        
        creator._create_target_database(Mock())
        
        # Verify database creation
        mock_cursor.execute.assert_any_call(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            ("mediabase_patient_TEST123",)
        )
        mock_cursor.execute.assert_any_call('CREATE DATABASE "mediabase_patient_TEST123"')
    
    @patch('psycopg2.connect')
    @patch('rich.prompt.Confirm.ask', return_value=True)
    def test_create_target_database_overwrite(self, mock_confirm: Mock, mock_connect: Mock, creator: PatientDatabaseCreator):
        """Test overwriting existing target database."""
        # Mock database connection and cursor
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor_context = Mock()
        mock_cursor_context.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor_context.__exit__ = Mock(return_value=None)
        mock_conn.cursor.return_value = mock_cursor_context
        mock_connect.return_value = mock_conn
        
        # Mock database exists
        mock_cursor.fetchone.return_value = [1]
        
        creator._create_target_database(Mock())
        
        # Verify database drop and recreation
        mock_cursor.execute.assert_any_call('DROP DATABASE "mediabase_patient_TEST123"')
        mock_cursor.execute.assert_any_call('CREATE DATABASE "mediabase_patient_TEST123"')
    
    @patch('psycopg2.connect')
    @patch('rich.prompt.Confirm.ask', return_value=False)
    def test_create_target_database_cancelled(self, mock_confirm: Mock, mock_connect: Mock, creator: PatientDatabaseCreator):
        """Test cancelling database creation when database exists."""
        # Mock database connection and cursor
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor_context = Mock()
        mock_cursor_context.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor_context.__exit__ = Mock(return_value=None)
        mock_conn.cursor.return_value = mock_cursor_context
        mock_connect.return_value = mock_conn
        
        # Mock database exists
        mock_cursor.fetchone.return_value = [1]
        
        with pytest.raises(DatabaseCopyError, match="Database creation cancelled by user"):
            creator._create_target_database(Mock())
    
    @patch('os.system')
    @patch('os.path.exists', return_value=True)
    @patch('os.remove')
    def test_copy_database_content(self, mock_remove: Mock, mock_exists: Mock, mock_system: Mock, creator: PatientDatabaseCreator):
        """Test database content copying."""
        mock_source_db = Mock()
        
        creator._copy_database_content(mock_source_db)
        
        # Verify pg_dump and psql commands were called
        assert mock_system.call_count == 2
        mock_remove.assert_called_once()
    
    @patch('src.db.database.get_db_manager')
    def test_update_fold_changes_success(self, mock_get_db: Mock, creator: PatientDatabaseCreator):
        """Test successful fold-change updates."""
        # Setup test data
        creator.transcript_updates = {
            'ENST00000123456': 2.5,
            'ENST00000789012': 0.3,
            'ENST00000345678': 1.8
        }
        
        # Mock database manager and cursor
        mock_db = Mock()
        mock_cursor = Mock()
        mock_transaction = Mock()
        mock_transaction.__enter__ = Mock(return_value=mock_cursor)
        mock_transaction.__exit__ = Mock(return_value=None)
        mock_db.transaction.return_value = mock_transaction
        mock_get_db.return_value = mock_db
        
        # Mock successful updates (all transcripts found)
        mock_cursor.fetchone.return_value = [3]
        
        creator.update_fold_changes()
        
        assert creator.stats["updates_applied"] == 3
        assert creator.stats["transcripts_not_found"] == 0
    
    @patch('src.db.database.get_db_manager')
    def test_update_fold_changes_partial(self, mock_get_db: Mock, creator: PatientDatabaseCreator):
        """Test fold-change updates with some transcripts not found."""
        # Setup test data
        creator.transcript_updates = {
            'ENST00000123456': 2.5,
            'ENST00000789012': 0.3,
            'ENST00000999999': 1.8  # This one won't be found
        }
        
        # Mock database manager and cursor
        mock_db = Mock()
        mock_cursor = Mock()
        mock_transaction = Mock()
        mock_transaction.__enter__ = Mock(return_value=mock_cursor)
        mock_transaction.__exit__ = Mock(return_value=None)
        mock_db.transaction.return_value = mock_transaction
        mock_get_db.return_value = mock_db
        
        # Mock partial updates (only 2 of 3 transcripts found)
        mock_cursor.fetchone.return_value = [2]
        
        creator.update_fold_changes()
        
        assert creator.stats["updates_applied"] == 2
        assert creator.stats["transcripts_not_found"] == 1
    
    @patch('src.db.database.get_db_manager')
    def test_update_fold_changes_database_error(self, mock_get_db: Mock, creator: PatientDatabaseCreator):
        """Test fold-change updates with database error."""
        creator.transcript_updates = {'ENST00000123456': 2.5}
        
        # Mock database error
        mock_get_db.side_effect = psycopg2.Error("Connection failed")
        
        with pytest.raises(FoldChangeUpdateError, match="Failed to update fold-change values"):
            creator.update_fold_changes()
    
    @patch('src.db.database.get_db_manager')
    def test_validate_result(self, mock_get_db: Mock, creator: PatientDatabaseCreator):
        """Test result validation."""
        # Mock database manager and cursor
        mock_db = Mock()
        mock_cursor = Mock()
        mock_transaction = Mock()
        mock_transaction.__enter__ = Mock(return_value=mock_cursor)
        mock_transaction.__exit__ = Mock(return_value=None)
        mock_db.transaction.return_value = mock_transaction
        mock_get_db.return_value = mock_db
        
        # Mock query results
        mock_cursor.fetchone.side_effect = [[10000], [150]]  # total, modified
        mock_cursor.fetchall.return_value = [
            ('ENST00000123456', 2.5),
            ('ENST00000789012', 0.3)
        ]
        
        # Should not raise any exceptions
        creator.validate_result()
    
    @patch('src.db.database.get_db_manager')
    def test_validate_result_error(self, mock_get_db: Mock, creator: PatientDatabaseCreator):
        """Test result validation with database error."""
        mock_get_db.side_effect = psycopg2.Error("Connection failed")
        
        with pytest.raises(PatientCopyError, match="Result validation failed"):
            creator.validate_result()

class TestCSVValidationEdgeCases:
    """Test edge cases for CSV validation."""

    @pytest.fixture(autouse=True)
    def setup_db(self, test_db):
        """Ensure test database exists for all tests in this class."""
        pass

    @pytest.fixture
    def db_config(self) -> Dict[str, Any]:
        """Database configuration for testing."""
        return {
            'host': os.getenv('MB_POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('MB_POSTGRES_PORT', '5435')),
            'dbname': os.getenv('MB_POSTGRES_NAME', 'mediabase_test'),
            'user': os.getenv('MB_POSTGRES_USER', 'mbase_user'),
            'password': os.getenv('MB_POSTGRES_PASSWORD', 'mbase_secret')
        }
    
    def test_mixed_case_columns(self, tmp_path: Path, db_config: Dict[str, Any]):
        """Test CSV with mixed case column names."""
        data = pd.DataFrame({
            'Transcript_ID': ['ENST00000123456'],
            'Cancer_Fold': [2.5]
        })
        
        csv_path = tmp_path / "mixed_case.csv"
        data.to_csv(csv_path, index=False)
        
        creator = PatientDatabaseCreator("TEST123", csv_path, db_config)
        creator.validate_csv_file()
        
        assert creator.column_mapping['transcript_id'] == 'Transcript_ID'
        assert creator.column_mapping['cancer_fold'] == 'Cancer_Fold'
    
    def test_extra_columns(self, tmp_path: Path, db_config: Dict[str, Any]):
        """Test CSV with extra columns."""
        data = pd.DataFrame({
            'transcript_id': ['ENST00000123456'],
            'cancer_fold': [2.5],
            'extra_col1': ['value1'],
            'extra_col2': [42],
            'another_col': ['ignored']
        })
        
        csv_path = tmp_path / "extra_cols.csv"
        data.to_csv(csv_path, index=False)
        
        creator = PatientDatabaseCreator("TEST123", csv_path, db_config)
        creator.validate_csv_file()
        
        # Should work fine, extra columns ignored
        assert len(creator.transcript_updates) == 1
    
    def test_scientific_notation_fold_values(self, tmp_path: Path, db_config: Dict[str, Any]):
        """Test CSV with scientific notation fold values."""
        data = pd.DataFrame({
            'transcript_id': ['ENST00000123456', 'ENST00000789012'],
            'cancer_fold': ['1.5e-3', '2.3E+2']
        })
        
        csv_path = tmp_path / "scientific.csv"
        data.to_csv(csv_path, index=False)
        
        creator = PatientDatabaseCreator("TEST123", csv_path, db_config)
        creator.validate_csv_file()
        
        assert creator.transcript_updates['ENST00000123456'] == pytest.approx(0.0015)
        assert creator.transcript_updates['ENST00000789012'] == pytest.approx(230.0)
    
    def test_negative_fold_values(self, tmp_path: Path, db_config: Dict[str, Any]):
        """Test CSV with negative fold values."""
        data = pd.DataFrame({
            'transcript_id': ['ENST00000123456'],
            'cancer_fold': [-1.5]
        })
        
        csv_path = tmp_path / "negative.csv"
        data.to_csv(csv_path, index=False)
        
        creator = PatientDatabaseCreator("TEST123", csv_path, db_config)
        creator.validate_csv_file()
        
        assert creator.transcript_updates['ENST00000123456'] == -1.5

class TestIntegrationScenarios:
    """Integration test scenarios."""

    @pytest.fixture(autouse=True)
    def setup_db(self, test_db):
        """Ensure test database exists for all tests in this class."""
        pass

    @pytest.fixture
    def db_config(self) -> Dict[str, Any]:
        """Database configuration for testing."""
        return {
            'host': os.getenv('MB_POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('MB_POSTGRES_PORT', '5435')),
            'dbname': os.getenv('MB_POSTGRES_NAME', 'mediabase_test'),
            'user': os.getenv('MB_POSTGRES_USER', 'mbase_user'),
            'password': os.getenv('MB_POSTGRES_PASSWORD', 'mbase_secret')
        }
    
    @pytest.mark.integration
    def test_full_pipeline_dry_run(self, tmp_path: Path, db_config: Dict[str, Any]):
        """Test complete pipeline in dry-run mode."""
        # Create test CSV
        data = pd.DataFrame({
            'transcript_id': ['ENST00000123456', 'ENST00000789012'],
            'cancer_fold': [2.5, 0.3]
        })
        
        csv_path = tmp_path / "test_data.csv"
        data.to_csv(csv_path, index=False)
        
        creator = PatientDatabaseCreator("TEST123", csv_path, db_config)
        
        # Should complete CSV validation without errors
        creator.validate_csv_file()
        
        assert len(creator.transcript_updates) == 2
        assert creator.stats["valid_transcripts"] == 2
        assert creator.stats["invalid_transcripts"] == 0
    
    def test_large_csv_handling(self, tmp_path: Path, db_config: Dict[str, Any]):
        """Test handling of large CSV files."""
        # Create large dataset
        n_rows = 10000
        data = pd.DataFrame({
            'transcript_id': [f'ENST{i:011d}' for i in range(n_rows)],
            'cancer_fold': [float(i % 100) / 10.0 for i in range(n_rows)]
        })
        
        csv_path = tmp_path / "large_data.csv"
        data.to_csv(csv_path, index=False)
        
        creator = PatientDatabaseCreator("TEST123", csv_path, db_config)
        creator.validate_csv_file()
        
        assert len(creator.transcript_updates) == n_rows
        assert creator.stats["valid_transcripts"] == n_rows

if __name__ == "__main__":
    pytest.main([__file__])
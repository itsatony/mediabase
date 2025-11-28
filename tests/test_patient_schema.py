"""Unit tests for patient schema management utilities.

This module contains comprehensive tests for patient schema creation, validation,
and management in the MEDIABASE v0.6.0 shared core architecture.

Architecture:
- Single mbase database with public schema (core transcriptome data)
- Patient-specific schemas: patient_<PATIENT_ID>
- Sparse storage: Only stores expression_fold_change != 1.0
"""

import os
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

# Add src to path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.db.patient_schema import (
    validate_patient_id,
    get_schema_name,
    schema_exists,
    create_patient_schema,
    insert_metadata,
    drop_patient_schema,
    list_patient_schemas,
    validate_patient_schema,
    get_patient_statistics,
    InvalidPatientIDError,
    SchemaExistsError,
    SchemaNotFoundError,
    PatientSchemaError,
)
from src.db.database import DatabaseManager


class TestPatientIDValidation:
    """Test suite for patient ID validation."""

    def test_valid_patient_id_simple(self):
        """Test valid simple patient ID."""
        assert validate_patient_id("TEST123") == True

    def test_valid_patient_id_with_underscore(self):
        """Test valid patient ID with underscore."""
        assert validate_patient_id("TEST_PATIENT_123") == True

    def test_valid_patient_id_with_hyphen(self):
        """Test valid patient ID with hyphen."""
        assert validate_patient_id("TEST-PATIENT-123") == True

    def test_valid_patient_id_mixed_case(self):
        """Test valid patient ID with mixed case."""
        assert validate_patient_id("TeSt123") == True

    def test_valid_patient_id_minimum_length(self):
        """Test valid patient ID at minimum length (3 chars)."""
        assert validate_patient_id("ABC") == True

    def test_valid_patient_id_maximum_length(self):
        """Test valid patient ID at maximum length (100 chars)."""
        long_id = "A" * 100
        assert validate_patient_id(long_id) == True

    def test_invalid_patient_id_too_short(self):
        """Test invalid patient ID - too short."""
        with pytest.raises(InvalidPatientIDError, match="must be 3-100 characters"):
            validate_patient_id("AB")

    def test_invalid_patient_id_too_long(self):
        """Test invalid patient ID - too long."""
        long_id = "A" * 101
        with pytest.raises(InvalidPatientIDError, match="must be 3-100 characters"):
            validate_patient_id(long_id)

    def test_invalid_patient_id_starts_with_number(self):
        """Test invalid patient ID - starts with number."""
        with pytest.raises(InvalidPatientIDError, match="must start with letter"):
            validate_patient_id("123TEST")

    def test_invalid_patient_id_special_characters(self):
        """Test invalid patient ID - contains special characters."""
        with pytest.raises(
            InvalidPatientIDError, match="alphanumeric, underscore, hyphen"
        ):
            validate_patient_id("TEST@123")

        with pytest.raises(InvalidPatientIDError):
            validate_patient_id("TEST.123")

        with pytest.raises(InvalidPatientIDError):
            validate_patient_id("TEST 123")

    def test_invalid_patient_id_reserved_word(self):
        """Test invalid patient ID - SQL reserved word."""
        reserved_words = [
            "public",
            "schema",
            "table",
            "select",
            "insert",
            "update",
            "delete",
            "drop",
            "create",
            "alter",
            "grant",
            "revoke",
            "user",
            "admin",
        ]

        for word in reserved_words:
            with pytest.raises(InvalidPatientIDError, match="reserved word"):
                validate_patient_id(word)

            # Case insensitive
            with pytest.raises(InvalidPatientIDError, match="reserved word"):
                validate_patient_id(word.upper())


class TestSchemaNameGeneration:
    """Test suite for schema name generation."""

    def test_get_schema_name_simple(self):
        """Test schema name generation for simple patient ID."""
        assert get_schema_name("TEST123") == "patient_TEST123"

    def test_get_schema_name_with_underscore(self):
        """Test schema name generation with underscore."""
        assert get_schema_name("TEST_PATIENT") == "patient_TEST_PATIENT"

    def test_get_schema_name_with_hyphen(self):
        """Test schema name generation with hyphen."""
        assert get_schema_name("TEST-PATIENT") == "patient_TEST-PATIENT"

    def test_get_schema_name_invalid_id(self):
        """Test schema name generation with invalid ID."""
        with pytest.raises(InvalidPatientIDError):
            get_schema_name("123TEST")


class TestSchemaExistence:
    """Test suite for schema existence checks."""

    @pytest.fixture(autouse=True)
    def setup_db(self, test_db):
        """Ensure test database exists for all tests in this class."""
        pass

    @pytest.fixture
    def db_manager(self) -> DatabaseManager:
        """Create mock database manager."""
        manager = Mock(spec=DatabaseManager)
        cursor = Mock()
        manager.cursor = cursor
        manager.connect = Mock()
        return manager

    def test_schema_exists_true(self, db_manager):
        """Test schema_exists returns True when schema exists."""
        db_manager.cursor.fetchone.return_value = [True]

        result = schema_exists("TEST123", db_manager)

        assert result == True
        db_manager.cursor.execute.assert_called_once()
        assert "patient_TEST123" in str(db_manager.cursor.execute.call_args)

    def test_schema_exists_false(self, db_manager):
        """Test schema_exists returns False when schema doesn't exist."""
        db_manager.cursor.fetchone.return_value = [False]

        result = schema_exists("TEST123", db_manager)

        assert result == False

    def test_schema_exists_none_result(self, db_manager):
        """Test schema_exists handles None result."""
        db_manager.cursor.fetchone.return_value = None

        result = schema_exists("TEST123", db_manager)

        assert result == False

    def test_schema_exists_connects_if_no_cursor(self, db_manager):
        """Test schema_exists connects to DB if cursor not available."""
        db_manager.cursor = None

        # Mock connect to set cursor
        def set_cursor():
            db_manager.cursor = Mock()
            db_manager.cursor.fetchone.return_value = [False]

        db_manager.connect.side_effect = set_cursor

        result = schema_exists("TEST123", db_manager)

        db_manager.connect.assert_called_once()


class TestSchemaCreation:
    """Test suite for patient schema creation."""

    @pytest.fixture(autouse=True)
    def setup_db(self, test_db):
        """Ensure test database exists for all tests in this class."""
        pass

    @pytest.fixture
    def db_manager(self) -> DatabaseManager:
        """Create mock database manager."""
        manager = Mock(spec=DatabaseManager)
        cursor = Mock()
        manager.cursor = cursor
        manager.connect = Mock()
        manager.db_config = {"user": "mbase_user", "host": "localhost", "port": 5435}
        return manager

    @patch("src.db.patient_schema.schema_exists")
    @patch("src.db.patient_schema.TEMPLATE_PATH")
    def test_create_patient_schema_success(
        self, mock_template_path, mock_schema_exists, db_manager
    ):
        """Test successful patient schema creation."""
        # Setup mocks
        mock_schema_exists.return_value = False
        mock_template_path.exists.return_value = True
        mock_template_path.read_text.return_value = """
            CREATE SCHEMA IF NOT EXISTS ${SCHEMA_NAME};
            COMMENT ON SCHEMA ${SCHEMA_NAME} IS 'Patient: ${PATIENT_ID}, Created: ${CREATED_DATE}';
            CREATE TABLE ${SCHEMA_NAME}.expression_data (
                transcript_id VARCHAR(50) PRIMARY KEY,
                expression_fold_change FLOAT NOT NULL
            );
            CREATE TABLE ${SCHEMA_NAME}.metadata (
                patient_id VARCHAR(100) PRIMARY KEY
            );
        """

        result = create_patient_schema("TEST123", db_manager)

        assert result["success"] == True
        assert result["patient_id"] == "TEST123"
        assert result["schema_name"] == "patient_TEST123"
        assert "created_date" in result

        # Verify SQL was executed
        db_manager.cursor.execute.assert_called_once()
        sql = db_manager.cursor.execute.call_args[0][0]
        assert "patient_TEST123" in sql
        assert "${SCHEMA_NAME}" not in sql  # Verify substitution happened
        assert "${PATIENT_ID}" not in sql

    @patch("src.db.patient_schema.schema_exists")
    def test_create_patient_schema_already_exists(self, mock_schema_exists, db_manager):
        """Test creating schema that already exists raises error."""
        mock_schema_exists.return_value = True

        with pytest.raises(SchemaExistsError, match="already exists"):
            create_patient_schema("TEST123", db_manager)

    @patch("src.db.patient_schema.schema_exists")
    @patch("src.db.patient_schema.drop_patient_schema")
    @patch("src.db.patient_schema.TEMPLATE_PATH")
    def test_create_patient_schema_overwrite(
        self, mock_template_path, mock_drop_schema, mock_schema_exists, db_manager
    ):
        """Test creating schema with overwrite=True."""
        # Setup mocks
        mock_schema_exists.return_value = True
        mock_template_path.exists.return_value = True
        mock_template_path.read_text.return_value = """
            CREATE SCHEMA IF NOT EXISTS ${SCHEMA_NAME};
        """

        result = create_patient_schema("TEST123", db_manager, overwrite=True)

        # Verify old schema was dropped
        mock_drop_schema.assert_called_once_with("TEST123", db_manager)

        # Verify new schema was created
        assert result["success"] == True

    @patch("src.db.patient_schema.schema_exists")
    @patch("src.db.patient_schema.insert_metadata")
    @patch("src.db.patient_schema.TEMPLATE_PATH")
    def test_create_patient_schema_with_metadata(
        self, mock_template_path, mock_insert_metadata, mock_schema_exists, db_manager
    ):
        """Test creating schema with metadata."""
        # Setup mocks
        mock_schema_exists.return_value = False
        mock_template_path.exists.return_value = True
        mock_template_path.read_text.return_value = """
            CREATE SCHEMA IF NOT EXISTS ${SCHEMA_NAME};
        """

        metadata = {
            "cancer_type": "Breast Cancer",
            "cancer_subtype": "HER2+",
            "source_file": "test.csv",
        }

        result = create_patient_schema("TEST123", db_manager, metadata=metadata)

        # Verify metadata was inserted
        mock_insert_metadata.assert_called_once_with(
            patient_id="TEST123", metadata=metadata, db_manager=db_manager
        )

        assert result["success"] == True

    def test_create_patient_schema_invalid_id(self, db_manager):
        """Test creating schema with invalid patient ID."""
        with pytest.raises(InvalidPatientIDError):
            create_patient_schema("123TEST", db_manager)

    @patch("src.db.patient_schema.schema_exists")
    @patch("src.db.patient_schema.TEMPLATE_PATH")
    def test_create_patient_schema_template_not_found(
        self, mock_template_path, mock_schema_exists, db_manager
    ):
        """Test creating schema when template file is missing."""
        mock_schema_exists.return_value = False
        mock_template_path.exists.return_value = False

        with pytest.raises(PatientSchemaError, match="template not found"):
            create_patient_schema("TEST123", db_manager)

    @patch("src.db.patient_schema.schema_exists")
    @patch("src.db.patient_schema.TEMPLATE_PATH")
    def test_create_patient_schema_execution_error(
        self, mock_template_path, mock_schema_exists, db_manager
    ):
        """Test creating schema when SQL execution fails."""
        mock_schema_exists.return_value = False
        mock_template_path.exists.return_value = True
        mock_template_path.read_text.return_value = "CREATE SCHEMA ${SCHEMA_NAME};"

        # Simulate SQL execution error
        db_manager.cursor.execute.side_effect = Exception("SQL execution failed")

        with pytest.raises(PatientSchemaError, match="Schema creation failed"):
            create_patient_schema("TEST123", db_manager)


class TestMetadataInsertion:
    """Test suite for metadata insertion."""

    @pytest.fixture(autouse=True)
    def setup_db(self, test_db):
        """Ensure test database exists for all tests in this class."""
        pass

    @pytest.fixture
    def db_manager(self) -> DatabaseManager:
        """Create mock database manager."""
        manager = Mock(spec=DatabaseManager)
        cursor = Mock()
        manager.cursor = cursor
        manager.connect = Mock()
        return manager

    def test_insert_metadata_basic_fields(self, db_manager):
        """Test inserting metadata with basic fields."""
        metadata = {
            "source_file": "test.csv",
            "file_format": "deseq2",
            "cancer_type": "Breast Cancer",
        }

        insert_metadata("TEST123", metadata, db_manager)

        # Verify INSERT statement was executed
        db_manager.cursor.execute.assert_called_once()
        sql = db_manager.cursor.execute.call_args[0][0]

        assert "patient_TEST123.metadata" in sql
        assert "source_file" in sql
        assert "file_format" in sql
        assert "cancer_type" in sql
        assert "ON CONFLICT (patient_id) DO UPDATE" in sql

    def test_insert_metadata_with_jsonb(self, db_manager):
        """Test inserting metadata with JSONB field."""
        metadata = {
            "source_file": "test.csv",
            "metadata_json": '{"stage": "III", "mutation": "TP53"}',
        }

        insert_metadata("TEST123", metadata, db_manager)

        # Verify JSONB casting
        sql = db_manager.cursor.execute.call_args[0][0]
        assert "metadata_json" in sql
        assert "%s::jsonb" in sql

    def test_insert_metadata_all_fields(self, db_manager):
        """Test inserting metadata with all supported fields."""
        metadata = {
            "source_file": "test.csv",
            "file_format": "deseq2",
            "normalization_method": "DESeq2",
            "total_transcripts_uploaded": 1000,
            "transcripts_matched": 950,
            "transcripts_unmatched": 50,
            "matching_success_rate": 0.95,
            "clinical_notes": "Test patient",
            "cancer_type": "Breast Cancer",
            "cancer_subtype": "HER2+",
            "tissue_type": "tumor",
            "sample_type": "biopsy",
            "sequencing_platform": "Illumina",
            "read_depth_millions": 50.5,
        }

        insert_metadata("TEST123", metadata, db_manager)

        sql = db_manager.cursor.execute.call_args[0][0]

        # Verify all fields are in SQL
        for field in metadata.keys():
            assert field in sql

    def test_insert_metadata_execution_error(self, db_manager):
        """Test metadata insertion when SQL execution fails."""
        metadata = {"source_file": "test.csv"}

        db_manager.cursor.execute.side_effect = Exception("Insert failed")

        with pytest.raises(PatientSchemaError, match="Metadata insert failed"):
            insert_metadata("TEST123", metadata, db_manager)

    def test_insert_metadata_connects_if_no_cursor(self, db_manager):
        """Test metadata insertion connects to DB if cursor not available."""
        db_manager.cursor = None

        def set_cursor():
            db_manager.cursor = Mock()

        db_manager.connect.side_effect = set_cursor

        metadata = {"source_file": "test.csv"}
        insert_metadata("TEST123", metadata, db_manager)

        db_manager.connect.assert_called_once()


class TestSchemaDrop:
    """Test suite for schema dropping."""

    @pytest.fixture(autouse=True)
    def setup_db(self, test_db):
        """Ensure test database exists for all tests in this class."""
        pass

    @pytest.fixture
    def db_manager(self) -> DatabaseManager:
        """Create mock database manager."""
        manager = Mock(spec=DatabaseManager)
        cursor = Mock()
        manager.cursor = cursor
        manager.connect = Mock()
        return manager

    @patch("src.db.patient_schema.schema_exists")
    def test_drop_patient_schema_success(self, mock_schema_exists, db_manager):
        """Test successful schema drop."""
        mock_schema_exists.return_value = True

        result = drop_patient_schema("TEST123", db_manager)

        assert result == True
        db_manager.cursor.execute.assert_called_once()
        sql = db_manager.cursor.execute.call_args[0][0]
        assert "DROP SCHEMA patient_TEST123 CASCADE" in sql

    @patch("src.db.patient_schema.schema_exists")
    def test_drop_patient_schema_restrict(self, mock_schema_exists, db_manager):
        """Test schema drop with RESTRICT."""
        mock_schema_exists.return_value = True

        result = drop_patient_schema("TEST123", db_manager, cascade=False)

        assert result == True
        sql = db_manager.cursor.execute.call_args[0][0]
        assert "DROP SCHEMA patient_TEST123 RESTRICT" in sql

    @patch("src.db.patient_schema.schema_exists")
    def test_drop_patient_schema_not_found(self, mock_schema_exists, db_manager):
        """Test dropping non-existent schema raises error."""
        mock_schema_exists.return_value = False

        with pytest.raises(SchemaNotFoundError, match="does not exist"):
            drop_patient_schema("TEST123", db_manager)

    @patch("src.db.patient_schema.schema_exists")
    def test_drop_patient_schema_execution_error(self, mock_schema_exists, db_manager):
        """Test schema drop when SQL execution fails."""
        mock_schema_exists.return_value = True
        db_manager.cursor.execute.side_effect = Exception("Drop failed")

        with pytest.raises(PatientSchemaError, match="Schema drop failed"):
            drop_patient_schema("TEST123", db_manager)


class TestListPatientSchemas:
    """Test suite for listing patient schemas."""

    @pytest.fixture(autouse=True)
    def setup_db(self, test_db):
        """Ensure test database exists for all tests in this class."""
        pass

    @pytest.fixture
    def db_manager(self) -> DatabaseManager:
        """Create mock database manager."""
        manager = Mock(spec=DatabaseManager)
        cursor = Mock()
        manager.cursor = cursor
        manager.connect = Mock()
        return manager

    def test_list_patient_schemas_multiple(self, db_manager):
        """Test listing multiple patient schemas."""
        db_manager.cursor.fetchall.return_value = [
            ("patient_TEST123", "TEST123"),
            ("patient_DEMO_HER2", "DEMO_HER2"),
            ("patient_TNBC_001", "TNBC_001"),
        ]

        result = list_patient_schemas(db_manager)

        assert len(result) == 3
        assert result[0] == {"schema_name": "patient_TEST123", "patient_id": "TEST123"}
        assert result[1] == {
            "schema_name": "patient_DEMO_HER2",
            "patient_id": "DEMO_HER2",
        }
        assert result[2] == {
            "schema_name": "patient_TNBC_001",
            "patient_id": "TNBC_001",
        }

    def test_list_patient_schemas_empty(self, db_manager):
        """Test listing when no patient schemas exist."""
        db_manager.cursor.fetchall.return_value = []

        result = list_patient_schemas(db_manager)

        assert result == []

    def test_list_patient_schemas_connects_if_no_cursor(self, db_manager):
        """Test listing connects to DB if cursor not available."""
        db_manager.cursor = None

        def set_cursor():
            db_manager.cursor = Mock()
            db_manager.cursor.fetchall.return_value = []

        db_manager.connect.side_effect = set_cursor

        result = list_patient_schemas(db_manager)

        db_manager.connect.assert_called_once()


class TestSchemaValidation:
    """Test suite for patient schema validation."""

    @pytest.fixture(autouse=True)
    def setup_db(self, test_db):
        """Ensure test database exists for all tests in this class."""
        pass

    @pytest.fixture
    def db_manager(self) -> DatabaseManager:
        """Create mock database manager."""
        manager = Mock(spec=DatabaseManager)
        cursor = Mock()
        manager.cursor = cursor
        manager.connect = Mock()

        # Mock cursor description for metadata fetch
        cursor.description = [
            ("patient_id",),
            ("upload_date",),
            ("source_file",),
            ("cancer_type",),
            ("cancer_subtype",),
        ]

        return manager

    @patch("src.db.patient_schema.schema_exists")
    def test_validate_patient_schema_not_found(self, mock_schema_exists, db_manager):
        """Test validating non-existent schema."""
        mock_schema_exists.return_value = False

        result = validate_patient_schema("TEST123", db_manager)

        assert result["valid"] == False
        assert "does not exist" in result["error"]

    @patch("src.db.patient_schema.schema_exists")
    def test_validate_patient_schema_all_pass(self, mock_schema_exists, db_manager):
        """Test validating schema with all checks passing."""
        mock_schema_exists.return_value = True

        # Setup cursor to return successful validation results
        db_manager.cursor.fetchone.side_effect = [
            (100,),  # expression_count
            (0,),  # sparse storage check (no fold_change=1.0)
            (0,),  # transcript references check (no orphans)
            (1,),  # metadata count
            (
                "TEST123",
                "2024-01-01",
                "test.csv",
                "Breast Cancer",
                "HER2+",
            ),  # metadata row
        ]

        result = validate_patient_schema("TEST123", db_manager)

        assert result["valid"] == True
        assert result["schema_name"] == "patient_TEST123"
        assert result["expression_count"] == 100
        assert result["checks"]["expression_table"] == "PASS"
        assert result["checks"]["sparse_storage"] == "PASS"
        assert result["checks"]["transcript_references"] == "PASS"
        assert result["checks"]["metadata"] == "PASS"
        assert "metadata" in result

    @patch("src.db.patient_schema.schema_exists")
    def test_validate_patient_schema_sparse_storage_fail(
        self, mock_schema_exists, db_manager
    ):
        """Test validating schema with sparse storage violation."""
        mock_schema_exists.return_value = True

        # Return 5 rows with fold_change=1.0 (violates sparse storage)
        db_manager.cursor.fetchone.side_effect = [
            (100,),  # expression_count
            (5,),  # sparse storage check FAIL
            (0,),  # transcript references
            (1,),  # metadata count
        ]

        result = validate_patient_schema("TEST123", db_manager)

        assert result["valid"] == False
        assert "FAIL" in result["checks"]["sparse_storage"]
        assert "5 rows with fold_change=1.0" in result["checks"]["sparse_storage"]

    @patch("src.db.patient_schema.schema_exists")
    def test_validate_patient_schema_orphaned_transcripts(
        self, mock_schema_exists, db_manager
    ):
        """Test validating schema with orphaned transcript IDs."""
        mock_schema_exists.return_value = True

        db_manager.cursor.fetchone.side_effect = [
            (100,),  # expression_count
            (0,),  # sparse storage
            (10,),  # orphaned transcripts FAIL
            (1,),  # metadata count
        ]

        result = validate_patient_schema("TEST123", db_manager)

        assert result["valid"] == False
        assert "FAIL" in result["checks"]["transcript_references"]
        assert "10 orphaned" in result["checks"]["transcript_references"]

    @patch("src.db.patient_schema.schema_exists")
    def test_validate_patient_schema_no_metadata(self, mock_schema_exists, db_manager):
        """Test validating schema with no metadata row."""
        mock_schema_exists.return_value = True

        db_manager.cursor.fetchone.side_effect = [
            (100,),  # expression_count
            (0,),  # sparse storage
            (0,),  # transcript references
            (0,),  # no metadata row
        ]

        result = validate_patient_schema("TEST123", db_manager)

        assert result["valid"] == True  # No metadata is warning, not failure
        assert "WARN" in result["checks"]["metadata"]

    @patch("src.db.patient_schema.schema_exists")
    def test_validate_patient_schema_multiple_metadata_rows(
        self, mock_schema_exists, db_manager
    ):
        """Test validating schema with multiple metadata rows."""
        mock_schema_exists.return_value = True

        db_manager.cursor.fetchone.side_effect = [
            (100,),  # expression_count
            (0,),  # sparse storage
            (0,),  # transcript references
            (3,),  # multiple metadata rows - FAIL
        ]

        result = validate_patient_schema("TEST123", db_manager)

        assert result["valid"] == False
        assert "FAIL" in result["checks"]["metadata"]
        assert "3" in result["checks"]["metadata"]


class TestPatientStatistics:
    """Test suite for patient statistics."""

    @pytest.fixture(autouse=True)
    def setup_db(self, test_db):
        """Ensure test database exists for all tests in this class."""
        pass

    @pytest.fixture
    def db_manager(self) -> DatabaseManager:
        """Create mock database manager."""
        manager = Mock(spec=DatabaseManager)
        cursor = Mock()
        manager.cursor = cursor
        manager.connect = Mock()
        return manager

    def test_get_patient_statistics_complete(self, db_manager):
        """Test getting complete patient statistics."""
        db_manager.cursor.fetchone.side_effect = [
            (500,),  # total transcripts
            (120,),  # overexpressed (>2.0)
            (80,),  # underexpressed (<0.5)
            (0.2, 8.5, 1.85, 1.3),  # min, max, avg, median fold change
        ]

        result = get_patient_statistics("TEST123", db_manager)

        assert result["patient_id"] == "TEST123"
        assert result["schema_name"] == "patient_TEST123"
        assert result["total_transcripts"] == 500
        assert result["overexpressed_count"] == 120
        assert result["underexpressed_count"] == 80
        assert result["min_fold_change"] == 0.2
        assert result["max_fold_change"] == 8.5
        assert result["avg_fold_change"] == 1.85
        assert result["median_fold_change"] == 1.3

    def test_get_patient_statistics_no_data(self, db_manager):
        """Test getting statistics with no expression data."""
        db_manager.cursor.fetchone.side_effect = [
            (0,),  # total transcripts
            (0,),  # overexpressed
            (0,),  # underexpressed
            (None, None, None, None),  # all None (no data)
        ]

        result = get_patient_statistics("TEST123", db_manager)

        assert result["total_transcripts"] == 0
        assert result["overexpressed_count"] == 0
        assert result["underexpressed_count"] == 0
        assert result["min_fold_change"] is None
        assert result["max_fold_change"] is None
        assert result["avg_fold_change"] is None
        assert result["median_fold_change"] is None

    def test_get_patient_statistics_connects_if_no_cursor(self, db_manager):
        """Test statistics connects to DB if cursor not available."""
        db_manager.cursor = None

        def set_cursor():
            db_manager.cursor = Mock()
            db_manager.cursor.fetchone.side_effect = [
                (100,),
                (20,),
                (15,),
                (0.5, 3.0, 1.2, 1.1),
            ]

        db_manager.connect.side_effect = set_cursor

        result = get_patient_statistics("TEST123", db_manager)

        db_manager.connect.assert_called_once()
        assert result["total_transcripts"] == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

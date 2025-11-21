"""Integration tests for patient schema creation and CSV import.

These tests use real database connections to validate the full patient schema
workflow including CSV import, data validation, and cross-patient queries.

Architecture:
- Single mbase database with public schema (core transcriptome data)
- Patient-specific schemas: patient_<PATIENT_ID>
- Sparse storage: Only stores expression_fold_change != 1.0

Requirements:
- Test database: Uses MB_POSTGRES_NAME env var (default: mbase)
- Public schema must be populated with transcripts and genes
- Requires running ETL at least once to populate public schema
"""

import os
import pytest
import tempfile
from pathlib import Path
from typing import Dict, Any

import pandas as pd

# Add src to path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.db.database import DatabaseManager
from src.db.patient_schema import (
    create_patient_schema,
    insert_metadata,
    drop_patient_schema,
    list_patient_schemas,
    validate_patient_schema,
    get_patient_statistics,
    schema_exists,
    SchemaExistsError,
    SchemaNotFoundError,
)


@pytest.fixture(scope="module")
def db_manager():
    """Create database manager for integration tests."""
    config = {
        "host": os.getenv("MB_POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("MB_POSTGRES_PORT", "5435")),
        "dbname": "mbase",  # HARDCODED: v0.6.0 patient schemas live in mbase database
        "user": os.getenv("MB_POSTGRES_USER", "mbase_user"),
        "password": os.getenv("MB_POSTGRES_PASSWORD", "mbase_secret"),
    }

    manager = DatabaseManager(config=config)
    if not manager.connect():
        pytest.fail("Failed to connect to test database")

    # Cleanup: Drop all test schemas before running tests (lowercase patterns!)
    cursor = manager.cursor
    cursor.execute(
        """
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name LIKE 'patient_integration_%'
           OR schema_name LIKE 'patient_temp_%';
    """
    )
    test_schemas = cursor.fetchall()

    for (schema_name,) in test_schemas:
        try:
            cursor.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE;")
            manager.conn.commit()
            print(f"✓ Cleaned up test schema: {schema_name}")
        except Exception as e:
            print(f"⚠ Warning: Failed to drop schema {schema_name}: {e}")

    yield manager

    # Cleanup after tests complete (lowercase patterns!)
    cursor = manager.cursor
    cursor.execute(
        """
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name LIKE 'patient_integration_%'
           OR schema_name LIKE 'patient_temp_%';
    """
    )
    test_schemas = cursor.fetchall()

    for (schema_name,) in test_schemas:
        try:
            cursor.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE;")
            manager.conn.commit()
        except Exception as e:
            print(f"⚠ Warning: Failed to drop schema {schema_name}: {e}")

    manager.close()


@pytest.fixture(scope="module")
def test_patient_ids():
    """Patient IDs to use for integration tests."""
    return ["INTEGRATION_TEST_001", "INTEGRATION_TEST_002", "INTEGRATION_TEST_003"]


# Note: Cleanup is now handled by db_manager fixture using SQL pattern matching
# This catches all test schemas (INTEGRATION_TEST_*, TEMP_*, etc.)


@pytest.fixture(scope="module", autouse=True)
def cleanup_test_schemas(db_manager, test_patient_ids):
    """Clean up any existing test schemas before and after tests."""
    # Cleanup is now handled by db_manager fixture
    # This placeholder ensures the fixture dependency is met
    yield
    # Cleanup after tests is also handled by db_manager fixture teardown


@pytest.mark.integration
class TestPatientSchemaCreationIntegration:
    """Integration tests for patient schema creation."""

    def test_create_patient_schema_full_workflow(self, db_manager, test_patient_ids):
        """Test complete patient schema creation workflow."""
        patient_id = test_patient_ids[0]

        # Verify schema doesn't exist initially
        assert schema_exists(patient_id, db_manager) == False

        # Create schema
        metadata = {
            "cancer_type": "Integration Test Cancer",
            "cancer_subtype": "Test Subtype",
            "source_file": "integration_test.csv",
            "file_format": "standard",
        }

        result = create_patient_schema(
            patient_id=patient_id,
            db_manager=db_manager,
            metadata=metadata,
            overwrite=False,
        )

        # Verify creation result
        assert result["success"] == True
        assert result["patient_id"] == patient_id
        assert (
            result["schema_name"] == f"patient_{patient_id.lower()}"
        )  # Lowercased per PostgreSQL identifier rules
        assert "created_date" in result

        # Verify schema now exists
        assert schema_exists(patient_id, db_manager) == True

        # Verify schema structure
        cursor = db_manager.cursor

        # Check expression_data table exists
        cursor.execute(
            f"""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = 'patient_{patient_id.lower()}'
            AND table_name = 'expression_data';
        """
        )
        assert cursor.fetchone()[0] == 1

        # Check metadata table exists
        cursor.execute(
            f"""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = 'patient_{patient_id.lower()}'
            AND table_name = 'metadata';
        """
        )
        assert cursor.fetchone()[0] == 1

        # Verify metadata was inserted
        cursor.execute(
            f"""
            SELECT patient_id, cancer_type, cancer_subtype, source_file
            FROM patient_{patient_id.lower()}.metadata;
        """
        )
        row = cursor.fetchone()
        assert row[0] == patient_id
        assert row[1] == "Integration Test Cancer"
        assert row[2] == "Test Subtype"
        assert row[3] == "integration_test.csv"

    def test_create_patient_schema_duplicate_error(self, db_manager, test_patient_ids):
        """Test that creating duplicate schema raises error."""
        patient_id = test_patient_ids[0]

        # Schema already exists from previous test
        assert schema_exists(patient_id, db_manager) == True

        # Attempt to create again should raise error
        with pytest.raises(SchemaExistsError):
            create_patient_schema(
                patient_id=patient_id, db_manager=db_manager, overwrite=False
            )

    def test_create_patient_schema_with_overwrite(self, db_manager, test_patient_ids):
        """Test schema creation with overwrite flag."""
        patient_id = test_patient_ids[0]

        # Schema exists from previous test
        assert schema_exists(patient_id, db_manager) == True

        # Create with overwrite should succeed
        metadata = {
            "cancer_type": "Overwritten Cancer Type",
            "source_file": "overwrite_test.csv",
        }

        result = create_patient_schema(
            patient_id=patient_id,
            db_manager=db_manager,
            metadata=metadata,
            overwrite=True,
        )

        assert result["success"] == True

        # Verify metadata was updated
        cursor = db_manager.cursor
        cursor.execute(
            f"""
            SELECT cancer_type FROM patient_{patient_id}.metadata;
        """
        )
        assert cursor.fetchone()[0] == "Overwritten Cancer Type"

    def test_list_patient_schemas_integration(self, db_manager, test_patient_ids):
        """Test listing patient schemas with real database."""
        # Create multiple patient schemas
        for idx, patient_id in enumerate(test_patient_ids):
            if not schema_exists(patient_id, db_manager):
                create_patient_schema(
                    patient_id=patient_id,
                    db_manager=db_manager,
                    metadata={"source_file": f"test_{idx}.csv"},
                )

        # List all patient schemas
        schemas = list_patient_schemas(db_manager)

        # Verify our test schemas are in the list
        schema_names = [s["schema_name"] for s in schemas]
        for patient_id in test_patient_ids:
            assert (
                f"patient_{patient_id.lower()}" in schema_names
            )  # Lowercased per PostgreSQL identifier rules


@pytest.mark.integration
class TestExpressionDataImport:
    """Integration tests for expression data import."""

    def test_import_expression_data_basic(self, db_manager, test_patient_ids):
        """Test basic expression data import."""
        patient_id = test_patient_ids[1]

        # Ensure schema exists
        if not schema_exists(patient_id, db_manager):
            create_patient_schema(patient_id, db_manager)

        # Insert sample expression data
        cursor = db_manager.cursor

        test_data = [
            ("ENST00000357654", 2.5),  # BRCA1 transcript
            ("ENST00000269305", 0.3),  # TP53 transcript
            ("ENST00000078429", 4.2),  # Random transcript
        ]

        for transcript_id, fold_change in test_data:
            cursor.execute(
                f"""
                INSERT INTO patient_{patient_id}.expression_data
                (transcript_id, expression_fold_change)
                VALUES (%s, %s)
                ON CONFLICT (transcript_id) DO UPDATE
                SET expression_fold_change = EXCLUDED.expression_fold_change;
            """,
                (transcript_id, fold_change),
            )

        # Verify data was inserted
        cursor.execute(
            f"""
            SELECT COUNT(*) FROM patient_{patient_id}.expression_data;
        """
        )
        assert cursor.fetchone()[0] == 3

        # Verify fold change values
        cursor.execute(
            f"""
            SELECT transcript_id, expression_fold_change
            FROM patient_{patient_id}.expression_data
            ORDER BY transcript_id;
        """
        )
        results = cursor.fetchall()

        assert len(results) == 3
        assert results[0][1] == pytest.approx(4.2)  # ENST00000078429
        assert results[1][1] == pytest.approx(0.3)  # ENST00000269305
        assert results[2][1] == pytest.approx(2.5)  # ENST00000357654

    def test_sparse_storage_constraint(self, db_manager, test_patient_ids):
        """Test that sparse storage constraint prevents fold_change=1.0."""
        patient_id = test_patient_ids[1]
        cursor = db_manager.cursor

        # Attempt to insert fold_change = 1.0 should fail
        with pytest.raises(Exception) as exc_info:
            cursor.execute(
                f"""
                INSERT INTO patient_{patient_id}.expression_data
                (transcript_id, expression_fold_change)
                VALUES ('ENST00000999999', 1.0);
            """
            )

        # Verify it's a constraint violation
        assert "check_fold_change_not_default" in str(exc_info.value)

    def test_positive_fold_change_constraint(self, db_manager, test_patient_ids):
        """Test that fold change must be positive."""
        patient_id = test_patient_ids[1]
        cursor = db_manager.cursor

        # Attempt to insert negative fold_change should fail
        with pytest.raises(Exception) as exc_info:
            cursor.execute(
                f"""
                INSERT INTO patient_{patient_id}.expression_data
                (transcript_id, expression_fold_change)
                VALUES ('ENST00000888888', -1.5);
            """
            )

        # Verify it's a constraint violation
        assert "check_fold_change_positive" in str(exc_info.value)

    def test_import_large_dataset(self, db_manager, test_patient_ids):
        """Test importing larger dataset (1000 transcripts)."""
        patient_id = test_patient_ids[2]

        # Ensure schema exists
        if not schema_exists(patient_id, db_manager):
            create_patient_schema(patient_id, db_manager)

        # Generate 1000 test transcripts
        cursor = db_manager.cursor

        import_data = []
        for i in range(1000):
            transcript_id = f"ENST{i:011d}"
            # Generate varied fold changes (avoid 1.0)
            fold_change = 0.5 + (i % 100) / 50.0
            if fold_change == 1.0:
                fold_change = 1.5
            import_data.append((transcript_id, fold_change))

        # Batch insert
        cursor.executemany(
            f"""
            INSERT INTO patient_{patient_id}.expression_data
            (transcript_id, expression_fold_change)
            VALUES (%s, %s)
            ON CONFLICT (transcript_id) DO NOTHING;
        """,
            import_data,
        )

        # Verify count
        cursor.execute(
            f"""
            SELECT COUNT(*) FROM patient_{patient_id}.expression_data;
        """
        )
        assert cursor.fetchone()[0] == 1000


@pytest.mark.integration
class TestSchemaValidationIntegration:
    """Integration tests for patient schema validation."""

    def test_validate_patient_schema_complete(self, db_manager, test_patient_ids):
        """Test complete schema validation workflow."""
        patient_id = test_patient_ids[1]

        # Run validation
        validation_result = validate_patient_schema(patient_id, db_manager)

        # Check overall validity
        assert validation_result["valid"] == True
        assert (
            validation_result["schema_name"] == f"patient_{patient_id.lower()}"
        )  # Lowercased per PostgreSQL identifier rules
        assert validation_result["patient_id"] == patient_id

        # Check individual validation checks
        assert validation_result["checks"]["expression_table"] == "PASS"
        assert validation_result["checks"]["sparse_storage"] == "PASS"
        assert validation_result["checks"]["transcript_references"] == "PASS"

        # Verify expression count
        assert validation_result["expression_count"] == 3  # From previous test

    def test_get_patient_statistics_integration(self, db_manager, test_patient_ids):
        """Test patient statistics calculation with real data."""
        patient_id = test_patient_ids[1]

        # Get statistics
        stats = get_patient_statistics(patient_id, db_manager)

        # Verify statistics
        assert stats["patient_id"] == patient_id
        assert (
            stats["schema_name"] == f"patient_{patient_id.lower()}"
        )  # Lowercased per PostgreSQL identifier rules
        assert stats["total_transcripts"] == 3

        # Check fold change statistics
        assert stats["overexpressed_count"] == 2  # 2.5 and 4.2
        assert stats["underexpressed_count"] == 1  # 0.3

        assert stats["min_fold_change"] == pytest.approx(0.3)
        assert stats["max_fold_change"] == pytest.approx(4.2)

        # Average: (2.5 + 0.3 + 4.2) / 3 = 2.333...
        assert stats["avg_fold_change"] == pytest.approx(2.333, abs=0.01)


@pytest.mark.integration
class TestCrossPatientQueries:
    """Integration tests for cross-patient queries."""

    def test_query_single_patient_overexpressed(self, db_manager, test_patient_ids):
        """Test querying overexpressed genes in single patient."""
        patient_id = test_patient_ids[1]
        cursor = db_manager.cursor

        # Query for overexpressed transcripts (fold_change > 2.0)
        cursor.execute(
            f"""
            SELECT
                t.transcript_id,
                g.gene_symbol,
                pe.expression_fold_change
            FROM public.transcripts t
            LEFT JOIN patient_{patient_id}.expression_data pe
                ON t.transcript_id = pe.transcript_id
            JOIN public.genes g ON t.gene_id = g.gene_id
            WHERE pe.expression_fold_change > 2.0
            ORDER BY pe.expression_fold_change DESC;
        """
        )

        results = cursor.fetchall()

        # Should have 2 results (4.2 and 2.5)
        assert len(results) == 2
        assert results[0][2] == pytest.approx(4.2)  # Highest first
        assert results[1][2] == pytest.approx(2.5)

    def test_query_with_coalesce_baseline(self, db_manager, test_patient_ids):
        """Test query using COALESCE for baseline expression."""
        patient_id = test_patient_ids[1]
        cursor = db_manager.cursor

        # Query specific transcripts with baseline fallback
        cursor.execute(
            f"""
            SELECT
                t.transcript_id,
                g.gene_symbol,
                COALESCE(pe.expression_fold_change, 1.0) as fold_change
            FROM public.transcripts t
            LEFT JOIN patient_{patient_id}.expression_data pe
                ON t.transcript_id = pe.transcript_id
            JOIN public.genes g ON t.gene_id = g.gene_id
            WHERE t.transcript_id IN (
                'ENST00000357654',  -- Has data (2.5)
                'ENST00000269305',  -- Has data (0.3)
                'ENST00000999999'   -- No data (should be 1.0)
            )
            ORDER BY t.transcript_id;
        """
        )

        results = cursor.fetchall()

        # Verify COALESCE behavior
        for transcript_id, gene_symbol, fold_change in results:
            if transcript_id == "ENST00000357654":
                assert fold_change == pytest.approx(2.5)
            elif transcript_id == "ENST00000269305":
                assert fold_change == pytest.approx(0.3)
            elif transcript_id == "ENST00000999999":
                assert fold_change == pytest.approx(1.0)  # Baseline

    def test_cross_patient_comparison(self, db_manager, test_patient_ids):
        """Test comparing expression across multiple patients."""
        patient1 = test_patient_ids[1]  # Has 3 transcripts
        patient2 = test_patient_ids[2]  # Has 1000 transcripts

        cursor = db_manager.cursor

        # Count overexpressed genes per patient
        cursor.execute(
            f"""
            SELECT
                'patient_1' as patient,
                COUNT(*) as overexpressed_count
            FROM patient_{patient1}.expression_data
            WHERE expression_fold_change > 2.0
            UNION ALL
            SELECT
                'patient_2' as patient,
                COUNT(*) as overexpressed_count
            FROM patient_{patient2}.expression_data
            WHERE expression_fold_change > 2.0;
        """
        )

        results = cursor.fetchall()

        assert len(results) == 2
        assert results[0][1] == 2  # Patient 1 has 2 overexpressed
        assert results[1][1] > 0  # Patient 2 has some overexpressed

    def test_find_commonly_overexpressed(self, db_manager, test_patient_ids):
        """Test finding commonly overexpressed transcripts across patients."""
        patient1 = test_patient_ids[1]
        patient2 = test_patient_ids[2]

        cursor = db_manager.cursor

        # Find transcripts overexpressed in both patients
        cursor.execute(
            f"""
            SELECT
                t.transcript_id,
                g.gene_symbol,
                pe1.expression_fold_change as patient1_fc,
                pe2.expression_fold_change as patient2_fc
            FROM public.transcripts t
            JOIN public.genes g ON t.gene_id = g.gene_id
            INNER JOIN patient_{patient1}.expression_data pe1
                ON t.transcript_id = pe1.transcript_id
            INNER JOIN patient_{patient2}.expression_data pe2
                ON t.transcript_id = pe2.transcript_id
            WHERE pe1.expression_fold_change > 2.0
              AND pe2.expression_fold_change > 2.0
            ORDER BY (pe1.expression_fold_change + pe2.expression_fold_change) DESC
            LIMIT 5;
        """
        )

        results = cursor.fetchall()

        # Verify results structure (may have 0 or more common transcripts)
        for transcript_id, gene_symbol, fc1, fc2 in results:
            assert fc1 > 2.0
            assert fc2 > 2.0


@pytest.mark.integration
class TestSchemaDropIntegration:
    """Integration tests for schema dropping."""

    def test_drop_patient_schema_integration(self, db_manager):
        """Test complete schema drop workflow."""
        # Create temporary schema
        temp_patient_id = "TEMP_DROP_TEST"

        create_patient_schema(temp_patient_id, db_manager)

        # Verify it exists
        assert schema_exists(temp_patient_id, db_manager) == True

        # Drop it
        result = drop_patient_schema(temp_patient_id, db_manager, cascade=True)

        assert result == True

        # Verify it's gone
        assert schema_exists(temp_patient_id, db_manager) == False

    def test_drop_nonexistent_schema_error(self, db_manager):
        """Test dropping non-existent schema raises error."""
        with pytest.raises(SchemaNotFoundError):
            drop_patient_schema("NONEXISTENT_PATIENT", db_manager)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])

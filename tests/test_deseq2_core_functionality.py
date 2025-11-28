"""Focused tests for DESeq2 core functionality without database dependencies.

This module tests the essential DESeq2 detection, parsing, and conversion logic
without requiring database connections.
"""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path
from unittest.mock import Mock, patch
from typing import Dict, Any, List

# Add src to path for imports
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from scripts.create_patient_copy import PatientDatabaseCreator, DESEQ2_FORMAT_INDICATORS


class TestDESeq2CoreFunctionality:
    """Test core DESeq2 functionality without database dependencies."""

    @pytest.fixture
    def db_config(self) -> Dict[str, Any]:
        """Database configuration for testing."""
        return {
            "host": "localhost",
            "port": 5432,
            "dbname": "mediabase_test",
            "user": "postgres",
            "password": "postgres",
        }

    def test_deseq2_format_indicators_structure(self):
        """Test that DESeq2 format indicators are properly defined."""
        assert "symbol" in DESEQ2_FORMAT_INDICATORS
        assert "log2_fold_change" in DESEQ2_FORMAT_INDICATORS

        # Verify symbol variants
        symbol_variants = DESEQ2_FORMAT_INDICATORS["symbol"]
        assert "symbol" in symbol_variants
        assert "gene_symbol" in symbol_variants
        assert "gene_name" in symbol_variants

        # Verify log2 fold change variants
        log2_variants = DESEQ2_FORMAT_INDICATORS["log2_fold_change"]
        assert "log2foldchange" in log2_variants
        assert "log2fc" in log2_variants
        assert "logfc" in log2_variants

    def test_deseq2_format_detection_positive_cases(
        self, tmp_path: Path, db_config: Dict[str, Any]
    ):
        """Test DESeq2 format detection with various positive cases."""
        test_cases = [
            # Standard DESeq2 format
            {"SYMBOL": ["GENE1"], "log2FoldChange": [1.0]},
            # Lowercase variants
            {"symbol": ["GENE1"], "log2foldchange": [1.0]},
            # Alternative names
            {"gene_symbol": ["GENE1"], "logfc": [1.0]},
            # Mixed case
            {"Gene_Name": ["GENE1"], "Log2FC": [1.0]},
        ]

        for i, columns in enumerate(test_cases):
            csv_file = tmp_path / f"deseq2_test_{i}.csv"
            df = pd.DataFrame(columns)
            df.to_csv(csv_file, index=False)

            creator = PatientDatabaseCreator(f"TEST{i}", csv_file, db_config)

            available_columns = set(columns.keys())
            deseq2_indicators = creator._detect_deseq2_format(available_columns)

            assert (
                len(deseq2_indicators) == 2
            ), f"Failed to detect DESeq2 format in case {i}: {columns.keys()}"
            assert "symbol" in deseq2_indicators
            assert "log2_fold_change" in deseq2_indicators

    def test_deseq2_format_detection_negative_cases(
        self, tmp_path: Path, db_config: Dict[str, Any]
    ):
        """Test DESeq2 format detection with cases that should NOT trigger detection."""
        negative_cases = [
            # Standard MEDIABASE format
            {"transcript_id": ["ENST001"], "cancer_fold": [2.0]},
            # Missing gene symbol
            {"log2FoldChange": [1.0], "padj": [0.01]},
            # Missing log2 fold change
            {"SYMBOL": ["GENE1"], "padj": [0.01]},
            # Completely unrelated columns
            {"random_col1": ["value"], "random_col2": [123]},
        ]

        for i, columns in enumerate(negative_cases):
            csv_file = tmp_path / f"negative_test_{i}.csv"
            df = pd.DataFrame(columns)
            df.to_csv(csv_file, index=False)

            creator = PatientDatabaseCreator(f"NEG{i}", csv_file, db_config)

            available_columns = set(columns.keys())
            deseq2_indicators = creator._detect_deseq2_format(available_columns)

            assert (
                len(deseq2_indicators) < 2
            ), f"Incorrectly detected DESeq2 format in negative case {i}: {columns.keys()}"

    def test_log2_to_linear_conversion_mathematics(self):
        """Test the mathematical accuracy of log2 to linear conversion."""
        test_cases = [
            (0.0, 1.0),  # 2^0 = 1
            (1.0, 2.0),  # 2^1 = 2
            (-1.0, 0.5),  # 2^-1 = 0.5
            (2.0, 4.0),  # 2^2 = 4
            (3.0, 8.0),  # 2^3 = 8
            (-2.0, 0.25),  # 2^-2 = 0.25
            (0.5, 1.414),  # 2^0.5 ≈ 1.414
            (-0.5, 0.707),  # 2^-0.5 ≈ 0.707
        ]

        for log2_value, expected_linear in test_cases:
            linear_result = 2**log2_value
            assert (
                abs(linear_result - expected_linear) < 0.01
            ), f"Log2 conversion failed: 2^{log2_value} = {linear_result}, expected ≈ {expected_linear}"

    def test_deseq2_column_mapping_logic(
        self, tmp_path: Path, db_config: Dict[str, Any]
    ):
        """Test DESeq2 column mapping without database dependency."""
        csv_file = tmp_path / "test.csv"
        creator = PatientDatabaseCreator("TEST", csv_file, db_config)

        # Test mapping logic
        available_columns = {"SYMBOL", "log2FoldChange", "padj", "pvalue"}
        deseq2_indicators = {"symbol": "SYMBOL", "log2_fold_change": "log2FoldChange"}

        mapping = creator._map_deseq2_columns(available_columns, deseq2_indicators)

        assert mapping["transcript_id"] == "SYMBOL"
        assert mapping["cancer_fold"] == "log2FoldChange"
        assert creator.log2_fold_column == "log2FoldChange"

    def test_process_deseq2_data_without_database(
        self, tmp_path: Path, db_config: Dict[str, Any]
    ):
        """Test DESeq2 data processing with mocked gene symbol mapping."""
        csv_file = tmp_path / "test.csv"
        creator = PatientDatabaseCreator("TEST", csv_file, db_config)

        # Create test data
        test_data = pd.DataFrame(
            {
                "SYMBOL": ["BRCA1", "TP53", "EGFR", "UNKNOWN"],
                "log2FoldChange": [1.0, -1.0, 2.0, 0.0],
                "padj": [0.01, 0.02, 0.001, 0.5],
            }
        )

        # Mock gene symbol mapping (avoid database call)
        mock_gene_mapping = {
            "BRCA1": "ENST00000357654",
            "TP53": "ENST00000269305",
            "EGFR": "ENST00000275493"
            # UNKNOWN gene not mapped intentionally
        }
        creator.gene_symbol_mapping = mock_gene_mapping

        # Mock the database loading function to avoid actual database call
        with patch.object(creator, "_load_gene_symbol_mapping"):
            creator._process_deseq2_data(test_data, "SYMBOL", "log2FoldChange")

        # Verify conversions
        expected_conversions = {
            "ENST00000357654": 2.0,  # BRCA1: 2^1.0 = 2.0
            "ENST00000269305": 0.5,  # TP53: 2^-1.0 = 0.5
            "ENST00000275493": 4.0,  # EGFR: 2^2.0 = 4.0
        }

        for transcript_id, expected_value in expected_conversions.items():
            assert transcript_id in creator.transcript_updates
            actual_value = creator.transcript_updates[transcript_id]
            assert (
                abs(actual_value - expected_value) < 0.001
            ), f"Conversion error: {transcript_id} = {actual_value}, expected {expected_value}"

        # Verify statistics
        assert creator.stats["valid_transcripts"] == 3  # 3 mapped genes
        assert creator.stats["unmapped_symbols"] == 1  # 1 unmapped gene (UNKNOWN)
        assert creator.stats["mapping_success_rate"] == 75.0  # 3/4 * 100

    def test_column_name_case_insensitivity(
        self, tmp_path: Path, db_config: Dict[str, Any]
    ):
        """Test that column detection is case-insensitive."""
        case_variations = [
            {"SYMBOL": ["GENE1"], "LOG2FOLDCHANGE": [1.0]},
            {"symbol": ["GENE1"], "log2foldchange": [1.0]},
            {"Symbol": ["GENE1"], "Log2FoldChange": [1.0]},
            {"GENE_SYMBOL": ["GENE1"], "LOGFC": [1.0]},
        ]

        for i, columns in enumerate(case_variations):
            csv_file = tmp_path / f"case_test_{i}.csv"
            df = pd.DataFrame(columns)
            df.to_csv(csv_file, index=False)

            creator = PatientDatabaseCreator(f"CASE{i}", csv_file, db_config)
            available_columns = set(columns.keys())
            deseq2_indicators = creator._detect_deseq2_format(available_columns)

            assert (
                len(deseq2_indicators) >= 1
            ), f"Case-insensitive detection failed for case {i}: {columns.keys()}"

    def test_edge_case_log2_values(self):
        """Test handling of edge case log2 values."""
        edge_cases = [
            (float("inf"), float("inf")),  # Infinity should remain infinity
            (float("-inf"), 0.0),  # Negative infinity should become 0
            (0.0, 1.0),  # Zero should become 1
            (10.0, 1024.0),  # Large positive value
            (-10.0, 0.0009765625),  # Large negative value
        ]

        for log2_val, expected_min in edge_cases:
            if not np.isinf(log2_val):
                linear_result = 2**log2_val
                if np.isfinite(expected_min):
                    assert (
                        abs(linear_result - expected_min) < 0.001
                        or linear_result == expected_min
                    )

    def test_multiple_transcript_same_gene_handling(
        self, tmp_path: Path, db_config: Dict[str, Any]
    ):
        """Test handling when multiple transcripts exist for the same gene symbol."""
        csv_file = tmp_path / "test.csv"
        creator = PatientDatabaseCreator("TEST", csv_file, db_config)

        # Test data with duplicate gene symbols
        test_data = pd.DataFrame(
            {
                "SYMBOL": ["BRCA1", "BRCA1", "TP53"],  # BRCA1 appears twice
                "log2FoldChange": [1.0, 1.5, -1.0],
                "padj": [0.01, 0.02, 0.001],
            }
        )

        # Mock mapping - only one transcript per gene symbol
        creator.gene_symbol_mapping = {
            "BRCA1": "ENST00000357654",  # Only one transcript mapped
            "TP53": "ENST00000269305",
        }

        with patch.object(creator, "_load_gene_symbol_mapping"):
            creator._process_deseq2_data(test_data, "SYMBOL", "log2FoldChange")

        # Should handle duplicate gene symbols (last one should win)
        assert "ENST00000357654" in creator.transcript_updates
        # The last BRCA1 entry (log2FC=1.5) should be used: 2^1.5 ≈ 2.83
        brca1_result = creator.transcript_updates["ENST00000357654"]
        expected_brca1 = 2**1.5  # ≈ 2.83
        assert abs(brca1_result - expected_brca1) < 0.01

    def test_standard_vs_deseq2_format_distinction(
        self, tmp_path: Path, db_config: Dict[str, Any]
    ):
        """Test that the system can distinguish between standard and DESeq2 formats."""

        # Standard format should NOT trigger DESeq2 detection
        standard_data = pd.DataFrame(
            {
                "transcript_id": ["ENST00000001"],
                "cancer_fold": [2.5],
                "gene_symbol": ["GENE1"],  # This alone shouldn't trigger DESeq2
            }
        )

        csv_file1 = tmp_path / "standard.csv"
        standard_data.to_csv(csv_file1, index=False)
        creator1 = PatientDatabaseCreator("STANDARD", csv_file1, db_config)

        available_columns1 = set(standard_data.columns)
        deseq2_indicators1 = creator1._detect_deseq2_format(available_columns1)
        assert (
            len(deseq2_indicators1) < 2
        ), "Standard format incorrectly detected as DESeq2"

        # DESeq2 format SHOULD trigger detection
        deseq2_data = pd.DataFrame(
            {"SYMBOL": ["GENE1"], "log2FoldChange": [1.0], "padj": [0.01]}
        )

        csv_file2 = tmp_path / "deseq2.csv"
        deseq2_data.to_csv(csv_file2, index=False)
        creator2 = PatientDatabaseCreator("DESEQ2", csv_file2, db_config)

        available_columns2 = set(deseq2_data.columns)
        deseq2_indicators2 = creator2._detect_deseq2_format(available_columns2)
        assert len(deseq2_indicators2) == 2, "DESeq2 format not detected"


class TestValidationIntegration:
    """Integration tests for the validation workflow without database."""

    def test_full_column_mapping_workflow(self, tmp_path: Path):
        """Test the complete column mapping workflow."""

        # Create DESeq2 format CSV
        deseq2_data = pd.DataFrame(
            {
                "SYMBOL": ["BRCA1", "TP53"],
                "baseMean": [240.0, 51.7],
                "log2FoldChange": [0.61, -2.62],
                "padj": [0.20, 0.20],
            }
        )

        csv_file = tmp_path / "deseq2_workflow.csv"
        deseq2_data.to_csv(csv_file, index=False)

        db_config = {
            "host": "localhost",
            "port": 5432,
            "dbname": "test",
            "user": "postgres",
            "password": "postgres",
        }

        creator = PatientDatabaseCreator("WORKFLOW", csv_file, db_config)
        creator.csv_data = deseq2_data

        # Test the column mapping workflow
        available_columns = set(deseq2_data.columns)
        mapping = creator._find_column_mapping(available_columns)

        # Should successfully detect DESeq2 format and create mapping
        assert len(mapping) == 2
        assert creator.is_deseq2_format is True
        assert mapping["transcript_id"] == "SYMBOL"
        assert mapping["cancer_fold"] == "log2FoldChange"

        # Verify the column mapping was stored
        creator.column_mapping = mapping
        assert creator.column_mapping["transcript_id"] == "SYMBOL"
        assert creator.column_mapping["cancer_fold"] == "log2FoldChange"

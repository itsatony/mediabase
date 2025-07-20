#!/usr/bin/env python3
"""Test flexible transcript ID matching functionality in patient copy script."""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from scripts.create_patient_copy import PatientDatabaseCreator


class TestFlexibleTranscriptMatching(unittest.TestCase):
    """Test flexible transcript ID matching logic."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_db_config = {
            'host': 'localhost',
            'port': 5432,
            'dbname': 'test_mediabase',
            'user': 'test_user',
            'password': 'test_pass'
        }
        
        self.patient_copy = PatientDatabaseCreator(
            patient_id="TEST123",
            csv_file=Path("test.csv"),
            source_db_config=self.mock_db_config
        )
    
    def test_normalize_transcript_id(self):
        """Test transcript ID normalization."""
        # Test versioned IDs
        self.assertEqual(
            self.patient_copy._normalize_transcript_id("ENST00000456328.1"),
            "ENST00000456328"
        )
        self.assertEqual(
            self.patient_copy._normalize_transcript_id("ENST00000456328.12"),
            "ENST00000456328"
        )
        
        # Test unversioned IDs (should remain unchanged)
        self.assertEqual(
            self.patient_copy._normalize_transcript_id("ENST00000456328"),
            "ENST00000456328"
        )
        
        # Test non-standard formats
        self.assertEqual(
            self.patient_copy._normalize_transcript_id("ENST00000456328.abc"),
            "ENST00000456328.abc"  # Non-numeric version should not be stripped
        )
        
        # Test empty/None inputs
        self.assertEqual(
            self.patient_copy._normalize_transcript_id(""),
            ""
        )
        self.assertEqual(
            self.patient_copy._normalize_transcript_id(None),
            None
        )
    
    def test_match_transcript_id_flexibly(self):
        """Test flexible transcript ID matching."""
        # Mock database IDs (mix of versioned and unversioned)
        database_ids = {
            "ENST00000456328",
            "ENST00000450305.1", 
            "ENST00000488147.2",
            "ENST00000619216",
            "ENST00000473358.1"
        }
        
        # Test exact matches
        self.assertEqual(
            self.patient_copy._match_transcript_id_flexibly("ENST00000456328", database_ids),
            "ENST00000456328"
        )
        self.assertEqual(
            self.patient_copy._match_transcript_id_flexibly("ENST00000450305.1", database_ids),
            "ENST00000450305.1"
        )
        
        # Test versioned input matching unversioned database ID
        self.assertEqual(
            self.patient_copy._match_transcript_id_flexibly("ENST00000456328.5", database_ids),
            "ENST00000456328"
        )
        
        # Test unversioned input matching versioned database ID
        self.assertEqual(
            self.patient_copy._match_transcript_id_flexibly("ENST00000450305", database_ids),
            "ENST00000450305.1"
        )
        
        # Test no match
        self.assertIsNone(
            self.patient_copy._match_transcript_id_flexibly("ENST99999999999", database_ids)
        )
        
        # Test empty/None inputs
        self.assertIsNone(
            self.patient_copy._match_transcript_id_flexibly("", database_ids)
        )
        self.assertIsNone(
            self.patient_copy._match_transcript_id_flexibly(None, database_ids)
        )
    
    def test_match_transcript_id_version_addition(self):
        """Test adding version suffixes to unversioned IDs."""
        database_ids = {
            "ENST00000456328.1",
            "ENST00000450305.2",
            "ENST00000488147.3"
        }
        
        # Test that unversioned input can match by adding version suffix
        self.assertEqual(
            self.patient_copy._match_transcript_id_flexibly("ENST00000456328", database_ids),
            "ENST00000456328.1"
        )
        self.assertEqual(
            self.patient_copy._match_transcript_id_flexibly("ENST00000450305", database_ids),
            "ENST00000450305.2"
        )
        self.assertEqual(
            self.patient_copy._match_transcript_id_flexibly("ENST00000488147", database_ids),
            "ENST00000488147.3"
        )
    
    def test_match_transcript_id_normalized_matching(self):
        """Test normalized matching where base IDs match."""
        database_ids = {
            "ENST00000456328.10",  # Higher version numbers
            "ENST00000450305.25"
        }
        
        # Test that different versions of same transcript can match
        self.assertEqual(
            self.patient_copy._match_transcript_id_flexibly("ENST00000456328.1", database_ids),
            "ENST00000456328.10"
        )
        self.assertEqual(
            self.patient_copy._match_transcript_id_flexibly("ENST00000450305", database_ids),
            "ENST00000450305.25"
        )


if __name__ == '__main__':
    unittest.main()
"""Integration test for complete patient copy workflow with DESeq2 data.

This test demonstrates that the enhanced patient copy system can successfully
process DESeq2 format files and create patient-specific database updates.
"""

import pytest
import pandas as pd
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from typing import Dict, Any

# Add src to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from scripts.create_patient_copy import PatientDatabaseCreator

class TestPatientWorkflowIntegration:
    """Integration tests for complete patient copy workflow."""
    
    def test_complete_deseq2_workflow_simulation(self, tmp_path: Path):
        """Test complete workflow from DESeq2 CSV to database updates."""
        
        # Create realistic DESeq2 output file (like user provided)
        deseq2_output = pd.DataFrame({
            'SYMBOL': ['BRCA1', 'TP53', 'EGFR', 'MYC', 'KRAS', 'PIK3CA'],
            'baseMean': [240.0033086, 51.74567233, 1850.465789, 1329.690696, 1638.35287, 892.123456],
            'log2FoldChange': [0.607602249, -2.61508112, -1.047249687, 0.617431664, 0.276392428, 1.234567],
            'lfcSE': [0.335758132, 1.446814346, 0.416750258, 0.173353097, 0.220527243, 0.123456],
            'stat': [1.80964269, -1.807475249, -2.512895114, 3.561699655, 1.253325552, 4.567890],
            'pvalue': [0.070351215, 0.07068821, 0.011974493, 0.000368462, 0.210087253, 0.000123],
            'padj': [0.203820552, 0.204308384, 0.052658351, 0.002889004, 0.433380619, 0.001234]
        })
        
        csv_file = tmp_path / "patient_deseq2_results.csv"
        deseq2_output.to_csv(csv_file, index=False)
        
        db_config = {
            'host': 'localhost',
            'port': 5432,
            'dbname': 'mediabase',
            'user': 'postgres',
            'password': 'postgres'
        }
        
        patient_creator = PatientDatabaseCreator("PATIENT_001", csv_file, db_config)
        
        # Mock the database operations to avoid requiring actual database
        mock_gene_mappings = [
            ('BRCA1', 'ENST00000357654'),
            ('TP53', 'ENST00000269305'),
            ('EGFR', 'ENST00000275493'),
            ('MYC', 'ENST00000377970'),
            ('KRAS', 'ENST00000256078'),
            ('PIK3CA', 'ENST00000263967')
        ]
        
        with patch('scripts.create_patient_copy.get_db_manager') as mock_db_manager:
            mock_manager = Mock()
            mock_cursor = Mock()
            mock_cursor.fetchall.return_value = mock_gene_mappings
            mock_manager.cursor = mock_cursor
            mock_manager.ensure_connection.return_value = True
            mock_db_manager.return_value = mock_manager
            
            # Run the CSV validation (this is where DESeq2 detection happens)
            patient_creator.validate_csv_file()
            
            # Verify DESeq2 format was detected
            assert patient_creator.is_deseq2_format is True
            assert patient_creator.log2_fold_column == 'log2FoldChange'
            
            # Verify column mapping
            assert patient_creator.column_mapping['transcript_id'] == 'SYMBOL'
            assert patient_creator.column_mapping['cancer_fold'] == 'log2FoldChange'
            
            # Verify transcript updates were created with log2 conversion
            assert len(patient_creator.transcript_updates) == 6
            
            # Check specific conversions
            expected_conversions = {
                'ENST00000357654': 2 ** 0.607602249,   # BRCA1: ~1.52
                'ENST00000269305': 2 ** -2.61508112,   # TP53: ~0.164
                'ENST00000275493': 2 ** -1.047249687,  # EGFR: ~0.483
                'ENST00000377970': 2 ** 0.617431664,   # MYC: ~1.53
                'ENST00000256078': 2 ** 0.276392428,   # KRAS: ~1.21
                'ENST00000263967': 2 ** 1.234567       # PIK3CA: ~2.35
            }
            
            for transcript_id, expected_value in expected_conversions.items():
                assert transcript_id in patient_creator.transcript_updates
                actual_value = patient_creator.transcript_updates[transcript_id]
                assert abs(actual_value - expected_value) < 0.001, f"Conversion error for {transcript_id}: {actual_value} vs {expected_value}"
            
            # Verify statistics
            assert patient_creator.stats['valid_transcripts'] == 6
            assert patient_creator.stats['unmapped_symbols'] == 0
            assert patient_creator.stats['mapping_success_rate'] == 100.0
            
            # Verify patient database configuration
            assert patient_creator.patient_id == "PATIENT_001"
            assert patient_creator.target_db_name == "mediabase_patient_PATIENT_001"
    
    def test_partial_mapping_scenario(self, tmp_path: Path):
        """Test scenario where some gene symbols can't be mapped."""
        
        # Include some genes that won't have mappings
        mixed_data = pd.DataFrame({
            'SYMBOL': ['BRCA1', 'UNKNOWN_GENE', 'TP53', 'INVALID_SYMBOL'],
            'log2FoldChange': [1.0, 2.0, -1.0, 0.5],
            'padj': [0.01, 0.02, 0.001, 0.5]
        })
        
        csv_file = tmp_path / "mixed_mapping.csv"
        mixed_data.to_csv(csv_file, index=False)
        
        db_config = {
            'host': 'localhost', 'port': 5432, 'dbname': 'mediabase',
            'user': 'postgres', 'password': 'postgres'
        }
        
        patient_creator = PatientDatabaseCreator("PATIENT_002", csv_file, db_config)
        
        # Mock partial gene mappings (only some genes mapped)
        partial_mappings = [
            ('BRCA1', 'ENST00000357654'),
            ('TP53', 'ENST00000269305')
            # UNKNOWN_GENE and INVALID_SYMBOL intentionally not mapped
        ]
        
        with patch('scripts.create_patient_copy.get_db_manager') as mock_db_manager:
            mock_manager = Mock()
            mock_cursor = Mock()
            mock_cursor.fetchall.return_value = partial_mappings
            mock_manager.cursor = mock_cursor
            mock_manager.ensure_connection.return_value = True
            mock_db_manager.return_value = mock_manager
            
            # Run validation
            patient_creator.validate_csv_file()
            
            # Verify partial mapping results
            assert patient_creator.is_deseq2_format is True
            assert len(patient_creator.transcript_updates) == 2  # Only mapped genes
            
            # Check mapped transcripts
            assert 'ENST00000357654' in patient_creator.transcript_updates  # BRCA1
            assert 'ENST00000269305' in patient_creator.transcript_updates  # TP53
            
            # Verify conversions
            brca1_fold = patient_creator.transcript_updates['ENST00000357654']
            tp53_fold = patient_creator.transcript_updates['ENST00000269305']
            
            assert abs(brca1_fold - (2 ** 1.0)) < 0.001  # 2^1.0 = 2.0
            assert abs(tp53_fold - (2 ** -1.0)) < 0.001  # 2^-1.0 = 0.5
            
            # Check statistics
            assert patient_creator.stats['valid_transcripts'] == 2
            assert patient_creator.stats['unmapped_symbols'] == 2
            assert patient_creator.stats['mapping_success_rate'] == 50.0  # 2/4 * 100
    
    def test_standard_format_vs_deseq2_comparison(self, tmp_path: Path):
        """Test that standard format still works alongside DESeq2 support."""
        
        # Test 1: Standard format should work as before
        standard_data = pd.DataFrame({
            'transcript_id': ['ENST00000357654', 'ENST00000269305'],
            'cancer_fold': [2.5, 0.3],
            'gene_symbol': ['BRCA1', 'TP53']
        })
        
        standard_file = tmp_path / "standard_format.csv"
        standard_data.to_csv(standard_file, index=False)
        
        db_config = {'host': 'localhost', 'port': 5432, 'dbname': 'mediabase', 'user': 'postgres', 'password': 'postgres'}
        standard_creator = PatientDatabaseCreator("STANDARD_PATIENT", standard_file, db_config)
        
        # Mock for standard format (no database call needed)
        standard_creator.csv_data = standard_data
        available_columns = set(standard_data.columns)
        mapping = standard_creator._find_column_mapping(available_columns)
        
        # Should use standard mapping, not DESeq2
        assert standard_creator.is_deseq2_format is False
        assert len(mapping) == 2
        assert mapping['transcript_id'] == 'transcript_id'
        assert mapping['cancer_fold'] == 'cancer_fold'
        
        # Test 2: DESeq2 format should trigger DESeq2 processing
        deseq2_data = pd.DataFrame({
            'SYMBOL': ['BRCA1', 'TP53'],
            'log2FoldChange': [1.0, -1.0],
            'padj': [0.01, 0.02]
        })
        
        deseq2_file = tmp_path / "deseq2_format.csv"
        deseq2_data.to_csv(deseq2_file, index=False)
        
        deseq2_creator = PatientDatabaseCreator("DESEQ2_PATIENT", deseq2_file, db_config)
        deseq2_creator.csv_data = deseq2_data
        
        available_columns = set(deseq2_data.columns)
        mapping = deseq2_creator._find_column_mapping(available_columns)
        
        # Should use DESeq2 mapping
        assert deseq2_creator.is_deseq2_format is True
        assert len(mapping) == 2
        assert mapping['transcript_id'] == 'SYMBOL'
        assert mapping['cancer_fold'] == 'log2FoldChange'
    
    def test_clinical_workflow_simulation(self, tmp_path: Path):
        """Simulate a realistic clinical workflow with DESeq2 data."""
        
        # Simulate realistic clinical transcriptomics data
        clinical_data = pd.DataFrame({
            'SYMBOL': [
                'BRCA1', 'BRCA2', 'TP53', 'PTEN', 'ATM', 'CHEK2',  # Tumor suppressors
                'EGFR', 'HER2', 'MYC', 'RAS', 'PI3K', 'AKT1',      # Oncogenes  
                'ESR1', 'PGR', 'AR', 'CCND1', 'RB1', 'CDK4'        # Hormone/cell cycle
            ],
            'log2FoldChange': [
                # Tumor suppressors (often downregulated)
                -1.2, -0.8, -2.1, -1.5, -0.7, -0.9,
                # Oncogenes (often upregulated) 
                2.3, 1.8, 1.9, 2.1, 1.7, 1.4,
                # Mixed regulation
                0.3, -0.4, 1.1, 1.6, -1.3, 0.8
            ],
            'padj': [0.001] * 18,  # All significant
            'baseMean': [100 + i * 50 for i in range(18)]  # Varying expression levels
        })
        
        clinical_file = tmp_path / "clinical_patient_data.csv"
        clinical_data.to_csv(clinical_file, index=False)
        
        db_config = {'host': 'localhost', 'port': 5432, 'dbname': 'mediabase', 'user': 'postgres', 'password': 'postgres'}
        clinical_creator = PatientDatabaseCreator("CLINICAL_001", clinical_file, db_config)
        
        # Mock comprehensive gene mappings
        clinical_mappings = [
            ('BRCA1', 'ENST00000357654'), ('BRCA2', 'ENST00000380152'), ('TP53', 'ENST00000269305'),
            ('PTEN', 'ENST00000371953'), ('ATM', 'ENST00000278616'), ('CHEK2', 'ENST00000382580'),
            ('EGFR', 'ENST00000275493'), ('HER2', 'ENST00000269571'), ('MYC', 'ENST00000377970'),
            ('RAS', 'ENST00000256078'), ('PI3K', 'ENST00000263967'), ('AKT1', 'ENST00000349310'),
            ('ESR1', 'ENST00000206249'), ('PGR', 'ENST00000315146'), ('AR', 'ENST00000374690'),
            ('CCND1', 'ENST00000227507'), ('RB1', 'ENST00000267163'), ('CDK4', 'ENST00000257904')
        ]
        
        with patch('scripts.create_patient_copy.get_db_manager') as mock_db_manager:
            mock_manager = Mock()
            mock_cursor = Mock()
            mock_cursor.fetchall.return_value = clinical_mappings
            mock_manager.cursor = mock_cursor
            mock_manager.ensure_connection.return_value = True
            mock_db_manager.return_value = mock_manager
            
            clinical_creator.validate_csv_file()
            
            # Verify all genes were processed
            assert len(clinical_creator.transcript_updates) == 18
            assert clinical_creator.stats['mapping_success_rate'] == 100.0
            
            # Verify clinical-relevant conversions
            # Check tumor suppressor downregulation
            brca1_fold = clinical_creator.transcript_updates['ENST00000357654']  # BRCA1
            tp53_fold = clinical_creator.transcript_updates['ENST00000269305']   # TP53
            
            assert brca1_fold < 1.0, "BRCA1 should be downregulated (fold < 1.0)"
            assert tp53_fold < 1.0, "TP53 should be downregulated (fold < 1.0)"
            
            # Check oncogene upregulation
            egfr_fold = clinical_creator.transcript_updates['ENST00000275493']  # EGFR
            myc_fold = clinical_creator.transcript_updates['ENST00000377970']   # MYC
            
            assert egfr_fold > 1.0, "EGFR should be upregulated (fold > 1.0)"
            assert myc_fold > 1.0, "MYC should be upregulated (fold > 1.0)"
            
            # Verify specific mathematical conversions
            expected_brca1 = 2 ** -1.2  # Should be ~0.435
            expected_egfr = 2 ** 2.3    # Should be ~4.925
            
            assert abs(brca1_fold - expected_brca1) < 0.001
            assert abs(egfr_fold - expected_egfr) < 0.001
            
            # Clinical interpretation checks
            upregulated_count = sum(1 for fold in clinical_creator.transcript_updates.values() if fold > 2.0)
            downregulated_count = sum(1 for fold in clinical_creator.transcript_updates.values() if fold < 0.5)
            
            assert upregulated_count > 0, "Should have some highly upregulated genes"
            assert downregulated_count > 0, "Should have some highly downregulated genes"
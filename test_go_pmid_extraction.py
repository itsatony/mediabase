#!/usr/bin/env python3
"""Test GO PMID extraction functionality."""

import sys
from pathlib import Path

# Add project root to Python path
src_path = Path(__file__).resolve().parent
sys.path.append(str(src_path))

from src.etl.go_terms import GOTermProcessor

def test_go_pmid_extraction():
    """Test that GO evidence codes with PMIDs are properly extracted."""
    
    # Create a minimal config
    config = {
        'cache_dir': '/tmp/mediabase/cache',
        'batch_size': 100,
        'skip_scores': True
    }
    
    try:
        # Initialize processor
        processor = GOTermProcessor(config)
        print("✓ GO processor initialized successfully")
        
        # Test sample GO terms with PMIDs
        test_go_terms = {
            'GO:0005515': {
                'term': 'protein binding',
                'evidence': 'PMID:33961781',
                'aspect': 'molecular_function',
                'pmid': '33961781'
            },
            'GO:0008486': {
                'term': 'diphosphoinositol-polyphosphate diphosphatase activity',
                'evidence': 'GO_REF:0000003',
                'aspect': 'molecular_function',
                'pmid': None
            },
            'GO:0016462': {
                'term': 'pyrophosphatase activity',
                'evidence': 'PMID:12345678',
                'aspect': 'molecular_function', 
                'pmid': '12345678'
            }
        }
        
        # Test publication extraction
        publications = processor.extract_publication_references(test_go_terms)
        
        print(f"\n✓ Extracted {len(publications)} publication references from {len(test_go_terms)} GO terms")
        
        # Verify extracted PMIDs
        expected_pmids = {'33961781', '12345678'}
        extracted_pmids = {pub['pmid'] for pub in publications}
        
        print(f"Expected PMIDs: {expected_pmids}")
        print(f"Extracted PMIDs: {extracted_pmids}")
        
        assert expected_pmids == extracted_pmids, f"PMID mismatch: expected {expected_pmids}, got {extracted_pmids}"
        print("✓ All expected PMIDs correctly extracted")
        
        # Test publication structure
        for pub in publications:
            assert 'pmid' in pub, "Missing PMID field"
            assert 'evidence_type' in pub, "Missing evidence_type field"
            assert 'source_db' in pub, "Missing source_db field"
            assert pub['source_db'] == 'GO', "Incorrect source_db"
            assert pub['evidence_type'] == 'experimental', "Incorrect evidence_type"
            
        print("✓ Publication structure validation passed")
        
        # Test with no PMIDs
        no_pmid_terms = {
            'GO:0000001': {
                'term': 'test term',
                'evidence': 'IEA',
                'aspect': 'biological_process',
                'pmid': None
            }
        }
        
        no_pmid_pubs = processor.extract_publication_references(no_pmid_terms)
        assert len(no_pmid_pubs) == 0, "Should extract 0 publications when no PMIDs present"
        print("✓ No false positives when no PMIDs present")
        
        print("\n✅ GO PMID extraction test completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ GO PMID extraction test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_go_pmid_extraction()
    sys.exit(0 if success else 1)
#!/usr/bin/env python3
"""Test DrugCentral PMID extraction functionality."""

import sys
from pathlib import Path

# Add project root to Python path
src_path = Path(__file__).resolve().parent
sys.path.append(str(src_path))

from src.utils.publication_utils import extract_pmids_from_urls, extract_pmids_from_text

def test_drugcentral_url_pmid_extraction():
    """Test that DrugCentral URL-based PMID extraction works correctly."""
    
    print("Testing DrugCentral URL-based PMID extraction...")
    
    # Test data simulating DrugCentral URL columns
    test_cases = [
        {
            'act_source_url': 'https://pubmed.ncbi.nlm.nih.gov/17276408',
            'moa_source_url': None,
            'expected_pmids': ['17276408']
        },
        {
            'act_source_url': None,
            'moa_source_url': 'https://pubmed.ncbi.nlm.nih.gov/25123456',
            'expected_pmids': ['25123456']
        },
        {
            'act_source_url': 'https://pubmed.ncbi.nlm.nih.gov/12345678',
            'moa_source_url': 'https://pubmed.ncbi.nlm.nih.gov/87654321',
            'expected_pmids': ['12345678', '87654321']
        },
        {
            'act_source_url': 'https://www.ncbi.nlm.nih.gov/pubmed/33961781',
            'moa_source_url': None,
            'expected_pmids': ['33961781']
        },
        {
            'act_source_url': 'non-pubmed-url.com',
            'moa_source_url': 'another-non-pubmed-url.org',
            'expected_pmids': []
        },
        {
            'act_source_url': None,
            'moa_source_url': None,
            'expected_pmids': []
        }
    ]
    
    all_tests_passed = True
    
    for i, test_case in enumerate(test_cases, 1):
        try:
            # Extract PMIDs using the new function
            extracted_pmids = extract_pmids_from_urls(
                test_case['act_source_url'], 
                test_case['moa_source_url']
            )
            
            # Sort for comparison
            extracted_pmids.sort()
            expected_pmids = sorted(test_case['expected_pmids'])
            
            print(f"Test {i}:")
            print(f"  ACT URL: {test_case['act_source_url']}")
            print(f"  MOA URL: {test_case['moa_source_url']}")
            print(f"  Expected: {expected_pmids}")
            print(f"  Extracted: {extracted_pmids}")
            
            if extracted_pmids == expected_pmids:
                print(f"  ✓ PASSED")
            else:
                print(f"  ❌ FAILED - Expected {expected_pmids}, got {extracted_pmids}")
                all_tests_passed = False
                
        except Exception as e:
            print(f"  ❌ ERROR - {e}")
            all_tests_passed = False
        
        print()
    
    # Test additional PMID patterns
    print("Testing additional PMID patterns...")
    
    pattern_tests = [
        {
            'text': 'PMID:12345678',
            'expected': ['12345678']
        },
        {
            'text': 'PubMed:87654321',
            'expected': ['87654321']
        },
        {
            'text': 'pubmed/33961781',
            'expected': ['33961781']
        },
        {
            'text': '[25123456]',
            'expected': ['25123456']
        },
        {
            'text': 'Multiple PMIDs: PMID:12345678 and PMID:87654321',
            'expected': ['12345678', '87654321']
        }
    ]
    
    for i, test_case in enumerate(pattern_tests, 1):
        try:
            extracted_pmids = extract_pmids_from_text(test_case['text'])
            extracted_pmids.sort()
            expected_pmids = sorted(test_case['expected'])
            
            print(f"Pattern Test {i}:")
            print(f"  Text: {test_case['text']}")
            print(f"  Expected: {expected_pmids}")
            print(f"  Extracted: {extracted_pmids}")
            
            if extracted_pmids == expected_pmids:
                print(f"  ✓ PASSED")
            else:
                print(f"  ❌ FAILED")
                all_tests_passed = False
                
        except Exception as e:
            print(f"  ❌ ERROR - {e}")
            all_tests_passed = False
        
        print()
    
    if all_tests_passed:
        print("✅ All DrugCentral PMID extraction tests passed!")
        return True
    else:
        print("❌ Some DrugCentral PMID extraction tests failed!")
        return False

if __name__ == "__main__":
    success = test_drugcentral_url_pmid_extraction()
    sys.exit(0 if success else 1)
#!/usr/bin/env python3
"""Test enhanced publication pattern matching functionality."""

import sys
from pathlib import Path

# Add project root to Python path
src_path = Path(__file__).resolve().parent
sys.path.append(str(src_path))

from src.utils.publication_utils import (
    extract_pmids_from_text, extract_dois_from_text, extract_pmc_ids_from_text,
    extract_clinical_trial_ids_from_text, extract_all_publication_identifiers,
    format_publication_url
)

def test_enhanced_publication_patterns():
    """Test enhanced publication pattern matching."""
    
    print("Testing enhanced publication pattern matching...")
    
    test_cases = [
        {
            'name': 'Enhanced PMID patterns',
            'text': 'PMID: 12345678, pmid=33961781, PubMed ID:25123456, pmid : 15634941',
            'expected': {
                'pmids': ['12345678', '33961781', '25123456', '15634941'],
                'dois': [],
                'pmc_ids': [],
                'clinical_trial_ids': [],
                'arxiv_ids': []
            }
        },
        {
            'name': 'DOI patterns',
            'text': 'doi:10.1038/nature12345 https://doi.org/10.1016/j.cell.2020.01.001 DOI: 10.1126/science.abc1234',
            'expected': {
                'pmids': [],
                'dois': ['10.1038/nature12345', '10.1016/j.cell.2020.01.001', '10.1126/science.abc1234'],
                'pmc_ids': [],
                'clinical_trial_ids': [],
                'arxiv_ids': []
            }
        },
        {
            'name': 'PMC patterns',
            'text': 'PMC1234567 pmc:7891234 https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5555666',
            'expected': {
                'pmids': [],
                'dois': [],
                'pmc_ids': ['1234567', '7891234', '5555666'],
                'clinical_trial_ids': [],
                'arxiv_ids': []
            }
        },
        {
            'name': 'Clinical trial patterns',
            'text': 'NCT01234567 ISRCTN12345678 EUDRACT2020-001234-56 CTRI/2021/03/031234',
            'expected': {
                'pmids': [],
                'dois': [],
                'pmc_ids': [],
                'clinical_trial_ids': ['01234567', '12345678', '2020-001234-56', 'CTRI/2021/03/031234'],
                'arxiv_ids': []
            }
        },
        {
            'name': 'ArXiv patterns',
            'text': 'arXiv:2012.12345 https://arxiv.org/abs/1234.5678',
            'expected': {
                'pmids': [],
                'dois': [],
                'pmc_ids': [],
                'clinical_trial_ids': [],
                'arxiv_ids': ['2012.12345', '1234.5678']
            }
        },
        {
            'name': 'Mixed identifiers',
            'text': 'Study PMID:12345678 with DOI:10.1038/nature12345 and NCT01234567',
            'expected': {
                'pmids': ['12345678'],
                'dois': ['10.1038/nature12345'],
                'pmc_ids': [],
                'clinical_trial_ids': ['01234567'],
                'arxiv_ids': []
            }
        },
        {
            'name': 'Real DrugCentral URL',
            'text': 'https://pubmed.ncbi.nlm.nih.gov/17276408 with additional info',
            'expected': {
                'pmids': ['17276408'],
                'dois': [],
                'pmc_ids': [],
                'clinical_trial_ids': [],
                'arxiv_ids': []
            }
        }
    ]
    
    all_tests_passed = True
    
    for test_case in test_cases:
        print(f"\nTesting: {test_case['name']}")
        print(f"Text: {test_case['text']}")
        
        try:
            # Extract all identifiers
            extracted = extract_all_publication_identifiers(test_case['text'])
            expected = test_case['expected']
            
            print(f"Expected: {expected}")
            print(f"Extracted: {extracted}")
            
            # Check each identifier type
            for id_type in expected.keys():
                expected_set = set(expected[id_type])
                extracted_set = set(extracted[id_type])
                
                if expected_set == extracted_set:
                    print(f"  ✓ {id_type}: PASSED")
                else:
                    print(f"  ❌ {id_type}: FAILED")
                    print(f"    Expected: {expected_set}")
                    print(f"    Got: {extracted_set}")
                    all_tests_passed = False
                    
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            all_tests_passed = False
    
    # Test URL formatting
    print(f"\nTesting URL formatting...")
    
    url_tests = [
        ('12345678', 'pmid', 'https://pubmed.ncbi.nlm.nih.gov/12345678/'),
        ('10.1038/nature12345', 'doi', 'https://doi.org/10.1038/nature12345'),
        ('1234567', 'pmc', 'https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1234567/'),
        ('2012.12345', 'arxiv', 'https://arxiv.org/abs/2012.12345'),
        ('NCT01234567', 'clinical_trial', 'https://clinicaltrials.gov/ct2/show/NCT01234567'),
    ]
    
    for identifier, id_type, expected_url in url_tests:
        try:
            actual_url = format_publication_url(identifier, id_type)
            if actual_url == expected_url:
                print(f"  ✓ {id_type} URL: PASSED")
            else:
                print(f"  ❌ {id_type} URL: FAILED")
                print(f"    Expected: {expected_url}")
                print(f"    Got: {actual_url}")
                all_tests_passed = False
        except Exception as e:
            print(f"  ❌ {id_type} URL ERROR: {e}")
            all_tests_passed = False
    
    # Test individual extraction functions
    print(f"\nTesting individual extraction functions...")
    
    individual_tests = [
        ('extract_pmids_from_text', 'PMID:12345678 and PMID:87654321', ['12345678', '87654321']),
        ('extract_dois_from_text', 'doi:10.1038/nature12345', ['10.1038/nature12345']),
        ('extract_pmc_ids_from_text', 'PMC1234567', ['1234567']),
        ('extract_clinical_trial_ids_from_text', 'NCT01234567', ['01234567']),
    ]
    
    for func_name, test_text, expected in individual_tests:
        try:
            func = globals()[func_name]
            result = func(test_text)
            if set(result) == set(expected):
                print(f"  ✓ {func_name}: PASSED")
            else:
                print(f"  ❌ {func_name}: FAILED")
                print(f"    Expected: {expected}")
                print(f"    Got: {result}")
                all_tests_passed = False
        except Exception as e:
            print(f"  ❌ {func_name} ERROR: {e}")
            all_tests_passed = False
    
    if all_tests_passed:
        print("\n✅ All enhanced publication pattern tests passed!")
        return True
    else:
        print("\n❌ Some enhanced publication pattern tests failed!")
        return False

if __name__ == "__main__":
    success = test_enhanced_publication_patterns()
    sys.exit(0 if success else 1)
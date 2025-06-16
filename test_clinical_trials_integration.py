#!/usr/bin/env python3
"""Test ClinicalTrials.gov integration functionality."""

import sys
from pathlib import Path

# Add project root to Python path
src_path = Path(__file__).resolve().parent
sys.path.append(str(src_path))

from src.etl.clinical_trials import ClinicalTrialsProcessor

def test_clinical_trials_processor_initialization():
    """Test ClinicalTrials processor initialization."""
    
    print("Testing ClinicalTrials processor initialization...")
    
    # Create a minimal config
    config = {
        'cache_dir': '/tmp/mediabase/cache',
        'batch_size': 100,
        'clinical_trials_cancer_only': True,
        'clinical_trials_max_results': 100,
        'clinical_trials_rate_limit': 1.0
    }
    
    try:
        # Initialize processor
        processor = ClinicalTrialsProcessor(config)
        
        # Test basic attributes
        assert hasattr(processor, 'api_base_url'), "Missing api_base_url attribute"
        assert hasattr(processor, 'rate_limit'), "Missing rate_limit attribute"
        assert hasattr(processor, 'cancer_only'), "Missing cancer_only attribute"
        
        assert processor.rate_limit == 1.0, "Incorrect rate limit setting"
        assert processor.cancer_only == True, "Incorrect cancer_only setting"
        assert processor.max_results == 100, "Incorrect max_results setting"
        
        print("✓ ClinicalTrials processor initialized successfully")
        return True
        
    except Exception as e:
        print(f"❌ ClinicalTrials processor initialization failed: {e}")
        return False

def test_clinical_trials_methods():
    """Test ClinicalTrials processor methods."""
    
    print("Testing ClinicalTrials processor methods...")
    
    config = {
        'cache_dir': '/tmp/mediabase/cache',
        'clinical_trials_cancer_only': True,
        'clinical_trials_rate_limit': 2.0  # Slower for testing
    }
    
    try:
        processor = ClinicalTrialsProcessor(config)
        
        # Test that required methods exist
        required_methods = [
            'search_trials_by_gene',
            'get_trials_for_genes', 
            'extract_publication_references',
            '_extract_trial_data',
            '_normalize_phase',
            '_is_recent_trial'
        ]
        
        for method_name in required_methods:
            assert hasattr(processor, method_name), f"Missing method: {method_name}"
            assert callable(getattr(processor, method_name)), f"Method {method_name} is not callable"
        
        print("✓ All required methods are present and callable")
        
        # Test phase normalization
        test_phases = [
            ('PHASE1', 'Phase 1'),
            ('PHASE2_PHASE3', 'Phase 2/3'),
            ('EARLY_PHASE1', 'Phase 0/1'),
            ('NOT_APPLICABLE', 'Not Applicable'),
            ('UNKNOWN', 'UNKNOWN')  # Should pass through unknown phases
        ]
        
        for input_phase, expected_output in test_phases:
            result = processor._normalize_phase(input_phase)
            assert result == expected_output, f"Phase normalization failed: {input_phase} -> {result}, expected {expected_output}"
        
        print("✓ Phase normalization working correctly")
        
        # Test recent trial detection
        recent_trial = {'start_date': '2022-01-01'}
        old_trial = {'start_date': '2010-01-01'}
        no_date_trial = {'start_date': ''}
        
        assert processor._is_recent_trial(recent_trial) == True, "Recent trial not detected"
        assert processor._is_recent_trial(old_trial) == False, "Old trial incorrectly marked as recent"
        assert processor._is_recent_trial(no_date_trial) == False, "Trial with no date incorrectly marked as recent"
        
        print("✓ Recent trial detection working correctly")
        
        # Test empty gene search (should not crash)
        empty_trials = processor.search_trials_by_gene("")
        assert isinstance(empty_trials, list), "Empty gene search should return list"
        
        print("✓ Empty gene search handled gracefully")
        
        # Test publication reference extraction with empty data
        empty_publications = processor.extract_publication_references({})
        assert isinstance(empty_publications, list), "Empty trial data should return list"
        assert len(empty_publications) == 0, "Empty trial data should return empty list"
        
        print("✓ Empty publication extraction handled gracefully")
        
        return True
        
    except Exception as e:
        print(f"❌ ClinicalTrials processor methods test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_clinical_trials_data_structures():
    """Test ClinicalTrials data structure handling."""
    
    print("Testing ClinicalTrials data structure handling...")
    
    config = {'cache_dir': '/tmp/mediabase/cache'}
    
    try:
        processor = ClinicalTrialsProcessor(config)
        
        # Test sample trial data extraction
        sample_study = {
            'protocolSection': {
                'identificationModule': {
                    'nctId': 'NCT12345678',
                    'briefTitle': 'Test Trial for EGFR',
                    'officialTitle': 'A Phase II Study of Test Drug in EGFR-positive Cancer'
                },
                'statusModule': {
                    'overallStatus': 'COMPLETED',
                    'startDateStruct': {'date': '2020-01-01'},
                    'completionDateStruct': {'date': '2022-12-31'}
                },
                'designModule': {
                    'phases': ['PHASE2']
                },
                'conditionsModule': {
                    'conditions': ['Non-small Cell Lung Cancer', 'EGFR Positive']
                },
                'armsInterventionsModule': {
                    'interventions': [
                        {
                            'type': 'Drug',
                            'name': 'Test Drug',
                            'description': 'Experimental EGFR inhibitor'
                        }
                    ]
                },
                'sponsorCollaboratorsModule': {
                    'leadSponsor': {
                        'name': 'Test Pharmaceutical'
                    }
                }
            }
        }
        
        # Test trial data extraction
        trial_data = processor._extract_trial_data(sample_study, 'EGFR')
        
        assert trial_data is not None, "Trial data extraction returned None"
        assert trial_data['nct_id'] == 'NCT12345678', "Incorrect NCT ID extraction"
        assert trial_data['gene_symbol'] == 'EGFR', "Incorrect gene symbol"
        assert trial_data['phase'] == 'Phase 2', "Incorrect phase extraction"
        assert trial_data['status'] == 'COMPLETED', "Incorrect status extraction"
        assert 'Non-small Cell Lung Cancer' in trial_data['conditions'], "Missing condition"
        assert len(trial_data['interventions']) == 1, "Incorrect intervention count"
        assert trial_data['lead_sponsor'] == 'Test Pharmaceutical', "Incorrect sponsor"
        
        print("✓ Trial data extraction working correctly")
        
        # Test publication reference structure
        sample_gene_trials = {
            'EGFR': [
                {
                    'nct_id': 'NCT12345678',
                    'title': 'Test Trial',
                    'phase': 'Phase 2',
                    'status': 'COMPLETED',
                    'conditions': ['Cancer'],
                    'publications': [
                        {
                            'pmid': '12345678',
                            'evidence_type': 'clinical_trial_publication',
                            'source_db': 'ClinicalTrials.gov',
                            'url': 'https://pubmed.ncbi.nlm.nih.gov/12345678/'
                        }
                    ]
                }
            ]
        }
        
        publications = processor.extract_publication_references(sample_gene_trials)
        
        assert len(publications) == 2, f"Expected 2 publications (1 PMID + 1 trial record), got {len(publications)}"
        
        # Check PMID publication
        pmid_pub = next((p for p in publications if p.get('pmid')), None)
        assert pmid_pub is not None, "PMID publication not found"
        assert pmid_pub['pmid'] == '12345678', "Incorrect PMID"
        assert pmid_pub['source_db'] == 'ClinicalTrials.gov', "Incorrect source database"
        assert pmid_pub['gene_symbol'] == 'EGFR', "Incorrect gene symbol in publication"
        
        # Check trial record
        trial_pub = next((p for p in publications if p.get('clinical_trial_id')), None)
        assert trial_pub is not None, "Trial record not found"
        assert trial_pub['clinical_trial_id'] == 'NCT12345678', "Incorrect trial ID"
        assert trial_pub['evidence_type'] == 'clinical_trial_record', "Incorrect evidence type"
        
        print("✓ Publication reference extraction working correctly")
        
        return True
        
    except Exception as e:
        print(f"❌ ClinicalTrials data structure test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_clinical_trials_api_integration():
    """Test ClinicalTrials API integration (without making real API calls)."""
    
    print("Testing ClinicalTrials API integration...")
    
    config = {
        'cache_dir': '/tmp/mediabase/cache',
        'clinical_trials_rate_limit': 1.0
    }
    
    try:
        processor = ClinicalTrialsProcessor(config)
        
        # Test API URL construction
        assert processor.api_base_url.startswith('https://'), "API base URL should use HTTPS"
        assert 'clinicaltrials.gov' in processor.api_base_url.lower(), "Should point to ClinicalTrials.gov"
        
        print("✓ API configuration is correct")
        
        # Test rate limiting attributes
        assert processor.rate_limit > 0, "Rate limit should be positive"
        assert hasattr(processor, 'api_requests_made'), "Should track API requests"
        assert hasattr(processor, 'last_request_time'), "Should track last request time"
        
        print("✓ Rate limiting attributes present")
        
        # Test search parameters construction
        # Note: We don't make actual API calls in this test
        gene_list = ['EGFR', 'TP53']
        
        # This should not make API calls but should set up the data structures
        result = processor.get_trials_for_genes([])  # Empty list
        assert isinstance(result, dict), "Should return dictionary"
        assert len(result) == 0, "Empty gene list should return empty result"
        
        print("✓ API integration methods handle empty input correctly")
        
        return True
        
    except Exception as e:
        print(f"❌ ClinicalTrials API integration test failed: {e}")
        return False

def run_all_clinical_trials_tests():
    """Run all ClinicalTrials integration tests."""
    
    print("🧪 Running ClinicalTrials.gov integration tests...\n")
    
    tests = [
        ("Processor Initialization", test_clinical_trials_processor_initialization),
        ("Processor Methods", test_clinical_trials_methods),
        ("Data Structures", test_clinical_trials_data_structures),
        ("API Integration", test_clinical_trials_api_integration),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        print(f"\n{'='*60}")
        print(f"Running: {test_name}")
        print('='*60)
        
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"❌ {test_name} encountered an error: {e}")
            results[test_name] = False
    
    # Summary
    print(f"\n{'='*60}")
    print("📊 CLINICAL TRIALS TESTS SUMMARY")
    print('='*60)
    
    passed = sum(1 for result in results.values() if result)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name:<30} {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL CLINICAL TRIALS INTEGRATION TESTS PASSED!")
        print("\n📈 ClinicalTrials.gov Integration Summary:")
        print("   • API configuration and rate limiting")
        print("   • Trial data extraction and processing")
        print("   • Publication reference extraction")
        print("   • Phase normalization and data validation")
        print("   • Integration with publications processor")
        return True
    else:
        print(f"\n❌ {total - passed} tests failed. Please review and fix issues.")
        return False

if __name__ == "__main__":
    success = run_all_clinical_trials_tests()
    sys.exit(0 if success else 1)
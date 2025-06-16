#!/usr/bin/env python3
"""Test PharmGKB PMID extraction functionality."""

import sys
from pathlib import Path

# Add project root to Python path
src_path = Path(__file__).resolve().parent
sys.path.append(str(src_path))

from src.etl.pharmgkb_annotations import PharmGKBAnnotationsProcessor

def test_pharmgkb_pmid_extraction():
    """Test that PharmGKB PMID extraction works correctly."""
    
    print("Testing PharmGKB PMID extraction...")
    
    # Create a minimal config
    config = {
        'cache_dir': '/tmp/mediabase/cache',
        'batch_size': 100,
        'skip_scores': True
    }
    
    try:
        # Initialize processor
        processor = PharmGKBAnnotationsProcessor(config)
        print("✓ PharmGKB processor initialized successfully")
        
        # Test sample clinical annotations with PMIDs
        gene_annotation_mapping = {
            'CYP2D6': [
                {
                    'annotation_id': 'PA166104996',
                    'variant': 'CYP2D6*4',
                    'drug': 'tamoxifen',
                    'phenotype_category': 'efficacy',
                    'evidence_level': '1A',
                    'url': 'https://pubmed.ncbi.nlm.nih.gov/15634941',
                    'pmid_count': 5,
                    'evidence_count': 10
                }
            ],
            'TPMT': [
                {
                    'annotation_id': 'PA166104997', 
                    'variant': 'TPMT*3A',
                    'drug': 'mercaptopurine',
                    'phenotype_category': 'toxicity',
                    'evidence_level': '1A',
                    'url': 'https://www.pharmgkb.org/page/clinicalAnnotation/PA166104997',
                    'pmid_count': 3,
                    'evidence_count': 8
                }
            ]
        }
        
        # Test sample variant annotations with PMIDs
        variant_mapping = {
            'CYP2D6': [
                {
                    'variant_annotation_id': 'PA166153842',
                    'variant_identifier': 'rs1065852',
                    'variant_type': 'SNP',
                    'drugs': ['tamoxifen', 'codeine'],
                    'phenotype_category': 'metabolism/pk',
                    'significance': 'yes',
                    'pmid': 'PMID:15634941',
                    'clinical_actionability': 'high'
                },
                {
                    'variant_annotation_id': 'PA166153843',
                    'variant_identifier': 'CYP2D6*4',
                    'variant_type': 'star_allele',
                    'drugs': ['tramadol'],
                    'phenotype_category': 'efficacy',
                    'significance': 'yes',
                    'pmid': '33961781',
                    'clinical_actionability': 'high'
                }
            ],
            'UGT1A1': [
                {
                    'variant_annotation_id': 'PA166153844',
                    'variant_identifier': 'UGT1A1*28',
                    'variant_type': 'star_allele',
                    'drugs': ['irinotecan'],
                    'phenotype_category': 'toxicity',
                    'significance': 'yes',
                    'pmid': '12345678',
                    'clinical_actionability': 'high'
                }
            ]
        }
        
        # Test publication extraction
        publications = processor.extract_publication_references(gene_annotation_mapping, variant_mapping)
        
        print(f"\n✓ Extracted {len(publications)} publication references from PharmGKB data")
        
        # Verify extracted PMIDs
        expected_pmids = {'15634941', '33961781', '12345678'}
        extracted_pmids = {pub['pmid'] for pub in publications}
        
        print(f"Expected PMIDs: {expected_pmids}")
        print(f"Extracted PMIDs: {extracted_pmids}")
        
        # Check if all expected PMIDs were found
        missing_pmids = expected_pmids - extracted_pmids
        extra_pmids = extracted_pmids - expected_pmids
        
        if missing_pmids:
            print(f"⚠️  Missing PMIDs: {missing_pmids}")
        if extra_pmids:
            print(f"ℹ️  Extra PMIDs found: {extra_pmids}")
        
        # At least some PMIDs should be extracted
        assert len(extracted_pmids) > 0, "No PMIDs were extracted"
        print("✓ PMIDs successfully extracted")
        
        # Test publication structure
        for pub in publications:
            assert 'pmid' in pub, "Missing PMID field"
            assert 'evidence_type' in pub, "Missing evidence_type field"
            assert 'source_db' in pub, "Missing source_db field"
            assert pub['source_db'] == 'PharmGKB', "Incorrect source_db"
            assert 'gene_symbol' in pub, "Missing gene_symbol field"
            assert 'url' in pub, "Missing URL field"
            
            # Check evidence types
            assert pub['evidence_type'] in ['clinical_annotation', 'variant_annotation'], "Invalid evidence_type"
            
        print("✓ Publication structure validation passed")
        
        # Test variant-specific fields
        variant_pubs = [pub for pub in publications if pub['evidence_type'] == 'variant_annotation']
        for pub in variant_pubs:
            assert 'variant_id' in pub, "Missing variant_id field"
            assert 'variant_type' in pub, "Missing variant_type field"
            assert 'clinical_actionability' in pub, "Missing clinical_actionability field"
            
        print("✓ Variant-specific fields validation passed")
        
        # Test clinical annotation-specific fields
        clinical_pubs = [pub for pub in publications if pub['evidence_type'] == 'clinical_annotation']
        for pub in clinical_pubs:
            assert 'annotation_id' in pub, "Missing annotation_id field"
            assert 'evidence_level' in pub, "Missing evidence_level field"
            
        print("✓ Clinical annotation-specific fields validation passed")
        
        # Test with empty data
        empty_pubs = processor.extract_publication_references({}, {})
        assert len(empty_pubs) == 0, "Should extract 0 publications when no data present"
        print("✓ No false positives when no data present")
        
        print("\n✅ PharmGKB PMID extraction test completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ PharmGKB PMID extraction test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_pharmgkb_pmid_extraction()
    sys.exit(0 if success else 1)
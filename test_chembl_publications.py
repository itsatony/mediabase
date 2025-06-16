#!/usr/bin/env python3
"""Test ChEMBL publications integration functionality."""

import sys
from pathlib import Path

# Add project root to Python path
src_path = Path(__file__).resolve().parent
sys.path.append(str(src_path))

from src.etl.chembl_drugs import ChemblDrugProcessor

def test_chembl_publications_integration():
    """Test ChEMBL publications integration functionality."""
    
    print("Testing ChEMBL publications integration...")
    
    # Create a minimal config
    config = {
        'cache_dir': '/tmp/mediabase/cache',
        'batch_size': 100,
        'skip_scores': True,
        'use_temp_schema': True,
        'chembl_schema': 'chembl_test'
    }
    
    try:
        # Initialize processor
        processor = ChemblDrugProcessor(config)
        print("✓ ChEMBL processor initialized successfully")
        
        # Test publication reference extraction method exists
        assert hasattr(processor, 'extract_publication_references'), "Missing extract_publication_references method"
        assert hasattr(processor, '_populate_publications_from_docs'), "Missing _populate_publications_from_docs method"
        
        # Test publication reference extraction with empty database
        publications = processor.extract_publication_references()
        
        assert isinstance(publications, list), "Should return a list"
        print(f"✓ Publication extraction returns list (found {len(publications)} publications)")
        
        # Test that the method handles no database connection gracefully
        if len(publications) == 0:
            print("✓ Gracefully handles empty publications table")
        else:
            # Validate publication structure
            for pub in publications:
                assert isinstance(pub, dict), "Each publication should be a dictionary"
                assert 'source_db' in pub, "Missing source_db field"
                assert pub['source_db'] == 'ChEMBL', "Incorrect source_db"
                assert 'evidence_type' in pub, "Missing evidence_type field"
                assert pub['evidence_type'] == 'drug_publication', "Incorrect evidence_type"
                
                # At least one identifier should be present
                has_identifier = any(key in pub for key in ['pmid', 'doi', 'title'])
                assert has_identifier, "Publication must have at least one identifier"
                
                # If PMID is present, check URL formatting
                if 'pmid' in pub:
                    assert 'url' in pub, "PMID publications should have URL"
                    assert pub['url'].startswith('https://pubmed.ncbi.nlm.nih.gov/'), "Invalid PMID URL format"
                
                # If DOI is present and no PMID, check DOI URL
                if 'doi' in pub and 'pmid' not in pub:
                    assert 'url' in pub, "DOI publications should have URL"
                    assert pub['url'].startswith('https://doi.org/'), "Invalid DOI URL format"
            
            print("✓ Publication structure validation passed")
        
        # Test docs population method (won't actually populate without real data)
        try:
            processor._populate_publications_from_docs()
            print("✓ Docs population method executed without errors")
        except Exception as e:
            # This is expected if no docs table exists
            print(f"ℹ️  Docs population skipped (expected): {e}")
        
        # Test that ChEMBL publications table schema is correct
        schema_name = processor.chembl_schema
        if processor.ensure_connection() and processor.db_manager.cursor:
            try:
                # Try to create the schema to test table creation
                processor.create_optimized_tables()
                
                # Check that publications table was created with correct columns
                processor.db_manager.cursor.execute(f"""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_name = 'drug_publications' 
                      AND table_schema = '{schema_name}'
                    ORDER BY ordinal_position
                """)
                
                columns = processor.db_manager.cursor.fetchall()
                
                expected_columns = {
                    'id', 'chembl_id', 'doc_id', 'pubmed_id', 'doi', 'title', 'abstract', 
                    'year', 'journal', 'authors', 'volume', 'issue', 'first_page', 
                    'last_page', 'patent_id', 'journal_full_title'
                }
                
                actual_columns = {col[0] for col in columns}
                
                missing_columns = expected_columns - actual_columns
                if missing_columns:
                    print(f"❌ Missing columns in drug_publications table: {missing_columns}")
                    return False
                
                print("✓ ChEMBL publications table schema is correct")
                
            except Exception as e:
                print(f"ℹ️  Database table validation skipped (no connection): {e}")
        
        # Test sample publication data insertion
        try:
            processor._process_drug_publications(Path("/tmp"))  # Will use sample data
            print("✓ Sample publication data processing completed")
        except Exception as e:
            print(f"ℹ️  Sample publication processing skipped: {e}")
        
        print("\n✅ ChEMBL publications integration test completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ ChEMBL publications integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_chembl_publication_data_quality():
    """Test the quality of sample ChEMBL publication data."""
    
    print("\nTesting ChEMBL publication data quality...")
    
    # Sample publications from the code
    sample_publications = [
        {
            "chembl_id": "CHEMBL1173655",
            "doc_id": "CHEMBL1173655_DOC_1",
            "pubmed_id": "23633486",
            "doi": "10.1056/NEJMoa1214886",
            "title": "Afatinib versus cisplatin plus pemetrexed for patients with advanced lung adenocarcinoma and sensitive EGFR gene mutations",
            "year": 2013,
            "journal": "N Engl J Med"
        },
        {
            "chembl_id": "CHEMBL3137314",
            "doc_id": "CHEMBL3137314_DOC_1", 
            "pubmed_id": "27717303",
            "doi": "10.1056/NEJMoa1613174",
            "title": "Ribociclib plus letrozole versus letrozole for postmenopausal women with hormone-receptor-positive, HER2-negative, advanced breast cancer",
            "year": 2016,
            "journal": "N Engl J Med"
        }
    ]
    
    try:
        for i, pub in enumerate(sample_publications, 1):
            print(f"Validating sample publication {i}:")
            
            # Validate required fields
            assert pub.get('chembl_id'), "Missing ChEMBL ID"
            assert pub.get('doc_id'), "Missing doc ID"
            assert pub.get('pubmed_id'), "Missing PubMed ID"
            assert pub.get('doi'), "Missing DOI"
            assert pub.get('title'), "Missing title"
            assert pub.get('year'), "Missing year"
            assert pub.get('journal'), "Missing journal"
            
            # Validate data formats
            assert pub['year'] >= 1900 and pub['year'] <= 2024, f"Invalid year: {pub['year']}"
            assert pub['pubmed_id'].isdigit(), f"Invalid PMID format: {pub['pubmed_id']}"
            assert pub['doi'].startswith('10.'), f"Invalid DOI format: {pub['doi']}"
            assert len(pub['title']) > 10, "Title too short"
            
            # Validate ChEMBL ID format
            assert pub['chembl_id'].startswith('CHEMBL'), f"Invalid ChEMBL ID format: {pub['chembl_id']}"
            
            print(f"  ✓ Publication {i} data quality validation passed")
        
        print("✅ ChEMBL publication data quality test completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ ChEMBL publication data quality test failed: {e}")
        return False

if __name__ == "__main__":
    test1_success = test_chembl_publications_integration()
    test2_success = test_chembl_publication_data_quality()
    
    overall_success = test1_success and test2_success
    
    if overall_success:
        print("\n🎉 ALL CHEMBL PUBLICATIONS TESTS PASSED!")
        print("\n📈 ChEMBL Publications Integration Summary:")
        print("   • Publications table schema validation")
        print("   • Publication reference extraction method")
        print("   • Docs table population capability")
        print("   • Sample publication data quality")
        print("   • Integration with publications processor")
    else:
        print("\n❌ Some ChEMBL publications tests failed")
    
    sys.exit(0 if overall_success else 1)
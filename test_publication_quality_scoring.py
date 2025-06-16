#!/usr/bin/env python3
"""Test publication quality scoring and citation metrics functionality."""

import sys
from pathlib import Path

# Add project root to Python path
src_path = Path(__file__).resolve().parent
sys.path.append(str(src_path))

from src.utils.publication_utils import (
    calculate_publication_impact_score, assess_publication_relevance,
    enhance_publication_with_metrics, rank_publications_by_relevance,
    get_journal_impact_estimates
)

def test_impact_score_calculation():
    """Test publication impact score calculation."""
    
    print("Testing publication impact score calculation...")
    
    # Test high-impact publication
    high_impact_pub = {
        'pmid': '12345678',
        'title': 'Breakthrough cancer therapy',
        'journal': 'Nature',
        'year': 2023,
        'abstract': 'This study presents a novel approach to cancer treatment with significant clinical implications.',
        'citation_count': 150,
        'evidence_type': 'clinical_trial'
    }
    
    score = calculate_publication_impact_score(high_impact_pub)
    print(f"  High-impact publication score: {score:.1f}")
    assert score > 60, f"High-impact publication should score >60, got {score}"
    
    # Test moderate publication
    moderate_pub = {
        'pmid': '87654321',
        'title': 'Gene expression analysis',
        'journal': 'PLoS One',
        'year': 2020,
        'abstract': 'Study of gene expression patterns.',
        'citation_count': 25,
        'evidence_type': 'experimental'
    }
    
    score = calculate_publication_impact_score(moderate_pub)
    print(f"  Moderate publication score: {score:.1f}")
    assert 20 <= score <= 80, f"Moderate publication should score 20-80, got {score}"
    
    # Test minimal publication
    minimal_pub = {
        'pmid': '11111111',
        'title': 'Small study',
        'year': 2010,
        'evidence_type': 'other'
    }
    
    score = calculate_publication_impact_score(minimal_pub)
    print(f"  Minimal publication score: {score:.1f}")
    assert score < 40, f"Minimal publication should score <40, got {score}"
    
    # Test empty publication
    empty_score = calculate_publication_impact_score({})
    assert empty_score == 0.0, "Empty publication should score 0"
    
    print("✓ Impact score calculation working correctly")
    return True

def test_relevance_assessment():
    """Test publication relevance assessment."""
    
    print("Testing publication relevance assessment...")
    
    # Test publication highly relevant to EGFR
    egfr_pub = {
        'pmid': '12345678',
        'title': 'EGFR mutations in lung cancer treatment',
        'abstract': 'This study examines EGFR mutations and their impact on treatment response in non-small cell lung cancer patients.',
        'evidence_type': 'clinical_trial',
        'source_db': 'ClinicalTrials.gov'
    }
    
    egfr_context = {
        'gene_symbol': 'EGFR',
        'diseases': ['lung cancer', 'non-small cell lung cancer'],
        'drugs': ['afatinib', 'erlotinib']
    }
    
    relevance = assess_publication_relevance(egfr_pub, egfr_context)
    print(f"  EGFR-relevant publication relevance: {relevance:.1f}")
    assert relevance > 60, f"Highly relevant publication should score >60, got {relevance}"
    
    # Test publication not relevant to EGFR
    unrelated_pub = {
        'pmid': '87654321',
        'title': 'Diabetes treatment outcomes',
        'abstract': 'Study of diabetes management strategies in elderly patients.',
        'evidence_type': 'clinical_trial'
    }
    
    relevance = assess_publication_relevance(unrelated_pub, egfr_context)
    print(f"  Unrelated publication relevance: {relevance:.1f}")
    assert relevance < 30, f"Unrelated publication should score <30, got {relevance}"
    
    # Test with partial relevance (gene in abstract only)
    partial_pub = {
        'pmid': '33333333',
        'title': 'Comprehensive cancer genomics',
        'abstract': 'Analysis includes multiple genes including EGFR, TP53, and KRAS in various cancer types.',
        'evidence_type': 'experimental'
    }
    
    relevance = assess_publication_relevance(partial_pub, egfr_context)
    print(f"  Partially relevant publication relevance: {relevance:.1f}")
    assert 20 <= relevance <= 60, f"Partially relevant publication should score 20-60, got {relevance}"
    
    print("✓ Relevance assessment working correctly")
    return True

def test_publication_enhancement():
    """Test publication enhancement with metrics."""
    
    print("Testing publication enhancement with metrics...")
    
    # Test high-quality publication enhancement
    nature_pub = {
        'pmid': '12345678',
        'title': 'Revolutionary cancer treatment',
        'journal': 'Nature',
        'year': 2023,
        'abstract': 'This groundbreaking study demonstrates significant improvements in cancer treatment outcomes.',
        'evidence_type': 'clinical_trial',
        'citation_count': 200
    }
    
    context = {
        'gene_symbol': 'TP53',
        'diseases': ['cancer'],
        'drugs': ['immunotherapy']
    }
    
    enhanced = enhance_publication_with_metrics(nature_pub, context)
    
    # Check that metrics were added
    assert 'impact_factor' in enhanced, "Should add impact factor for Nature"
    assert enhanced['impact_factor'] > 40, "Nature should have high impact factor"
    assert 'impact_score' in enhanced, "Should add impact score"
    assert 'relevance_score' in enhanced, "Should add relevance score"
    assert 'quality_indicators' in enhanced, "Should add quality indicators"
    assert 'quality_tier' in enhanced, "Should add quality tier"
    
    # Check quality indicators
    quality_indicators = enhanced['quality_indicators']
    assert 'high_impact_journal' in quality_indicators, "Should identify high impact journal"
    assert 'recent' in quality_indicators, "Should identify recent publication"
    assert 'clinical_evidence' in quality_indicators, "Should identify clinical evidence"
    assert 'highly_cited' in quality_indicators, "Should identify highly cited paper"
    
    # Check quality tier
    assert enhanced['quality_tier'] == 'exceptional', f"High-quality paper should be 'exceptional', got {enhanced['quality_tier']}"
    
    print(f"  Enhanced publication quality tier: {enhanced['quality_tier']}")
    print(f"  Quality indicators: {quality_indicators}")
    
    # Test lower quality publication
    low_quality_pub = {
        'pmid': '87654321',
        'title': 'Small preliminary study',
        'year': 2015,
        'evidence_type': 'other'
    }
    
    enhanced_low = enhance_publication_with_metrics(low_quality_pub)
    assert enhanced_low['quality_tier'] in ['minimal', 'basic'], f"Low-quality paper should be 'minimal' or 'basic', got {enhanced_low['quality_tier']}"
    
    print("✓ Publication enhancement working correctly")
    return True

def test_publication_ranking():
    """Test publication ranking by relevance."""
    
    print("Testing publication ranking by relevance...")
    
    # Create test publications with varying relevance and quality
    publications = [
        {
            'pmid': '11111111',
            'title': 'EGFR in cancer',
            'journal': 'Nature',
            'year': 2023,
            'abstract': 'EGFR mutations in lung cancer',
            'evidence_type': 'clinical_trial',
            'citation_count': 100
        },
        {
            'pmid': '22222222',
            'title': 'Unrelated diabetes study',
            'journal': 'Diabetes Journal',
            'year': 2022,
            'abstract': 'Diabetes treatment strategies',
            'evidence_type': 'clinical_trial',
            'citation_count': 50
        },
        {
            'pmid': '33333333',
            'title': 'Cancer genomics including EGFR',
            'journal': 'Science',
            'year': 2021,
            'abstract': 'Comprehensive analysis of cancer genes including EGFR',
            'evidence_type': 'experimental',
            'citation_count': 75
        },
        {
            'pmid': '44444444',
            'title': 'EGFR therapy resistance',
            'journal': 'Cell',
            'year': 2020,
            'abstract': 'Mechanisms of EGFR therapy resistance in cancer patients',
            'evidence_type': 'experimental',
            'citation_count': 120
        }
    ]
    
    context = {
        'gene_symbol': 'EGFR',
        'diseases': ['cancer', 'lung cancer'],
        'drugs': ['erlotinib']
    }
    
    ranked = rank_publications_by_relevance(publications, context)
    
    # Check that publications are ranked correctly
    assert len(ranked) == len(publications), "Should return all publications"
    
    # The most relevant should be EGFR-specific publications
    top_pub = ranked[0]
    assert 'egfr' in top_pub['title'].lower(), f"Top publication should be EGFR-related, got: {top_pub['title']}"
    
    # The least relevant should be the diabetes study
    last_pub = ranked[-1]
    assert 'diabetes' in last_pub['title'].lower(), f"Last publication should be diabetes study, got: {last_pub['title']}"
    
    # Check that all publications have been enhanced with metrics
    for pub in ranked:
        assert 'impact_score' in pub, "All publications should have impact score"
        assert 'relevance_score' in pub, "All publications should have relevance score"
        assert 'quality_tier' in pub, "All publications should have quality tier"
    
    print(f"  Publications ranked (top to bottom):")
    for i, pub in enumerate(ranked, 1):
        print(f"    {i}. {pub['title'][:50]}... (relevance: {pub.get('relevance_score', 0):.1f}, impact: {pub.get('impact_score', 0):.1f})")
    
    print("✓ Publication ranking working correctly")
    return True

def test_journal_impact_estimates():
    """Test journal impact factor estimates."""
    
    print("Testing journal impact factor estimates...")
    
    impact_factors = get_journal_impact_estimates()
    
    # Check that we have impact factors for major journals
    major_journals = ['nature', 'science', 'cell', 'nejm']
    for journal in major_journals:
        assert journal in impact_factors, f"Should have impact factor for {journal}"
        assert impact_factors[journal] > 10, f"Major journal {journal} should have high impact factor"
    
    # Check that Nature has the highest impact among the test set
    assert impact_factors['nature'] > 30, "Nature should have very high impact factor"
    assert impact_factors['nejm'] > 50, "NEJM should have very high impact factor"
    
    print(f"  Found impact factors for {len(impact_factors)} journals")
    print(f"  Sample: Nature={impact_factors['nature']}, Science={impact_factors['science']}")
    
    print("✓ Journal impact estimates working correctly")
    return True

def run_all_quality_scoring_tests():
    """Run all publication quality scoring tests."""
    
    print("🧪 Running publication quality scoring tests...\n")
    
    tests = [
        ("Impact Score Calculation", test_impact_score_calculation),
        ("Relevance Assessment", test_relevance_assessment),
        ("Publication Enhancement", test_publication_enhancement),
        ("Publication Ranking", test_publication_ranking),
        ("Journal Impact Estimates", test_journal_impact_estimates),
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
            import traceback
            traceback.print_exc()
            results[test_name] = False
    
    # Summary
    print(f"\n{'='*60}")
    print("📊 PUBLICATION QUALITY SCORING TESTS SUMMARY")
    print('='*60)
    
    passed = sum(1 for result in results.values() if result)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name:<30} {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL PUBLICATION QUALITY SCORING TESTS PASSED!")
        print("\n📈 Publication Quality Scoring Summary:")
        print("   • Impact score calculation with multiple factors")
        print("   • Relevance assessment based on context")
        print("   • Publication enhancement with metrics and quality tiers")
        print("   • Intelligent ranking by relevance and impact")
        print("   • Journal impact factor integration")
        print("   • Quality indicators and tier classification")
        return True
    else:
        print(f"\n❌ {total - passed} tests failed. Please review and fix issues.")
        return False

if __name__ == "__main__":
    success = run_all_quality_scoring_tests()
    sys.exit(0 if success else 1)
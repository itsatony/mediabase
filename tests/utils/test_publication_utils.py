"""Test publication utility functions."""

import pytest
from typing import List
from src.utils.publication_utils import (
    is_valid_pmid,
    extract_pmid_from_text,
    extract_pmids_from_text,
    format_pmid_url,
    format_publication_citation,
    merge_publication_references,
)
from src.etl.publications import Publication

@pytest.mark.parametrize("pmid,expected", [
    ("12345678", True),
    ("123", True),
    ("12345678901", False),  # Too long
    ("abc", False),          # Not numeric
    ("", False),             # Empty
    ("0", True),            # Single digit
])
def test_is_valid_pmid(pmid: str, expected: bool) -> None:
    """Test PMID validation."""
    assert is_valid_pmid(pmid) == expected

@pytest.mark.parametrize("text,expected", [
    ("PMID: 12345678", "12345678"),
    ("Found in PubMed:123456", "123456"),
    ("Reference [12345678]", "12345678"),
    ("See pubmed/12345678 for details", "12345678"),
    ("No PMID here", None),
    ("", None),
    ("PMID: invalid", None),
])
def test_extract_pmid_from_text(text: str, expected: str | None) -> None:
    """Test extracting single PMID from text."""
    assert extract_pmid_from_text(text) == expected

def test_extract_multiple_pmids() -> None:
    """Test extracting multiple PMIDs from text."""
    text = """
    First reference PMID:12345678
    Second in PubMed:87654321
    Third [11223344]
    Also at pubmed/99887766
    Invalid PMID: abc
    """
    expected = ["11223344", "12345678", "87654321", "99887766"]
    assert extract_pmids_from_text(text) == expected

def test_format_pmid_url() -> None:
    """Test formatting PMID as URL."""
    pmid = "12345678"
    expected = "https://pubmed.ncbi.nlm.nih.gov/12345678/"
    assert format_pmid_url(pmid) == expected
    assert format_pmid_url("invalid") == ""

def test_format_publication_citation() -> None:
    """Test formatting publication as citation."""
    pub: Publication = {
        "pmid": "12345678",
        "title": "Test Article",
        "journal": "Science",
        "year": 2023,
        "authors": ["Smith J", "Doe R", "Jones M"],
        "evidence_type": "experimental",
        "source_db": "pubmed"
    }
    expected = "Smith J, Doe R, Jones M. Test Article. Science, 2023. PMID: 12345678"
    assert format_publication_citation(pub) == expected

def test_format_publication_citation_many_authors() -> None:
    """Test citation formatting with many authors."""
    pub: Publication = {
        "pmid": "12345678",
        "title": "Test Article",
        "journal": "Nature",
        "year": 2023,
        "authors": ["Smith J", "Doe R", "Jones M", "Black K", "White L"],
        "evidence_type": "experimental",
        "source_db": "pubmed"
    }
    expected = "Smith J et al. Test Article. Nature, 2023. PMID: 12345678"
    assert format_publication_citation(pub) == expected

def test_merge_publication_references() -> None:
    """Test merging publication references."""
    pub1: Publication = {
        "pmid": "12345678",
        "title": "Test Article",
        "journal": "Science",
        "year": 2023,
        "authors": ["Smith J"],
        "evidence_type": "experimental",
        "source_db": "pubmed"
    }
    pub2: Publication = {
        "pmid": "12345678",
        "title": "Better Title",
        "abstract": "Test abstract",
        "doi": "10.1234/test",
        "evidence_type": "computational",
        "source_db": "pubmed"
    }
    merged = merge_publication_references(pub1, pub2)
    
    # Non-empty values from pub2 should override pub1
    assert merged["title"] == "Better Title"
    assert merged["journal"] == "Science"  # Kept from pub1
    assert merged["abstract"] == "Test abstract"  # Added from pub2
    assert merged["doi"] == "10.1234/test"  # Added from pub2
    assert merged["evidence_type"] == "computational"  # Updated from pub2

def test_merge_publication_references_empty_values() -> None:
    """Test merging with empty values."""
    pub1: Publication = {
        "pmid": "12345678",
        "title": "Test Article",
        "authors": ["Smith J"],
        "evidence_type": "experimental",
        "source_db": "pubmed"
    }
    pub2: Publication = {
        "pmid": "12345678",
        "title": "",  # Empty value
        "authors": [],  # Empty list
        "evidence_type": "experimental",
        "source_db": "pubmed"
    }
    merged = merge_publication_references(pub1, pub2)
    
    # Empty values from pub2 should not override pub1
    assert merged["title"] == "Test Article"
    assert merged["authors"] == ["Smith J"]

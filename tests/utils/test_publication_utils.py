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
    ("Found in PubMed:1234567", "1234567"),  # Fixed: requires 7-8 digits
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
    result = extract_pmids_from_text(text)
    expected = ["11223344", "12345678", "87654321", "99887766"]
    # Sort both since set() doesn't preserve order
    assert sorted(result) == sorted(expected)

def test_format_pmid_url() -> None:
    """Test formatting PMID as URL."""
    pmid = "12345678"
    expected = "https://pubmed.ncbi.nlm.nih.gov/12345678/"
    assert format_pmid_url(pmid) == expected
    # Function doesn't validate, it just formats - so invalid PMIDs still get formatted
    assert format_pmid_url("invalid") == "https://pubmed.ncbi.nlm.nih.gov/invalid/"

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
    # Format: "Authors et al. (Year). Title. Journal" (no PMID in citation)
    expected = "Smith J et al. (2023). Test Article. Science"
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
    # Format: "First author et al. (Year). Title. Journal"
    expected = "Smith J et al. (2023). Test Article. Nature"
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

    # Implementation: pub1 values are kept unless None, pub2 fills in missing fields
    assert merged["title"] == "Test Article"  # Kept from pub1 (not None)
    assert merged["journal"] == "Science"  # Kept from pub1
    assert merged["abstract"] == "Test abstract"  # Added from pub2 (was missing)
    assert merged["doi"] == "10.1234/test"  # Added from pub2 (was missing)
    assert merged["evidence_type"] == "experimental"  # Kept from pub1 (not None)

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

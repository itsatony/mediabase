"""Utilities for processing publication references."""

import re
import logging
from typing import List, Optional, Dict, Any, Set, Union, cast
from ..etl.publications import Publication

logger = logging.getLogger(__name__)

# Regular expressions for different PMID formats
PMID_PATTERNS = [
    # Standard format: PMID: 12345678
    re.compile(r'PMID:\s*(\d+)', re.IGNORECASE),
    # PubMed ID: 12345678
    re.compile(r'PubMed\s+ID:?\s*(\d+)', re.IGNORECASE),
    # PubMed:12345678
    re.compile(r'PubMed:?\s*(\d+)', re.IGNORECASE),
    # PMID=12345678
    re.compile(r'PMID\s*=\s*(\d+)', re.IGNORECASE),
    # Bare PMID in parentheses: (12345678)
    re.compile(r'\((\d{1,8})\)'),
    # URLs: /pubmed/12345678
    re.compile(r'/pubmed/(\d+)', re.IGNORECASE),
]

def extract_pmid_from_text(text: str) -> Optional[str]:
    """Extract a PMID from text if present.
    
    Args:
        text: Text that might contain a PMID
        
    Returns:
        Extracted PMID or None if not found
    """
    if not text:
        return None
        
    # Try all patterns
    for pattern in PMID_PATTERNS:
        match = pattern.search(text)
        if match:
            pmid = match.group(1).strip()
            if pmid.isdigit() and 1 <= len(pmid) <= 8:
                return pmid
                
    return None

def extract_pmids_from_text(text: str) -> List[str]:
    """Extract all PMIDs from text.
    
    Args:
        text: Text that might contain PMIDs
        
    Returns:
        List of extracted PMIDs (empty if none found)
    """
    if not text:
        return []
        
    pmids = []
    
    # Try all patterns
    for pattern in PMID_PATTERNS:
        matches = pattern.finditer(text)
        for match in matches:
            pmid = match.group(1).strip()
            if pmid.isdigit() and 1 <= len(pmid) <= 8 and pmid not in pmids:
                pmids.append(pmid)
                
    return pmids

def is_valid_pmid(pmid: str) -> bool:
    """Check if a string is a valid PMID.
    
    Args:
        pmid: String to check
        
    Returns:
        True if valid PMID, False otherwise
    """
    if not pmid:
        return False
        
    # PMIDs are 1-8 digit numbers
    return pmid.isdigit() and 1 <= len(pmid) <= 8

def format_pmid_url(pmid: str) -> str:
    """Format a PMID as a PubMed URL.
    
    Args:
        pmid: PubMed ID
        
    Returns:
        URL to PubMed page for the given PMID
    """
    if not is_valid_pmid(pmid):
        return ""
    return f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

def format_publication_citation(pub: Publication) -> str:
    """Format a publication reference as a citation.
    
    Args:
        pub: Publication reference
        
    Returns:
        str: Formatted citation
    """
    if not pub:
        return ""
        
    # Get author list, limited to first 3 with et al. if more
    authors = pub.get("authors", [])
    if authors and len(authors) > 3:
        author_text = f"{authors[0]} et al."
    elif authors:
        author_text = ", ".join(authors)
    else:
        author_text = "Unknown authors"
        
    title = pub.get("title", "Untitled")
    journal = pub.get("journal", "Unknown journal")
    year = pub.get("year", "")
    pmid = pub.get("pmid", "")
    
    citation = f"{author_text}. {title}. {journal}"
    if year:
        citation += f", {year}"
    if pmid:
        citation += f". PMID: {pmid}"
        
    return citation

def merge_publication_references(pub1: Publication, pub2: Publication) -> Publication:
    """Merge two publication references, preferring non-empty values.
    
    Args:
        pub1: First publication reference
        pub2: Second publication reference
        
    Returns:
        Publication: Merged publication reference
    """
    result: Dict[str, Any] = {}
    
    # Start with all fields from pub1
    for key, value in pub1.items():
        result[key] = value
    
    # Override with non-empty values from pub2
    for key, value in pub2.items():
        if value is not None and value != "" and value != [] and value != {}:
            result[key] = value
            
    # Ensure we have the required fields
    if "pmid" not in result:
        result["pmid"] = ""
    if "evidence_type" not in result:
        result["evidence_type"] = "unknown"
    if "source_db" not in result:
        result["source_db"] = "unknown"
        
    return cast(Publication, result)

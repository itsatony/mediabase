"""Utility functions for publication reference handling."""

import re
import logging
from typing import List, Optional, Dict, Any, Set, Union, cast
from ..etl.publications import Publication

logger = logging.getLogger(__name__)

# Regular expressions for finding PMIDs
PMID_PATTERNS = [
    r'PMID:\s*(\d+)',  # Standard PMID:12345678 format
    r'PubMed:\s*(\d+)',  # PubMed:12345678 format
    r'\[(\d{6,8})\]',  # [12345678] format
    r'pubmed/(\d{6,8})',  # pubmed/12345678 format
]

def is_valid_pmid(pmid: str) -> bool:
    """Validate PMID format.
    
    Args:
        pmid: PubMed ID to validate
        
    Returns:
        bool: True if valid PMID format
    """
    # PMIDs are 1-8 digit numbers
    return bool(re.match(r'^\d{1,8}$', pmid))

def extract_pmid_from_text(text: str) -> Optional[str]:
    """Extract single PMID from text.
    
    Args:
        text: Text to extract PMID from
        
    Returns:
        Optional[str]: First valid PMID found or None
    """
    if not text:
        return None
        
    # Try each pattern
    for pattern in PMID_PATTERNS:
        match = re.search(pattern, text)
        if match:
            pmid = match.group(1)
            if is_valid_pmid(pmid):
                return pmid
    return None

def extract_pmids_from_text(text: str) -> List[str]:
    """Extract all PMIDs from text.
    
    Args:
        text: Text to extract PMIDs from
        
    Returns:
        List[str]: List of valid PMIDs found
    """
    if not text:
        return []
        
    pmids: Set[str] = set()
    
    # Try each pattern
    for pattern in PMID_PATTERNS:
        matches = re.finditer(pattern, text)
        for match in matches:
            pmid = match.group(1)
            if is_valid_pmid(pmid):
                pmids.add(pmid)
                
    return sorted(list(pmids))

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

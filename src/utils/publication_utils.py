"""Utility functions for publication reference handling."""
import re
import logging
from typing import List, Optional, Dict, Any, Set, Union, cast

from .publication_types import Publication

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
    if not text or not isinstance(text, str):
        return None
        
    # Try each pattern
    for pattern in PMID_PATTERNS:
        match = re.search(pattern, text)
        if match and match.group(1):
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
    if not text or not isinstance(text, str):
        return []
        
    pmids: Set[str] = set()
    
    # Try each pattern
    for pattern in PMID_PATTERNS:
        matches = re.finditer(pattern, text)
        for match in matches:
            if match and match.group(1):
                pmid = match.group(1)
                if is_valid_pmid(pmid):
                    pmids.add(pmid)
    
    return list(pmids)

def format_pmid_url(pmid: str) -> str:
    """Format a PMID as a URL to PubMed.
    
    Args:
        pmid: PubMed ID
        
    Returns:
        str: URL to the publication on PubMed
    """
    return f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

def format_publication_citation(pub: Publication) -> str:
    """Format a publication as a citation string.
    
    Args:
        pub: Publication data
        
    Returns:
        str: Formatted citation
    """
    if not pub:
        return ""
        
    # Extract publication components with safe access
    authors_str = ""
    if pub.get('authors'):
        # Only access 'authors' if it exists and is not None
        authors = pub.get('authors', [])
        if authors and len(authors) > 2:
            authors_str = f"{authors[0]} et al."
        elif authors:
            authors_str = ", ".join(authors)
    
    # Safely access year
    year = pub.get('year')
    year_str = f"({year})" if year is not None else ""
    
    # Safely access title and journal
    title = pub.get('title', 'No title')
    journal = pub.get('journal', '')
    
    # Format citation
    if authors_str and year_str:
        return f"{authors_str} {year_str}. {title}. {journal}"
    elif authors_str:
        return f"{authors_str}. {title}. {journal}"
    else:
        return f"{title}. {journal} {year_str}"

def merge_publication_references(pub1: Publication, pub2: Publication) -> Publication:
    """Merge two publication references, preferring non-None values.
    
    Args:
        pub1: First publication reference
        pub2: Second publication reference
        
    Returns:
        Publication: Merged publication reference
    """
    if not pub1:
        return pub2
    if not pub2:
        return pub1
        
    # Ensure same PMID
    if pub1.get('pmid') != pub2.get('pmid'):
        return pub1  # Don't merge different publications
    
    # Create merged publication
    merged: Publication = {}
    
    # Copy all fields from pub1
    for key, value in pub1.items():
        merged[key] = value
    
    # Merge with pub2, preferring non-None values
    for key, value in pub2.items():
        if value is not None and (key not in merged or merged.get(key) is None):
            merged[key] = value
    
    return merged

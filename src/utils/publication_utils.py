"""Utility functions for working with publication references."""

import re
import logging
from typing import Optional, Dict, List, Any, Set, Union, cast
from ..etl.publications import Publication

logger = logging.getLogger(__name__)

def extract_pmid_from_text(text: str) -> Optional[str]:
    """Extract PubMed ID from text.
    
    Args:
        text: Text containing a PMID reference (PMID:12345678, PMID 12345678, etc.)
        
    Returns:
        str: Extracted PMID or None if not found
    """
    if not text:
        return None
        
    # Common patterns for PMID references
    patterns = [
        r'PMID:(\d+)',           # PMID:12345678
        r'PMID\s+(\d+)',         # PMID 12345678
        r'pubmed/(\d+)',         # pubmed/12345678
        r'PubMed ID:\s*(\d+)',   # PubMed ID: 12345678
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
            
    return None

def extract_pmids_from_text(text: str) -> Set[str]:
    """Extract all PubMed IDs from text.
    
    Args:
        text: Text containing PMID references
        
    Returns:
        Set[str]: All extracted PMIDs
    """
    if not text:
        return set()
        
    # Common patterns for PMID references
    patterns = [
        r'PMID:(\d+)',           # PMID:12345678
        r'PMID\s+(\d+)',         # PMID 12345678
        r'pubmed/(\d+)',         # pubmed/12345678
        r'PubMed ID:\s*(\d+)',   # PubMed ID: 12345678
    ]
    
    pmids = set()
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        pmids.update(matches)
            
    return pmids

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

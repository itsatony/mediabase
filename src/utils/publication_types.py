"""Type definitions for publication data structures."""

from typing import Dict, List, Optional, TypedDict, Any

class Publication(TypedDict, total=False):
    """Publication reference type definition."""
    pmid: str
    evidence_type: str
    source_db: str
    title: Optional[str]
    abstract: Optional[str]
    year: Optional[int]
    journal: Optional[str]
    authors: Optional[List[str]]
    citation_count: Optional[int]
    doi: Optional[str]
    url: Optional[str]

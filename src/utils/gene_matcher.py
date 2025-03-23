"""Gene symbol matching utilities for MediaBase.

This module provides functions for matching gene symbols between different
data sources with support for case-insensitive matching to handle
differences in gene symbol representations.
"""

import logging
import re
from typing import Dict, List, Set, Tuple, Optional, Union, Any

logger = logging.getLogger(__name__)

def normalize_gene_symbol(symbol: str) -> str:
    """Normalize a gene symbol for consistent matching.
    
    Args:
        symbol: Raw gene symbol string
        
    Returns:
        Normalized gene symbol
    """
    if not symbol:
        return ""
    
    # Convert to uppercase and remove whitespace
    normalized = symbol.upper().strip()
    
    # Remove common version suffixes (e.g., -1, .1)
    normalized = re.sub(r'[-\.][0-9]+$', '', normalized)
    
    return normalized

def match_exact(symbol: str, targets: Union[List[str], Set[str], Dict[str, Any]]) -> Optional[str]:
    """Find exact (case-insensitive) match for a gene symbol.
    
    Args:
        symbol: Gene symbol to match
        targets: List, set, or dict keys of potential target gene symbols
        
    Returns:
        Matched symbol from targets or None if no match
    """
    if not symbol or not targets:
        return None
        
    normalized = normalize_gene_symbol(symbol)
    if not normalized:
        return None
    
    # For dict, check against keys
    if isinstance(targets, dict):
        for target in targets.keys():
            if normalize_gene_symbol(target) == normalized:
                return target
    # For list or set
    else:
        for target in targets:
            if normalize_gene_symbol(target) == normalized:
                return target
    
    return None

def build_normalized_map(genes: Union[List[str], Set[str]]) -> Dict[str, str]:
    """Build a map of normalized gene symbols to original symbols.
    
    This is useful for bulk matching to avoid repeated normalization.
    
    Args:
        genes: List or set of gene symbols
        
    Returns:
        Dictionary mapping normalized gene symbols to original symbols
    """
    normalized_map = {}
    for gene in genes:
        if gene:
            normalized = normalize_gene_symbol(gene)
            if normalized and normalized not in normalized_map:
                normalized_map[normalized] = gene
    
    return normalized_map

def match_genes_bulk(
    query_genes: List[str],
    target_genes: Union[List[str], Set[str], Dict[str, Any]],
    use_fuzzy: bool = False,  # Parameter kept for backward compatibility but ignored
    threshold: int = 2  # Parameter kept for backward compatibility but ignored
) -> Dict[str, str]:
    """Match gene symbols in bulk with case-insensitive matching.
    
    Args:
        query_genes: List of gene symbols to match
        target_genes: List, set, or dict keys of potential target gene symbols
        use_fuzzy: Ignored (kept for backward compatibility)
        threshold: Ignored (kept for backward compatibility)
        
    Returns:
        Dictionary mapping query genes to matched target genes
    """
    if not query_genes or not target_genes:
        return {}
    
    # Build normalized map of target genes for faster lookups
    if isinstance(target_genes, dict):
        target_list = list(target_genes.keys())
    else:
        target_list = list(target_genes)
    
    target_norm_map = build_normalized_map(target_list)
    
    # Match each query gene
    matches = {}
    for query in query_genes:
        if not query:
            continue
            
        # Only use exact case-insensitive matching
        norm_query = normalize_gene_symbol(query)
        if norm_query in target_norm_map:
            matches[query] = target_norm_map[norm_query]
    
    return matches

def get_gene_match_stats(
    query_genes: List[str],
    matched_genes: Dict[str, str]
) -> Dict[str, Any]:
    """Calculate gene matching statistics.
    
    Args:
        query_genes: Original list of gene symbols to match
        matched_genes: Dictionary of matched gene symbols
        
    Returns:
        Dictionary with matching statistics
    """
    total = len([g for g in query_genes if g])
    matched = len(matched_genes)
    
    return {
        'total_genes': total,
        'matched_genes': matched,
        'match_rate': round(matched / max(1, total) * 100, 2),
        'unmatched_genes': total - matched
    }

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
    """Normalize gene symbol for consistent matching.
    
    Args:
        symbol: Gene symbol to normalize
        
    Returns:
        Normalized gene symbol
    """
    if not symbol or not isinstance(symbol, str):
        return ""
        
    # Convert to uppercase
    normalized = symbol.upper()
    
    # Remove common prefixes like "HUMAN_" that might appear in SwissProt IDs
    if "_" in normalized:
        parts = normalized.split("_")
        if len(parts) == 2 and parts[1] in ["HUMAN", "MOUSE"]:
            normalized = parts[0]
            
    # Remove spaces, hyphens and underscores
    normalized = re.sub(r'[\s\-_]', '', normalized)
    
    # Remove version numbers (e.g., "GENE.1" -> "GENE")
    normalized = re.sub(r'\.\d+$', '', normalized)
    
    # Handle specific inconsistencies in gene naming
    if normalized.startswith('HLA') and len(normalized) > 3:
        # HLA genes often have inconsistent formatting (HLA-DRA vs HLADRA)
        if normalized[3] != 'D':
            normalized = f"HLA{normalized[3:]}"
    
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

def match_genes_bulk(query_genes: List[str], target_genes: List[str], use_fuzzy: bool = False) -> Dict[str, str]:
    """Match a list of query genes to target genes, with optional fuzzy matching.
    
    Args:
        query_genes: List of gene symbols to match
        target_genes: List of reference gene symbols
        use_fuzzy: Whether to use fuzzy matching for unmatched genes
        
    Returns:
        Dictionary mapping query genes to matched target genes
    """
    # Create normalized target gene mapping
    normalized_targets = {normalize_gene_symbol(g): g for g in target_genes if g}
    
    # Match genes using direct and normalized comparison
    matches = {}
    unmatched = []
    
    for query in query_genes:
        if not query:
            continue
            
        # Try direct match first
        if query in target_genes:
            matches[query] = query
            continue
            
        # Try normalized match
        norm_query = normalize_gene_symbol(query)
        if norm_query in normalized_targets:
            matches[query] = normalized_targets[norm_query]
            continue
            
        # If no match found, add to unmatched list
        unmatched.append(query)
    
    # If fuzzy matching is enabled, try to match remaining genes
    if use_fuzzy and unmatched:
        # Maximum acceptable Levenshtein distance (adjust based on gene symbol length)
        max_distance = 2
        
        for query in unmatched:
            norm_query = normalize_gene_symbol(query)
            
            # Skip very short gene symbols for fuzzy matching to prevent false positives
            if len(norm_query) < 3:
                continue
                
            # Find best fuzzy match
            best_match = None
            best_distance = max_distance + 1
            
            for target_norm, target in normalized_targets.items():
                # Skip targets that have very different lengths
                if abs(len(target_norm) - len(norm_query)) > max_distance:
                    continue
                    
                # Calculate Levenshtein distance
                distance = levenshtein_distance(norm_query, target_norm)
                
                # Check if this is the best match so far
                if distance <= max_distance and distance < best_distance:
                    best_match = target
                    best_distance = distance
            
            # If we found a match, add it
            if best_match:
                matches[query] = best_match
    
    return matches

def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein edit distance between two strings.
    
    Args:
        s1: First string
        s2: Second string
        
    Returns:
        Edit distance as an integer
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    
    if not s2:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            # Calculate insertions, deletions and substitutions
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            
            # Get minimum of the three operations
            current_row.append(min(insertions, deletions, substitutions))
        
        previous_row = current_row
    
    return previous_row[-1]

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

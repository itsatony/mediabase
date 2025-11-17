"""ETL Module Dependency and Sequence Configuration.

This module defines the correct execution order and dependencies for the ETL pipeline
to ensure data is processed in the proper sequence.
"""

from typing import Dict, List, Set, Optional, Any

# Module dependency graph
# Maps each module to its prerequisites
MODULE_DEPENDENCIES = {
    'transcript': [],  # No prerequisites
    'id_enrichment': ['transcript'],  # Needs transcript data
    'go_terms': ['transcript'],  # Needs transcript data
    'products': ['transcript', 'id_enrichment'],  # Needs transcript and ID data
    'pathways': ['transcript', 'id_enrichment'],  # Needs transcript and ID data
    'pubtator': ['transcript', 'id_enrichment'],  # Needs transcript and NCBI Gene ID mappings
    'opentargets': ['transcript', 'id_enrichment'],  # Needs transcript and Ensembl Gene ID mappings
    'drugs': ['transcript', 'id_enrichment', 'go_terms', 'pathways', 'products'],  # Needs many dependencies
    'publications': ['transcript', 'go_terms', 'products', 'pathways', 'drugs'],  # Needs all sources of PMIDs
    'evidence_scoring': ['transcript', 'drugs', 'pathways', 'go_terms', 'publications'],  # Needs all evidence sources
    'pharmgkb_annotations': ['transcript', 'id_enrichment'],  # Needs transcript and ID data
    'chembl_drugs': ['transcript', 'id_enrichment'],  # Needs transcript and ID data
    'drug_repurposing_hub': ['transcript']  # Needs transcript data
}

# Default execution sequence (correct order)
DEFAULT_SEQUENCE = [
    'transcript',             # Always first - loads base data
    'id_enrichment',          # Second - adds cross-database identifiers
    'go_terms',               # Third - adds GO terms and molecular functions
    'products',               # Fourth - classifies gene products
    'pathways',               # Fifth - adds pathway data
    'pubtator',               # Sixth - adds gene-publication associations from PubTator Central
    'opentargets',            # Seventh - adds disease-gene associations and drug-target evidence
    'drugs',                  # Eighth - adds drug interaction data
    'pharmgkb_annotations',   # Ninth - adds pharmacogenomic annotations
    'chembl_drugs',           # Tenth - adds ChEMBL drug data
    'drug_repurposing_hub',   # Eleventh - adds drug repurposing data
    'publications',           # Twelfth - enriches publication references from all modules
    'evidence_scoring'        # Last - generates comprehensive evidence scores
]

def validate_sequence(modules: List[str]) -> bool:
    """Validate that a module sequence respects all dependencies.
    
    Args:
        modules: List of module names in proposed execution order
        
    Returns:
        True if the sequence is valid, False otherwise
    """
    executed: Set[str] = set()
    
    for module in modules:
        # Skip unknown modules
        if module not in MODULE_DEPENDENCIES:
            continue
            
        # Check if all dependencies have been executed
        for dependency in MODULE_DEPENDENCIES[module]:
            if dependency not in executed:
                return False
                
        executed.add(module)
        
    return True

def get_optimal_sequence(requested_modules: Optional[List[str]] = None) -> List[str]:
    """Get optimal execution sequence for requested modules.
    
    Args:
        requested_modules: List of requested modules or None for all modules
        
    Returns:
        List of modules in correct execution order
    """
    if not requested_modules:
        return DEFAULT_SEQUENCE
    
    # Filter to only known modules
    valid_modules = [m for m in requested_modules if m in MODULE_DEPENDENCIES]
    
    # Get all dependencies recursively
    all_modules = set(valid_modules)
    for module in valid_modules:
        _add_dependencies_recursive(module, all_modules)
    
    # Return modules in correct order
    return [m for m in DEFAULT_SEQUENCE if m in all_modules]

def _add_dependencies_recursive(module: str, all_modules: Set[str]) -> None:
    """Add all recursive dependencies of a module to the set.
    
    Args:
        module: Module to add dependencies for
        all_modules: Set to add dependencies to
    """
    if module not in MODULE_DEPENDENCIES:
        return
        
    for dependency in MODULE_DEPENDENCIES[module]:
        all_modules.add(dependency)
        _add_dependencies_recursive(dependency, all_modules)

"""
Test fixtures for MEDIABASE v0.6.0

This package contains expected query results and validation data for
cancer-specific query guides.
"""

from .expected_query_results import (
    # HER2+ Breast Cancer
    HER2_SIGNATURE_GENES,
    HER2_EXPECTED_DRUGS,
    HER2_TREATMENT_RECOMMENDATIONS,

    # Triple-Negative Breast Cancer (TNBC)
    TNBC_SIGNATURE_GENES,
    TNBC_EXPECTED_DRUGS,
    TNBC_TREATMENT_RECOMMENDATIONS,

    # Lung Adenocarcinoma (EGFR-Mutant)
    LUAD_SIGNATURE_GENES,
    LUAD_EXPECTED_DRUGS,
    LUAD_TREATMENT_RECOMMENDATIONS,

    # Colorectal Cancer (CRC)
    CRC_SIGNATURE_GENES,
    CRC_EXPECTED_DRUGS,
    CRC_TREATMENT_RECOMMENDATIONS,

    # Utility Functions
    get_expected_genes,
    get_expected_drugs,
    get_treatment_recommendations,
    validate_fold_change,
)

__all__ = [
    # HER2+
    "HER2_SIGNATURE_GENES",
    "HER2_EXPECTED_DRUGS",
    "HER2_TREATMENT_RECOMMENDATIONS",

    # TNBC
    "TNBC_SIGNATURE_GENES",
    "TNBC_EXPECTED_DRUGS",
    "TNBC_TREATMENT_RECOMMENDATIONS",

    # LUAD
    "LUAD_SIGNATURE_GENES",
    "LUAD_EXPECTED_DRUGS",
    "LUAD_TREATMENT_RECOMMENDATIONS",

    # CRC
    "CRC_SIGNATURE_GENES",
    "CRC_EXPECTED_DRUGS",
    "CRC_TREATMENT_RECOMMENDATIONS",

    # Utilities
    "get_expected_genes",
    "get_expected_drugs",
    "get_treatment_recommendations",
    "validate_fold_change",
]

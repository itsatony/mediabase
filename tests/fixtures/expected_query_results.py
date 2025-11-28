"""
Expected Query Results for Cancer-Specific Query Guides

This fixture file contains expected fold-change values and query results
based on the actual synthetic patient data in the mbase database.

Version: v0.6.0
Last Updated: 2025-11-28
"""

from typing import Dict, List, Any

# ============================================================================
# HER2+ BREAST CANCER (patient_synthetic_her2)
# ============================================================================

HER2_SIGNATURE_GENES = {
    # Target Genes - HER2 Amplification
    "ERBB2": {
        "expected_fc": 5.51,
        "min_fc": 4.0,
        "max_fc": 6.0,
        "interpretation": "HER2+ CONFIRMED - Anti-HER2 Therapy Eligible",
        "clinical_significance": "Primary therapeutic target",
    },
    "GRB7": {
        "expected_fc": 4.54,
        "min_fc": 3.0,
        "max_fc": 6.0,
        "interpretation": "Co-amplified (17q12 amplicon validation)",
        "clinical_significance": "Validates ERBB2 amplification event",
    },
    "PNMT": {
        "expected_fc": 3.95,
        "min_fc": 2.5,
        "max_fc": 5.0,
        "interpretation": "Co-amplified (17q12 amplicon)",
        "clinical_significance": "Amplicon validation marker",
    },
    "PGAP3": {
        "expected_fc": 3.63,
        "min_fc": 2.5,
        "max_fc": 5.0,
        "interpretation": "Co-amplified (17q12 amplicon validation)",
        "clinical_significance": "Amplicon validation marker",
    },

    # Resistance Mechanisms - PI3K/AKT/mTOR Pathway
    "PIK3CA": {
        "expected_fc": 2.51,
        "min_fc": 2.0,
        "max_fc": 4.0,
        "interpretation": "PI3K INHIBITOR TARGET (Alpelisib)",
        "clinical_significance": "Resistance mechanism, consider PI3K inhibitor",
    },
    "AKT1": {
        "expected_fc": 1.65,
        "min_fc": 1.5,
        "max_fc": 3.0,
        "interpretation": "AKT ACTIVATION (downstream of PI3K)",
        "clinical_significance": "Pathway activation marker",
    },
    "MTOR": {
        "expected_fc": 1.88,
        "min_fc": 1.5,
        "max_fc": 3.0,
        "interpretation": "mTOR ACTIVATION (consider Everolimus)",
        "clinical_significance": "Potential mTOR inhibitor target",
    },
    "PTEN": {
        "expected_fc": 0.80,
        "min_fc": 0.5,
        "max_fc": 1.0,
        "interpretation": "PTEN LOSS (mTOR pathway activated)",
        "clinical_significance": "Alternative resistance mechanism",
    },

    # CDK4/6 Inhibitor Eligibility (Hormone Receptor)
    "ESR1": {
        "expected_fc": 1.76,
        "min_fc": 1.5,
        "max_fc": 3.0,
        "interpretation": "ER POSITIVE (hormone receptor positive)",
        "clinical_significance": "HER2+/HR+ subtype, consider endocrine therapy",
    },
    "PGR": {
        "expected_fc": 1.53,
        "min_fc": 1.3,
        "max_fc": 3.0,
        "interpretation": "PR POSITIVE (hormone receptor positive)",
        "clinical_significance": "HER2+/HR+ subtype",
    },
    "CCND1": {
        "expected_fc": 3.66,
        "min_fc": 3.0,
        "max_fc": 5.0,
        "interpretation": "CDK4/6 INHIBITOR TARGET (Palbociclib, Abemaciclib)",
        "clinical_significance": "Strong CDK4/6 inhibitor candidate",
    },
    "CDK4": {
        "expected_fc": 2.73,
        "min_fc": 2.0,
        "max_fc": 4.0,
        "interpretation": "CDK4/6 INHIBITOR TARGET",
        "clinical_significance": "CDK4/6 pathway activation",
    },
}

HER2_EXPECTED_DRUGS = [
    {
        "drug_name": "TRASTUZUMAB",
        "mechanism": "HER2/ERBB2 monoclonal antibody",
        "indication": "HER2+ breast cancer",
        "is_approved": True,
        "max_phase": 4,
    },
    {
        "drug_name": "PERTUZUMAB",
        "mechanism": "HER2 dimerization inhibitor",
        "indication": "HER2+ breast cancer",
        "is_approved": True,
        "max_phase": 4,
    },
    {
        "drug_name": "LAPATINIB",
        "mechanism": "EGFR/HER2 dual TKI",
        "indication": "HER2+ breast cancer",
        "is_approved": True,
        "max_phase": 4,
    },
    {
        "drug_name": "NERATINIB",
        "mechanism": "Pan-HER irreversible TKI",
        "indication": "HER2+ breast cancer (adjuvant)",
        "is_approved": True,
        "max_phase": 4,
    },
]

HER2_TREATMENT_RECOMMENDATIONS = {
    "first_line": "TRASTUZUMAB + PERTUZUMAB + PALBOCICLIB (HER2+/HR+, CCND1 amplified)",
    "second_line": "T-DM1 (Trastuzumab emtansine) for 2nd line",
    "third_line": "T-DXd (Trastuzumab deruxtecan) for 3rd line",
    "resistance_strategy": "PI3K inhibitor (Alpelisib) + anti-HER2 therapy (PIK3CA activated)",
    "evidence_level": "FDA Approved",
}

# ============================================================================
# TRIPLE-NEGATIVE BREAST CANCER (patient_synthetic_tnbc)
# ============================================================================

TNBC_SIGNATURE_GENES = {
    # Triple-Negative Status Confirmation
    "ESR1": {
        "expected_fc": 0.15,
        "min_fc": 0.0,
        "max_fc": 0.5,
        "interpretation": "ER NEGATIVE (triple-negative confirmed)",
        "clinical_significance": "ER-negative status confirmed",
    },
    "PGR": {
        "expected_fc": 0.28,
        "min_fc": 0.0,
        "max_fc": 0.5,
        "interpretation": "PR NEGATIVE (triple-negative confirmed)",
        "clinical_significance": "PR-negative status confirmed",
    },
    "ERBB2": {
        "expected_fc": 0.81,
        "min_fc": 0.5,
        "max_fc": 1.5,
        "interpretation": "HER2 NEGATIVE (triple-negative confirmed)",
        "clinical_significance": "HER2-negative status confirmed",
    },

    # Basal-like Subtype Markers
    "KRT5": {
        "expected_fc": 4.28,
        "min_fc": 3.0,
        "max_fc": 6.0,
        "interpretation": "BASAL-LIKE MARKER (basal cytokeratin)",
        "clinical_significance": "Basal-like TNBC subtype",
    },
    "KRT14": {
        "expected_fc": 4.10,
        "min_fc": 3.0,
        "max_fc": 6.0,
        "interpretation": "BASAL-LIKE MARKER (basal cytokeratin)",
        "clinical_significance": "Basal-like TNBC subtype",
    },
    "EGFR": {
        "expected_fc": 2.84,
        "min_fc": 2.0,
        "max_fc": 4.0,
        "interpretation": "EGFR OVEREXPRESSION (basal-like)",
        "clinical_significance": "EGFR inhibitor candidate (investigational)",
    },

    # Immune Checkpoint Eligibility
    "CD274": {
        "expected_fc": 2.23,
        "min_fc": 1.5,
        "max_fc": 4.0,
        "interpretation": "PD-L1 POSITIVE (immune checkpoint inhibitor eligible)",
        "clinical_significance": "Pembrolizumab eligible (PD-L1+)",
    },
    "PDCD1": {
        "expected_fc": 1.65,
        "min_fc": 1.0,
        "max_fc": 3.0,
        "interpretation": "PD-1 EXPRESSION (immune checkpoint marker)",
        "clinical_significance": "Immune checkpoint pathway active",
    },

    # PARP Inhibitor Eligibility
    "BRCA1": {
        "expected_fc": 0.75,
        "min_fc": 0.5,
        "max_fc": 1.0,
        "interpretation": "BRCA1 DEFICIENCY MARKER",
        "clinical_significance": "Potential PARP inhibitor candidate (confirm with DNA sequencing)",
    },
    "TP53": {
        "expected_fc": 0.26,
        "min_fc": 0.0,
        "max_fc": 0.5,
        "interpretation": "TP53 LOSS (tumor suppressor loss)",
        "clinical_significance": "Common in TNBC, no specific therapy",
    },
}

TNBC_EXPECTED_DRUGS = [
    {
        "drug_name": "PEMBROLIZUMAB",
        "mechanism": "PD-1 immune checkpoint inhibitor",
        "indication": "PD-L1+ TNBC (first-line)",
        "is_approved": True,
        "max_phase": 4,
    },
    {
        "drug_name": "OLAPARIB",
        "mechanism": "PARP inhibitor",
        "indication": "BRCA-mutant TNBC",
        "is_approved": True,
        "max_phase": 4,
    },
    {
        "drug_name": "TALAZOPARIB",
        "mechanism": "PARP inhibitor",
        "indication": "BRCA-mutant TNBC",
        "is_approved": True,
        "max_phase": 4,
    },
]

TNBC_TREATMENT_RECOMMENDATIONS = {
    "first_line": "PEMBROLIZUMAB + CHEMOTHERAPY (PD-L1+ confirmed, CPS ≥10)",
    "second_line": "OLAPARIB or TALAZOPARIB (if BRCA1/2 mutation confirmed by DNA sequencing)",
    "third_line": "SACITUZUMAB GOVITECAN (Trodelvy, FDA approved 2nd-line)",
    "confirmatory_tests": "DNA sequencing for BRCA1/2 mutations; IHC for ER/PR/HER2",
    "evidence_level": "FDA Approved",
}

# ============================================================================
# LUNG ADENOCARCINOMA EGFR-MUTANT (patient_synthetic_luad)
# ============================================================================

LUAD_SIGNATURE_GENES = {
    # EGFR Pathway Activation
    "EGFR": {
        "expected_fc": 4.20,
        "min_fc": 3.0,
        "max_fc": 6.0,
        "interpretation": "EGFR OVEREXPRESSION (EGFR-mutant surrogate)",
        "clinical_significance": "EGFR TKI eligible (confirm mutation with DNA sequencing)",
    },
    "KRAS": {
        "expected_fc": 1.68,
        "min_fc": 0.8,
        "max_fc": 2.5,
        "interpretation": "KRAS BASELINE (mutually exclusive with EGFR mutations)",
        "clinical_significance": "KRAS mutation unlikely (EGFR-mutant patient)",
    },
    "ALK": {
        "expected_fc": 1.0,
        "min_fc": 0.8,
        "max_fc": 2.0,
        "interpretation": "ALK BASELINE (no ALK rearrangement)",
        "clinical_significance": "ALK inhibitors not indicated",
    },

    # Angiogenesis Pathway
    "VEGFA": {
        "expected_fc": 3.28,
        "min_fc": 2.5,
        "max_fc": 5.0,
        "interpretation": "VEGF PATHWAY ACTIVATION (ramucirumab candidate)",
        "clinical_significance": "Anti-VEGF therapy eligible",
    },
    "KDR": {
        "expected_fc": 1.0,
        "min_fc": 0.8,
        "max_fc": 2.0,
        "interpretation": "VEGFR2 BASELINE",
        "clinical_significance": "VEGFR2 target",
    },

    # Resistance Mechanisms
    "ERBB3": {
        "expected_fc": 2.16,
        "min_fc": 1.5,
        "max_fc": 3.0,
        "interpretation": "HER3 BYPASS MECHANISM (EGFR TKI resistance)",
        "clinical_significance": "Potential EGFR TKI resistance mechanism",
    },
    "AKT1": {
        "expected_fc": 3.16,
        "min_fc": 2.0,
        "max_fc": 4.0,
        "interpretation": "AKT ACTIVATION (PI3K/AKT pathway)",
        "clinical_significance": "PI3K/AKT pathway resistance mechanism",
    },
    "PIK3CA": {
        "expected_fc": 2.96,
        "min_fc": 2.0,
        "max_fc": 4.0,
        "interpretation": "PIK3CA ACTIVATION (resistance mechanism)",
        "clinical_significance": "PI3K inhibitor candidate",
    },
    "MAPK1": {
        "expected_fc": 2.41,
        "min_fc": 1.5,
        "max_fc": 3.5,
        "interpretation": "MAPK PATHWAY ACTIVATION (EGFR downstream)",
        "clinical_significance": "EGFR pathway activated",
    },
    "BRAF": {
        "expected_fc": 0.80,
        "min_fc": 0.5,
        "max_fc": 1.5,
        "interpretation": "BRAF BASELINE (no V600E mutation)",
        "clinical_significance": "BRAF inhibitors not indicated",
    },
}

LUAD_EXPECTED_DRUGS = [
    {
        "drug_name": "OSIMERTINIB",
        "mechanism": "3rd-gen EGFR TKI (T790M active)",
        "indication": "EGFR-mutant NSCLC (first-line)",
        "is_approved": True,
        "max_phase": 4,
    },
    {
        "drug_name": "ERLOTINIB",
        "mechanism": "1st-gen EGFR TKI",
        "indication": "EGFR-mutant NSCLC",
        "is_approved": True,
        "max_phase": 4,
    },
    {
        "drug_name": "GEFITINIB",
        "mechanism": "1st-gen EGFR TKI",
        "indication": "EGFR-mutant NSCLC",
        "is_approved": True,
        "max_phase": 4,
    },
    {
        "drug_name": "AFATINIB",
        "mechanism": "2nd-gen irreversible EGFR TKI",
        "indication": "EGFR-mutant NSCLC",
        "is_approved": True,
        "max_phase": 4,
    },
    {
        "drug_name": "DACOMITINIB",
        "mechanism": "2nd-gen irreversible EGFR TKI",
        "indication": "EGFR-mutant NSCLC",
        "is_approved": True,
        "max_phase": 4,
    },
    {
        "drug_name": "RAMUCIRUMAB",
        "mechanism": "VEGFR2 monoclonal antibody",
        "indication": "NSCLC (combination with erlotinib)",
        "is_approved": True,
        "max_phase": 4,
    },
]

LUAD_TREATMENT_RECOMMENDATIONS = {
    "first_line": "OSIMERTINIB (3rd-gen EGFR TKI, first-line standard)",
    "second_line": "RAMUCIRUMAB + ERLOTINIB (RELAY trial, VEGF pathway activated)",
    "third_line": "AMIVANTAMAB + LAZERTINIB (MARIPOSA trial, HER3 bypass mechanism)",
    "confirmatory_tests": "DNA sequencing for EGFR mutations (Exon 19 del, L858R, T790M)",
    "evidence_level": "FDA Approved",
}

# ============================================================================
# COLORECTAL CANCER (CRC) - Template (No synthetic patient data yet)
# ============================================================================

CRC_SIGNATURE_GENES = {
    # RAS/BRAF Status (Anti-EGFR Eligibility)
    "KRAS": {
        "expected_fc_range": (0.5, 2.0),
        "interpretation_wild_type": "KRAS WT (anti-EGFR therapy eligible)",
        "interpretation_mutant": "KRAS MUTANT (anti-EGFR therapy ineligible)",
        "clinical_significance": "Primary biomarker for anti-EGFR therapy eligibility",
    },
    "BRAF": {
        "expected_fc_range": (0.5, 2.0),
        "interpretation_wild_type": "BRAF WT (standard chemotherapy)",
        "interpretation_mutant": "BRAF V600E MUTANT (encorafenib + cetuximab eligible)",
        "clinical_significance": "BRAF V600E confers poor prognosis; specific therapy available",
    },

    # MSI-H/dMMR Markers (Immunotherapy Eligibility)
    "MLH1": {
        "expected_fc_range": (0.3, 1.0),
        "interpretation_loss": "MLH1 LOSS (MSI-H/dMMR marker)",
        "clinical_significance": "Immunotherapy eligible if MLH1 loss confirmed",
    },
    "MSH2": {
        "expected_fc_range": (0.3, 1.0),
        "interpretation_loss": "MSH2 LOSS (MSI-H/dMMR marker)",
        "clinical_significance": "Lynch syndrome marker, immunotherapy eligible",
    },
    "MSH6": {
        "expected_fc_range": (0.3, 1.0),
        "interpretation_loss": "MSH6 LOSS (MSI-H/dMMR marker)",
        "clinical_significance": "Lynch syndrome marker, immunotherapy eligible",
    },
    "PMS2": {
        "expected_fc_range": (0.3, 1.0),
        "interpretation_loss": "PMS2 LOSS (MSI-H/dMMR marker)",
        "clinical_significance": "Lynch syndrome marker, immunotherapy eligible",
    },

    # VEGF Pathway (Anti-Angiogenesis)
    "VEGFA": {
        "expected_fc_range": (2.0, 5.0),
        "interpretation": "VEGF PATHWAY ACTIVATION (bevacizumab, ramucirumab eligible)",
        "clinical_significance": "Anti-VEGF therapy indicated",
    },
    "KDR": {
        "expected_fc_range": (1.5, 3.0),
        "interpretation": "VEGFR2 OVEREXPRESSION",
        "clinical_significance": "VEGFR2 target for anti-angiogenesis",
    },

    # HER2 Amplification (~5% of CRC)
    "ERBB2": {
        "expected_fc_range": (4.0, 8.0),
        "interpretation_amplified": "HER2 AMPLIFIED (tucatinib + trastuzumab eligible)",
        "interpretation_baseline": "HER2 BASELINE (no HER2 therapy)",
        "clinical_significance": "Emerging target in ~5% of CRC patients",
    },
}

CRC_EXPECTED_DRUGS = [
    # Immunotherapy (MSI-H/dMMR)
    {
        "drug_name": "PEMBROLIZUMAB",
        "mechanism": "PD-1 immune checkpoint inhibitor",
        "indication": "MSI-H/dMMR CRC (first-line)",
        "is_approved": True,
        "max_phase": 4,
    },
    {
        "drug_name": "NIVOLUMAB",
        "mechanism": "PD-1 immune checkpoint inhibitor",
        "indication": "MSI-H/dMMR CRC",
        "is_approved": True,
        "max_phase": 4,
    },

    # Anti-EGFR (RAS/BRAF WT)
    {
        "drug_name": "CETUXIMAB",
        "mechanism": "EGFR monoclonal antibody",
        "indication": "RAS/BRAF WT mCRC",
        "is_approved": True,
        "max_phase": 4,
    },
    {
        "drug_name": "PANITUMUMAB",
        "mechanism": "EGFR monoclonal antibody",
        "indication": "RAS/BRAF WT mCRC",
        "is_approved": True,
        "max_phase": 4,
    },

    # Anti-VEGF (All Subtypes)
    {
        "drug_name": "BEVACIZUMAB",
        "mechanism": "VEGF monoclonal antibody",
        "indication": "mCRC (all subtypes)",
        "is_approved": True,
        "max_phase": 4,
    },
    {
        "drug_name": "RAMUCIRUMAB",
        "mechanism": "VEGFR2 monoclonal antibody",
        "indication": "mCRC (second-line)",
        "is_approved": True,
        "max_phase": 4,
    },

    # BRAF V600E
    {
        "drug_name": "ENCORAFENIB",
        "mechanism": "BRAF inhibitor",
        "indication": "BRAF V600E mCRC (+ cetuximab)",
        "is_approved": True,
        "max_phase": 4,
    },
]

CRC_TREATMENT_RECOMMENDATIONS = {
    "msi_h_first_line": "PEMBROLIZUMAB or NIVOLUMAB (MSI-H/dMMR confirmed by IHC or PCR)",
    "ras_wt_first_line": "CETUXIMAB or PANITUMUMAB + chemotherapy (RAS/BRAF WT)",
    "braf_v600e": "ENCORAFENIB + CETUXIMAB (BRAF V600E confirmed by DNA sequencing)",
    "all_subtypes": "BEVACIZUMAB or RAMUCIRUMAB + chemotherapy",
    "confirmatory_tests": "DNA sequencing for KRAS, NRAS, BRAF; MSI-H/dMMR testing (IHC or PCR)",
    "evidence_level": "FDA Approved",
}

# ============================================================================
# Utility Functions
# ============================================================================

def get_expected_genes(cancer_type: str) -> Dict[str, Any]:
    """Get expected gene signature for a cancer type."""
    mapping = {
        "HER2_BREAST_CANCER": HER2_SIGNATURE_GENES,
        "TNBC": TNBC_SIGNATURE_GENES,
        "LUAD_EGFR": LUAD_SIGNATURE_GENES,
        "COLORECTAL_CANCER": CRC_SIGNATURE_GENES,
    }
    return mapping.get(cancer_type, {})


def get_expected_drugs(cancer_type: str) -> List[Dict[str, Any]]:
    """Get expected FDA-approved drugs for a cancer type."""
    mapping = {
        "HER2_BREAST_CANCER": HER2_EXPECTED_DRUGS,
        "TNBC": TNBC_EXPECTED_DRUGS,
        "LUAD_EGFR": LUAD_EXPECTED_DRUGS,
        "COLORECTAL_CANCER": CRC_EXPECTED_DRUGS,
    }
    return mapping.get(cancer_type, [])


def get_treatment_recommendations(cancer_type: str) -> Dict[str, str]:
    """Get treatment recommendations for a cancer type."""
    mapping = {
        "HER2_BREAST_CANCER": HER2_TREATMENT_RECOMMENDATIONS,
        "TNBC": TNBC_TREATMENT_RECOMMENDATIONS,
        "LUAD_EGFR": LUAD_TREATMENT_RECOMMENDATIONS,
        "COLORECTAL_CANCER": CRC_TREATMENT_RECOMMENDATIONS,
    }
    return mapping.get(cancer_type, {})


def validate_fold_change(gene_symbol: str, actual_fc: float, cancer_type: str, tolerance: float = 0.5) -> bool:
    """
    Validate that actual fold-change is within expected range.

    Args:
        gene_symbol: Gene symbol (e.g., 'ERBB2')
        actual_fc: Actual fold-change from query result
        cancer_type: Cancer type identifier
        tolerance: Tolerance for fold-change comparison (default: 0.5x)

    Returns:
        True if within expected range, False otherwise
    """
    expected_genes = get_expected_genes(cancer_type)
    if gene_symbol not in expected_genes:
        return True  # Unknown gene, skip validation

    gene_data = expected_genes[gene_symbol]
    expected_fc = gene_data.get("expected_fc")
    min_fc = gene_data.get("min_fc")
    max_fc = gene_data.get("max_fc")

    if expected_fc is not None:
        # Check if within tolerance of expected value
        return abs(actual_fc - expected_fc) <= tolerance

    if min_fc is not None and max_fc is not None:
        # Check if within expected range
        return min_fc <= actual_fc <= max_fc

    return True  # No specific expectation, pass validation

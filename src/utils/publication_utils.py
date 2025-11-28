"""Utility functions for publication reference handling."""
import re
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any, Set, Union, cast

from .publication_types import Publication

logger = logging.getLogger(__name__)

# Enhanced regular expressions for finding PMIDs
PMID_PATTERNS = [
    r"PMID[:\s]*(\d{7,8})",  # Standard PMID:12345678 format
    r"PubMed[:\s]*(\d{7,8})",  # PubMed:12345678 format
    r"https?://pubmed\.ncbi\.nlm\.nih\.gov/(\d{7,8})",  # PubMed URLs
    r"www\.ncbi\.nlm\.nih\.gov/pubmed/(\d{7,8})",  # Alternative URL format
    r"ncbi\.nlm\.nih\.gov/pubmed/(\d{7,8})",  # Short URL format
    r"pubmed/(\d{7,8})",  # Simple pubmed/12345678 format
    r"\[(\d{7,8})\]",  # [12345678] format
    r"pmid\s*=\s*(\d{7,8})",  # pmid=12345678 format (case insensitive)
    r"pubmed\s*id[:\s]*(\d{7,8})",  # pubmed id:12345678 format
    r"pmid\s*:\s*(\d{7,8})",  # pmid : 12345678 format with spaces
]

# Enhanced DOI patterns
DOI_PATTERNS = [
    r"doi[:\s]*(10\.\d+/[^\s\)\,]+)",  # DOI format with various separators, excluding punctuation
    r"https?://doi\.org/(10\.\d+/[^\s\)\,]+)",  # DOI URLs
    r"https?://dx\.doi\.org/(10\.\d+/[^\s\)\,]+)",  # Alternative DOI URLs
    r"DOI[:\s]*(10\.\d+/[^\s\)\,]+)",  # Uppercase DOI
    r"Digital\s+Object\s+Identifier[:\s]*(10\.\d+/[^\s\)\,]+)",  # Full DOI name
]

# PMC (PubMed Central) patterns
PMC_PATTERNS = [
    r"PMC(\d{6,7})",  # PMC1234567 format
    r"pmc[:\s]*(\d{6,7})",  # pmc:1234567 format
    r"https?://www\.ncbi\.nlm\.nih\.gov/pmc/articles/PMC(\d{6,7})",  # PMC URLs
]

# Clinical trial ID patterns
CLINICAL_TRIAL_PATTERNS = [
    r"NCT(\d{8})",  # ClinicalTrials.gov format
    r"ISRCTN(\d+)",  # International Standard Randomised Controlled Trial Number
    r"EUDRACT(\d{4}-\d{6}-\d{2})",  # EudraCT numbers
    r"CTRI/\d{4}/\d{2}/\d{6}",  # Clinical Trials Registry - India
]

# ArXiv patterns
ARXIV_PATTERNS = [
    r"arXiv[:\s]*(\d{4}\.\d{4,5})",  # arXiv:1234.5678 format
    r"https?://arxiv\.org/abs/(\d{4}\.\d{4,5})",  # ArXiv URLs
]


def is_valid_pmid(pmid: str) -> bool:
    """Validate PMID format.

    Args:
        pmid: PubMed ID to validate

    Returns:
        bool: True if valid PMID format
    """
    # PMIDs are 1-8 digit numbers
    return bool(re.match(r"^\d{1,8}$", pmid))


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


def extract_pmids_from_urls(url1: str = None, url2: str = None) -> List[str]:
    """Extract PMIDs specifically from PubMed URLs.

    Args:
        url1: First URL to check (e.g., ACT_SOURCE_URL)
        url2: Second URL to check (e.g., MOA_SOURCE_URL)

    Returns:
        List of extracted PMIDs
    """
    pmids = []

    for url in [url1, url2]:
        if not url or not isinstance(url, str):
            continue

        # Extract PMIDs from PubMed URLs
        for pattern in PMID_PATTERNS:
            if "pubmed" in pattern.lower() or "ncbi" in pattern.lower():
                matches = re.findall(pattern, url, re.IGNORECASE)
                pmids.extend(matches)

    # Deduplicate and validate
    unique_pmids = []
    for pmid in set(pmids):
        if is_valid_pmid(pmid):
            unique_pmids.append(pmid)

    return unique_pmids


def extract_pmids_from_text(text: str) -> List[str]:
    """Extract PubMed IDs (PMIDs) from text with enhanced pattern matching.

    Args:
        text: Text that may contain PMIDs

    Returns:
        List of extracted PMIDs
    """
    if not text or not isinstance(text, str):
        return []

    pmids = []

    # Use all enhanced PMID patterns
    for pattern in PMID_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        pmids.extend(matches)

    # Special case for CHEMBL references (more conservative)
    if "CHEMBL" in text.upper():
        # Look for 7-8 digit numbers that could be PMIDs
        chembl_number_pattern = r"\b(\d{7,8})\b"
        matches = re.findall(chembl_number_pattern, text)
        pmids.extend(matches)

    # Deduplicate and validate
    unique_pmids = []
    for pmid in set(pmids):
        if is_valid_pmid(pmid):
            unique_pmids.append(pmid)

    # Log results for debugging
    if len(unique_pmids) > 0:
        logger.debug(f"Extracted PMIDs from text: {unique_pmids}")

    return unique_pmids


def format_pmid_url(pmid: str) -> str:
    """Format a PubMed ID as a URL.

    Args:
        pmid: PubMed ID

    Returns:
        URL to the PubMed article
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
    if pub.get("authors"):
        # Only access 'authors' if it exists and is not None
        authors = pub.get("authors", [])
        if authors and len(authors) > 2:
            authors_str = f"{authors[0]} et al."
        elif authors:
            authors_str = ", ".join(authors)

    # Safely access year
    year = pub.get("year")
    year_str = f"({year})" if year is not None else ""

    # Safely access title and journal
    title = pub.get("title", "No title")
    journal = pub.get("journal", "")

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
    if pub1.get("pmid") != pub2.get("pmid"):
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


def extract_dois_from_text(text: str) -> List[str]:
    """Extract DOIs from text.

    Args:
        text: Text that may contain DOIs

    Returns:
        List of extracted DOIs
    """
    if not text or not isinstance(text, str):
        return []

    dois = []

    # Use all DOI patterns
    for pattern in DOI_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        dois.extend(matches)

    # Deduplicate and validate
    unique_dois = []
    for doi in set(dois):
        # Basic DOI validation: should start with 10. and contain /
        if doi.startswith("10.") and "/" in doi:
            unique_dois.append(doi)

    if len(unique_dois) > 0:
        logger.debug(f"Extracted DOIs from text: {unique_dois}")

    return unique_dois


def extract_pmc_ids_from_text(text: str) -> List[str]:
    """Extract PMC IDs from text.

    Args:
        text: Text that may contain PMC IDs

    Returns:
        List of extracted PMC IDs
    """
    if not text or not isinstance(text, str):
        return []

    pmc_ids = []

    # Use all PMC patterns
    for pattern in PMC_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        pmc_ids.extend(matches)

    # Deduplicate and validate
    unique_pmcs = []
    for pmc_id in set(pmc_ids):
        # PMC IDs should be 6-7 digit numbers
        if pmc_id.isdigit() and len(pmc_id) in [6, 7]:
            unique_pmcs.append(pmc_id)

    if len(unique_pmcs) > 0:
        logger.debug(f"Extracted PMC IDs from text: {unique_pmcs}")

    return unique_pmcs


def extract_clinical_trial_ids_from_text(text: str) -> List[str]:
    """Extract clinical trial IDs from text.

    Args:
        text: Text that may contain clinical trial IDs

    Returns:
        List of extracted clinical trial IDs
    """
    if not text or not isinstance(text, str):
        return []

    trial_ids = []

    # Use all clinical trial patterns
    for pattern in CLINICAL_TRIAL_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        trial_ids.extend(matches)

    # For full format matches (like CTRI), include the full match
    full_pattern_matches = []
    for pattern in [r"CTRI/\d{4}/\d{2}/\d{6}"]:
        matches = re.findall(pattern, text, re.IGNORECASE)
        full_pattern_matches.extend(matches)

    trial_ids.extend(full_pattern_matches)

    # Deduplicate
    unique_trials = list(set(trial_ids))

    if len(unique_trials) > 0:
        logger.debug(f"Extracted clinical trial IDs from text: {unique_trials}")

    return unique_trials


def extract_all_publication_identifiers(text: str) -> Dict[str, List[str]]:
    """Extract all types of publication identifiers from text.

    Args:
        text: Text that may contain publication identifiers

    Returns:
        Dictionary with lists of extracted identifiers by type
    """
    if not text or not isinstance(text, str):
        return {
            "pmids": [],
            "dois": [],
            "pmc_ids": [],
            "clinical_trial_ids": [],
            "arxiv_ids": [],
        }

    identifiers = {
        "pmids": extract_pmids_from_text(text),
        "dois": extract_dois_from_text(text),
        "pmc_ids": extract_pmc_ids_from_text(text),
        "clinical_trial_ids": extract_clinical_trial_ids_from_text(text),
        "arxiv_ids": [],
    }

    # Extract ArXiv IDs
    for pattern in ARXIV_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        identifiers["arxiv_ids"].extend(matches)

    # Deduplicate ArXiv IDs
    identifiers["arxiv_ids"] = list(set(identifiers["arxiv_ids"]))

    return identifiers


def format_publication_url(identifier: str, identifier_type: str) -> str:
    """Format a publication identifier as a URL.

    Args:
        identifier: Publication identifier
        identifier_type: Type of identifier (pmid, doi, pmc, etc.)

    Returns:
        URL to the publication
    """
    if identifier_type.lower() == "pmid":
        return format_pmid_url(identifier)
    elif identifier_type.lower() == "doi":
        return f"https://doi.org/{identifier}"
    elif identifier_type.lower() == "pmc":
        return f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{identifier}/"
    elif identifier_type.lower() == "arxiv":
        return f"https://arxiv.org/abs/{identifier}"
    elif identifier_type.lower() == "clinical_trial":
        if identifier.startswith("NCT"):
            return f"https://clinicaltrials.gov/ct2/show/{identifier}"
        elif identifier.startswith("ISRCTN"):
            return f"https://www.isrctn.com/{identifier}"
        elif identifier.startswith("EUDRACT"):
            return f"https://www.clinicaltrialsregister.eu/ctr-search/search?query={identifier}"

    return ""


def calculate_publication_impact_score(publication: Publication) -> float:
    """Calculate a publication impact score based on multiple factors.

    Args:
        publication: Publication data

    Returns:
        Impact score (0-100)
    """
    if not publication:
        return 0.0

    score = 0.0

    # Base score for having a publication
    score += 10.0

    # Citation count score (if available)
    citation_count = publication.get("citation_count", 0)
    if citation_count:
        # Logarithmic scaling for citation count (max 35 points)
        citation_score = min(35.0, 15.0 * (citation_count**0.5) / 10.0)
        score += citation_score

    # Journal impact factor score (if available)
    impact_factor = publication.get("impact_factor", 0)
    if impact_factor:
        # Impact factor contribution (max 25 points)
        if_score = min(25.0, impact_factor * 0.6)
        score += if_score

    # Recency score - newer publications get higher scores
    year = publication.get("year")
    if year:
        current_year = datetime.now().year
        years_old = current_year - year
        if years_old <= 2:
            score += 15.0  # Very recent
        elif years_old <= 5:
            score += 10.0  # Recent
        elif years_old <= 10:
            score += 5.0  # Moderately recent
        # Older papers get no recency bonus

    # Evidence type bonus
    evidence_type = publication.get("evidence_type", "")
    if evidence_type == "clinical_trial":
        score += 15.0  # Clinical trials are high value
    elif evidence_type == "experimental":
        score += 10.0  # Experimental evidence
    elif evidence_type == "review":
        score += 8.0  # Reviews provide good overview

    # Journal quality indicators
    journal = publication.get("journal", "").lower()
    if any(
        high_impact in journal
        for high_impact in [
            "nature",
            "science",
            "cell",
            "nejm",
            "new england journal of medicine",
            "lancet",
            "jama",
            "bmj",
            "pnas",
        ]
    ):
        score += 10.0  # High impact journal bonus

    # Abstract quality indicator
    abstract = publication.get("abstract", "")
    if abstract and len(abstract) > 100:
        score += 5.0  # Having a substantial abstract

    # Cap the maximum score
    return min(100.0, score)


def assess_publication_relevance(
    publication: Publication, context: Dict[str, Any]
) -> float:
    """Assess how relevant a publication is to a specific context.

    Args:
        publication: Publication data
        context: Context information (gene, disease, drug, etc.)

    Returns:
        Relevance score (0-100)
    """
    if not publication:
        return 0.0

    relevance_score = 0.0

    # Extract context information
    gene_symbol = context.get("gene_symbol", "")
    disease_terms = context.get("diseases", [])
    drug_terms = context.get("drugs", [])

    # Get text fields for analysis
    title = publication.get("title", "").lower()
    abstract = publication.get("abstract", "").lower()
    keywords = publication.get("keywords", [])

    # Gene symbol relevance
    if gene_symbol:
        gene_lower = gene_symbol.lower()
        if gene_lower in title:
            relevance_score += 30.0  # Gene in title is highly relevant
        elif gene_lower in abstract:
            relevance_score += 20.0  # Gene in abstract is relevant
        elif any(gene_lower in kw.lower() for kw in keywords):
            relevance_score += 15.0  # Gene in keywords

    # Disease relevance
    if disease_terms:
        disease_matches = 0
        for disease in disease_terms:
            disease_lower = disease.lower()
            if disease_lower in title:
                disease_matches += 2
            elif disease_lower in abstract:
                disease_matches += 1

        relevance_score += min(25.0, disease_matches * 5.0)

    # Drug relevance
    if drug_terms:
        drug_matches = 0
        for drug in drug_terms:
            drug_lower = drug.lower()
            if drug_lower in title:
                drug_matches += 2
            elif drug_lower in abstract:
                drug_matches += 1

        relevance_score += min(20.0, drug_matches * 5.0)

    # Evidence type relevance
    evidence_type = publication.get("evidence_type", "")
    if evidence_type in ["clinical_trial", "experimental"]:
        relevance_score += 15.0
    elif evidence_type in ["variant_annotation", "drug_publication"]:
        relevance_score += 10.0

    # Source database relevance
    source_db = publication.get("source_db", "")
    if source_db in ["ClinicalTrials.gov", "ChEMBL"]:
        relevance_score += 10.0
    elif source_db in ["PharmGKB", "GO"]:
        relevance_score += 5.0

    return min(100.0, relevance_score)


def get_journal_impact_estimates() -> Dict[str, float]:
    """Get estimated impact factors for common journals.

    Returns:
        Dictionary mapping journal names to estimated impact factors
    """
    # These are rough estimates for demonstration
    # In production, you would use actual impact factor data
    journal_impacts = {
        "nature": 42.8,
        "science": 41.8,
        "cell": 38.0,
        "new england journal of medicine": 70.7,
        "nejm": 70.7,
        "lancet": 60.4,
        "jama": 45.5,
        "nature medicine": 30.6,
        "nature genetics": 27.6,
        "cancer cell": 26.6,
        "cell metabolism": 22.4,
        "pnas": 9.4,
        "nature communications": 12.1,
        "plos one": 2.7,
        "scientific reports": 3.8,
        "bmj": 27.6,
        "journal of clinical oncology": 28.2,
        "cancer research": 9.7,
        "oncogene": 6.6,
        "blood": 17.5,
        "leukemia": 10.0,
    }

    return journal_impacts


def enhance_publication_with_metrics(
    publication: Publication, context: Optional[Dict[str, Any]] = None
) -> Publication:
    """Enhance a publication with calculated metrics.

    Args:
        publication: Publication data
        context: Optional context for relevance scoring

    Returns:
        Enhanced publication with metrics
    """
    if not publication:
        return publication

    enhanced_pub = publication.copy()

    # Add estimated impact factor if journal is recognized
    journal = publication.get("journal", "").lower()
    journal_impacts = get_journal_impact_estimates()

    for journal_name, impact_factor in journal_impacts.items():
        if journal_name in journal:
            enhanced_pub["impact_factor"] = impact_factor
            break

    # Calculate impact score
    enhanced_pub["impact_score"] = calculate_publication_impact_score(enhanced_pub)

    # Calculate relevance score if context provided
    if context:
        enhanced_pub["relevance_score"] = assess_publication_relevance(
            enhanced_pub, context
        )

    # Add quality indicators
    quality_indicators = []

    # High impact journal
    if enhanced_pub.get("impact_factor", 0) > 10:
        quality_indicators.append("high_impact_journal")

    # Recent publication
    year = enhanced_pub.get("year")
    if year and (datetime.now().year - year) <= 3:
        quality_indicators.append("recent")

    # Clinical evidence
    if enhanced_pub.get("evidence_type") in ["clinical_trial", "clinical_annotation"]:
        quality_indicators.append("clinical_evidence")

    # High citation count (if available)
    if enhanced_pub.get("citation_count", 0) > 50:
        quality_indicators.append("highly_cited")

    enhanced_pub["quality_indicators"] = quality_indicators

    # Overall quality tier
    impact_score = enhanced_pub.get("impact_score", 0)
    if impact_score >= 80:
        enhanced_pub["quality_tier"] = "exceptional"
    elif impact_score >= 60:
        enhanced_pub["quality_tier"] = "high"
    elif impact_score >= 40:
        enhanced_pub["quality_tier"] = "moderate"
    elif impact_score >= 20:
        enhanced_pub["quality_tier"] = "basic"
    else:
        enhanced_pub["quality_tier"] = "minimal"

    return enhanced_pub


def rank_publications_by_relevance(
    publications: List[Publication], context: Dict[str, Any]
) -> List[Publication]:
    """Rank publications by relevance to a given context.

    Args:
        publications: List of publications
        context: Context for relevance assessment

    Returns:
        Publications ranked by relevance (highest first)
    """
    if not publications:
        return publications

    # Enhance all publications with metrics
    enhanced_pubs = []
    for pub in publications:
        enhanced_pub = enhance_publication_with_metrics(pub, context)
        enhanced_pubs.append(enhanced_pub)

    # Sort by combined relevance and impact score
    def sort_key(pub):
        relevance = pub.get("relevance_score", 0)
        impact = pub.get("impact_score", 0)
        # Weight relevance more heavily than impact
        return (relevance * 0.7) + (impact * 0.3)

    ranked_pubs = sorted(enhanced_pubs, key=sort_key, reverse=True)

    return ranked_pubs

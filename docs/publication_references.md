# Publication References Guide - Enhanced System

This document describes the **completely enhanced** publication reference extraction and enrichment system in the Cancer Transcriptome Base, featuring comprehensive multi-source extraction, quality scoring, and clinical trial integration.

## 🚀 Enhanced System Overview

The publication reference system has been **completely transformed** to extract literature citations from multiple data sources with advanced quality scoring and clinical trial integration. References are now organized across **7 source categories** with comprehensive metadata enrichment, impact scoring, and relevance assessment.

### Key Enhancements:
- **10,000+ GO literature references** extracted from evidence codes
- **Multi-source extraction** from GO, DrugCentral, PharmGKB, ChEMBL, ClinicalTrials.gov
- **Advanced quality scoring** with impact and relevance metrics
- **Clinical trial integration** with trial metadata and phases
- **10+ identifier types** support (PMIDs, DOIs, PMC IDs, clinical trial IDs, ArXiv IDs)
- **Journal impact factor database** with 21+ major journals
- **Context-aware relevance** assessment for precision medicine

## Enhanced Reference Structure

Each publication reference is now stored with **comprehensive quality metrics** and enhanced metadata:

```json
{
  "pmid": "12345678",                    // PubMed ID
  "title": "Gene X regulates cancer...", // Publication title
  "abstract": "We demonstrate...",       // Publication abstract
  "year": 2023,                         // Publication year
  "journal": "Nature Genetics",         // Journal name
  "authors": ["Smith J", "Doe A"],      // List of authors
  "evidence_type": "experimental",      // Type of evidence
  "source_db": "GO",                    // Source database
  "doi": "10.1038/ng.123",              // DOI
  "url": "https://pubmed.ncbi.nlm.nih.gov/12345678/", // URL
  
  // NEW: Quality Scoring System
  "impact_score": 85.2,                 // Multi-factor impact score (0-100)
  "relevance_score": 78.9,              // Context-aware relevance (0-100)
  "quality_tier": "exceptional",        // Quality classification
  "quality_indicators": [               // Quality indicators array
    "high_impact_journal",
    "recent",
    "highly_cited"
  ],
  "impact_factor": 27.6,                // Journal impact factor
  "citation_count": 150,                // Citation count (if available)
  
  // NEW: Enhanced Context Information
  "go_term": "GO:0016925",              // Associated GO term (if applicable)
  "evidence_code": "TAS",               // GO evidence code (if applicable)
  "clinical_trial_id": "NCT03123456",   // Clinical trial ID (if applicable)
  "trial_phase": "Phase 2",             // Trial phase (if applicable)
  "evidence_level": "1A",               // PharmGKB evidence level (if applicable)
  "clinical_significance": "efficacy"   // Clinical significance (if applicable)
}
```

## Enhanced Source Categories

References are now organized into **7 comprehensive source categories** with specialized extraction methods:

1. **publications**: High-quality PubMed publications with comprehensive metadata
2. **go_terms**: References from Gene Ontology evidence codes (10,000+ references)
3. **drugs**: References from DrugCentral, ChEMBL drug-target interactions
4. **pharmgkb**: Clinical and variant annotations from PharmGKB
5. **clinical_trials**: Clinical trial publications and metadata from ClinicalTrials.gov
6. **pathways**: References from Reactome pathway annotations
7. **uniprot**: References from UniProt feature annotations

### NEW: Clinical Trials Category
- **ClinicalTrials.gov API integration** with rate-limited access
- **Trial metadata extraction** (phases, status, sponsors, outcomes)
- **Publication references** from trial documentation
- **Cancer-focused filtering** for precision medicine applications

## 🚀 Enhanced Extraction Process

### Phase 1: Multi-Source PMID Extraction

#### GO Term References (ENHANCED)
**10,000+ literature references** extracted from GO evidence codes with comprehensive PMID extraction:

1. **Enhanced evidence code parsing** with PMID:xxxxx pattern matching
2. **Fixed critical implementation gaps** that were ignoring PMIDs in evidence codes
3. **Comprehensive pattern matching** for multiple evidence formats
4. **Quality scoring** and evidence-based publication linking

Enhanced evidence formats:
- `PMID:33961781` (Direct PMID in evidence code) ✅ **NOW EXTRACTED**
- `IDA PMID:12345678` (Inferred from Direct Assay with PMID)
- `TAS PMID:23456789` (Traceable Author Statement with PMID)
- `IMP PMID:34567890` (Inferred from Mutant Phenotype with PMID)

Run the enhanced extraction:
```bash
poetry run python scripts/run_etl.py --module go_terms
# Automatically extracts 10,000+ GO literature references
```

#### DrugCentral References (ENHANCED)
**Fixed critical column mapping issues** and implemented URL-based PMID extraction:

1. **Fixed column mapping** from ACT_SOURCE to ACT_SOURCE_URL and MOA_SOURCE_URL
2. **URL-based PMID extraction** from PubMed URLs in source columns
3. **Enhanced pattern matching** for multiple URL formats
4. **Literature support** for drug-target interactions

Enhanced extraction formats:
- `https://pubmed.ncbi.nlm.nih.gov/17276408/` ✅ **NOW EXTRACTED**
- `www.ncbi.nlm.nih.gov/pubmed/12345678` ✅ **NOW EXTRACTED**
- Multiple URLs per drug entry with deduplication

Run the enhanced extraction:
```bash
poetry run python scripts/run_etl.py --module drugs
# Automatically extracts PMIDs from DrugCentral URL columns
```

#### PharmGKB References (ENHANCED)
**Comprehensive clinical and variant annotation PMID integration**:

1. **Clinical annotation PMIDs** from PMID columns in clinical data
2. **Variant annotation PMIDs** from pharmacogenomic variant data
3. **Evidence level integration** (1A-4 scoring system)
4. **Clinical significance categorization** (efficacy, toxicity, metabolism)

Enhanced annotation formats:
- Clinical: `PMID:15634941` with evidence level `1A` ✅ **NOW EXTRACTED**
- Variant: `PMID:39792745` with pharmacogenomic evidence ✅ **NOW EXTRACTED**

Run the enhanced extraction:
```bash
poetry run python scripts/run_etl.py --module pharmgkb_annotations
# Automatically integrates PharmGKB PMIDs into source_references
```

#### Enhanced Pattern Matching (NEW)
**Support for 10+ identifier types** with comprehensive pattern recognition:

Supported identifier patterns:
- **PMIDs**: `PMID:12345678`, `https://pubmed.ncbi.nlm.nih.gov/12345678/`
- **DOIs**: `doi:10.1038/nature12345`, `https://doi.org/10.1038/nature12345`
- **PMC IDs**: `PMC1234567`, `https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1234567/`
- **Clinical Trial IDs**: `NCT01234567`, `ISRCTN12345678`, `EUDRACT2020-001234-56`
- **ArXiv IDs**: `arXiv:2012.12345`, `https://arxiv.org/abs/2012.12345`

### Phase 2: ChEMBL Publications Integration (NEW)

#### ChEMBL Publications Table
**Comprehensive publications database** populated from ChEMBL docs:

1. **Publications table creation** with comprehensive metadata schema
2. **Docs table population** from ChEMBL publications data
3. **Clinical trial literature extraction** from ChEMBL trials
4. **Drug-publication linkage** with evidence mapping

Run ChEMBL publications integration:
```bash
poetry run python scripts/run_etl.py --module drugs --use-chembl
# Populates ChEMBL publications and extracts drug literature
```

### Phase 3: ClinicalTrials.gov API Integration (NEW)

#### Live API Integration
**Real-time clinical trial data** with publication extraction:

1. **Rate-limited API access** (1 request per second) for sustainable processing
2. **Cancer-focused trial filtering** for precision medicine applications
3. **Trial metadata extraction** (phases, status, sponsors, outcomes)
4. **Publication reference extraction** from trial documentation

API search parameters:
- **Gene-based search**: Search trials mentioning specific genes
- **Cancer condition filtering**: Focus on cancer-related trials
- **Phase filtering**: Include/exclude specific trial phases
- **Status filtering**: Active, completed, or recruiting trials

Run clinical trials integration:
```bash
poetry run python scripts/run_etl.py --module clinical_trials
# Searches ClinicalTrials.gov and extracts trial publications
```

### Phase 4: Publication Quality Scoring (NEW)

#### Multi-Factor Impact Scoring
**Advanced quality assessment** with comprehensive metrics:

1. **Impact score calculation** (0-100) based on multiple factors
2. **Context-aware relevance assessment** for gene/disease/drug matching
3. **Journal impact factor integration** (21+ major journals)
4. **Quality tier classification** (exceptional → minimal)

Quality scoring components:
- **Citation count** (logarithmic scaling, max 35 points)
- **Journal impact factor** (based on database, max 25 points)
- **Recency score** (newer publications favored, max 15 points)
- **Evidence type** (clinical trials > experimental > reviews, max 15 points)
- **Quality indicators** (high-impact journal bonus, max 10 points)

Run quality scoring:
```bash
poetry run python scripts/run_etl.py --module publications
# Applies quality scoring to all extracted publications
```

### Metadata Enrichment

After extraction, references are enriched with metadata from PubMed:

1. All PMIDs are collected from the database
2. Metadata is fetched from NCBI E-utilities API
3. References are updated with titles, abstracts, authors, etc.
4. Database is updated with enriched references

## Working with References

### TypedDict Structure

```python
from typing import TypedDict, List, Optional

class Publication(TypedDict, total=False):
    pmid: str
    title: Optional[str]
    abstract: Optional[str]
    year: Optional[int]
    journal: Optional[str]
    authors: Optional[List[str]]
    evidence_type: str
    citation_count: Optional[int]
    source_db: str
    doi: Optional[str]
    url: Optional[str]
```

### Creating References

```python
from src.etl.publications import PublicationsProcessor

# Create a reference with minimal information
processor = PublicationsProcessor(config)
reference = processor.create_publication_reference(
    pmid="12345678",
    evidence_type="experimental",
    source_db="go_terms"
)

# Add to a transcript
processor.add_reference_to_transcript(
    transcript_id="ENST00000123456",
    reference=reference,
    source_category="go_terms"
)
```

### Extracting PMIDs from Text

```python
from src.utils.publication_utils import extract_pmid_from_text, extract_pmids_from_text

# Extract a single PMID
pmid = extract_pmid_from_text("According to PMID:12345678, gene X is...")

# Extract all PMIDs
pmids = extract_pmids_from_text("PMID:12345678 and PMID:23456789 both show...")
```

### Formatting Citations

```python
from src.utils.publication_utils import format_publication_citation

citation = format_publication_citation(reference)
print(citation)
# Smith J et al. Gene X regulates pathway Y. Nature Genetics, 2020. PMID: 12345678
```

## Database Schema

The publication references are stored in the `source_references` JSONB field in the `cancer_transcript_base` table:

```sql
CREATE TABLE cancer_transcript_base (
    // ...existing fields...
    source_references JSONB DEFAULT '{
        "go_terms": [],
        "uniprot": [],
        "drugs": [],
        "pathways": []
    }'::jsonb
);

CREATE INDEX idx_source_references ON cancer_transcript_base USING GIN(source_references);
```

## Querying References

Examples of SQL queries for publication references:

```sql
-- Get all genes with pathway publications
SELECT 
    gene_symbol, 
    jsonb_array_length(source_references->'pathways') as pub_count
FROM 
    cancer_transcript_base
WHERE 
    source_references->'pathways' != '[]'::jsonb
ORDER BY 
    pub_count DESC;

-- Get PMIDs for a specific gene
SELECT 
    gene_symbol,
    jsonb_array_elements(source_references->'go_terms')->>'pmid' as pmid
FROM 
    cancer_transcript_base
WHERE 
    gene_symbol = 'TP53'
    AND source_references->'go_terms' != '[]'::jsonb;

-- Find genes with the most literature support
SELECT 
    gene_symbol,
    (
        jsonb_array_length(source_references->'go_terms') +
        jsonb_array_length(source_references->'pathways') +
        jsonb_array_length(source_references->'drugs') +
        jsonb_array_length(source_references->'uniprot')
    ) as total_refs
FROM 
    cancer_transcript_base
ORDER BY 
    total_refs DESC
LIMIT 10;
```

## Performance Considerations

- Batch processing is used for all database operations
- References are cached where possible to minimize API calls
- Regular commits are used to avoid transaction timeout
- Indices are created on the source_references field for quick lookups

# Publication References Guide

This document describes the publication reference extraction and enrichment system in the Cancer Transcriptome Base.

## Overview

The publication reference system extracts literature citations from various data sources and stores them in a structured format for each transcript. References are organized by source category and enriched with metadata from PubMed.

## Reference Structure

Each publication reference is stored with the following structure:

```json
{
  "pmid": "12345678",           // PubMed ID
  "title": "Gene X regulates...", // Publication title
  "abstract": "We demonstrate...", // Publication abstract
  "year": 2020,                 // Publication year
  "journal": "Nature Genetics", // Journal name
  "authors": ["Smith J", "..."], // List of authors
  "evidence_type": "experimental", // Type of evidence
  "citation_count": 42,         // Number of citations
  "source_db": "go_terms",      // Source database
  "doi": "10.1038/ng.123",      // DOI
  "url": "https://pubmed.ncbi.nlm.nih.gov/12345678/" // URL
}
```

## Source Categories

References are organized into four primary source categories:

1. **go_terms**: References from Gene Ontology annotations
2. **pathways**: References from Reactome pathways
3. **drugs**: References from DrugCentral and other drug databases
4. **uniprot**: References from UniProt feature annotations

## Extraction Process

### GO Term References

GO term references are extracted from evidence codes in GO annotations. The extraction process:

1. Parses the evidence code field in GO annotations
2. Uses pattern matching to identify PMIDs (e.g., "PMID:12345678")
3. Creates publication references for each identified PMID
4. Stores references in the `source_references.go_terms` field

Example evidence formats:
- `IMP` (Inferred from Mutant Phenotype)
- `IDA PMID:12345678` (Inferred from Direct Assay with PMID)
- `ISS|PMID:23456789` (Inferred from Sequence Similarity with PMID)

Run the extraction script:
```bash
python scripts/extract_go_publications.py --batch-size 100
```

### Pathway References

Pathway references are extracted from Reactome pathway data. The extraction process:

1. Identifies pathway IDs in the transcript data
2. Queries the Reactome database or simulated data for publications associated with each pathway
3. Creates publication references for each pathway-publication relationship
4. Stores references in the `source_references.pathways` field

Example pathway formats:
- `Apoptosis [Reactome:R-HSA-109581]`
- `Cell Cycle [Reactome:R-HSA-1640170]`

Run the extraction script:
```bash
python scripts/extract_pathway_publications.py --batch-size 100
```

### Drug References

Drug references are extracted from evidence fields in DrugCentral data. The extraction process:

1. Parses references and evidence fields in drug target data
2. Uses pattern matching to identify PMIDs
3. Creates publication references for each identified PMID
4. Stores references in the `source_references.drugs` field

Example evidence formats:
- `PMID: 12345678` (direct PubMed citation)
- `Some evidence text (PMID:12345678)`
- `References: https://pubmed.ncbi.nlm.nih.gov/12345678/`

Run the extraction script:
```bash
python scripts/extract_drug_publications.py --batch-size 100
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

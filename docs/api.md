# API Reference Documentation

## Overview

## Publications Module

### PublicationsProcessor

```python
from src.etl.publications import PublicationsProcessor, Publication

# Initialize with configuration
processor = PublicationsProcessor(config)

# Create a reference
ref = processor.create_publication_reference(
    pmid="12345678",
    evidence_type="experimental",
    source_db="go_terms"
)

# Add to transcript
processor.add_reference_to_transcript(
    transcript_id="ENST00000123456",
    reference=ref,
    source_category="go_terms"
)

# Run enrichment pipeline
processor.run()
```

### Publication Utilities

```python
from src.utils.publication_utils import (
    extract_pmid_from_text,
    extract_pmids_from_text,
    format_publication_citation,
    merge_publication_references
)

# Extract PMIDs
pmid = extract_pmid_from_text("PMID:12345678")
pmids = extract_pmids_from_text("Multiple PMIDs: PMID:12345678, PMID:23456789")

# Format citation
citation = format_publication_citation(reference)

# Merge references
merged = merge_publication_references(ref1, ref2)
```

## Pathway Module

### PathwayProcessor

```python
from src.etl.pathways import PathwayProcessor

# Initialize with configuration
processor = PathwayProcessor(config)

# Run full pipeline (includes publication extraction)
processor.run()

# Extract publication references from pathway evidence
publications = processor._extract_pathway_publications(evidence, pathway_id)
```

### Pathway Publication Extraction

```bash
# Run extraction script
python scripts/extract_pathway_publications.py --batch-size 100
```

## GO Terms Module

### GOTermProcessor

```python
from src.etl.go_terms import GOTermProcessor

# Initialize with configuration
processor = GOTermProcessor(config)

# Run full pipeline
processor.run()

# Extract publications from GO evidence codes
publications = processor.extract_publication_references(go_terms)
```

### GO Publication Extraction

```bash
# Run extraction script
python scripts/extract_go_publications.py --batch-size 100
```

For detailed information on publication references, see [Publication References Guide](publication_references.md).


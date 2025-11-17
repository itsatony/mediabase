# PubMed Title + Abstract Enrichment Plan

## Executive Summary

This document outlines a comprehensive strategy to enrich MEDIABASE with PubMed titles and abstracts, enabling LLM-assisted reasoning about scientific literature for clinical oncology applications.

**Goal**: Store title + abstract for ~5-7 million unique PMIDs to support LLM queries like:
- "What do recent papers say about ERBB2 resistance mechanisms?"
- "Summarize key findings from publications about my patient's overexpressed genes"
- "Find papers discussing combination therapies for TP53 mutations"

**Approach**: Hybrid bulk download + API enrichment with smart prioritization

**Timeline**:
- Phase 1 (Week 1): Schema + infrastructure (2-3 days)
- Phase 2 (Week 1-2): Bulk baseline import (~1-2 days processing)
- Phase 3 (Ongoing): Background API enrichment (~10-30 days for full coverage)

**Storage**: ~15-20 GB for 5-7 million publications (title + abstract + metadata)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     MEDIABASE Database                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────────┐         ┌──────────────────────┐   │
│  │ gene_publications  │         │ publication_metadata │   │
│  │ ─────────────────  │         │ ──────────────────── │   │
│  │ gene_id           │────┐     │ pmid (PK)           │   │
│  │ pmid              │    └────→│ title               │   │
│  │ mention_count     │          │ abstract            │   │
│  │ first_seen_year   │          │ journal             │   │
│  └────────────────────┘          │ pub_date            │   │
│                                   │ authors             │   │
│                                   │ mesh_terms          │   │
│                                   │ enriched_at         │   │
│                                   │ source              │   │
│                                   └──────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                          │
                          │ Enrichment Queue
                          ▼
        ┌─────────────────────────────────────────┐
        │  Background Enrichment Service          │
        │  ─────────────────────────────────────  │
        │                                          │
        │  Priority Queue:                         │
        │  1. Patient-specific gene publications   │
        │  2. High mention count (≥10)            │
        │  3. Recent papers (last 5 years)        │
        │  4. Remaining backfill                  │
        └─────────────────────────────────────────┘
                          │
            ┌─────────────┴─────────────┐
            ▼                           ▼
   ┌──────────────────┐      ┌──────────────────┐
   │  PubMed Baseline │      │  PubMed E-utils  │
   │  (Bulk Download) │      │  API (efetch)    │
   │                  │      │                  │
   │  • Annual        │      │  • Rate limited  │
   │  • ~50GB XML     │      │  • 200 PMIDs/req │
   │  • Historical    │      │  • Current data  │
   └──────────────────┘      └──────────────────┘
```

---

## Phase 1: Schema Extension (Week 1, Days 1-2)

### 1.1 Add to v0.5.0 Migration

```sql
-- =============================================================================
-- PART X: PUBLICATION METADATA (PubMed Title + Abstract Enrichment)
-- =============================================================================

CREATE TABLE IF NOT EXISTS publication_metadata (
    pmid VARCHAR(20) PRIMARY KEY,
    title TEXT NOT NULL,
    abstract TEXT,
    journal VARCHAR(500),
    pub_date DATE,
    pub_year INTEGER GENERATED ALWAYS AS (EXTRACT(YEAR FROM pub_date)) STORED,
    authors TEXT[],  -- Array of author names
    mesh_terms TEXT[],  -- Medical Subject Headings for topic classification
    doi VARCHAR(100),
    pmc_id VARCHAR(20),  -- PubMed Central ID if available
    citation_count INTEGER DEFAULT 0,
    is_open_access BOOLEAN DEFAULT false,
    enriched_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    source VARCHAR(20) DEFAULT 'api',  -- 'baseline' or 'api'
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Full-text search support
    title_abstract_tsv TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(abstract, ''))
    ) STORED
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_publication_metadata_year
ON publication_metadata(pub_year DESC);

CREATE INDEX IF NOT EXISTS idx_publication_metadata_journal
ON publication_metadata(journal);

CREATE INDEX IF NOT EXISTS idx_publication_metadata_enriched
ON publication_metadata(enriched_at DESC);

CREATE INDEX IF NOT EXISTS idx_publication_metadata_source
ON publication_metadata(source);

-- Full-text search index (PostgreSQL specific)
CREATE INDEX IF NOT EXISTS idx_publication_metadata_fulltext
ON publication_metadata USING GIN(title_abstract_tsv);

-- MeSH terms array index for topic filtering
CREATE INDEX IF NOT EXISTS idx_publication_metadata_mesh
ON publication_metadata USING GIN(mesh_terms);

-- Composite index for common query pattern: gene → recent papers
CREATE INDEX IF NOT EXISTS idx_publication_metadata_recent
ON publication_metadata(pub_year DESC, enriched_at DESC)
WHERE pub_year >= EXTRACT(YEAR FROM CURRENT_DATE) - 5;

-- LLM-friendly comments
COMMENT ON TABLE publication_metadata IS
'PubMed publication metadata including title, abstract, and bibliographic information.
Source: PubMed baseline (annual) + E-utilities API (incremental)
Update: Continuous background enrichment
Coverage: Title (~100%), Abstract (~85%), Full metadata (~95%)

Use Cases for LLM Queries:
- Find papers discussing specific genes/proteins
- Extract key findings from abstracts
- Identify recent research trends
- Discover combination therapy studies
- Assess evidence quality from publication venues

Example Queries:
1. "What do recent papers say about BRCA1 mutations?"
   → Join gene_publications + publication_metadata on pmid, filter pub_year

2. "Summarize abstracts mentioning resistance mechanisms"
   → Full-text search on title_abstract_tsv for ''resistance mechanism''

3. "Find high-impact papers (based on journal) about my genes"
   → Filter by journal (Nature, Science, Cell, NEJM, etc.)';

COMMENT ON COLUMN publication_metadata.pmid IS
'PubMed ID - unique identifier for publications in PubMed database.
Primary key. Joinable with gene_publications.pmid.';

COMMENT ON COLUMN publication_metadata.title IS
'Publication title. Always present. Use for quick relevance assessment.';

COMMENT ON COLUMN publication_metadata.abstract IS
'Publication abstract. Present for ~85% of articles.
NULL for older papers, case reports, or editorials without abstracts.
Contains key findings, methods, and conclusions - most valuable for LLM reasoning.';

COMMENT ON COLUMN publication_metadata.journal IS
'Journal name. Use to assess publication quality/impact.
High-impact oncology journals: Nature, Science, Cell, NEJM, Lancet, JCO, Cancer Cell, etc.';

COMMENT ON COLUMN publication_metadata.pub_date IS
'Publication date. Use to filter for recent research (last 2-5 years).';

COMMENT ON COLUMN publication_metadata.authors IS
'Array of author names (last name + initials).
First/last authors often indicate lab leaders. Use for attribution.';

COMMENT ON COLUMN publication_metadata.mesh_terms IS
'Medical Subject Headings - controlled vocabulary for topic classification.
Examples: "Breast Neoplasms", "Drug Resistance, Neoplasm", "Targeted Therapy"
Use to filter papers by specific topics without full-text search.';

COMMENT ON COLUMN publication_metadata.is_open_access IS
'True if full text is freely available via PubMed Central.
Useful for providing full-text links to oncologists.';

COMMENT ON COLUMN publication_metadata.title_abstract_tsv IS
'Full-text search vector combining title and abstract.
Use with to_tsquery() for relevance-ranked text search.
Example: WHERE title_abstract_tsv @@ to_tsquery(''BRCA1 & mutation & resistance'')';

-- Enrichment tracking table
CREATE TABLE IF NOT EXISTS publication_enrichment_queue (
    pmid VARCHAR(20) PRIMARY KEY,
    priority INTEGER NOT NULL DEFAULT 100,  -- Lower = higher priority
    gene_id VARCHAR(50),  -- If associated with a specific gene query
    requested_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    attempts INTEGER DEFAULT 0,
    last_attempt TIMESTAMP WITH TIME ZONE,
    status VARCHAR(20) DEFAULT 'pending',  -- pending, processing, completed, failed
    error_message TEXT,

    FOREIGN KEY (gene_id) REFERENCES genes(gene_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_enrichment_queue_priority
ON publication_enrichment_queue(priority ASC, requested_at ASC)
WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_enrichment_queue_status
ON publication_enrichment_queue(status);

COMMENT ON TABLE publication_enrichment_queue IS
'Queue for background PubMed metadata enrichment.
Priority-based processing ensures patient-relevant papers are enriched first.

Priority Levels:
- 1-10: Patient-specific queries (urgent)
- 11-50: High-mention genes (≥10 mentions in literature)
- 51-100: Recent papers (last 5 years)
- 101+: Backfill remaining publications

Status Values:
- pending: Awaiting enrichment
- processing: Currently being fetched from PubMed API
- completed: Successfully enriched
- failed: API error (will retry with exponential backoff)';

-- Helper function to queue PMIDs for enrichment
CREATE OR REPLACE FUNCTION queue_publication_enrichment(
    pmid_list TEXT[],
    priority_level INTEGER DEFAULT 100,
    associated_gene_id VARCHAR(50) DEFAULT NULL
)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    queued_count INTEGER := 0;
    pmid_val TEXT;
BEGIN
    FOREACH pmid_val IN ARRAY pmid_list
    LOOP
        INSERT INTO publication_enrichment_queue (pmid, priority, gene_id)
        VALUES (pmid_val, priority_level, associated_gene_id)
        ON CONFLICT (pmid) DO UPDATE
        SET priority = LEAST(publication_enrichment_queue.priority, EXCLUDED.priority),
            requested_at = CURRENT_TIMESTAMP
        WHERE publication_enrichment_queue.status != 'completed';

        queued_count := queued_count + 1;
    END LOOP;

    RETURN queued_count;
END;
$$;

COMMENT ON FUNCTION queue_publication_enrichment IS
'Queue PMIDs for background enrichment with priority.
Usage: SELECT queue_publication_enrichment(ARRAY[''12345678'', ''87654321''], 10, ''ENSG00000141510'');
Returns number of PMIDs queued.';

-- View for enrichment progress tracking
CREATE OR REPLACE VIEW publication_enrichment_progress AS
SELECT
    COUNT(*) FILTER (WHERE pm.pmid IS NULL) as unenriched_count,
    COUNT(*) FILTER (WHERE pm.pmid IS NOT NULL) as enriched_count,
    ROUND(
        (COUNT(*) FILTER (WHERE pm.pmid IS NOT NULL)::DECIMAL /
         NULLIF(COUNT(*), 0) * 100),
        2
    ) as enrichment_percentage,
    COUNT(*) FILTER (WHERE peq.status = 'pending') as queue_pending,
    COUNT(*) FILTER (WHERE peq.status = 'processing') as queue_processing,
    COUNT(*) FILTER (WHERE peq.status = 'failed') as queue_failed,
    COUNT(DISTINCT gp.pmid) as total_unique_pmids
FROM gene_publications gp
LEFT JOIN publication_metadata pm ON gp.pmid = pm.pmid
LEFT JOIN publication_enrichment_queue peq ON gp.pmid = peq.pmid;

COMMENT ON VIEW publication_enrichment_progress IS
'Real-time dashboard of publication enrichment status.
Query this to monitor background enrichment progress.';
```

---

## Phase 2: Bulk Baseline Import (Week 1-2)

### 2.1 Download PubMed Baseline

**Source**: NIH FTP server
**URL**: `ftp://ftp.ncbi.nlm.nih.gov/pubmed/baseline/`
**Format**: XML files (pubmedYYn####.xml.gz)
**Size**: ~1,200 files × ~40MB = ~50GB compressed
**Coverage**: All PubMed records up to December of previous year

### 2.2 Baseline Import Script

Create `scripts/import_pubmed_baseline.py`:

```python
"""
Import PubMed baseline XML files into publication_metadata table.

This script:
1. Downloads PubMed baseline files from NCBI FTP
2. Parses XML to extract title, abstract, metadata
3. Batch inserts into publication_metadata table
4. Tracks progress and handles errors gracefully

Expected runtime: 8-24 hours depending on CPU and disk I/O
"""

# Key features:
# - Resume capability (tracks processed files)
# - Parallel XML parsing (multiprocessing)
# - Batch inserts (5000 records at a time)
# - Memory efficient (streaming XML parsing)
# - Error logging and retry logic
```

### 2.3 Selective Import Strategy

**Option A: Import All (~35M publications)**
- ✅ Complete coverage
- ❌ ~20GB storage, 12-24 hours processing
- **Use if**: Storage not an issue, want completeness

**Option B: Import Cancer-Relevant Only (~5-8M publications)**
- ✅ Reduced storage (5-8GB), faster import (2-4 hours)
- ✅ More relevant to oncology use case
- ❌ May miss some relevant papers
- **Use if**: Storage limited, focused application

**Filtering criteria for Option B**:
- Papers linked to genes in our database (via PubTator)
- Papers with cancer-related MeSH terms
- Papers from top oncology journals

**Recommendation**: Start with Option B, expand to Option A if needed

---

## Phase 3: API-Based Enrichment Service (Ongoing)

### 3.1 Background Enrichment Architecture

Create `src/services/pubmed_enrichment_service.py`:

```python
"""
Background service for continuous PubMed metadata enrichment.

Features:
- Priority-based queue processing
- Rate limiting (10 req/sec with API key, 3/sec without)
- Batch fetching (200 PMIDs per request using efetch)
- Exponential backoff on errors
- Resume capability (tracks progress in DB)
- Prometheus metrics for monitoring
"""

from typing import List, Dict, Any
import time
from dataclasses import dataclass
import logging

@dataclass
class EnrichmentConfig:
    api_key: str  # NCBI API key (register at NCBI)
    rate_limit: int = 10  # requests per second
    batch_size: int = 200  # PMIDs per request
    max_retries: int = 3
    retry_backoff: float = 2.0  # exponential backoff multiplier


class PubMedEnrichmentService:
    """
    Manages background enrichment of publication metadata from PubMed API.

    Usage:
        service = PubMedEnrichmentService(config)
        service.start()  # Runs continuously until interrupted
    """

    def __init__(self, config: EnrichmentConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)

    async def process_queue(self):
        """
        Main processing loop:
        1. Fetch next batch from queue (ordered by priority)
        2. Request metadata from PubMed E-utilities
        3. Parse XML/JSON response
        4. Insert into publication_metadata table
        5. Mark as completed in queue
        6. Sleep for rate limiting
        """
        pass

    async def fetch_batch(self, pmids: List[str]) -> Dict[str, Any]:
        """
        Fetch metadata for up to 200 PMIDs in one request.

        Uses PubMed efetch API:
        https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?
            db=pubmed&id=12345678,87654321&retmode=xml&api_key=XXX
        """
        pass

    def parse_pubmed_xml(self, xml: str) -> List[Dict]:
        """Extract title, abstract, journal, etc. from PubMed XML."""
        pass
```

### 3.2 Smart Prioritization Logic

```python
def calculate_priority(pmid: str, gene_id: str = None) -> int:
    """
    Calculate enrichment priority for a PMID.

    Priority Tiers (lower = higher priority):
    - 1-10: Patient-specific query (gene in active patient database)
    - 11-30: High-impact genes (TP53, BRCA1, EGFR, etc.)
    - 31-50: High mention count (≥50 mentions across genes)
    - 51-70: Recent papers (last 2 years)
    - 71-90: Medium mention count (≥10 mentions)
    - 91-100: Recent papers (last 5 years)
    - 101+: Backfill remaining
    """
    # Implementation logic
    pass
```

### 3.3 Rate Limiting Strategy

```python
from ratelimit import limits, sleep_and_retry
import requests

# With API key: 10 requests per second
@sleep_and_retry
@limits(calls=10, period=1)
def api_call_with_key(url: str) -> requests.Response:
    return requests.get(url)

# Without API key: 3 requests per second (more conservative)
@sleep_and_retry
@limits(calls=3, period=1)
def api_call_no_key(url: str) -> requests.Response:
    return requests.get(url)
```

**Expected throughput**:
- With API key: 10 req/sec × 200 PMIDs/req = 2,000 PMIDs/sec = 7.2M PMIDs/hour
- In practice: ~1,000-2,000 PMIDs/sec accounting for parsing, DB writes
- **Full enrichment time**: 5M PMIDs ÷ 1,500 PMIDs/sec = ~55 minutes

---

## Phase 4: Deployment & Operations

### 4.1 Background Service Deployment

**Option A: Systemd Service (Linux)**
```bash
# /etc/systemd/system/pubmed-enrichment.service
[Unit]
Description=MEDIABASE PubMed Enrichment Service
After=postgresql.service

[Service]
Type=simple
User=mediabase
WorkingDirectory=/opt/mediabase
ExecStart=/opt/mediabase/venv/bin/python src/services/pubmed_enrichment_service.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
```

**Option B: Docker Container**
```dockerfile
FROM python:3.11-slim
COPY src/ /app/src/
COPY requirements.txt /app/
RUN pip install -r requirements.txt
CMD ["python", "/app/src/services/pubmed_enrichment_service.py"]
```

**Option C: Cron Job (Simple Start)**
```bash
# Run every hour, process up to 10,000 PMIDs per run
0 * * * * cd /opt/mediabase && python scripts/enrich_publications_batch.py --limit 10000
```

### 4.2 Monitoring & Metrics

```python
# Prometheus metrics
from prometheus_client import Counter, Gauge, Histogram

enrichment_total = Counter('pubmed_enrichment_total', 'Total PMIDs enriched')
enrichment_failed = Counter('pubmed_enrichment_failed', 'Failed enrichment attempts')
enrichment_rate = Gauge('pubmed_enrichment_rate', 'Current enrichment rate (PMIDs/sec)')
enrichment_queue_size = Gauge('pubmed_queue_size', 'Number of PMIDs pending enrichment')
api_latency = Histogram('pubmed_api_latency', 'PubMed API response time')
```

**Grafana Dashboard**:
- Enrichment progress (% complete)
- Current queue size
- Processing rate (PMIDs/minute)
- API error rate
- Estimated time to completion

### 4.3 Operational Procedures

**Daily**:
- Check enrichment progress view
- Monitor API error rate
- Verify queue is processing

**Weekly**:
- Review failed enrichments, retry with updated logic
- Check storage usage
- Update priority for new patient queries

**Monthly**:
- Download and process PubMed daily update files
- Vacuum/analyze publication_metadata table
- Review and optimize slow queries

---

## Phase 5: LLM Integration

### 5.1 Enhanced Query Patterns

```sql
-- Before (just PMIDs)
SELECT gp.gene_id, gp.pmid, gp.mention_count
FROM gene_publications gp
WHERE gp.gene_id = 'ENSG00000141510'  -- TP53
ORDER BY gp.mention_count DESC
LIMIT 10;

-- After (with title + abstract)
SELECT
    g.gene_symbol,
    pm.pmid,
    pm.title,
    pm.abstract,
    pm.journal,
    pm.pub_year,
    gp.mention_count,
    CONCAT('https://pubmed.ncbi.nlm.nih.gov/', pm.pmid) as pubmed_url
FROM gene_publications gp
JOIN genes g ON gp.gene_id = g.gene_id
JOIN publication_metadata pm ON gp.pmid = pm.pmid
WHERE g.gene_symbol = 'TP53'
  AND pm.pub_year >= EXTRACT(YEAR FROM CURRENT_DATE) - 5
  AND pm.abstract IS NOT NULL
ORDER BY gp.mention_count DESC, pm.pub_year DESC
LIMIT 10;
```

### 5.2 LLM Prompt Templates

```python
# Template for "summarize papers" query
def generate_literature_summary(gene_symbol: str, pmids: List[str]) -> str:
    papers = fetch_papers_with_abstracts(pmids)

    prompt = f"""
    You are a clinical oncology expert. Summarize the key findings about {gene_symbol}
    from these recent publications:

    {format_papers_for_llm(papers)}

    Focus on:
    1. Role in cancer progression
    2. Therapeutic implications
    3. Resistance mechanisms
    4. Prognostic significance

    Provide a concise 3-4 paragraph summary suitable for an oncologist.
    """
    return prompt
```

### 5.3 Full-Text Search Examples

```sql
-- Find papers discussing specific topics
SELECT
    pm.pmid,
    pm.title,
    ts_headline('english', pm.abstract,
                to_tsquery('resistance & mechanism'),
                'MaxWords=50, MinWords=25') as relevant_excerpt,
    ts_rank(pm.title_abstract_tsv, to_tsquery('resistance & mechanism')) as relevance
FROM publication_metadata pm
WHERE pm.title_abstract_tsv @@ to_tsquery('resistance & mechanism')
  AND pm.pub_year >= 2020
ORDER BY relevance DESC
LIMIT 20;
```

---

## Cost & Resource Analysis

### Storage

| Component | Count | Size per Item | Total Size |
|-----------|-------|---------------|------------|
| Title | 5-7M | ~100 bytes | ~600 MB |
| Abstract | 4-6M (85%) | ~1.5 KB | ~8 GB |
| Metadata | 5-7M | ~500 bytes | ~3 GB |
| Indexes | - | ~30% overhead | ~4 GB |
| **Total** | - | - | **~15-16 GB** |

### API Costs

- **PubMed E-utilities**: FREE (with registration and API key)
- **Rate limits**: 10 req/sec with key, 3 req/sec without
- **No usage fees**: NCBI services are publicly funded

### Compute Time

| Phase | Duration | Notes |
|-------|----------|-------|
| Schema setup | 1-2 hours | One-time |
| Baseline import (selective) | 2-4 hours | One-time, ~5-8M records |
| API enrichment (5M PMIDs) | 1-8 hours | Depends on rate limit |
| Daily maintenance | <5 minutes | New publications only |

---

## Implementation Checklist

### Week 1: Foundation
- [ ] Extend v0.5.0 migration with publication_metadata tables
- [ ] Create helper functions (queue_publication_enrichment, etc.)
- [ ] Set up monitoring views (publication_enrichment_progress)
- [ ] Register for NCBI API key (instant, free)
- [ ] Test API connectivity with sample PMIDs

### Week 2: Bulk Import
- [ ] Download PubMed baseline (or subset)
- [ ] Implement baseline XML parser
- [ ] Run import with progress tracking
- [ ] Verify data quality (spot checks)
- [ ] Create initial enrichment queue

### Week 3-4: API Enrichment
- [ ] Implement background enrichment service
- [ ] Set up rate limiting and error handling
- [ ] Deploy as systemd service or cron job
- [ ] Monitor enrichment progress
- [ ] Iterate on prioritization logic

### Ongoing: Operations
- [ ] Weekly monitoring of enrichment status
- [ ] Monthly PubMed update imports
- [ ] Quarterly full-text search optimization
- [ ] As-needed priority adjustments for patient queries

---

## Success Metrics

**Coverage**:
- ✅ 95%+ of gene_publications PMIDs have titles
- ✅ 85%+ have abstracts
- ✅ Patient-relevant papers enriched within 1 hour

**Performance**:
- ✅ Full-text search queries < 500ms
- ✅ Gene-paper join queries < 200ms
- ✅ LLM query generation success rate > 90%

**Clinical Value**:
- ✅ Oncologists can ask natural language questions about literature
- ✅ LLM provides accurate summaries from abstracts
- ✅ System identifies relevant papers for novel gene combinations

---

## Future Enhancements

### Phase 2 (Months 3-6)
1. **Europe PMC integration** - Better full-text access for open access papers
2. **Citation network analysis** - Identify highly-cited papers automatically
3. **Author disambiguation** - Link papers by research groups
4. **Topic modeling** - Cluster papers by research themes (LDA, BERTopic)

### Phase 3 (Months 6-12)
1. **Semantic search** - Vector embeddings for abstract similarity
2. **Automated evidence extraction** - NER for extracting specific claims
3. **Drug-paper links** - Parse abstracts for drug mentions and outcomes
4. **Clinical trial matching** - Link papers to ClinicalTrials.gov entries

---

## Alternative Approaches Considered

### 1. Europe PMC API (https://europepmc.org/)
- ✅ Better full-text access for open access papers
- ✅ More permissive rate limits
- ❌ Smaller corpus than PubMed (~40M vs 36M)
- **Decision**: Use as secondary source for full-text when available

### 2. Semantic Scholar API (https://www.semanticscholar.org/)
- ✅ Citation counts, influence metrics
- ✅ Paper recommendations
- ❌ Smaller biomedical corpus
- ❌ Commercial restrictions
- **Decision**: Not suitable for primary source

### 3. OpenAlex (https://openalex.org/)
- ✅ Comprehensive metadata
- ✅ Open data (no rate limits)
- ❌ Less focused on biomedicine
- **Decision**: Potential future integration for citation analysis

---

## Conclusion

This plan provides a comprehensive, production-ready approach to enriching MEDIABASE with PubMed titles and abstracts. The hybrid bulk download + API enrichment strategy balances:

- **Completeness**: Cover historical + current literature
- **Efficiency**: Smart prioritization minimizes wait time for patient-relevant papers
- **Sustainability**: Background service handles ongoing updates automatically
- **Clinical value**: Enables LLM-powered literature reasoning for oncologists

**Next step**: Extend v0.5.0 schema migration with publication_metadata tables, then proceed with phased implementation.

# Open Targets Platform - Implementation Guide

## Executive Summary

This guide provides step-by-step instructions for integrating Open Targets Platform data into MEDIABASE to enable LLM-assisted clinical oncology queries. The integration adds disease-gene associations, drug-target information, and tractability assessments to enhance clinical decision support for oncologists.

**Timeline:** 4-5 weeks for complete implementation
**Complexity:** Moderate - requires data download, ETL development, and schema migration
**Impact:** High - enables actionable drug recommendations and evidence-based gene prioritization

---

## Prerequisites

### System Requirements
- PostgreSQL 12+ with existing MEDIABASE schema (v0.3.0+)
- Python 3.10+ with Poetry dependency management
- At least 50GB disk space for Open Targets data caching
- Network access to EBI FTP servers

### Completed Dependencies
Ensure these MEDIABASE modules are already processed:
- ✅ `transcript` - Base gene data
- ✅ `id_enrichment` - Gene ID mapping (Ensembl cross-references)

### Software Dependencies
Add to `pyproject.toml`:
```toml
[tool.poetry.dependencies]
pyarrow = "^14.0.0"  # Parquet file reading
fastparquet = "^2023.10.0"  # Alternative Parquet library
ftplib = "*"  # Built-in, but ensure available
```

Install with:
```bash
poetry add pyarrow fastparquet
```

---

## Phase 1: Data Download (Days 1-2)

### Step 1.1: Identify Current Release

Visit Open Targets Platform:
- Website: https://platform.opentargets.org/
- Check "About" → "Data Download" for latest release version
- As of November 2025, latest is typically 24.09 or 24.12

### Step 1.2: Create Download Script

Create `/home/itsatony/code/mediabase/scripts/download_opentargets.py`:

```python
"""
Download Open Targets Platform datasets via FTP.
"""
import ftplib
import logging
from pathlib import Path
from typing import List
from tqdm import tqdm

logger = logging.getLogger(__name__)

FTP_HOST = "ftp.ebi.ac.uk"
RELEASE_VERSION = "24.09"  # Update to current release
BASE_PATH = f"/pub/databases/opentargets/platform/{RELEASE_VERSION}/output/etl/parquet"

# Priority datasets for oncology
DATASETS = [
    "diseases",
    "associationByOverallDirect",
    "knownDrugsAggregated",
    "targets",
    "mechanismOfAction"
]

def download_opentargets_datasets(
    cache_dir: Path,
    datasets: List[str] = DATASETS,
    version: str = RELEASE_VERSION
) -> None:
    """Download Open Targets datasets via FTP."""

    cache_dir = Path(cache_dir) / f"opentargets_{version}"
    cache_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Connecting to {FTP_HOST}...")
    ftp = ftplib.FTP(FTP_HOST)
    ftp.login()  # Anonymous login

    for dataset_name in datasets:
        dataset_path = f"{BASE_PATH}/{dataset_name}"
        local_dataset_dir = cache_dir / dataset_name
        local_dataset_dir.mkdir(exist_ok=True)

        logger.info(f"Downloading dataset: {dataset_name}")

        try:
            ftp.cwd(dataset_path)
            files = ftp.nlst()

            # Filter for Parquet files
            parquet_files = [f for f in files if f.endswith('.parquet')]

            for filename in tqdm(parquet_files, desc=f"Downloading {dataset_name}"):
                local_file = local_dataset_dir / filename

                if local_file.exists():
                    logger.info(f"Skipping {filename} (already downloaded)")
                    continue

                with open(local_file, 'wb') as f:
                    ftp.retrbinary(f'RETR {filename}', f.write)

                logger.info(f"Downloaded {filename}")

        except ftplib.error_perm as e:
            logger.error(f"FTP error for {dataset_name}: {e}")
            continue

    ftp.quit()
    logger.info("Download complete")


if __name__ == "__main__":
    import sys
    from src.utils.logging import setup_logging

    setup_logging(level=logging.INFO)

    cache_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/mediabase/cache/opentargets")
    download_opentargets_datasets(cache_dir)
```

### Step 1.3: Execute Download

```bash
# Create cache directory
mkdir -p /tmp/mediabase/cache/opentargets

# Run download (may take 1-2 hours for all datasets)
poetry run python scripts/download_opentargets.py /tmp/mediabase/cache/opentargets

# Verify downloads
ls -lh /tmp/mediabase/cache/opentargets/opentargets_24.09/
```

**Expected sizes:**
- diseases: ~50-100 MB
- associationByOverallDirect: ~2-5 GB
- knownDrugsAggregated: ~500 MB
- targets: ~200-400 MB
- mechanismOfAction: ~100 MB

---

## Phase 2: Schema Migration (Days 3-4)

### Step 2.1: Review Schema

The schema migration is already prepared:
- **File:** `/home/itsatony/code/mediabase/src/db/migrations/006_opentargets_schema.sql`
- **Tables:** 5 core tables + 1 materialized view
- **Indexes:** 20+ optimized indexes for LLM queries

Review the schema:
```bash
cat /home/itsatony/code/mediabase/src/db/migrations/006_opentargets_schema.sql
```

### Step 2.2: Apply Migration

**Option A: Manual application (recommended for first time)**
```bash
# Connect to database
psql -h $MB_POSTGRES_HOST -U $MB_POSTGRES_USER -d $MB_POSTGRES_DB

# Apply migration
\i /home/itsatony/code/mediabase/src/db/migrations/006_opentargets_schema.sql

# Verify tables created
\dt opentargets_*

# Check comments (LLM-friendly descriptions)
\d+ opentargets_gene_disease_associations

# Exit
\q
```

**Option B: Automated application (if migration system exists)**
```bash
poetry run python scripts/manage_db.py --apply-migration 006
```

### Step 2.3: Verify Schema

```sql
-- Count tables
SELECT COUNT(*) FROM information_schema.tables
WHERE table_name LIKE 'opentargets_%';
-- Expected: 5 tables

-- Check indexes
SELECT tablename, indexname FROM pg_indexes
WHERE tablename LIKE 'opentargets_%';
-- Expected: 20+ indexes

-- Verify materialized view
SELECT COUNT(*) FROM gene_clinical_summary;
-- Expected: 0 (empty until populated)
```

---

## Phase 3: ETL Implementation (Days 5-12)

### Step 3.1: Complete ETL Processor

The skeleton ETL processor is at:
- **File:** `/home/itsatony/code/mediabase/src/etl/opentargets.py`

Complete the implementation by filling in these methods:

#### 3.1.1: FTP Download Integration

```python
def _download_dataset(self, dataset_name: str) -> Path:
    """Download dataset from Open Targets FTP with caching."""
    cache_subdir = self.cache_dir / f"opentargets_{self.config.version}"
    dataset_dir = cache_subdir / dataset_name

    # Check cache
    if dataset_dir.exists() and any(dataset_dir.glob("*.parquet")):
        logger.info(f"Using cached {dataset_name} from {dataset_dir}")
        return dataset_dir

    # Download if not cached
    logger.info(f"Downloading {dataset_name}...")
    # Use download_opentargets.py logic here
    # Or call it as subprocess

    return dataset_dir
```

#### 3.1.2: Batch Insert Methods

```python
def _batch_insert_diseases(self, records: List[Dict]) -> None:
    """Batch insert disease records with upsert."""
    if not records:
        return

    # Prepare values for bulk insert
    values = []
    for r in records:
        values.append((
            r['disease_id'],
            r['disease_name'],
            r['disease_description'],
            r['therapeutic_areas'],
            r['ontology_source'],
            r['is_cancer'],
            r['parent_disease_ids'],
            r['metadata'],
            r['ot_version']
        ))

    # Use psycopg2 execute_values for efficiency
    from psycopg2.extras import execute_values

    with self.db_manager.transaction() as cursor:
        execute_values(
            cursor,
            """
            INSERT INTO opentargets_diseases
            (disease_id, disease_name, disease_description, therapeutic_areas,
             ontology_source, is_cancer, parent_disease_ids, metadata, ot_version)
            VALUES %s
            ON CONFLICT (disease_id) DO UPDATE SET
                disease_name = EXCLUDED.disease_name,
                disease_description = EXCLUDED.disease_description,
                therapeutic_areas = EXCLUDED.therapeutic_areas,
                updated_at = NOW()
            """,
            values,
            page_size=1000
        )
```

Similar implementations needed for:
- `_batch_insert_associations()`
- `_batch_insert_drugs()`
- `_batch_insert_tractability()`

#### 3.1.3: Gene ID Mapping Enhancement

Ensure robust mapping from Ensembl gene IDs to MEDIABASE gene_id:

```python
def _get_gene_id_mapping(self) -> Dict[str, str]:
    """
    Get mapping from Ensembl gene ID to MEDIABASE gene_id.

    Handles multiple formats:
    - ENSG00000139618 (Ensembl)
    - ENSG00000139618.15 (with version)
    """
    result = self.db_manager.query("""
        SELECT
            ensembl_gene_id,
            gene_id
        FROM gene_id_map
        WHERE ensembl_gene_id IS NOT NULL
        UNION
        SELECT
            gene_id as ensembl_gene_id,
            gene_id
        FROM gene_transcript
        WHERE gene_id LIKE 'ENSG%'
    """)

    # Create bidirectional mapping with version handling
    mapping = {}
    for ensembl_id, gene_id in result:
        # Store both versioned and unversioned
        mapping[ensembl_id] = gene_id
        if '.' in ensembl_id:
            base_id = ensembl_id.split('.')[0]
            mapping[base_id] = gene_id

    return mapping
```

### Step 3.2: Add to ETL Sequence

Update `/home/itsatony/code/mediabase/config/etl_sequence.py`:

```python
ETL_SEQUENCE = [
    "transcript",
    "id_enrichment",
    "go_terms",
    "products",
    "pathways",
    "opentargets",  # ADD THIS LINE
    "drugs",
    "publications"
]

ETL_DEPENDENCIES = {
    # ... existing dependencies ...
    "opentargets": ["transcript", "id_enrichment"],
    "drugs": ["transcript", "id_enrichment", "opentargets"],  # Update this
}
```

### Step 3.3: Test ETL Module

```bash
# Run ETL for Open Targets only
poetry run python scripts/run_etl.py --modules opentargets --log-level DEBUG

# Monitor progress
# Expected runtime: 30-60 minutes depending on data size
```

**Expected output:**
```
[INFO] Starting Open Targets ETL (version 24.09)
[INFO] Creating Open Targets schema...
[INFO] Processing diseases...
[INFO] Loaded 15,234 diseases (3,456 cancer)
[INFO] Processing gene-disease associations...
[INFO] Filtering associations: score >= 0.5, cancer only
[INFO] Retained 145,678 associations after filtering
[INFO] Loaded 145,678 associations
[INFO] Processing known drugs...
[INFO] Loaded 23,456 drug-target-disease entries
[INFO] Processing target tractability...
[INFO] Loaded 18,234 tractability assessments
[INFO] Creating indexes...
[INFO] Open Targets ETL completed successfully
```

---

## Phase 4: Validation & Testing (Days 13-15)

### Step 4.1: Data Quality Validation

Create `/home/itsatony/code/mediabase/scripts/validate_opentargets.py`:

```python
"""Validate Open Targets data quality and coverage."""
import logging
from src.db.database import get_db_manager

logger = logging.getLogger(__name__)

def validate_opentargets_integration():
    """Run comprehensive validation checks."""
    db = get_db_manager()

    checks = {}

    # Check 1: Table record counts
    tables = [
        'opentargets_diseases',
        'opentargets_gene_disease_associations',
        'opentargets_known_drugs',
        'opentargets_target_tractability'
    ]

    for table in tables:
        result = db.query(f"SELECT COUNT(*) FROM {table}")
        count = result[0][0]
        checks[f"{table}_count"] = count
        logger.info(f"{table}: {count:,} records")

        if count == 0:
            logger.error(f"ERROR: {table} is empty!")

    # Check 2: Cancer disease proportion
    result = db.query("""
        SELECT
            COUNT(*) FILTER (WHERE is_cancer = true) as cancer,
            COUNT(*) as total
        FROM opentargets_diseases
    """)
    cancer, total = result[0]
    cancer_pct = (cancer / total * 100) if total > 0 else 0
    checks['cancer_disease_percentage'] = cancer_pct
    logger.info(f"Cancer diseases: {cancer:,} / {total:,} ({cancer_pct:.1f}%)")

    if cancer_pct < 20:
        logger.warning("WARNING: Low cancer disease proportion")

    # Check 3: Gene ID mapping coverage
    result = db.query("""
        SELECT
            COUNT(DISTINCT oga.gene_id) as mapped,
            COUNT(*) as total
        FROM opentargets_gene_disease_associations oga
        JOIN gene_transcript gt ON oga.gene_id = gt.gene_id
    """)
    mapped, total = result[0] if result else (0, 0)
    mapping_pct = (mapped / total * 100) if total > 0 else 0
    checks['gene_mapping_percentage'] = mapping_pct
    logger.info(f"Gene ID mapping: {mapped:,} / {total:,} ({mapping_pct:.1f}%)")

    if mapping_pct < 80:
        logger.error("ERROR: Poor gene ID mapping coverage")

    # Check 4: Evidence score distribution
    result = db.query("""
        SELECT
            COUNT(*) FILTER (WHERE overall_score >= 0.85) as very_strong,
            COUNT(*) FILTER (WHERE overall_score >= 0.7 AND overall_score < 0.85) as strong,
            COUNT(*) FILTER (WHERE overall_score >= 0.5 AND overall_score < 0.7) as moderate,
            COUNT(*) as total
        FROM opentargets_gene_disease_associations
    """)
    vs, s, m, total = result[0]
    logger.info(f"Evidence distribution:")
    logger.info(f"  Very strong (≥0.85): {vs:,} ({vs/total*100:.1f}%)")
    logger.info(f"  Strong (0.7-0.84): {s:,} ({s/total*100:.1f}%)")
    logger.info(f"  Moderate (0.5-0.69): {m:,} ({m/total*100:.1f}%)")

    # Check 5: Drug actionability
    result = db.query("""
        SELECT
            COUNT(DISTINCT target_gene_id) as genes_with_drugs,
            COUNT(*) FILTER (WHERE is_approved = true) as approved_drugs,
            COUNT(*) FILTER (WHERE clinical_phase >= 2) as phase2_plus
        FROM opentargets_known_drugs
        WHERE target_gene_id IS NOT NULL
    """)
    genes, approved, phase2 = result[0]
    logger.info(f"Drug coverage:")
    logger.info(f"  Genes with drugs: {genes:,}")
    logger.info(f"  Approved drugs: {approved:,}")
    logger.info(f"  Phase II+ drugs: {phase2:,}")

    checks['genes_with_approved_drugs'] = genes
    checks['approved_drug_count'] = approved

    # Check 6: Tractability coverage
    result = db.query("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE sm_clinical_precedence = true) as sm_precedent,
            COUNT(*) FILTER (WHERE ab_clinical_precedence = true) as ab_precedent
        FROM opentargets_target_tractability
    """)
    total, sm, ab = result[0]
    logger.info(f"Tractability:")
    logger.info(f"  Total assessed: {total:,}")
    logger.info(f"  SM clinical precedence: {sm:,} ({sm/total*100:.1f}%)")
    logger.info(f"  AB clinical precedence: {ab:,} ({ab/total*100:.1f}%)")

    # Check 7: Known cancer genes present
    well_known_cancer_genes = [
        'TP53', 'EGFR', 'KRAS', 'BRAF', 'PIK3CA',
        'BRCA1', 'BRCA2', 'PTEN', 'MYC', 'RB1'
    ]

    result = db.query("""
        SELECT DISTINCT gt.gene_symbol
        FROM gene_transcript gt
        JOIN opentargets_gene_disease_associations oga ON gt.gene_id = oga.gene_id
        JOIN opentargets_diseases od ON oga.disease_id = od.disease_id
        WHERE gt.gene_symbol = ANY(%s)
            AND od.is_cancer = true
            AND oga.overall_score >= 0.7
    """, (well_known_cancer_genes,))

    found_genes = [r[0] for r in result]
    missing_genes = set(well_known_cancer_genes) - set(found_genes)

    logger.info(f"Well-known cancer genes:")
    logger.info(f"  Found: {len(found_genes)} / {len(well_known_cancer_genes)}")
    if missing_genes:
        logger.warning(f"  Missing: {', '.join(missing_genes)}")

    checks['known_cancer_genes_found'] = len(found_genes)

    # Overall status
    if all([
        checks.get('opentargets_diseases_count', 0) > 10000,
        checks.get('opentargets_gene_disease_associations_count', 0) > 50000,
        checks.get('gene_mapping_percentage', 0) >= 80,
        checks.get('known_cancer_genes_found', 0) >= 8
    ]):
        logger.info("✓ Validation PASSED")
        return True
    else:
        logger.error("✗ Validation FAILED")
        return False


if __name__ == "__main__":
    from src.utils.logging import setup_logging
    setup_logging(level=logging.INFO)
    validate_opentargets_integration()
```

Run validation:
```bash
poetry run python scripts/validate_opentargets.py
```

### Step 4.2: Test Query Examples

Test the example queries from `OPENTARGETS_QUERY_EXAMPLES.sql`:

```bash
# Connect to database
psql -h $MB_POSTGRES_HOST -U $MB_POSTGRES_USER -d $MB_POSTGRES_DB

# Test Example 1: Approved drugs for overexpressed genes
\i /home/itsatony/code/mediabase/docs/OPENTARGETS_QUERY_EXAMPLES.sql

# Run just Example 1 (copy-paste the query)
# Should return results in < 200ms

# Test materialized view
SELECT COUNT(*) FROM gene_clinical_summary;
-- If 0, needs initial refresh:
REFRESH MATERIALIZED VIEW gene_clinical_summary;

# Verify materialized view
SELECT * FROM gene_clinical_summary
WHERE cancer_fold > 2.0
    AND approved_drug_count > 0
LIMIT 10;
```

### Step 4.3: Integration Testing with Patient Data

Test with existing patient database:

```bash
# Create test patient if needed
poetry run python scripts/create_patient_copy.py \
    --patient-id TEST_OT_001 \
    --csv-file examples/patient_data_example.csv

# Switch to patient database
psql -h $MB_POSTGRES_HOST -U $MB_POSTGRES_USER -d mediabase_patient_TEST_OT_001

# Test actionable gene query
SELECT
    gt.gene_symbol,
    gt.cancer_fold,
    okd.molecule_name,
    okd.clinical_phase
FROM gene_transcript gt
JOIN opentargets_known_drugs okd ON gt.gene_id = okd.target_gene_id
WHERE gt.cancer_fold > 2.0
    AND okd.is_approved = true
LIMIT 10;
```

---

## Phase 5: API Integration (Days 16-18)

### Step 5.1: Add Open Targets Endpoints

Update `/home/itsatony/code/mediabase/src/api/server.py`:

```python
# Add new endpoints for Open Targets queries

@app.get("/api/v1/genes/{gene_symbol}/clinical-summary")
async def get_gene_clinical_summary(gene_symbol: str):
    """Get comprehensive clinical summary for a gene."""
    # Implementation of Example 9 from query examples
    pass

@app.get("/api/v1/genes/actionable")
async def get_actionable_genes(
    min_fold_change: float = 2.0,
    min_evidence_score: float = 0.5,
    approved_only: bool = True
):
    """Get actionable overexpressed genes with drug options."""
    # Implementation of Example 1 from query examples
    pass

@app.get("/api/v1/drugs/search")
async def search_drugs(
    target_gene: Optional[str] = None,
    cancer_type: Optional[str] = None,
    min_phase: float = 2.0
):
    """Search drugs by target gene or cancer type."""
    pass
```

### Step 5.2: Test API Endpoints

```bash
# Start API server
poetry run python -m src.api.server

# In another terminal, test endpoints
curl http://localhost:8000/api/v1/genes/EGFR/clinical-summary

curl "http://localhost:8000/api/v1/genes/actionable?min_fold_change=2.0&approved_only=true"
```

---

## Phase 6: Documentation & LLM Context (Days 19-20)

### Step 6.1: Update CLAUDE.md

Add to `/home/itsatony/code/mediabase/CLAUDE.md`:

```markdown
## Open Targets Integration (v0.4.0+)

### Data Source
- Open Targets Platform: Disease-gene associations, drug-target data, tractability
- Version tracking: Check `opentargets_metadata` table for current version
- Update frequency: Quarterly (March, June, September, December)

### Key Tables
- `opentargets_diseases`: Cancer ontology and classifications
- `opentargets_gene_disease_associations`: Gene-cancer evidence with scores
- `opentargets_known_drugs`: Approved and clinical-stage drugs
- `opentargets_target_tractability`: Druggability assessments
- `gene_clinical_summary`: Materialized view for fast queries

### Common Queries
See `/home/itsatony/code/mediabase/docs/OPENTARGETS_QUERY_EXAMPLES.sql` for:
- Approved drugs for overexpressed genes
- Novel target discovery
- Clinical trial matching
- Evidence-based gene ranking

### ETL Management
```bash
# Update Open Targets data
poetry run python scripts/run_etl.py --modules opentargets

# Validate integration
poetry run python scripts/validate_opentargets.py

# Refresh materialized view
psql -c "REFRESH MATERIALIZED VIEW CONCURRENTLY gene_clinical_summary"
```
```

### Step 6.2: Create User-Facing Documentation

Create `/home/itsatony/code/mediabase/docs/OPENTARGETS_USER_GUIDE.md`:

```markdown
# Open Targets Integration - User Guide

## Overview

MEDIABASE now integrates Open Targets Platform data to provide:
- Evidence-based gene-cancer associations
- Actionable drug recommendations
- Clinical trial matching
- Target tractability assessments

## Key Features

### 1. Drug Actionability
Identify approved drugs targeting overexpressed genes in patient samples.

### 2. Evidence Scoring
Multiple evidence types:
- Somatic mutations (cancer-specific)
- Clinical drugs (treatment availability)
- Literature (published research)
- Expression patterns
- Genetic associations

### 3. Tractability Assessment
Druggability predictions for novel targets.

### 4. Clinical Trial Matching
Find active trials for patient molecular profiles.

## Query Examples

[Include simplified versions of queries for clinical users]
```

---

## Phase 7: Deployment & Maintenance (Ongoing)

### Step 7.1: Production Deployment Checklist

- [ ] Backup existing database before migration
- [ ] Apply schema migration (006_opentargets_schema.sql)
- [ ] Run full ETL with production data
- [ ] Validate integration
- [ ] Refresh materialized view
- [ ] Test API endpoints
- [ ] Update all patient databases (if needed)
- [ ] Monitor query performance
- [ ] Document version in release notes

### Step 7.2: Quarterly Update Procedure

When new Open Targets release is available:

```bash
# 1. Download new data
poetry run python scripts/download_opentargets.py \
    /tmp/mediabase/cache/opentargets \
    --version 24.12  # New version

# 2. Run ETL with new version
# Update version in config or pass as parameter
poetry run python scripts/run_etl.py \
    --modules opentargets \
    --ot-version 24.12

# 3. Validate
poetry run python scripts/validate_opentargets.py

# 4. Compare versions
psql -c "SELECT version, record_counts FROM opentargets_metadata ORDER BY version"

# 5. Refresh materialized view
psql -c "REFRESH MATERIALIZED VIEW CONCURRENTLY gene_clinical_summary"

# 6. Update patient databases (if schema unchanged)
# Run update script for each patient database
```

### Step 7.3: Performance Monitoring

Monitor these metrics:
- Query response times (target: < 200ms for common patterns)
- Index usage (pg_stat_user_indexes)
- Materialized view refresh time (target: < 5 minutes)
- API endpoint latency

```sql
-- Check query performance
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
    AND tablename LIKE 'opentargets_%'
ORDER BY idx_scan DESC;

-- Check slow queries
SELECT
    query,
    calls,
    mean_exec_time,
    max_exec_time
FROM pg_stat_statements
WHERE query LIKE '%opentargets%'
ORDER BY mean_exec_time DESC
LIMIT 10;
```

---

## Troubleshooting

### Issue: Low gene ID mapping coverage

**Symptoms:** Validation shows < 80% gene mapping
**Cause:** Mismatch between Open Targets Ensembl IDs and MEDIABASE gene_id format
**Solution:**
```python
# Enhance _get_gene_id_mapping() to handle version numbers
# Add fallback to symbol mapping if Ensembl ID fails
```

### Issue: Slow association queries

**Symptoms:** Queries take > 1 second
**Cause:** Missing or unused indexes
**Solution:**
```sql
-- Check index usage
EXPLAIN ANALYZE [your slow query];

-- Rebuild index if needed
REINDEX INDEX CONCURRENTLY idx_ot_assoc_gene_score;

-- Update table statistics
ANALYZE opentargets_gene_disease_associations;
```

### Issue: Materialized view out of date

**Symptoms:** Query results don't reflect recent updates
**Cause:** Materialized view not refreshed after data changes
**Solution:**
```bash
# Refresh view (CONCURRENTLY to avoid locking)
psql -c "REFRESH MATERIALIZED VIEW CONCURRENTLY gene_clinical_summary"

# Schedule automatic refresh (cron job)
# Daily at 2 AM:
# 0 2 * * * psql -c "REFRESH MATERIALIZED VIEW CONCURRENTLY gene_clinical_summary"
```

### Issue: FTP download failures

**Symptoms:** ETL fails during data download
**Cause:** Network issues, EBI server maintenance
**Solution:**
```bash
# Retry with manual download
wget -r -np -nH --cut-dirs=7 \
  ftp://ftp.ebi.ac.uk/pub/databases/opentargets/platform/24.09/output/etl/parquet/diseases/

# Or use alternative download method (HTTP)
# Check Open Targets website for HTTP links
```

---

## Success Criteria

Integration is complete when:

1. **Data Quality**
   - ✅ All 5 tables populated with expected record counts
   - ✅ > 80% gene ID mapping coverage
   - ✅ Well-known cancer genes (TP53, EGFR, etc.) present with strong evidence
   - ✅ > 20% of diseases classified as cancer

2. **Performance**
   - ✅ Common queries execute in < 200ms
   - ✅ Materialized view refresh < 5 minutes
   - ✅ API endpoints respond in < 500ms

3. **Functionality**
   - ✅ All 10 example queries return reasonable results
   - ✅ Integration with existing patient workflows
   - ✅ API endpoints functional

4. **Documentation**
   - ✅ Schema fully commented (LLM-friendly)
   - ✅ Query examples documented
   - ✅ User guide created
   - ✅ Maintenance procedures documented

---

## Resources

### Open Targets Documentation
- Platform: https://platform.opentargets.org/
- Docs: https://platform-docs.opentargets.org/
- API: https://platform-docs.opentargets.org/data-access/graphql
- FTP: ftp://ftp.ebi.ac.uk/pub/databases/opentargets/platform/

### MEDIABASE Documentation
- Integration plan: `/home/itsatony/code/mediabase/docs/OPENTARGETS_INTEGRATION_PLAN.md`
- Query examples: `/home/itsatony/code/mediabase/docs/OPENTARGETS_QUERY_EXAMPLES.sql`
- ETL code: `/home/itsatony/code/mediabase/src/etl/opentargets.py`
- Schema migration: `/home/itsatony/code/mediabase/src/db/migrations/006_opentargets_schema.sql`

### Support
- Open Targets Helpdesk: helpdesk@opentargets.org
- MEDIABASE Issues: [GitHub repo]

---

## Next Steps

After successful integration:
1. Train LLM on new schema and query patterns
2. Develop clinical use cases with oncology partners
3. Integrate with additional data sources (OncoKB, CIViC)
4. Build visualization dashboards
5. Publish integration methodology

---

**Document Version:** 1.0
**Last Updated:** 2025-11-16
**Author:** MEDIABASE Development Team

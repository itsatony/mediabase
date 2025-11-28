# Query Migration Guide: v0.5.0 → v0.6.0
**MEDIABASE Version 0.6.0** | Schema Migration and Query Updates

## Overview

MEDIABASE v0.6.0 introduces a **shared core architecture** that fundamentally changes how patient data is stored and queried. This guide provides step-by-step instructions for migrating queries from v0.5.0 (database-per-patient) to v0.6.0 (schema-per-patient).

---

## Architecture Changes Summary

### v0.5.0 Architecture (Old)
- **Database Model**: One database per patient (`mediabase_patient_PATIENT123`)
- **Connection**: Separate connection per patient database
- **Baseline**: All transcripts stored with `expression_fold_change = 1.0` (100% storage)
- **Query Pattern**: Direct queries against patient-specific database

### v0.6.0 Architecture (New)
- **Database Model**: One shared database (`mbase`) with multiple patient schemas
- **Connection**: Single connection, query multiple patient schemas
- **Baseline**: Only non-baseline values stored (`expression_fold_change != 1.0`, 99.75% storage savings)
- **Query Pattern**: LEFT JOIN between public schema and patient schema with COALESCE

---

## Key Migration Concepts

### 1. Database Connection Changes

**v0.5.0 (Old)**:
```python
# Connect to patient-specific database
conn = psycopg2.connect(
    host="localhost",
    database="mediabase_patient_PATIENT123",  # Patient-specific database
    user="mbase_user",
    password="mbase_secret"
)
```

**v0.6.0 (New)**:
```python
# Connect to shared database
conn = psycopg2.connect(
    host="localhost",
    database="mbase",  # Shared database for all patients
    user="mbase_user",
    password="mbase_secret"
)
```

### 2. Schema Qualification Changes

**v0.5.0 (Old)**:
```sql
-- Tables in default public schema
SELECT * FROM cancer_transcript_base;
SELECT * FROM genes;
```

**v0.6.0 (New)**:
```sql
-- Core data in public schema, patient data in patient-specific schema
SELECT * FROM public.genes;  -- Shared core data
SELECT * FROM patient_PATIENT123.expression_data;  -- Patient-specific data
```

### 3. Baseline Expression Handling

**v0.5.0 (Old)**:
```sql
-- All transcripts stored, baseline = 1.0 explicitly stored
SELECT gene_symbol, expression_fold_change
FROM cancer_transcript_base
WHERE expression_fold_change > 2.0;
```

**v0.6.0 (New)**:
```sql
-- Only non-baseline stored, use COALESCE for baseline 1.0
SELECT
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as expression_fold_change
FROM public.transcripts t
JOIN public.genes g ON t.gene_id = g.gene_id
LEFT JOIN patient_PATIENT123.expression_data pe
    ON t.transcript_id = pe.transcript_id
WHERE COALESCE(pe.expression_fold_change, 1.0) > 2.0;
```

---

## Migration Patterns

### Pattern 1: Simple Gene Expression Query

**v0.5.0 (Old)**:
```sql
-- Find overexpressed genes
SELECT
    gene_symbol,
    expression_fold_change
FROM cancer_transcript_base
WHERE expression_fold_change > 3.0
ORDER BY expression_fold_change DESC
LIMIT 20;
```

**v0.6.0 (New)**:
```sql
-- Find overexpressed genes (patient-specific)
SELECT
    g.gene_symbol,
    MAX(COALESCE(pe.expression_fold_change, 1.0)) as max_fold_change
FROM public.genes g
LEFT JOIN public.transcripts t ON g.gene_id = t.gene_id
LEFT JOIN patient_PATIENT123.expression_data pe
    ON t.transcript_id = pe.transcript_id
GROUP BY g.gene_symbol
HAVING MAX(COALESCE(pe.expression_fold_change, 1.0)) > 3.0
ORDER BY max_fold_change DESC
LIMIT 20;
```

### Pattern 2: Drug Targeting Query

**v0.5.0 (Old)**:
```sql
-- Find FDA-approved drugs for overexpressed genes
SELECT
    ctb.gene_symbol,
    ctb.expression_fold_change,
    okd.molecule_name as drug_name
FROM cancer_transcript_base ctb
JOIN opentargets_known_drugs okd
    ON ctb.gene_id = okd.target_gene_id
WHERE ctb.expression_fold_change > 2.0
  AND okd.is_approved = true
ORDER BY ctb.expression_fold_change DESC;
```

**v0.6.0 (New)**:
```sql
-- Find FDA-approved drugs for overexpressed genes (patient-specific)
SELECT
    g.gene_symbol,
    COALESCE(MAX(pe.expression_fold_change), 1.0) as max_fold_change,
    okd.molecule_name as drug_name
FROM public.genes g
LEFT JOIN public.transcripts t ON g.gene_id = t.gene_id
LEFT JOIN patient_PATIENT123.expression_data pe
    ON t.transcript_id = pe.transcript_id
JOIN public.opentargets_known_drugs okd
    ON g.gene_id = okd.target_gene_id
WHERE okd.is_approved = true
GROUP BY g.gene_symbol, okd.molecule_name
HAVING COALESCE(MAX(pe.expression_fold_change), 1.0) > 2.0
ORDER BY max_fold_change DESC;
```

### Pattern 3: Pathway Enrichment Query

**v0.5.0 (Old)**:
```sql
-- Find enriched pathways
SELECT
    UNNEST(pathways) as pathway_id,
    COUNT(*) as gene_count,
    AVG(expression_fold_change) as avg_fold_change
FROM cancer_transcript_base
WHERE expression_fold_change > 2.0
GROUP BY pathway_id
HAVING COUNT(*) >= 5
ORDER BY gene_count DESC;
```

**v0.6.0 (New)**:
```sql
-- Find enriched pathways (patient-specific)
SELECT
    gp.pathway_id,
    gp.pathway_name,
    COUNT(DISTINCT g.gene_id) as gene_count,
    AVG(COALESCE(pe.expression_fold_change, 1.0)) as avg_fold_change
FROM public.gene_pathways gp
JOIN public.genes g ON gp.gene_id = g.gene_id
LEFT JOIN public.transcripts t ON g.gene_id = t.gene_id
LEFT JOIN patient_PATIENT123.expression_data pe
    ON t.transcript_id = pe.transcript_id
WHERE COALESCE(pe.expression_fold_change, 1.0) > 2.0
GROUP BY gp.pathway_id, gp.pathway_name
HAVING COUNT(DISTINCT g.gene_id) >= 5
ORDER BY gene_count DESC;
```

### Pattern 4: Publication Evidence Query

**v0.5.0 (Old)**:
```sql
-- Find publications for overexpressed genes
SELECT
    ctb.gene_symbol,
    ctb.expression_fold_change,
    gp.pmid,
    gp.mention_count
FROM cancer_transcript_base ctb
JOIN gene_publications gp ON ctb.gene_id = gp.gene_id
WHERE ctb.expression_fold_change > 3.0
ORDER BY ctb.expression_fold_change DESC, gp.mention_count DESC
LIMIT 50;
```

**v0.6.0 (New)**:
```sql
-- Find publications for overexpressed genes (patient-specific)
SELECT
    g.gene_symbol,
    MAX(COALESCE(pe.expression_fold_change, 1.0)) as max_fold_change,
    gp.pmid,
    gp.mention_count
FROM public.genes g
LEFT JOIN public.transcripts t ON g.gene_id = t.gene_id
LEFT JOIN patient_PATIENT123.expression_data pe
    ON t.transcript_id = pe.transcript_id
JOIN public.gene_publications gp ON g.gene_id = gp.gene_id
GROUP BY g.gene_symbol, gp.pmid, gp.mention_count
HAVING MAX(COALESCE(pe.expression_fold_change, 1.0)) > 3.0
ORDER BY max_fold_change DESC, gp.mention_count DESC
LIMIT 50;
```

---

## Automated Migration Utility

### Python Migration Script

Create `scripts/migrate_queries_v060.py`:

```python
#!/usr/bin/env python3
"""
Migrate v0.5.0 queries to v0.6.0 format.

Usage:
    python scripts/migrate_queries_v060.py --query-file old_query.sql --patient-id PATIENT123 --output new_query.sql
"""

import re
import argparse
from pathlib import Path


def migrate_query_v050_to_v060(query: str, patient_id: str) -> str:
    """
    Migrate a v0.5.0 query to v0.6.0 format.

    Args:
        query: SQL query string in v0.5.0 format
        patient_id: Patient identifier for schema qualification

    Returns:
        Migrated query string in v0.6.0 format
    """
    migrated = query

    # 1. Replace cancer_transcript_base references with proper joins
    if 'FROM cancer_transcript_base' in migrated:
        # This is a complex transformation - provide template
        print("WARNING: cancer_transcript_base migration requires manual review")
        print("         Replace with: public.genes + public.transcripts + patient_schema.expression_data")

    # 2. Add COALESCE around expression_fold_change references
    migrated = re.sub(
        r'\bexpression_fold_change\b',
        'COALESCE(expression_fold_change, 1.0)',
        migrated
    )

    # 3. Qualify table names with public schema
    for table in ['genes', 'transcripts', 'opentargets_known_drugs',
                  'gene_publications', 'gene_pathways', 'pubmed_metadata']:
        migrated = re.sub(
            rf'\bFROM\s+{table}\b',
            f'FROM public.{table}',
            migrated,
            flags=re.IGNORECASE
        )
        migrated = re.sub(
            rf'\bJOIN\s+{table}\b',
            f'JOIN public.{table}',
            migrated,
            flags=re.IGNORECASE
        )

    # 4. Add patient schema qualification comment
    header = f"""/*
 * MIGRATED TO v0.6.0 ARCHITECTURE
 * Patient Schema: patient_{patient_id}
 * Migration Date: {{date}}
 *
 * NOTE: This query has been automatically migrated from v0.5.0.
 *       Please review all COALESCE() expressions and table joins.
 */

"""

    return header + migrated


def main():
    parser = argparse.ArgumentParser(description='Migrate v0.5.0 queries to v0.6.0')
    parser.add_argument('--query-file', required=True, help='Input query file (v0.5.0)')
    parser.add_argument('--patient-id', required=True, help='Patient identifier')
    parser.add_argument('--output', required=True, help='Output query file (v0.6.0)')

    args = parser.parse_args()

    # Read old query
    query_file = Path(args.query_file)
    if not query_file.exists():
        print(f"ERROR: Query file not found: {query_file}")
        return 1

    query = query_file.read_text()

    # Migrate
    migrated_query = migrate_query_v050_to_v060(query, args.patient_id)

    # Write new query
    output_file = Path(args.output)
    output_file.write_text(migrated_query)

    print(f"SUCCESS: Migrated query written to {output_file}")
    print(f"         Please review the migrated query manually before use.")

    return 0


if __name__ == '__main__':
    exit(main())
```

---

## Common Migration Issues

### Issue 1: Missing COALESCE()

**Problem**: Queries return NULL for baseline transcripts instead of 1.0

**Solution**: Wrap all `expression_fold_change` references in `COALESCE(expression_fold_change, 1.0)`

### Issue 2: Ambiguous Table References

**Problem**: `ERROR: column reference "gene_id" is ambiguous`

**Solution**: Qualify all column references with table aliases:
```sql
-- Bad
WHERE gene_id = 'ENSG00000141510'

-- Good
WHERE g.gene_id = 'ENSG00000141510'
```

### Issue 3: Aggregation Without Grouping

**Problem**: `ERROR: column must appear in the GROUP BY clause`

**Solution**: Use MAX() aggregate for fold-change in GROUP BY queries:
```sql
SELECT
    g.gene_symbol,
    MAX(COALESCE(pe.expression_fold_change, 1.0)) as max_fold_change
FROM ...
GROUP BY g.gene_symbol
```

### Issue 4: Performance Degradation

**Problem**: Queries slower after migration

**Solution**: Add indexes on patient schema join columns:
```sql
-- Run once per patient schema
CREATE INDEX idx_expression_data_transcript_id
    ON patient_PATIENT123.expression_data(transcript_id);

CREATE INDEX idx_expression_data_fold_change
    ON patient_PATIENT123.expression_data(expression_fold_change)
    WHERE expression_fold_change IS NOT NULL;
```

---

## Testing Migrated Queries

### Validation Checklist

- [ ] Query connects to `mbase` database (not `mediabase_patient_*`)
- [ ] Patient schema is correctly qualified (`patient_<ID>.expression_data`)
- [ ] All core tables qualified with `public.` schema
- [ ] All `expression_fold_change` references use `COALESCE(..., 1.0)`
- [ ] LEFT JOIN used for patient expression data (not INNER JOIN)
- [ ] GROUP BY includes all selected columns except aggregates
- [ ] Query returns expected results for test patient schemas

### Test with Synthetic Patients

```bash
# Test HER2+ query with synthetic patient
PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U mbase_user -d mbase -c "
SELECT
    g.gene_symbol,
    MAX(COALESCE(pe.expression_fold_change, 1.0)) as max_fold_change
FROM public.genes g
LEFT JOIN public.transcripts t ON g.gene_id = t.gene_id
LEFT JOIN patient_synthetic_her2.expression_data pe
    ON t.transcript_id = pe.transcript_id
WHERE g.gene_symbol IN ('ERBB2', 'GRB7', 'PIK3CA')
GROUP BY g.gene_symbol
ORDER BY max_fold_change DESC;
"

# Expected results:
# ERBB2: ~5.51x
# GRB7: ~4.54x
# PIK3CA: ~2.51x
```

---

## Schema Detection Utility

To automatically detect which schema version your database uses:

```bash
# Run schema detection
poetry run python scripts/detect_schema_version.py --database mbase

# Expected output:
# Database: mbase
# Schema Version: v0.6.0 (Shared Core Architecture)
# Patient Schemas Found: 3
#   - patient_synthetic_her2
#   - patient_synthetic_tnbc
#   - patient_synthetic_luad
```

---

## Migration Timeline

| Phase | Task | Estimated Time |
|-------|------|----------------|
| **Phase 1** | Review existing queries | 30 minutes |
| **Phase 2** | Run migration utility | 15 minutes |
| **Phase 3** | Manual review and adjustments | 1-2 hours |
| **Phase 4** | Test with synthetic patients | 30 minutes |
| **Phase 5** | Validate with production data | 1-2 hours |

**Total**: 3-5 hours for typical query library

---

## Migration Support

### Resources

- **Migration Script**: `scripts/migrate_queries_v060.py`
- **Schema Detection**: `scripts/detect_schema_version.py`
- **Test Fixtures**: `tests/fixtures/expected_query_results.py`
- **Example Queries**: `docs/WORKING_QUERY_EXAMPLES.sql`
- **Cancer Guides**: `docs/queries/*.sql` (HER2+, TNBC, LUAD, CRC)

### Getting Help

If you encounter migration issues:

1. **Check Documentation**: [MEDIABASE_SCHEMA_REFERENCE.md](MEDIABASE_SCHEMA_REFERENCE.md)
2. **Review Examples**: [WORKING_QUERY_EXAMPLES.sql](WORKING_QUERY_EXAMPLES.sql)
3. **Run Tests**: `poetry run pytest tests/test_query_documentation.py`
4. **Ask for Help**: [GitHub Issues](https://github.com/itsatony/mediabase/issues)

---

**Version**: MEDIABASE v0.6.0
**Last Updated**: 2025-11-28
**Migration Complexity**: Medium (3-5 hours)
**Backward Compatibility**: None (breaking changes)


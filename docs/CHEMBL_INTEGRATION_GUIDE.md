# ChEMBL v35 Integration Guide

**Version:** 0.4.1 | **Last Updated:** 2025-11-20

## Overview

MEDIABASE v0.4.1 introduces comprehensive support for ChEMBL v35, the world's largest open-access bioactivity database. This guide provides complete documentation for integration, usage, and troubleshooting.

### ChEMBL v35 Statistics (Verified)

Based on production validation tests:
- **2,496,335** drug molecules
- **16,003** biological targets
- **2,474,590** compound structures
- **2,478,212** compound properties
- **55,442** drug indications
- **7,330** mechanism of action entries
- **14,836** target components
- **11,457** component sequences

## Architecture

### pg_restore Pattern

ChEMBL v35 uses a **temporary database extraction pattern** for optimal performance and isolation:

```
┌──────────────────────────────────────────────────┐
│ 1. Download ChEMBL v35 Archive                   │
│    chembl_35_postgresql.tar.gz (1.83GB)          │
└──────────────────┬───────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────┐
│ 2. Extract .dmp File                             │
│    chembl_35/chembl_35_postgresql.dmp            │
└──────────────────┬───────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────┐
│ 3. Create Temporary Database                     │
│    chembl_temp_35_{timestamp}                    │
└──────────────────┬───────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────┐
│ 4. Restore with pg_restore                       │
│    Duration: ~10 minutes                         │
└──────────────────┬───────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────┐
│ 5. Extract 12 Tables to CSV                      │
│    Duration: ~30 seconds                         │
└──────────────────┬───────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────┐
│ 6. Process CSV Files                             │
│    Load into MEDIABASE schema                    │
└──────────────────┬───────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────┐
│ 7. Cleanup Temporary Database                    │
│    Automatic cleanup after successful extraction │
└──────────────────────────────────────────────────┘
```

### Why This Architecture?

1. **Isolation**: Temporary database prevents conflicts with main database
2. **Performance**: Direct SQL queries faster than parsing SQL files
3. **Portability**: CSV exports can be cached and reused
4. **Reliability**: Automatic cleanup ensures no orphaned databases
5. **Reproducibility**: Timestamped databases enable parallel processing

## Setup Instructions

### Prerequisites

- PostgreSQL 12+ with pg_restore
- 10GB disk space (2GB archive + 8GB extracted data)
- Internet connection for initial download

### Quick Start

```bash
# Run ETL with ChEMBL v35
poetry run python scripts/run_etl.py --modules drugs --use-chembl

# First run: Downloads 1.83GB archive and extracts (10-12 min)
# Subsequent runs: Uses cached data (instant)
```

### Manual Setup

1. **Download ChEMBL v35**:
```bash
# Automatic (recommended)
poetry run python scripts/run_etl.py --modules drugs --use-chembl

# Manual download
wget ftp://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/releases/chembl_35/chembl_35_postgresql.tar.gz
mkdir -p /tmp/mediabase/cache/chembl_35
mv chembl_35_postgresql.tar.gz /tmp/mediabase/cache/chembl_35/
```

2. **Verify Download**:
```bash
# Check file size (should be ~1.83GB)
ls -lh /tmp/mediabase/cache/chembl_35/chembl_35_postgresql.tar.gz

# Check MD5 (optional)
md5sum /tmp/mediabase/cache/chembl_35/chembl_35_postgresql.tar.gz
```

3. **Run Import**:
```bash
MB_POSTGRES_HOST=localhost \
MB_POSTGRES_PORT=5432 \
MB_POSTGRES_NAME=mbase \
MB_POSTGRES_USER=postgres \
MB_POSTGRES_PASSWORD=yourpassword \
poetry run python scripts/run_etl.py --modules drugs --use-chembl --log-level INFO
```

## Schema Documentation

### Extracted Tables (12 total)

#### 1. molecule_dictionary
- **Rows**: 2,496,335
- **Purpose**: Core drug/compound information
- **Key Columns**:
  - `molregno`: Unique molecule identifier
  - `chembl_id`: ChEMBL ID (e.g., CHEMBL123)
  - `pref_name`: Preferred compound name
  - `max_phase`: Clinical development phase (0-4)
  - `molecule_type`: Type classification

#### 2. compound_structures
- **Rows**: 2,474,590
- **Purpose**: Chemical structure data
- **Key Columns**:
  - `molregno`: Links to molecule_dictionary
  - `canonical_smiles`: SMILES notation
  - `standard_inchi`: InChI identifier
  - `standard_inchi_key`: InChI hash key

#### 3. compound_properties
- **Rows**: 2,478,212
- **Purpose**: Physicochemical properties
- **Key Columns**:
  - `molregno`: Links to molecule_dictionary
  - `mw_freebase`: Molecular weight
  - `alogp`: Lipophilicity
  - `hba`: Hydrogen bond acceptors
  - `hbd`: Hydrogen bond donors

#### 4. target_dictionary
- **Rows**: 16,003
- **Purpose**: Biological target information
- **Key Columns**:
  - `tid`: Target identifier
  - `chembl_id`: ChEMBL target ID
  - `pref_name`: Target name
  - `target_type`: Classification
  - `organism`: Source organism

#### 5. target_components
- **Rows**: 14,836
- **Purpose**: Target component relationships
- **Key Columns**:
  - `tid`: Links to target_dictionary
  - `component_id`: Links to component_sequences
  - `targcomp_id`: Target component identifier

#### 6. component_sequences
- **Rows**: 11,457
- **Purpose**: Protein/gene sequences
- **Key Columns**:
  - `component_id`: Unique identifier
  - `component_type`: Type classification
  - `accession`: UniProt/RefSeq accession
  - `sequence`: Protein sequence

#### 7. drug_mechanism
- **Rows**: 7,330
- **Purpose**: Drug mechanism of action
- **Key Columns**:
  - `mec_id`: Mechanism identifier
  - `molregno`: Links to molecule_dictionary
  - `mechanism_of_action`: Description
  - `action_type`: Type of action
  - `tid`: Links to target_dictionary

**⚠️ Schema Note**: Column name remains `tid` (not changed to `toid` in v35)

#### 8. activities
- **Purpose**: Bioactivity data
- **Key Columns**:
  - `activity_id`: Unique identifier
  - `molregno`: Links to molecule_dictionary
  - `toid`: Target identifier (CHANGED in v35: was `tid`)
  - `standard_type`: Activity type
  - `standard_value`: Measured value
  - `standard_units`: Units

**⚠️ Schema Change**: v35 renamed `tid` → `toid` in this table only

#### 9. drug_indication
- **Rows**: 55,442
- **Purpose**: Clinical indications
- **Key Columns**:
  - `drugind_id`: Indication identifier
  - `molregno`: Links to molecule_dictionary
  - `mesh_id`: MeSH disease identifier
  - `mesh_heading`: Disease name
  - `max_phase_for_ind`: Clinical phase for indication

#### 10-12. Additional Tables
- binding_sites: Protein binding site data
- protein_classification: Protein family hierarchies
- mechanism_refs: Literature references

### Table Relationships

```
molecule_dictionary (molregno)
    ├── compound_structures (molregno)
    ├── compound_properties (molregno)
    ├── activities (molregno) ──> target_dictionary (toid)
    ├── drug_mechanism (molregno) ──> target_dictionary (tid)
    └── drug_indication (molregno)

target_dictionary (tid)
    └── target_components (tid) ──> component_sequences (component_id)
```

## Query Examples

### 1. Find Approved Drugs for a Gene

```sql
-- Find drugs targeting ERBB2 (HER2)
SELECT
    md.chembl_id,
    md.pref_name AS drug_name,
    md.max_phase AS clinical_phase,
    dm.mechanism_of_action,
    td.pref_name AS target_name
FROM molecule_dictionary md
INNER JOIN drug_mechanism dm ON md.molregno = dm.molregno
INNER JOIN target_dictionary td ON dm.tid = td.tid
INNER JOIN target_components tc ON td.tid = tc.tid
INNER JOIN component_sequences cs ON tc.component_id = cs.component_id
WHERE cs.accession IN (
    SELECT uniprot_id
    FROM genes
    WHERE gene_symbol = 'ERBB2'
)
AND md.max_phase = 4  -- Approved drugs only
ORDER BY md.pref_name;
```

### 2. Drugs in Clinical Trials for Cancer

```sql
-- Find drugs in Phase 2+ trials for cancer indications
SELECT
    md.chembl_id,
    md.pref_name AS drug_name,
    di.mesh_heading AS indication,
    di.max_phase_for_ind AS trial_phase,
    dm.mechanism_of_action
FROM molecule_dictionary md
INNER JOIN drug_indication di ON md.molregno = di.molregno
LEFT JOIN drug_mechanism dm ON md.molregno = dm.molregno
WHERE di.mesh_heading LIKE '%cancer%'
   OR di.mesh_heading LIKE '%carcinoma%'
   OR di.mesh_heading LIKE '%tumor%'
AND di.max_phase_for_ind >= 2
ORDER BY di.max_phase_for_ind DESC, md.pref_name;
```

### 3. Find Drug Targets with Known Mechanisms

```sql
-- Identify targetable proteins with multiple drugs
SELECT
    td.chembl_id AS target_chembl_id,
    td.pref_name AS target_name,
    td.target_type,
    COUNT(DISTINCT md.molregno) AS drug_count,
    STRING_AGG(DISTINCT md.pref_name, '; ') AS drug_names
FROM target_dictionary td
INNER JOIN drug_mechanism dm ON td.tid = dm.tid
INNER JOIN molecule_dictionary md ON dm.molregno = md.molregno
WHERE md.max_phase >= 2  -- Clinical phase 2+
GROUP BY td.chembl_id, td.pref_name, td.target_type
HAVING COUNT(DISTINCT md.molregno) >= 3
ORDER BY drug_count DESC;
```

### 4. Chemical Similarity Search

```sql
-- Find compounds similar to a reference drug
SELECT
    md.chembl_id,
    md.pref_name,
    cs.canonical_smiles,
    cp.mw_freebase AS molecular_weight,
    cp.alogp AS lipophilicity
FROM molecule_dictionary md
INNER JOIN compound_structures cs ON md.molregno = cs.molregno
INNER JOIN compound_properties cp ON md.molregno = cp.molregno
WHERE cp.mw_freebase BETWEEN 400 AND 600  -- Similar molecular weight
  AND cp.alogp BETWEEN 2 AND 4            -- Similar lipophilicity
  AND md.max_phase >= 1                    -- At least Phase 1
ORDER BY cp.mw_freebase, cp.alogp
LIMIT 100;
```

## Performance Metrics

### Extraction Times (Validated on Production System)

| Operation | Duration | Notes |
|-----------|----------|-------|
| Download archive | 17 seconds | 1.83GB at ~100MB/s |
| Extract .tar.gz | 5 seconds | Decompress to temp directory |
| pg_restore | 8min 50sec | Main bottleneck |
| Extract 12 tables | 38 seconds | Query + CSV export |
| Process CSVs | Variable | Depends on target schema |
| Cleanup | 2 seconds | Drop temporary database |
| **Total (first run)** | **~10 minutes** | One-time operation |
| **Subsequent runs** | **instant** | Uses cached CSVs |

### Resource Usage

- **Disk Space**:
  - Archive: 1.83GB
  - Extracted CSV files: ~3.5GB
  - Temporary database: ~4GB (auto-deleted)
  - Total cached: ~5.3GB
- **Memory**: ~2GB RAM during pg_restore
- **CPU**: Moderate usage during extraction, low during processing

### Cache Management

```bash
# Check cache size
du -sh /tmp/mediabase/cache/chembl_35/

# Clear cache to force re-extraction
rm -rf /tmp/mediabase/cache/chembl_35/

# Verify extraction integrity
ls -lh /tmp/mediabase/cache/chembl_35/extracted/*.csv
```

## ChEMBL vs DrugCentral Comparison

| Feature | ChEMBL v35 | DrugCentral |
|---------|-----------|-------------|
| **Drugs** | 2.5M+ | ~5K |
| **Clinical Phases** | 0-4 (all stages) | Approved only |
| **Targets** | 16K+ | ~2K |
| **Bioactivity Data** | Extensive | Limited |
| **Publications** | Comprehensive | Moderate |
| **Update Frequency** | Quarterly | Annual |
| **Size** | 1.83GB | ~50MB |
| **Setup Time** | ~10 min | ~2 min |
| **Best For** | Research, drug discovery | Clinical use, approved drugs |

### When to Use ChEMBL

✅ **Use ChEMBL when**:
- Need comprehensive drug-target data
- Researching early-stage drugs (Phase 0-2)
- Analyzing bioactivity relationships
- Building drug repurposing models
- Need extensive publication references

### When to Use DrugCentral

✅ **Use DrugCentral when**:
- Only need approved drugs
- Fast setup required
- Limited disk space
- Clinical decision support focus

### Using Both

```bash
# Import both databases (recommended for comprehensive coverage)
poetry run python scripts/run_etl.py --modules drugs --use-chembl
poetry run python scripts/run_etl.py --modules drugs  # Adds DrugCentral
```

## Troubleshooting

### Issue: pg_restore Fails

**Symptoms**:
```
ERROR: could not restore from custom format archive
```

**Solutions**:
1. Verify PostgreSQL version (need 12+):
   ```bash
   psql --version
   ```

2. Check disk space:
   ```bash
   df -h /tmp
   ```

3. Verify archive integrity:
   ```bash
   tar -tzf /tmp/mediabase/cache/chembl_35/chembl_35_postgresql.tar.gz | head
   ```

### Issue: Column "toid" Does Not Exist

**Symptoms**:
```
ERROR: column "toid" does not exist
HINT: Perhaps you meant to reference the column "drug_mechanism.tid"
```

**Solution**: This is expected! ChEMBL v35 schema changes:
- `activities` table: `tid` → `toid` (CHANGED)
- `drug_mechanism` table: stays as `tid` (UNCHANGED)

Make sure your queries use the correct column name for each table.

### Issue: Temporary Database Not Cleaned Up

**Symptoms**:
```
WARNING: Temporary database chembl_temp_35_* still exists
```

**Solution**: Manual cleanup:
```sql
-- List temporary databases
SELECT datname FROM pg_database WHERE datname LIKE 'chembl_temp_%';

-- Drop manually if needed
DROP DATABASE IF EXISTS chembl_temp_35_1234567890;
```

### Issue: Extraction Takes Too Long

**Symptoms**: pg_restore runs for >15 minutes

**Solutions**:
1. Check system resources:
   ```bash
   top -o %CPU
   iostat -x 1 5
   ```

2. Verify PostgreSQL not overloaded:
   ```sql
   SELECT * FROM pg_stat_activity;
   ```

3. Use SSD if available:
   ```bash
   export MB_CACHE_DIR=/path/to/ssd
   ```

### Issue: Out of Disk Space

**Symptoms**:
```
ERROR: could not extend file: No space left on device
```

**Solutions**:
1. Check disk usage:
   ```bash
   df -h
   du -sh /tmp/mediabase/cache/chembl_35/
   ```

2. Clear old extractions:
   ```bash
   rm -rf /tmp/mediabase/cache/chembl_35/extracted/
   ```

3. Use external storage:
   ```bash
   export MB_CACHE_DIR=/mnt/external/mediabase_cache
   ```

## Migration Notes

### Upgrading from v34 to v35

**Schema Changes**:
- `activities.tid` → `activities.toid`
- All other tables unchanged

**Code Updates Required**: NONE (handled automatically in v0.4.1)

**Data Migration**:
```bash
# Clear v34 cache
rm -rf /tmp/mediabase/cache/chembl_34/

# Import v35
poetry run python scripts/run_etl.py --modules drugs --use-chembl
```

### Backward Compatibility

- v0.4.1+ automatically handles v35 schema
- v0.3.x and earlier: use DrugCentral or upgrade
- No manual schema adjustments needed

## Advanced Usage

### Parallel Extraction

```bash
# Extract to multiple isolated databases
for i in {1..3}; do
    MB_POSTGRES_NAME=mbase_${i} \
    poetry run python scripts/run_etl.py --modules drugs --use-chembl &
done
wait
```

### Custom Table Selection

Edit `src/etl/chembl_drugs.py` line 380-395 to extract only needed tables:

```python
# Extract only essential tables
tables_to_extract = {
    "molecule_dictionary": ["molregno", "chembl_id", "pref_name", "max_phase"],
    "drug_mechanism": ["mec_id", "molregno", "mechanism_of_action", "tid"],
    "target_dictionary": ["tid", "chembl_id", "pref_name"],
}
```

### Monitoring Extraction

```bash
# Watch extraction progress
tail -f /tmp/mediabase/logs/chembl_extraction.log

# Monitor database size during restore
watch -n 5 'psql -c "SELECT pg_size_pretty(pg_database_size(current_database()));"'
```

## Support & Resources

### Official ChEMBL Resources
- **Website**: https://www.ebi.ac.uk/chembl/
- **Documentation**: https://chembl.gitbook.io/chembl-interface-documentation/
- **FTP Site**: ftp://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/releases/
- **Help Desk**: chembl-help@ebi.ac.uk

### MEDIABASE Resources
- **Issues**: https://github.com/your-repo/mediabase/issues
- **Discussions**: https://github.com/your-repo/mediabase/discussions
- **CHANGELOG**: [CHANGELOG.md](../CHANGELOG.md)
- **SOTA Queries**: [SOTA_QUERIES_GUIDE.md](SOTA_QUERIES_GUIDE.md)

### Citation

If you use ChEMBL in your research, please cite:

```
Davies M, Nowotka M, Papadatos G, Dedman N, Gaulton A, Atkinson F, Bellis L,
Overington JP. (2015) 'ChEMBL web services: streamlining access to drug
discovery data and utilities.' Nucleic Acids Res., 43(W1):W612-W620.
DOI: 10.1093/nar/gkv352
```

---

**Document Version**: 1.0
**Last Validated**: 2025-11-20 with MEDIABASE v0.4.1
**ChEMBL Version**: v35 (2024-2025 release)

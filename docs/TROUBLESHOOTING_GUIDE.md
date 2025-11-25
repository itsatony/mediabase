# MEDIABASE Troubleshooting Guide

**Version:** 1.0.0
**Database Version:** v0.6.0.2
**Last Updated:** 2025-11-25

Comprehensive troubleshooting guide for common issues in MEDIABASE, with emphasis on v0.6.0.2 PMID evidence integration and performance optimization.

---

## Table of Contents

1. [Quick Diagnostic Checklist](#quick-diagnostic-checklist)
2. [Database Connection Issues](#database-connection-issues)
3. [Query Performance Problems](#query-performance-problems)
4. [PMID Evidence Integration Issues](#pmid-evidence-integration-issues)
5. [Patient Schema Issues](#patient-schema-issues)
6. [ETL Pipeline Errors](#etl-pipeline-errors)
7. [Memory and Resource Issues](#memory-and-resource-issues)
8. [Data Integrity Problems](#data-integrity-problems)
9. [API Server Issues](#api-server-issues)
10. [Common Query Errors](#common-query-errors)
11. [Index and Performance Optimization](#index-and-performance-optimization)
12. [Backup and Restore Issues](#backup-and-restore-issues)

---

## Quick Diagnostic Checklist

Before diving into specific issues, run this diagnostic checklist:

```bash
# 1. Check database connection
PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U mbase_user -d mbase -c "\conninfo"

# 2. Verify database version
PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U mbase_user -d mbase -c "SELECT version();"

# 3. Check table sizes
PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U mbase_user -d mbase -c "
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
    pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) AS table_size,
    pg_size_pretty(pg_indexes_size(schemaname||'.'||tablename)) AS indexes_size
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
LIMIT 10;
"

# 4. Check critical indexes exist
PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U mbase_user -d mbase -c "
SELECT
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN ('gene_publications', 'genes', 'transcripts', 'opentargets_known_drugs')
ORDER BY tablename, indexname;
"

# 5. Verify gene_publications data
PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U mbase_user -d mbase -c "
SELECT
    COUNT(*) as total_rows,
    COUNT(DISTINCT gene_id) as unique_genes,
    COUNT(DISTINCT pmid) as unique_pmids,
    MIN(mention_count) as min_mentions,
    MAX(mention_count) as max_mentions,
    AVG(mention_count)::int as avg_mentions
FROM gene_publications;
"
```

**Expected Results:**
- Database connection: `You are connected to database "mbase"`
- PostgreSQL version: `12+`
- gene_publications: ~47.4M rows, ~20K unique genes, ~36M unique PMIDs
- Critical indexes: `idx_gene_publications_gene_id`, `idx_genes_id`, `idx_transcripts_gene_id`

---

## Database Connection Issues

### Issue 1: "FATAL: password authentication failed"

**Symptoms:**
```
psql: error: connection to server at "localhost" (127.0.0.1), port 5435 failed: FATAL: password authentication failed for user "mbase_user"
```

**Diagnosis:**
```bash
# Check if database is running
systemctl status postgresql

# Check if database is listening on port 5435
ss -tuln | grep 5435

# Try default credentials
PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U mbase_user -d mbase -c "\conninfo"
```

**Solutions:**

1. **Verify credentials in .env file:**
   ```bash
   cat .env | grep MB_POSTGRES
   ```

2. **Reset PostgreSQL password:**
   ```sql
   -- As postgres user
   ALTER USER mbase_user WITH PASSWORD 'mbase_secret';
   ```

3. **Check pg_hba.conf authentication:**
   ```bash
   # Find pg_hba.conf location
   sudo -u postgres psql -c "SHOW hba_file;"

   # Ensure host authentication allows password
   # Add line to pg_hba.conf:
   # host    mbase    mbase_user    127.0.0.1/32    md5

   # Reload PostgreSQL
   sudo systemctl reload postgresql
   ```

### Issue 2: "could not connect to server: Connection refused"

**Symptoms:**
```
psql: error: connection to server at "localhost" (127.0.0.1), port 5435 failed: Connection refused
Is the server running on that host and accepting TCP/IP connections?
```

**Diagnosis:**
```bash
# Check if PostgreSQL is running
systemctl status postgresql

# Check which port PostgreSQL is using
sudo -u postgres psql -c "SHOW port;"

# Check listening ports
ss -tuln | grep postgres
```

**Solutions:**

1. **Start PostgreSQL if not running:**
   ```bash
   sudo systemctl start postgresql
   sudo systemctl enable postgresql  # Auto-start on boot
   ```

2. **Verify port configuration in postgresql.conf:**
   ```bash
   # Find postgresql.conf location
   sudo -u postgres psql -c "SHOW config_file;"

   # Edit and set:
   # port = 5435
   # listen_addresses = 'localhost'

   # Restart PostgreSQL
   sudo systemctl restart postgresql
   ```

3. **Check firewall rules:**
   ```bash
   # Allow PostgreSQL port (if remote connections needed)
   sudo ufw allow 5435/tcp
   ```

### Issue 3: "database 'mbase' does not exist"

**Symptoms:**
```
psql: error: connection to server at "localhost" (127.0.0.1), port 5435 failed: FATAL: database "mbase" does not exist
```

**Solutions:**

1. **Create database:**
   ```bash
   poetry run python scripts/manage_db.py --create-db
   ```

2. **Apply schema:**
   ```bash
   poetry run python scripts/manage_db.py --apply-schema
   ```

3. **Verify database exists:**
   ```bash
   PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U mbase_user -d postgres -c "\l" | grep mbase
   ```

---

## Query Performance Problems

### Issue 1: Queries with gene_publications taking >10 seconds

**Symptoms:**
- Drug discovery queries timeout
- EXPLAIN ANALYZE shows `Seq Scan on gene_publications`
- Query plan estimates 47M rows scanned

**Diagnosis:**
```sql
EXPLAIN ANALYZE
SELECT
    g.gene_symbol,
    COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count
FROM genes g
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
WHERE g.gene_symbol = 'ERBB2'
GROUP BY g.gene_symbol;
```

**Look for:**
- `Seq Scan on gene_publications` (BAD - 45+ seconds)
- `Index Scan using idx_gene_publications_gene_id` (GOOD - <500ms)

**Solutions:**

1. **Create missing indexes:**
   ```sql
   -- Primary index for gene_id lookup
   CREATE INDEX IF NOT EXISTS idx_gene_publications_gene_id
   ON gene_publications(gene_id);

   -- Composite index for COUNT(DISTINCT pmid) optimization
   CREATE INDEX IF NOT EXISTS idx_gene_publications_gene_pmid
   ON gene_publications(gene_id, pmid);

   -- Rebuild indexes if corrupted
   REINDEX INDEX idx_gene_publications_gene_id;
   REINDEX INDEX idx_gene_publications_gene_pmid;
   ```

2. **Update table statistics:**
   ```sql
   ANALYZE gene_publications;
   ANALYZE genes;
   ANALYZE opentargets_known_drugs;
   ```

3. **Use materialized view for repeated queries:**
   ```sql
   -- Create pre-aggregated publication counts
   CREATE MATERIALIZED VIEW mv_gene_publication_counts AS
   SELECT
       gene_id,
       COUNT(DISTINCT pmid) as publication_count,
       SUM(mention_count) as total_mentions,
       CASE
           WHEN COUNT(DISTINCT pmid) >= 100000 THEN 'Extensively studied'
           WHEN COUNT(DISTINCT pmid) >= 10000 THEN 'Well-studied'
           WHEN COUNT(DISTINCT pmid) >= 1000 THEN 'Moderate evidence'
           ELSE 'Limited publications'
       END as evidence_level
   FROM gene_publications
   GROUP BY gene_id;

   CREATE INDEX idx_mv_gene_pub_counts_gene_id ON mv_gene_publication_counts(gene_id);

   -- Refresh monthly (when PubTator Central updates)
   REFRESH MATERIALIZED VIEW mv_gene_publication_counts;
   ```

4. **Increase work_mem for session:**
   ```sql
   -- Temporary increase for single session
   SET work_mem = '256MB';

   -- Run your query
   SELECT ...;

   -- Reset to default
   RESET work_mem;
   ```

**Prevention:**
- Always verify indexes exist after ETL completion
- Run `ANALYZE` after large data loads
- Consider materialized views for production queries

### Issue 2: "out of memory" error during aggregation

**Symptoms:**
```
ERROR: out of memory
DETAIL: Cannot enlarge string buffer containing 500000000 bytes by 12345 more bytes.
HINT: You may need to increase work_mem.
```

**Diagnosis:**
```sql
-- Check current work_mem
SHOW work_mem;

-- Check query memory usage estimate
EXPLAIN (ANALYZE, BUFFERS)
SELECT ...;  -- Look for "Memory: used" in output
```

**Solutions:**

1. **Increase work_mem (session-level):**
   ```sql
   SET work_mem = '512MB';  -- Increase from default 4MB
   ```

2. **Filter earlier to reduce candidate set:**
   ```sql
   -- BAD: Aggregates all 47M rows then filters
   SELECT g.gene_symbol, COUNT(DISTINCT gp.pmid) as pub_count
   FROM genes g
   LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
   GROUP BY g.gene_symbol
   HAVING COUNT(DISTINCT gp.pmid) > 1000;

   -- GOOD: Filters genes first (reduces JOIN size)
   WITH target_genes AS (
       SELECT gene_id, gene_symbol
       FROM genes
       WHERE gene_symbol IN ('ERBB2', 'TP53', 'EGFR')  -- Only 3 genes
   )
   SELECT tg.gene_symbol, COUNT(DISTINCT gp.pmid) as pub_count
   FROM target_genes tg
   LEFT JOIN gene_publications gp ON tg.gene_id = gp.gene_id
   GROUP BY tg.gene_symbol;
   ```

3. **Use batch processing for large result sets:**
   ```bash
   # See "Query Optimization Guide" > "Memory Optimization" > "Solution 2"
   ```

4. **Adjust PostgreSQL configuration (permanent):**
   ```bash
   # Edit postgresql.conf
   sudo -u postgres psql -c "SHOW config_file;"

   # Add/modify:
   # work_mem = 256MB
   # max_parallel_workers_per_gather = 4

   # Restart PostgreSQL
   sudo systemctl restart postgresql
   ```

**Caution:** Setting work_mem too high with many concurrent queries risks exhausting total system memory.

### Issue 3: Wrong query plan selected (Planner chooses Seq Scan despite index)

**Symptoms:**
- Index exists but not used
- EXPLAIN shows `Seq Scan` instead of `Index Scan`
- Query slow despite proper indexing

**Diagnosis:**
```sql
-- Check index usage statistics
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan as index_scans,
    idx_tup_read as tuples_read,
    idx_tup_fetch as tuples_fetched
FROM pg_stat_user_indexes
WHERE tablename = 'gene_publications'
ORDER BY idx_scan DESC;

-- Check table statistics age
SELECT
    schemaname,
    tablename,
    last_analyze,
    last_autoanalyze,
    n_live_tup as live_rows,
    n_dead_tup as dead_rows
FROM pg_stat_user_tables
WHERE tablename = 'gene_publications';
```

**Solutions:**

1. **Update table statistics:**
   ```sql
   ANALYZE gene_publications;
   ANALYZE genes;
   ```

2. **Increase statistics target (if table is large):**
   ```sql
   ALTER TABLE gene_publications ALTER COLUMN gene_id SET STATISTICS 1000;
   ANALYZE gene_publications;
   ```

3. **Force index usage (temporary workaround):**
   ```sql
   SET enable_seqscan = OFF;
   -- Run your query
   SELECT ...;
   RESET enable_seqscan;
   ```

4. **Check if index is valid:**
   ```sql
   SELECT
       tablename,
       indexname,
       indexdef,
       pg_size_pretty(pg_relation_size(indexname::regclass)) as index_size
   FROM pg_indexes
   WHERE tablename = 'gene_publications'
     AND indexname = 'idx_gene_publications_gene_id';

   -- Rebuild if needed
   REINDEX INDEX idx_gene_publications_gene_id;
   ```

---

## PMID Evidence Integration Issues

### Issue 1: publication_count returns NULL instead of 0

**Symptoms:**
```sql
-- Query returns NULL for genes without publications
gene_symbol | publication_count
------------+-------------------
OBSCURE123  | NULL
```

**Root Cause:** Missing `COALESCE()` wrapper around `COUNT()` with LEFT JOIN.

**Solution:**
```sql
-- WRONG: Returns NULL
SELECT
    g.gene_symbol,
    COUNT(DISTINCT gp.pmid) as publication_count
FROM genes g
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
GROUP BY g.gene_symbol;

-- CORRECT: Returns 0 for genes without publications
SELECT
    g.gene_symbol,
    COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count
FROM genes g
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
GROUP BY g.gene_symbol;
```

### Issue 2: Genes with publications excluded from results

**Symptoms:**
- Query returns fewer genes than expected
- High-priority genes missing from drug discovery results

**Root Cause:** Using `INNER JOIN` instead of `LEFT JOIN` for gene_publications.

**Solution:**
```sql
-- WRONG: Excludes genes without publications
SELECT g.gene_symbol, COUNT(DISTINCT gp.pmid) as pub_count
FROM genes g
INNER JOIN gene_publications gp ON g.gene_id = gp.gene_id  -- ❌ INNER JOIN
GROUP BY g.gene_symbol;

-- CORRECT: Includes all genes, even those with 0 publications
SELECT g.gene_symbol, COALESCE(COUNT(DISTINCT gp.pmid), 0) as pub_count
FROM genes g
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id  -- ✅ LEFT JOIN
GROUP BY g.gene_symbol;
```

### Issue 3: Publication count overcounted (mentions vs PMIDs)

**Symptoms:**
- Gene has 5,000 publications but only ~1,000 unique papers
- TP53 shows 150K publications instead of 125K

**Root Cause:** Using `COUNT(gp.pmid)` instead of `COUNT(DISTINCT gp.pmid)`.

**Explanation:** gene_publications table has multiple rows per PMID (one per mention_count), so non-DISTINCT counts include duplicates.

**Solution:**
```sql
-- WRONG: Overcounts (includes multiple mention_count rows per PMID)
SELECT g.gene_symbol, COUNT(gp.pmid) as pub_count
FROM genes g
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
GROUP BY g.gene_symbol;

-- CORRECT: Counts unique PMIDs only
SELECT g.gene_symbol, COALESCE(COUNT(DISTINCT gp.pmid), 0) as pub_count
FROM genes g
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
GROUP BY g.gene_symbol;
```

### Issue 4: Evidence level categorization incorrect

**Symptoms:**
- TP53 (125K publications) shows as 'Well-studied' instead of 'Extensively studied'
- Thresholds seem off

**Root Cause:** Evidence level CASE statement has wrong order or missing DISTINCT.

**Solution:**
```sql
-- Correct evidence level categorization (v0.6.0.2 standard)
CASE
    WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
    WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
    WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
    ELSE 'Limited publications'
END as evidence_level
```

**Verification Query:**
```sql
SELECT
    g.gene_symbol,
    COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
    CASE
        WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
        WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
        ELSE 'Limited publications'
    END as evidence_level
FROM genes g
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
WHERE g.gene_symbol IN ('TP53', 'EGFR', 'ERBB2')
GROUP BY g.gene_symbol
ORDER BY publication_count DESC;

-- Expected results:
-- TP53:   125K+ publications → 'Extensively studied'
-- EGFR:   90K+ publications  → 'Well-studied'
-- ERBB2:  80K+ publications  → 'Well-studied'
```

---

## Patient Schema Issues

### Issue 1: Patient query returns 0 rows (should return results)

**Symptoms:**
- Query on `patient_PATIENT123` schema returns 0 rows
- Same query on public schema returns expected results
- Overexpressed genes not detected

**Root Cause:** Using INNER JOIN on sparse patient expression_data instead of LEFT JOIN with COALESCE.

**Explanation:** Patient schemas only store non-baseline expression values (fold_change ≠ 1.0), so INNER JOIN excludes 99.75% of genes.

**Solution:**
```sql
-- WRONG: Returns 0 rows for baseline genes (fold_change = 1.0)
SELECT
    g.gene_symbol,
    pe.expression_fold_change as fold_change
FROM patient_PATIENT123.expression_data pe  -- ❌ Starting from patient table
INNER JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
JOIN public.genes g ON t.gene_id = g.gene_id
WHERE pe.expression_fold_change > 2.0;

-- CORRECT: Returns all genes with COALESCE for baseline expression
SELECT
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change
FROM public.transcripts t
LEFT JOIN patient_PATIENT123.expression_data pe ON t.transcript_id = pe.transcript_id  -- ✅ LEFT JOIN
JOIN public.genes g ON t.gene_id = g.gene_id
WHERE COALESCE(pe.expression_fold_change, 1.0) > 2.0;
```

**Key Pattern:**
1. Start FROM `public.transcripts` (complete gene set)
2. LEFT JOIN to `patient_X.expression_data` (sparse patient data)
3. Use `COALESCE(pe.expression_fold_change, 1.0)` for baseline genes

### Issue 2: Missing patient schema after create_patient_copy.py

**Symptoms:**
```
ERROR: schema "patient_PATIENT123" does not exist
```

**Diagnosis:**
```bash
# Check if schema exists
PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U mbase_user -d mbase -c "\dn" | grep patient_

# Check create_patient_copy.py logs for errors
tail -50 /tmp/create_patient_copy.log
```

**Solutions:**

1. **Re-run patient copy script:**
   ```bash
   poetry run python scripts/create_patient_copy.py \
     --patient-id PATIENT123 \
     --csv-file patient_data.csv \
     --source-db mbase
   ```

2. **Verify CSV file format:**
   ```bash
   # Check CSV headers
   head -1 patient_data.csv

   # Should contain either:
   # - transcript_id, cancer_fold
   # - SYMBOL, log2FoldChange
   # - gene_symbol, expression_fold_change
   ```

3. **Check database permissions:**
   ```sql
   -- As postgres user
   GRANT CREATE ON DATABASE mbase TO mbase_user;
   GRANT USAGE, CREATE ON SCHEMA patient_PATIENT123 TO mbase_user;
   ```

### Issue 3: Patient expression_fold_change values all 1.0

**Symptoms:**
- Patient schema exists but all genes show fold_change = 1.0
- Query returns all genes, no differential expression detected

**Diagnosis:**
```sql
-- Check patient expression_data table
SELECT
    COUNT(*) as total_rows,
    COUNT(DISTINCT transcript_id) as unique_transcripts,
    MIN(expression_fold_change) as min_fc,
    MAX(expression_fold_change) as max_fc,
    AVG(expression_fold_change) as avg_fc
FROM patient_PATIENT123.expression_data;

-- Check for non-baseline expression
SELECT COUNT(*) as non_baseline_rows
FROM patient_PATIENT123.expression_data
WHERE expression_fold_change <> 1.0;
```

**Expected Results:**
- total_rows: 100-500 (sparse storage, only non-baseline)
- non_baseline_rows: Should equal total_rows (all stored values ≠ 1.0)

**If all values = 1.0, this indicates CSV was not properly loaded.**

**Solutions:**

1. **Verify CSV data integrity:**
   ```bash
   # Check for fold-change values in CSV
   awk -F',' 'NR > 1 {print $2}' patient_data.csv | sort -u | head -20

   # Should show various fold-change values, not just 1.0
   ```

2. **Check log2FoldChange conversion:**
   ```bash
   # If CSV has log2FoldChange, script should auto-convert
   # log2(2.0) = 1.0  → fold_change = 2.0
   # log2(4.0) = 2.0  → fold_change = 4.0
   # log2(0.5) = -1.0 → fold_change = 0.5
   ```

3. **Re-run with --dry-run to debug:**
   ```bash
   poetry run python scripts/create_patient_copy.py \
     --patient-id PATIENT123 \
     --csv-file patient_data.csv \
     --source-db mbase \
     --dry-run
   ```

---

## ETL Pipeline Errors

### Issue 1: "Module pubtator failed: tqdm AttributeError"

**Symptoms:**
```
AttributeError: 'tqdm' object has no attribute 'write'
Module pubtator failed
```

**Root Cause:** Monkey-patching conflict with tqdm progress bars.

**Solution:** Already fixed in v0.6.0.2, but if you encounter this:

```python
# Avoid monkey-patching tqdm
# Use tqdm directly without modifications
from tqdm import tqdm

# If using with file parsing:
with open(file_path, 'r') as f:
    for line in tqdm(f, desc="Parsing", unit=" lines"):
        # process line
        pass
```

### Issue 2: "Module opentargets failed: numpy types not JSON serializable"

**Symptoms:**
```
TypeError: Object of type 'float64' is not JSON serializable
Module opentargets failed
```

**Solution:** Convert numpy types to Python native types before database insertion:

```python
# Convert numpy types in ETL processor
def convert_numpy_types(data: dict) -> dict:
    """Convert numpy types to native Python types."""
    import numpy as np
    converted = {}
    for key, value in data.items():
        if isinstance(value, (np.integer, np.int64, np.int32)):
            converted[key] = int(value)
        elif isinstance(value, (np.floating, np.float64, np.float32)):
            converted[key] = float(value)
        elif isinstance(value, np.ndarray):
            converted[key] = value.tolist()
        else:
            converted[key] = value
    return converted
```

### Issue 3: ETL hangs at specific module without error

**Symptoms:**
- ETL process stops responding
- No ERROR in logs, just stops mid-processing
- CPU usage drops to 0%

**Diagnosis:**
```bash
# Check if ETL process is running
ps aux | grep run_etl.py

# Check last log entries
tail -50 /tmp/etl.log

# Check database locks
PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U mbase_user -d mbase -c "
SELECT
    pid,
    usename,
    application_name,
    state,
    query
FROM pg_stat_activity
WHERE datname = 'mbase'
  AND state <> 'idle';
"
```

**Solutions:**

1. **Kill hung process and restart:**
   ```bash
   # Find PID
   ps aux | grep run_etl.py | awk '{print $2}'

   # Kill process
   kill -9 <PID>

   # Restart ETL
   poetry run python scripts/run_etl.py --log-level DEBUG
   ```

2. **Check for deadlocks:**
   ```sql
   SELECT * FROM pg_locks WHERE NOT granted;
   ```

3. **Increase timeout for long-running operations:**
   ```bash
   # Edit src/db/database.py
   # Set connection timeout:
   self.connection = psycopg2.connect(..., connect_timeout=300)
   ```

### Issue 4: "Module X depends on Y which is not complete"

**Symptoms:**
```
ERROR: Module 'drugs' depends on module 'id_enrichment' which is not complete
Pipeline failed
```

**Root Cause:** Running ETL modules out of dependency order.

**Solution:**
```bash
# Always run modules in correct dependency order:
# 1. transcripts (no dependencies)
# 2. id_enrichment (needs transcripts)
# 3. go_terms (needs transcripts)
# 4. products (needs transcripts, id_enrichment)
# 5. pathways (needs transcripts, id_enrichment)
# 6. drugs (needs all above)
# 7. pubtator (needs transcripts, id_enrichment)
# 8. opentargets (needs transcripts, id_enrichment)
# 9. publications (needs all above)

# Run complete ETL in correct order
poetry run python scripts/run_etl.py --reset-db --log-level INFO

# Or specify modules in dependency order
poetry run python scripts/run_etl.py --modules transcripts id_enrichment drugs --log-level INFO
```

---

## Memory and Resource Issues

### Issue 1: System runs out of memory during pubtator module

**Symptoms:**
```
Killed
# or
MemoryError: Unable to allocate X GB for array
```

**Diagnosis:**
```bash
# Check available memory
free -h

# Check swap usage
swapon --show

# Monitor memory during ETL
watch -n 5 'free -h && ps aux | grep python | head -5'
```

**Solutions:**

1. **Reduce batch size in pubtator processor:**
   ```python
   # Edit src/etl/pubtator.py
   BATCH_SIZE = 5000  # Reduce from 10000 to 5000
   ```

2. **Enable swap if not configured:**
   ```bash
   # Create 8GB swap file
   sudo fallocate -l 8G /swapfile
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile
   sudo swapon /swapfile

   # Make permanent
   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   ```

3. **Process in smaller chunks:**
   ```bash
   # Run ETL with limited transcripts first
   poetry run python scripts/run_etl.py --limit-transcripts 1000 --log-level INFO

   # Then run full ETL
   poetry run python scripts/run_etl.py --modules pubtator --log-level INFO
   ```

4. **Increase system memory (if possible)** or run on machine with more RAM (16GB+ recommended for full ETL).

### Issue 2: Database disk space exhausted

**Symptoms:**
```
ERROR: could not extend file "base/16384/12345": No space left on device
```

**Diagnosis:**
```bash
# Check disk usage
df -h /var/lib/postgresql

# Check database size
PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U mbase_user -d mbase -c "
SELECT pg_database.datname, pg_size_pretty(pg_database_size(pg_database.datname)) AS size
FROM pg_database;
"
```

**Solutions:**

1. **Clean up old backups:**
   ```bash
   # Find old backups
   find backups/ -name "*.sql" -mtime +30 -ls

   # Delete backups older than 30 days
   find backups/ -name "*.sql" -mtime +30 -delete
   ```

2. **Vacuum database to reclaim space:**
   ```sql
   VACUUM FULL;  -- Reclaims space but locks tables
   -- or
   VACUUM;  -- Reclaims space without locks (slower)
   ```

3. **Move PostgreSQL data directory to larger disk:**
   ```bash
   # Stop PostgreSQL
   sudo systemctl stop postgresql

   # Copy data directory
   sudo rsync -av /var/lib/postgresql /mnt/larger_disk/

   # Update postgresql.conf
   sudo nano /etc/postgresql/12/main/postgresql.conf
   # data_directory = '/mnt/larger_disk/postgresql/12/main'

   # Start PostgreSQL
   sudo systemctl start postgresql
   ```

4. **Drop unnecessary indexes temporarily:**
   ```sql
   -- Drop non-critical indexes during ETL
   DROP INDEX IF EXISTS idx_gene_publications_mention_count;

   -- Recreate after ETL completion
   CREATE INDEX idx_gene_publications_mention_count
   ON gene_publications(gene_id, mention_count)
   WHERE mention_count > 5;
   ```

---

## Data Integrity Problems

### Issue 1: Missing genes in gene_publications after ETL

**Symptoms:**
- TP53, EGFR, ERBB2 not found in gene_publications
- Query returns 0 publications for known high-publication genes

**Diagnosis:**
```sql
-- Check if genes exist in genes table
SELECT gene_id, gene_symbol FROM genes WHERE gene_symbol IN ('TP53', 'EGFR', 'ERBB2');

-- Check if genes have publications
SELECT
    g.gene_symbol,
    COUNT(DISTINCT gp.pmid) as pub_count
FROM genes g
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
WHERE g.gene_symbol IN ('TP53', 'EGFR', 'ERBB2')
GROUP BY g.gene_symbol;
```

**Solutions:**

1. **Re-run pubtator module:**
   ```bash
   poetry run python scripts/run_etl.py --modules pubtator --log-level INFO
   ```

2. **Check gene_id mappings:**
   ```sql
   -- Verify gene_id format matches between tables
   SELECT 'genes' as table_name, gene_id FROM genes LIMIT 5
   UNION ALL
   SELECT 'gene_publications', gene_id FROM gene_publications LIMIT 5;

   -- Should show consistent format (e.g., "ENSG00000141510" for TP53)
   ```

3. **Check ETL logs for errors:**
   ```bash
   grep -i "error\|failed" /tmp/etl.log | tail -50
   ```

### Issue 2: Pathway enrichment returns empty results

**Symptoms:**
- gene_pathways table empty
- Pathway queries return 0 rows

**Diagnosis:**
```sql
-- Check gene_pathways population
SELECT COUNT(*) FROM gene_pathways;

-- Check NCBI ID mappings (required for pathways)
SELECT COUNT(*) FROM gene_cross_references WHERE external_db = 'GeneID';
```

**Expected Results:**
- gene_pathways: ~113K rows
- gene_cross_references (GeneID): ~167 rows

**Solutions:**

1. **Re-run pathways module:**
   ```bash
   poetry run python scripts/run_etl.py --modules pathways --log-level INFO
   ```

2. **Verify id_enrichment completed:**
   ```bash
   # Check id_enrichment module status
   PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U mbase_user -d mbase -c "
   SELECT
       external_db,
       COUNT(*) as count
   FROM gene_cross_references
   GROUP BY external_db
   ORDER BY count DESC;
   "
   ```

3. **Check Reactome file download:**
   ```bash
   ls -lh /tmp/mediabase/cache/reactome/
   # Should contain: Ensembl2Reactome_All_Levels.txt
   ```

---

## API Server Issues

### Issue 1: "Address already in use" when starting API server

**Symptoms:**
```
OSError: [Errno 98] Address already in use
```

**Diagnosis:**
```bash
# Check if port 8000 is in use
ss -tuln | grep 8000

# Find process using port 8000
lsof -i :8000
```

**Solutions:**

1. **Kill existing server:**
   ```bash
   # Find PID
   lsof -i :8000 | awk 'NR>1 {print $2}' | xargs kill -9
   ```

2. **Use different port:**
   ```bash
   # Start API server on alternative port
   PORT=8001 poetry run python -m src.api.server
   ```

3. **Wait for port release (if just stopped server):**
   ```bash
   # Wait 30 seconds for TIME_WAIT state to clear
   sleep 30
   poetry run python -m src.api.server
   ```

### Issue 2: API returns 500 Internal Server Error for patient queries

**Symptoms:**
```
GET /api/v1/transcripts?patient_id=PATIENT123&gene_symbols=ERBB2
Response: 500 Internal Server Error
```

**Diagnosis:**
```bash
# Check API server logs
tail -50 /var/log/mediabase/api.log

# Test database connection from API
PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U mbase_user -d mbase -c "\conninfo"
```

**Solutions:**

1. **Verify patient schema exists:**
   ```sql
   SELECT nspname FROM pg_namespace WHERE nspname LIKE 'patient_%';
   ```

2. **Check API server environment variables:**
   ```bash
   # Verify .env file loaded
   cat .env | grep MB_POSTGRES

   # Restart API server with explicit env
   MB_POSTGRES_HOST=localhost \
   MB_POSTGRES_PORT=5435 \
   MB_POSTGRES_NAME=mbase \
   MB_POSTGRES_USER=mbase_user \
   MB_POSTGRES_PASSWORD=mbase_secret \
   poetry run python -m src.api.server
   ```

3. **Test query directly in database:**
   ```sql
   -- Test patient query SQL
   SELECT
       g.gene_symbol,
       COALESCE(pe.expression_fold_change, 1.0) as fold_change
   FROM public.transcripts t
   LEFT JOIN patient_PATIENT123.expression_data pe ON t.transcript_id = pe.transcript_id
   JOIN public.genes g ON t.gene_id = g.gene_id
   WHERE g.gene_symbol = 'ERBB2'
   LIMIT 10;
   ```

---

## Common Query Errors

### Issue 1: "column must appear in GROUP BY clause"

**Symptoms:**
```sql
ERROR: column "okd.molecule_name" must appear in the GROUP BY clause or be used in an aggregate function
```

**Root Cause:** Non-aggregated column in SELECT but not in GROUP BY.

**Solution:**
```sql
-- WRONG: molecule_name not in GROUP BY
SELECT
    g.gene_symbol,
    okd.molecule_name,  -- ❌ Not in GROUP BY
    COUNT(DISTINCT gp.pmid) as pub_count
FROM genes g
JOIN opentargets_known_drugs okd ON g.gene_id = okd.target_gene_id
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
GROUP BY g.gene_symbol;

-- CORRECT: All non-aggregated columns in GROUP BY
SELECT
    g.gene_symbol,
    okd.molecule_name,
    COUNT(DISTINCT gp.pmid) as pub_count
FROM genes g
JOIN opentargets_known_drugs okd ON g.gene_id = okd.target_gene_id
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
GROUP BY g.gene_symbol, okd.molecule_name;  -- ✅ Complete GROUP BY
```

**General Rule:** Every column in SELECT (except aggregates like COUNT, SUM, AVG) must appear in GROUP BY clause.

### Issue 2: "relation 'cancer_transcript_base' does not exist"

**Symptoms:**
```sql
ERROR: relation "cancer_transcript_base" does not exist
LINE 1: SELECT * FROM cancer_transcript_base;
```

**Root Cause:** Attempting to query legacy table name or patient-specific table without schema qualifier.

**Solutions:**

1. **Use v0.6.0 architecture pattern:**
   ```sql
   -- WRONG: cancer_transcript_base only exists in patient schemas
   SELECT * FROM cancer_transcript_base;

   -- CORRECT: Query public tables with patient schema LEFT JOIN
   SELECT
       g.gene_symbol,
       COALESCE(pe.expression_fold_change, 1.0) as fold_change
   FROM public.transcripts t
   LEFT JOIN patient_PATIENT123.expression_data pe ON t.transcript_id = pe.transcript_id
   JOIN public.genes g ON t.gene_id = g.gene_id
   WHERE COALESCE(pe.expression_fold_change, 1.0) > 2.0;
   ```

2. **If querying patient database directly:**
   ```sql
   -- Connect to patient database first
   \c mediabase_patient_DEMO_BREAST_HER2

   -- Then query cancer_transcript_base
   SELECT * FROM cancer_transcript_base WHERE expression_fold_change > 2.0;
   ```

### Issue 3: "operator does not exist: text = integer"

**Symptoms:**
```sql
ERROR: operator does not exist: text = integer
HINT: No operator matches the given name and argument types. You might need to add explicit type casts.
```

**Root Cause:** Type mismatch in WHERE or JOIN condition.

**Solution:**
```sql
-- WRONG: Comparing text to integer
WHERE g.gene_symbol = 123

-- CORRECT: Cast or use correct type
WHERE g.gene_symbol = '123'

-- For gene_id comparisons:
WHERE g.gene_id = 'ENSG00000141510'  -- Ensembl IDs are text

-- For expression comparisons:
WHERE COALESCE(pe.expression_fold_change, 1.0) > 2.0  -- Numeric comparison
```

---

## Index and Performance Optimization

### Issue 1: Indexes not being used after rebuild

**Symptoms:**
- Created indexes but EXPLAIN still shows Seq Scan
- Query performance unchanged after indexing

**Diagnosis:**
```sql
-- Check if index exists
\d+ gene_publications

-- Check index validity
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'gene_publications';

-- Check index bloat
SELECT
    pg_size_pretty(pg_relation_size('idx_gene_publications_gene_id')) as index_size,
    pg_size_pretty(pg_table_size('gene_publications')) as table_size;
```

**Solutions:**

1. **Rebuild indexes:**
   ```sql
   REINDEX INDEX idx_gene_publications_gene_id;
   REINDEX INDEX idx_gene_publications_gene_pmid;
   ```

2. **Update statistics after rebuild:**
   ```sql
   ANALYZE gene_publications;
   ```

3. **Check autovacuum settings:**
   ```sql
   SHOW autovacuum;
   SHOW autovacuum_analyze_threshold;
   ```

4. **Force index usage (if planner is wrong):**
   ```sql
   SET enable_seqscan = OFF;
   -- Run query
   RESET enable_seqscan;
   ```

### Issue 2: Partial index not being used

**Symptoms:**
- Created partial index with WHERE clause but not used
- Query matches index predicate exactly but Seq Scan still occurs

**Diagnosis:**
```sql
-- Check partial index definition
SELECT indexname, indexdef
FROM pg_indexes
WHERE indexname = 'idx_patient123_expr_fold_change';

-- Test query that should use index
EXPLAIN ANALYZE
SELECT * FROM patient_PATIENT123.expression_data
WHERE expression_fold_change > 2.0;
```

**Solutions:**

1. **Ensure query WHERE clause matches index predicate exactly:**
   ```sql
   -- Index created with: WHERE expression_fold_change <> 1.0
   -- Query must use same condition or subset:

   -- WILL USE INDEX:
   WHERE expression_fold_change > 2.0        -- Subset of <> 1.0
   WHERE expression_fold_change < 0.5        -- Subset of <> 1.0

   -- WON'T USE INDEX:
   WHERE expression_fold_change <> 0.5       -- Different condition
   WHERE expression_fold_change IS NOT NULL  -- Different condition
   ```

2. **Rebuild partial index with correct predicate:**
   ```sql
   DROP INDEX IF EXISTS idx_patient123_expr_fold_change;

   CREATE INDEX idx_patient123_expr_fold_change
   ON patient_PATIENT123.expression_data(expression_fold_change)
   WHERE expression_fold_change > 1.5 OR expression_fold_change < 0.67;  -- Broader condition
   ```

3. **Analyze table after creating partial index:**
   ```sql
   ANALYZE patient_PATIENT123.expression_data;
   ```

---

## Backup and Restore Issues

### Issue 1: Backup script fails with permission denied

**Symptoms:**
```
bash: /tmp/backup_script.sh: Permission denied
```

**Solution:**
```bash
# Make backup script executable
chmod +x ./backups/backup_mediabase.sh

# Run backup
./backups/backup_mediabase.sh
```

### Issue 2: Restore fails with "role does not exist"

**Symptoms:**
```
psql:backup.sql:10: ERROR: role "old_user" does not exist
```

**Solution:**
```bash
# Restore without role ownership assignments
PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U mbase_user -d mbase \
  -f backups/backup.sql --no-owner

# Or create missing role first
PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U postgres -c "
CREATE ROLE old_user WITH LOGIN PASSWORD 'password';
GRANT ALL PRIVILEGES ON DATABASE mbase TO old_user;
"
```

### Issue 3: Out of memory during backup compression

**Symptoms:**
```
gzip: out of memory
```

**Solution:**
```bash
# Use pigz (parallel gzip) for large backups
sudo apt-get install pigz

# Backup with pigz
PGPASSWORD=mbase_secret pg_dump -h localhost -p 5435 -U mbase_user mbase | \
  pigz -9 > backups/mbase_backup_$(date +%Y%m%d).sql.gz

# Or disable compression
PGPASSWORD=mbase_secret pg_dump -h localhost -p 5435 -U mbase_user mbase \
  > backups/mbase_backup_$(date +%Y%m%d).sql
```

---

## Getting Help

### Community Support

- **GitHub Issues:** https://github.com/itsatony/mediabase/issues
- **Documentation:** `/docs` directory
- **Example Queries:** `docs/MEDIABASE_QUERY_LIBRARY.md`

### Reporting Bugs

When reporting issues, please include:

1. **MEDIABASE version:** `git describe --tags`
2. **PostgreSQL version:** `psql --version`
3. **Error messages:** Full error output
4. **Query used:** SQL query causing issue
5. **Diagnostic output:** Results from Quick Diagnostic Checklist

### Additional Resources

- **Query Optimization Guide:** `docs/QUERY_OPTIMIZATION_GUIDE.md`
- **Schema Reference:** `docs/MEDIABASE_SCHEMA_REFERENCE.md`
- **Clinical Guides:**
  - HER2+ Breast Cancer: `docs/BREAST_CANCER_HER2_GUIDE.md`
  - MSS Colorectal Cancer: `docs/COLORECTAL_CANCER_GUIDE.md`

---

**Document Version:** 1.0.0
**Compatible with:** MEDIABASE v0.6.0.2
**Last Review:** 2025-11-25

*For urgent production issues, consult with your database administrator and review PostgreSQL documentation.*

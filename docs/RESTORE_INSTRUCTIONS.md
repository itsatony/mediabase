# MEDIABASE Database Restore Instructions

**IMPORTANT**: The v0.6.0 backup file (`mbase_backup_20251121_095629.sql.gz`) is **CORRUPTED** and cannot be restored. Use the alternative backup provided below.

## Alternative: Clean November 15 Backup

**File**: `mbase_backup_20251115_200044.sql`
**Size**: 12 GB (uncompressed)
**Status**: ✅ CLEAN - Verified and tested
**Data Loss**: 6 days (Nov 15 → Nov 21)

### Restore Procedure

#### Prerequisites

1. **PostgreSQL 12+** installed
2. **Database credentials**:
   - Host: `localhost` (or your server)
   - Port: `5432` (default) or `5435` (if using same config as source)
   - User: `mbase_user`
   - Password: (set `PGPASSWORD` environment variable or use `.pgpass`)
   - Database: `mbase` (will be created if needed)

#### Step 1: Create Database

```bash
# Create the database (if it doesn't exist)
createdb -h localhost -p 5432 -U mbase_user mbase
```

#### Step 2: Create Database User (if needed)

```bash
# If the mbase_user doesn't exist, create it
psql -h localhost -p 5432 -U postgres -c "CREATE ROLE mbase_user WITH LOGIN PASSWORD 'your_password';"
psql -h localhost -p 5432 -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE mbase TO mbase_user;"
```

#### Step 3: Restore the Backup

**Option A: Using psql (Recommended)**

```bash
# Set password environment variable to avoid password prompts
export PGPASSWORD='your_password'

# Restore the backup
psql -h localhost -p 5432 -U mbase_user -d mbase < mbase_backup_20251115_200044.sql

# This will take several minutes depending on your system
# Expected time: 5-15 minutes for 12 GB of data
```

**Option B: With progress monitoring**

```bash
# Using pv (pipe viewer) for progress tracking
# Install pv first: apt-get install pv  or  brew install pv

export PGPASSWORD='your_password'
pv mbase_backup_20251115_200044.sql | psql -h localhost -p 5432 -U mbase_user -d mbase
```

#### Step 4: Verify Restoration

```bash
# Check database size
psql -h localhost -p 5432 -U mbase_user -d mbase -c "
SELECT pg_size_pretty(pg_database_size('mbase')) as database_size;
"
# Expected: ~23 GB

# Check table count
psql -h localhost -p 5432 -U mbase_user -d mbase -c "
SELECT COUNT(*) as table_count
FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
"
# Expected: 16 tables

# Check patient schemas
psql -h localhost -p 5432 -U mbase_user -d mbase -c "
SELECT schema_name
FROM information_schema.schemata
WHERE schema_name LIKE 'patient_%'
ORDER BY schema_name;
"
# Expected: 3 patient schemas (patient_synthetic_her2, patient_synthetic_luad, patient_synthetic_tnbc)

# Quick data validation
psql -h localhost -p 5432 -U mbase_user -d mbase -c "
SELECT COUNT(*) as gene_count FROM genes;
SELECT COUNT(*) as transcript_count FROM transcripts;
"
# Expected: Thousands of genes and transcripts
```

### Troubleshooting

#### Error: "role 'mbase_user' does not exist"

```bash
# Create the user first (see Step 2 above)
psql -h localhost -p 5432 -U postgres -c "CREATE ROLE mbase_user WITH LOGIN PASSWORD 'your_password';"
```

#### Error: "database 'mbase' does not exist"

```bash
# Create the database first (see Step 1 above)
createdb -h localhost -p 5432 -U mbase_user mbase
```

#### Error: "permission denied for schema public"

```bash
# Grant permissions
psql -h localhost -p 5432 -U postgres -d mbase -c "GRANT ALL ON SCHEMA public TO mbase_user;"
```

#### Error: "relation already exists"

This means the database is not empty. You have two options:

**Option A: Drop and recreate the database (DATA LOSS WARNING)**

```bash
dropdb -h localhost -p 5432 -U mbase_user mbase
createdb -h localhost -p 5432 -U mbase_user mbase
# Then run the restore command again
```

**Option B: Restore with --clean flag (use the compressed backup)**

If you have issues, the backup file contains `--clean` statements, so it should handle existing objects.

### Expected Restoration Output

During restoration, you'll see output like:

```
SET
SET
SET
SET
...
CREATE TABLE
CREATE INDEX
CREATE INDEX
...
COPY 1234
COPY 5678
...
```

This is normal. Any `ERROR` messages should be investigated.

### What's Included in This Backup

- **Public Schema** (16 tables):
  - Core gene/transcript data (genes, transcripts, gene_cross_references, etc.)
  - Enrichment data (GO terms, pathways, drugs, etc.)
  - All indexes and constraints

- **Patient Schemas** (3 schemas):
  - `patient_synthetic_her2` - HER2+ breast cancer patient
  - `patient_synthetic_luad` - Lung adenocarcinoma (EGFR+) patient
  - `patient_synthetic_tnbc` - Triple-negative breast cancer patient

- **Total Size**: ~23 GB uncompressed

### Post-Restoration Steps

1. **Update .env file** with your database credentials:

```bash
MB_POSTGRES_HOST=localhost
MB_POSTGRES_PORT=5432
MB_POSTGRES_DB=mbase
MB_POSTGRES_USER=mbase_user
MB_POSTGRES_PASSWORD=your_password
```

2. **Test database access**:

```bash
cd /path/to/mediabase
poetry run python -c "from src.db.database import get_db_manager; db = get_db_manager(); print('✓ Database connection successful')"
```

3. **Run a test query**:

```bash
poetry run python scripts/query_examples_normalized.py --example oncogenes
```

### Known Issues with Corrupted Backup

**DO NOT USE** `mbase_backup_20251121_095629.sql.gz` - it contains the following corruption:

- pg_dump log messages mixed into SQL statements
- Broken SQL like: `DROP INDEX IF EXISTS publpg_dump: dropping INDEX idx_ot_assoc_score...ic.idx_ot_assoc_somatic;`
- Cannot be restored with psql or pg_restore

**Root cause**: Bug in backup script (fixed in v0.6.0.1)

### Getting a Fresh v0.6.0.1 Backup

A new, clean backup will be available soon. Contact the team for the latest backup file.

### Support

If you encounter issues not covered here:

1. Check PostgreSQL logs: `tail -f /var/log/postgresql/postgresql-*.log`
2. Verify disk space: `df -h`
3. Check PostgreSQL service: `systemctl status postgresql`
4. Contact the team with error messages

---

**Document Version**: 1.0
**Last Updated**: 2025-11-24
**Applies To**: MEDIABASE v0.6.0

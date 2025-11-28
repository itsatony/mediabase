# PostgreSQL Setup Guide

## Prerequisites

- PostgreSQL 12 or higher
- Python 3.10 or higher
- Poetry for dependency management

## Database Management

The project now uses a centralized DatabaseManager for all database operations:

## Container Setup

1. Create a named volume:
   ```bash
   podman volume create mbase_pgdata
   ```

2. Start the PostgreSQL container:
   ```bash
   podman run -d \
     --name mbase_postgres \
     -e POSTGRES_PASSWORD=mbase_secret \
     -e POSTGRES_USER=mbase_user \
     -e POSTGRES_DB=mbase \
     -v mbase_pgdata:/var/lib/postgresql/data \
     -p 5435:5432 \
     postgres:15
   ```

Note: We're using port 5435 to avoid conflicts with other PostgreSQL instances.

## Database Management Scripts

The project includes several scripts for database management in the `scripts/db` directory:

1. `reset_db.sh`: Removes and recreates the database
2. `init_db.sh`: Initializes schemas and tables
3. `create_indices.sh`: Creates all necessary indices

### Usage

1. Reset the database (WARNING: This will delete all data):
   ```bash
   ./scripts/db/reset_db.sh
   ```

2. Initialize a fresh database:
   ```bash
   ./scripts/db/init_db.sh
   ```

3. Create indices:
   ```bash
   ./scripts/db/create_indices.sh
   ```

## Environment Configuration

Update your `.env` file with these settings:

```ini
MB_POSTGRES_HOST=localhost
MB_POSTGRES_PORT=5432
MB_POSTGRES_DB=mediabase
MB_POSTGRES_USER=postgres
MB_POSTGRES_PASSWORD=postgres
```

## Verification

Test the connection:

```bash
psql -h localhost -p 5435 -U mbase_user -d mbase
```

## Container Management

- Stop the container:
  ```bash
  podman stop mbase_postgres
  ```

- Start an existing container:
  ```bash
  podman start mbase_postgres
  ```

- Remove the container (data persists in volume):
  ```bash
  podman rm mbase_postgres
  ```

- Remove the volume (WARNING: This will delete all data):
  ```bash
  podman volume rm mbase_pgdata
  ```

## Backup and Restore

Create a backup:
```bash
podman exec mbase_postgres pg_dump -U mbase_user mbase > backup.sql
```

Restore from backup:
```bash
cat backup.sql | podman exec -i mbase_postgres psql -U mbase_user -d mbase
```

## Troubleshooting

1. Port conflicts:
   - If port 5435 is in use, choose a different port in the `podman run` command
   - Update your `.env` file accordingly

2. Permission issues:
   - Ensure your user has permissions to create volumes
   - Check SELinux settings if using RHEL/Fedora

3. Container fails to start:
   - Check logs: `podman logs mbase_postgres`
   - Verify volume permissions
   - Ensure sufficient disk space

## Schema Management

### Current Schema Features

The current schema (v0.4.1) includes:

1. Alternative ID Storage
   - Flexible JSONB storage for transcript and gene IDs
   - Array storage for standardized IDs (UniProt, NCBI, RefSeq)
   - Optimized GIN indices for efficient querying

2. Source-specific References
   - Structured JSONB storage for publication references
   - Organized by data source (GO terms, drugs, pathways, UniProt)
   - Enhanced evidence tracking with metadata

### Schema Migration

1. Automatic migration:
   ```bash
   poetry run python scripts/manage_db.py --apply-schema
   ```

2. Manual migration:
   ```sql
   -- Add new columns
   ALTER TABLE cancer_transcript_base
   ADD COLUMN alt_transcript_ids JSONB DEFAULT '{}'::jsonb,
   ADD COLUMN alt_gene_ids JSONB DEFAULT '{}'::jsonb,
   ADD COLUMN uniprot_ids TEXT[] DEFAULT '{}',
   ADD COLUMN ncbi_ids TEXT[] DEFAULT '{}',
   ADD COLUMN refseq_ids TEXT[] DEFAULT '{}',
   ADD COLUMN source_references JSONB DEFAULT '{
       "go_terms": [],
       "uniprot": [],
       "drugs": [],
       "pathways": []
   }'::jsonb;

   -- Create indices
   CREATE INDEX idx_alt_transcript_ids ON cancer_transcript_base USING GIN(alt_transcript_ids);
   CREATE INDEX idx_alt_gene_ids ON cancer_transcript_base USING GIN(alt_gene_ids);
   CREATE INDEX idx_uniprot_ids ON cancer_transcript_base USING GIN(uniprot_ids);
   CREATE INDEX idx_ncbi_ids ON cancer_transcript_base USING GIN(ncbi_ids);
   CREATE INDEX idx_refseq_ids ON cancer_transcript_base USING GIN(refseq_ids);
   CREATE INDEX idx_source_references ON cancer_transcript_base USING GIN(source_references);

   -- Drop obsolete column
   ALTER TABLE cancer_transcript_base DROP COLUMN publications;
   ```

### Maintenance

Regular maintenance tasks for the new schema:

1. Index maintenance:
   ```sql
   REINDEX INDEX idx_alt_transcript_ids;
   REINDEX INDEX idx_alt_gene_ids;
   REINDEX INDEX idx_source_references;
   ```

2. JSONB storage optimization:
   ```sql
   VACUUM ANALYZE cancer_transcript_base;
   ```

3. Monitor index usage:
   ```sql
   SELECT 
       schemaname || '.' || relname as table_name,
       indexrelname as index_name,
       idx_scan as number_of_scans,
       idx_tup_read as tuples_read,
       idx_tup_fetch as tuples_fetched
   FROM pg_stat_user_indexes
   WHERE schemaname = 'public'
   ORDER BY idx_scan DESC;
   ```
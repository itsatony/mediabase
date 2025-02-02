# PostgreSQL Setup Guide

This guide explains how to set up a PostgreSQL container for the Cancer Transcriptome Base project.

## Prerequisites

- [Podman](https://podman.io/) installed (or Docker)
- Sufficient disk space for the database volume

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
DB_HOST=localhost
DB_PORT=5435
DB_NAME=mbase
DB_USER=mbase_user
DB_PASSWORD=mbase_secret
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
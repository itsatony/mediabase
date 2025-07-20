# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MEDIABASE is a comprehensive cancer transcriptomics database system that integrates biological data from multiple sources:
- Gene transcript data from GENCODE
- Gene product classification from UniProt  
- GO terms from Gene Ontology
- Pathway data from Reactome
- Drug interactions from DrugCentral/ChEMBL
- Scientific literature from PubMed

## Development Environment

### Dependency Management
- **Poetry 2.0.1+** is used for dependency management and virtual environments
- Always use `poetry run` or activate the environment with `poetry shell`
- Dependencies are defined in `pyproject.toml`

### Python Version
- Requires **Python 3.10+**
- Type hints are mandatory throughout the codebase
- Use mypy for type checking in strict mode

## Common Development Commands

### Environment Setup
```bash
# Install dependencies
poetry install

# Activate environment
poetry shell

# Install new dependency
poetry add <package-name>
```

### Testing
```bash
# Run all tests
poetry run pytest

# Run specific test file
poetry run pytest tests/etl/test_transcript.py

# Run with coverage
poetry run pytest --cov=src

# Run integration tests only
poetry run pytest -m integration

# Run unit tests only  
poetry run pytest -m unit
```

### Code Quality
```bash
# Format code
poetry run black .

# Sort imports
poetry run isort .

# Type checking
poetry run mypy src

# Lint code
poetry run flake8 src
```

### Database Management
```bash
# Database operations via manage_db.py
poetry run python scripts/manage_db.py --create-db
poetry run python scripts/manage_db.py --apply-schema
poetry run python scripts/manage_db.py --reset

# Initialize test database
poetry run python scripts/manage_db.py --non-interactive
```

### ETL Pipeline
```bash
# Run complete ETL pipeline
poetry run python scripts/run_etl.py

# Run specific modules
poetry run python scripts/run_etl.py --modules transcripts,products

# Limit processing for testing
poetry run python scripts/run_etl.py --reset-db --limit-transcripts 100

# Run with debug output
poetry run python scripts/run_etl.py --log-level DEBUG
```

## Architecture

### ETL Module Structure
The ETL system follows a strict dependency hierarchy defined in `config/etl_sequence.py`:

1. **transcript** - Base gene transcript data (no dependencies)
2. **id_enrichment** - Cross-database ID mappings (needs transcript)
3. **go_terms** - Gene Ontology terms (needs transcript)
4. **products** - Gene product classification (needs transcript, id_enrichment)
5. **pathways** - Reactome pathway data (needs transcript, id_enrichment)
6. **drugs** - Drug interaction data (needs most other modules)
7. **publications** - PubMed literature enrichment (needs all modules)

### Base Classes
- All ETL processors inherit from `BaseProcessor` in `src/etl/base_processor.py`
- Database operations use `DatabaseManager` from `src/db/database.py`
- Standardized logging via `src/utils/logging.py`

### Database Schema
- PostgreSQL 12+ with JSONB support
- Schema versioning system with migrations in `src/db/migrations/`
- Current schema version is tracked in the database

## Code Style Guidelines

### From Copilot Instructions
- Use clear, descriptive names - no abbreviations
- Type hints are mandatory for all functions and methods
- Follow Google-style docstrings
- Use snake_case for variables/functions, CamelCase for classes
- Constants in ALL_CAPS at top of file
- Prefer list comprehensions over loops where readable
- Use f-strings for formatting
- Safe dictionary access with `.get()` method

### Logging Standards
```python
# Console logging with rich formatting
from rich.console import Console
console = Console()

# Progress bars with tqdm
from tqdm import tqdm
for item in tqdm(items, desc="Processing"):
    # work

# File logging with rotation
import logging
logger = logging.getLogger(__name__)
```

### Error Handling
- Use specific exception classes from `base_processor.py`
- Always include proper error context and logging
- Use try/except blocks with appropriate rollback for database operations

## Database Operations

### Connection Management
```python
from src.db.database import get_db_manager

# Get database manager instance
db_manager = get_db_manager()

# Use context manager for transactions
with db_manager.transaction() as cursor:
    cursor.execute("SELECT ...")
```

### Environment Variables
Required environment variables (copy from `.env.example`):
- `MB_POSTGRES_HOST`, `MB_POSTGRES_PORT`, `MB_POSTGRES_DB`
- `MB_POSTGRES_USER`, `MB_POSTGRES_PASSWORD`
- `MB_PUBMED_EMAIL`, `MB_PUBMED_API_KEY` (for PubMed access)
- `MB_CACHE_DIR`, `MB_CACHE_TTL`

## Testing Guidelines

### Test Organization
- Unit tests: `tests/` directory structure mirrors `src/`
- Integration tests: marked with `@pytest.mark.integration`
- Use `conftest.py` for shared fixtures
- Mock external services in unit tests, use real database for integration tests

### Database Testing
- Test database must be configured separately from development
- Use `MB_POSTGRES_NAME=mediabase_test` for test environment
- Integration tests may require actual ETL data for validation

## Patient Copy Functionality

### Creating Patient-Specific Databases
MEDIABASE includes functionality to create patient-specific database copies with custom fold-change data:

```bash
# Create patient copy with transcriptome data
poetry run python scripts/create_patient_copy.py \
    --patient-id PATIENT123 \
    --csv-file patient_transcriptome.csv

# Validate CSV without making changes
poetry run python scripts/create_patient_copy.py \
    --patient-id PATIENT123 \
    --csv-file data.csv \
    --dry-run
```

### CSV Requirements
- **Required columns**: `transcript_id` and `cancer_fold` (or alternatives)
- **Format**: Standard CSV with header row
- **Data**: Ensembl transcript IDs and numeric fold-change values
- **Example**: See `examples/patient_data_example.csv`

### Workflow
1. **CSV Validation**: Automatic column detection and data validation
2. **Database Copy**: Complete schema and data duplication 
3. **Fold-Change Update**: Batch update of `expression_fold_change` column
4. **Validation**: Verification of successful updates

## Important Notes

### When Working on ETL Modules
- Always check module dependencies in `config/etl_sequence.py`
- Use `BaseProcessor` methods for consistent caching and download behavior
- Update schema version requirements when making database changes
- Include comprehensive logging and progress tracking

### Performance Considerations
- ETL processes are designed for batch operations with configurable batch sizes
- Large files are processed with streaming and chunking
- Database operations use temporary tables and bulk inserts where possible
- Caching system with TTL prevents unnecessary re-downloads

### Error Recovery
- ETL processes include automatic retry logic for network operations
- Database transactions are properly scoped to allow rollback on errors
- Cache validation prevents use of corrupted cached files
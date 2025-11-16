# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🎯 PRIMARY USE CASE (CRITICAL CONTEXT)

**Target Users**: Non-informatician oncologists in clinical practice

**Workflow**:
1. Oncologist uploads patient transcriptome data (DESeq2 results, RNA-seq data)
2. System creates **patient-specific database copy** with integrated fold-change data
3. Oncologist interacts with **LLM-based bioinformatics assistant**
4. Assistant translates normal medical conversation into optimized SQL queries
5. Assistant provides clinical insights based on query results

**Design Imperatives**:
- **Schema must be LLM-friendly**: Clear table/column names, intuitive relationships
- **Documentation must be comprehensive**: Every data source, every relationship documented
- **Queries must be SOTA**: State-of-the-art cancer bioinformatics queries as examples
- **Database must be easily cloneable**: Patient-specific copies are core functionality
- **ETL must be robust**: Download+cache pattern, reproducible, well-documented

**This means ALL future work should prioritize**:
1. Query accessibility for LLMs (clear schema, good examples)
2. Clinical relevance (cancer-specific insights, therapeutic recommendations)
3. Documentation quality (source attribution, data provenance, relationship explanations)
4. Reproducibility (cached downloads, version tracking, consistent ETL patterns)

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

# Test specific functionality (NEW in v0.2.0)
poetry run pytest tests/test_deseq2_core_functionality.py -v
poetry run pytest tests/test_patient_workflow_integration.py -v
poetry run pytest tests/test_api_server.py -v
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

### API Server (NEW in v0.2.0)
```bash
# Start API server
poetry run python -m src.api.server

# API endpoints available at:
# - http://localhost:8000/docs (Interactive docs)
# - http://localhost:8000/api/v1/transcripts (Search endpoint)
# - http://localhost:8000/health (Health check)
```

### Patient Copy with DESeq2 Support (Enhanced in v0.2.0)
```bash
# Process DESeq2 format files automatically
poetry run python scripts/create_patient_copy.py \
    --patient-id PATIENT123 \
    --csv-file deseq2_results.csv

# System automatically detects:
# - SYMBOL column → gene symbol mapping
# - log2FoldChange column → linear conversion
# - Provides mapping success rate statistics
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

## ChEMBL v35 Integration (NEW in v0.4.0)

MEDIABASE now supports **ChEMBL v35** with a production-ready pg_restore architecture.

### Key Features

**Architecture**:
- Temporary database extraction using PostgreSQL pg_restore
- CSV export format for portable data caching
- Automatic cleanup to prevent orphaned databases
- Performance: ~10 minutes first run, instant on subsequent runs (cached)

**Statistics** (Verified from validation tests):
- **2,496,335** drug molecules
- **16,003** biological targets
- **55,442** drug indications
- **7,330** mechanism of action entries

### Usage

```bash
# Run ETL with ChEMBL v35 (automatic download and extraction)
poetry run python scripts/run_etl.py --modules drugs --use-chembl

# The system will:
# 1. Download ChEMBL v35 archive (1.83GB, ~17 seconds)
# 2. Extract .dmp file from archive
# 3. Create temporary database: chembl_temp_35_<timestamp>
# 4. Restore using pg_restore (~9 minutes)
# 5. Extract 12 tables to CSV files (~38 seconds)
# 6. Process drug data through pipeline
# 7. Cleanup temporary database
```

### Implementation Details

**Extracted Tables** (12 critical tables):
- molecule_dictionary (2.5M compounds)
- compound_structures, compound_properties
- target_dictionary (16K targets)
- target_components, component_sequences
- drug_indication (55K indications)
- drug_mechanism (7.3K mechanisms)
- activities, binding_sites, protein_classification
- assays (bioactivity data)

**Cache Location**: `/tmp/mediabase/cache/chembl_35/`

**For comprehensive documentation**, see: `docs/CHEMBL_INTEGRATION_GUIDE.md`

## Pathway Enrichment Fix (v0.4.0)

### NCBI ID Mapping Fix

v0.4.0 fixes a critical bug in pathway enrichment where gene pathway data was not being populated.

**Problem**: Pathways module queried for `external_db IN ('NCBI', 'EntrezGene')` but id_enrichment wrote `external_db='GeneID'`

**Fix** (src/etl/pathways.py:232):
```python
# FIXED: Added 'GeneID' to WHERE clause
WHERE external_db IN ('GeneID', 'NCBI', 'EntrezGene')
```

**Result**: 167+ NCBI cross-references now successfully populated

### Validation

```bash
# Verify pathway enrichment is working
PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U mbase_user -d mbase -c "
SELECT COUNT(*) FROM gene_cross_references WHERE external_db = 'GeneID';
-- Expected: 167+ rows

SELECT COUNT(*) as genes_with_pathways,
       AVG(array_length(pathways, 1)) as avg_pathways_per_gene
FROM (SELECT unnest(pathways) as pathway FROM cancer_transcript_base) p;
-- Expected: 89+ genes with avg 11.2 pathways/gene
"
```

## SOTA Query Files

MEDIABASE provides State-Of-The-Art (SOTA) SQL queries for cancer therapeutic analysis on patient-specific databases.

### Available Query Files

**PRIMARY QUERY FILE** (NEW in v0.4.0):
- **`WORKING_QUERY_EXAMPLES.sql`**: Comprehensive verified query library ✅
  - **Status**: Fully tested and production-ready
  - **Size**: 433 lines with 15+ working queries
  - **Coverage**: Patient databases + main database queries
  - **Best for**: Clinical cancer analytics, therapeutic targeting, biomarker discovery
  - **Tested on**: All 6 demo patient databases + main database
  - **Sections**: Patient queries, main database queries, cross-schema compatibility, troubleshooting

**Recommended Alternatives**:
- **`cancer_specific_sota_queries.sql`**: Cancer-type-specific queries (HER2+, TNBC, EGFR+, MSI-high, PDAC)
  - Simplest to use
  - Direct clinical recommendations
  - Tested and working

- **`legacy_sota_queries_for_patients.sql`**: General SOTA queries (v0.3.1 - FIXED)
  - 4 main SOTA queries + validation query
  - All PostgreSQL syntax errors corrected
  - Works with legacy `cancer_transcript_base` schema
  - Comprehensive therapeutic analysis

**Advanced** (requires migration):
- **`normalized_sota_queries_for_patients.sql`**: High-performance queries
  - Requires normalized schema (not yet in patient databases)
  - 10-100x performance improvement with materialized views

**Deprecated**:
- **`working_sota_queries_for_patients.sql`**: BROKEN - DO NOT USE
  - Contains 5 PostgreSQL syntax errors
  - Replaced by `legacy_sota_queries_for_patients.sql`

### Usage Example

```bash
# Connect to patient database
PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U mbase_user \
  -d mediabase_patient_DEMO_BREAST_HER2

# Run PRIMARY query file (recommended)
\i WORKING_QUERY_EXAMPLES.sql

# Or run cancer-specific queries
\i cancer_specific_sota_queries.sql

# Or run comprehensive SOTA analysis
\i legacy_sota_queries_for_patients.sql
```

### Query Examples from WORKING_QUERY_EXAMPLES.sql

**HER2+ Targeted Therapy Selection** (Lines 19-50):
```sql
SELECT gene_symbol, expression_fold_change,
  CASE
    WHEN gene_symbol = 'ERBB2' AND expression_fold_change > 4.0
      THEN '🎯 TRASTUZUMAB/PERTUZUMAB TARGET (High Priority)'
    WHEN gene_symbol IN ('PIK3CA', 'AKT1') AND expression_fold_change > 3.0
      THEN '🎯 PI3K/AKT INHIBITOR TARGET'
  END as her2_therapeutic_strategy
FROM cancer_transcript_base
WHERE expression_fold_change <> 1.0;
```

**Tumor Suppressor Loss Analysis** (Lines 85-106):
```sql
SELECT gene_symbol, expression_fold_change,
  ROUND((1.0 - expression_fold_change) * 100, 1) as percent_loss,
  CASE
    WHEN expression_fold_change < 0.2 THEN '🚨 SEVERE LOSS (>80%)'
    WHEN expression_fold_change < 0.5 THEN '⚠️ SIGNIFICANT LOSS (>50%)'
  END as loss_severity
FROM cancer_transcript_base
WHERE expression_fold_change < 0.8
  AND gene_symbol IN ('TP53', 'RB1', 'BRCA1', 'BRCA2', 'PTEN');
```

### Documentation

For detailed query documentation, interpretation guidelines, and clinical decision frameworks, see:
- **`WORKING_QUERY_EXAMPLES.sql`**: PRIMARY verified query file (433 lines)
- **`docs/SOTA_QUERIES_GUIDE.md`**: Comprehensive guide to all SOTA queries
- **`README.md`**: Quick start and integration examples

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

## Adding New Data Sources (v0.5.0+)

### Requirements for New ETL Modules

When adding new data sources, follow these requirements to support the LLM-assistant use case:

#### 1. **ETL Pattern Compliance**
```python
# All ETL processors MUST:
class NewSourceProcessor(BaseProcessor):
    def download_source(self) -> Path:
        """Download and cache source file"""
        return self.download_file(url=SOURCE_URL, file_path=cache_path)

    def process_source(self) -> Dict:
        """Process cached file into structured data"""
        pass

    def integrate_source(self) -> None:
        """Insert processed data into normalized tables"""
        pass
```

#### 2. **Documentation Requirements**

**README.md must include**:
- Data source name, URL, and license
- Update frequency and versioning
- Table names and relationships
- Example queries for common clinical questions

**Schema comments required**:
```sql
COMMENT ON TABLE gene_publications IS
  'Gene-publication links from PubTator Central.
   Updated monthly.
   Source: https://ftp.ncbi.nlm.nih.gov/pub/lu/PubTatorCentral/';

COMMENT ON COLUMN gene_publications.mention_count IS
  'Number of times gene mentioned in abstract/full-text';
```

#### 3. **Query Examples Required**

Every new data source MUST provide 3-5 example queries in `docs/QUERY_EXAMPLES.md`:

```sql
-- Example: Find publications linking overexpressed genes to drug resistance
-- Clinical Question: "Which papers discuss resistance mechanisms for my patient's upregulated genes?"
SELECT
    ctb.gene_symbol,
    ctb.expression_fold_change,
    gp.pmid,
    gp.mention_count
FROM cancer_transcript_base ctb
INNER JOIN gene_publications gp ON ctb.gene_id = gp.gene_id
WHERE ctb.expression_fold_change > 3.0
  AND gp.pmid IN (
    SELECT pmid FROM pubmed_metadata
    WHERE abstract ILIKE '%resistance%' OR abstract ILIKE '%refractory%'
  )
ORDER BY ctb.expression_fold_change DESC, gp.mention_count DESC
LIMIT 20;
```

#### 4. **LLM-Friendly Schema Design**

**Table naming**:
- Use full words, not abbreviations: `gene_publications` not `gene_pubs`
- Be explicit: `clinical_trial_gene_associations` not `trial_genes`
- Follow pattern: `{entity}_{relationship}_{entity}` for join tables

**Column naming**:
- Use medical/biological terms oncologists know: `expression_fold_change` not `fc`
- Include units in name where relevant: `tumor_size_mm`, `survival_months`
- Be unambiguous: `therapeutic_target_priority` not `priority`

#### 5. **Data Provenance Tracking**

Every row MUST track its source:
```sql
CREATE TABLE gene_disease_associations (
    -- ... data columns ...
    source VARCHAR(50) NOT NULL,  -- 'Open Targets', 'DisGeNET', etc.
    evidence_score FLOAT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_version VARCHAR(20)  -- '2024.06', 'v7.3', etc.
);
```

#### 6. **Clinical Relevance Priority**

Prioritize data that answers clinical questions:
- **HIGH**: Drug-gene interactions, clinical trials, treatment outcomes
- **MEDIUM**: Pathways, gene-disease associations, biomarkers
- **LOW**: Sequence features, technical annotations

#### 7. **Test Queries for LLM Validation**

Create test queries in `tests/test_queries/` that an LLM should be able to generate:

```sql
-- Test: LLM should generate this from "Show me targeted therapies for HER2+ breast cancer"
SELECT
    d.drug_name,
    d.max_phase,
    dm.mechanism_of_action,
    di.indication
FROM drugs d
INNER JOIN drug_mechanisms dm ON d.drug_id = dm.drug_id
INNER JOIN drug_indications di ON d.drug_id = di.drug_id
WHERE di.indication ILIKE '%breast cancer%'
  AND dm.target_gene_symbol = 'ERBB2'
  AND d.max_phase >= 3;
```

### Data Source Integration Checklist

Before submitting new data source integration:

- [ ] ETL processor follows BaseProcessor pattern
- [ ] Download+cache implemented (no API rate limits)
- [ ] Schema has descriptive table/column names
- [ ] All tables have COMMENT ON statements
- [ ] 3-5 example queries written in docs/
- [ ] Data provenance tracked (source, version, date)
- [ ] README.md updated with source description
- [ ] Tests verify data loading and basic queries
- [ ] Validated on patient-specific database copy
- [ ] Query examples tested with actual LLM (Claude/GPT-4)

### Example: Well-Documented Table

```sql
CREATE TABLE clinical_trial_gene_associations (
    nct_id VARCHAR(20) REFERENCES clinical_trials(nct_id),
    gene_id VARCHAR(50) REFERENCES genes(gene_id),
    association_type VARCHAR(50) NOT NULL,  -- 'target', 'biomarker', 'eligibility_criterion'
    evidence_source VARCHAR(100),  -- How we linked this gene to trial
    confidence_score FLOAT,  -- 0.0-1.0
    PRIMARY KEY (nct_id, gene_id, association_type)
);

COMMENT ON TABLE clinical_trial_gene_associations IS
  'Links clinical trials to genes based on trial descriptions, inclusion criteria, and molecular targets.
   Source: ClinicalTrials.gov + Open Targets Platform evidence.
   Updated: Monthly.
   Use Case: Find relevant trials for patient"s aberrantly expressed genes.';

COMMENT ON COLUMN clinical_trial_gene_associations.association_type IS
  'How gene relates to trial:
   - target: Gene/protein is therapeutic target
   - biomarker: Gene expression used for patient selection
   - eligibility_criterion: Gene mutation/expression required for enrollment';
```

## Version History & Migration

### v0.5.0 (Planned) - Publications & Clinical Trials
- PubTator Central gene-publication links
- ClinicalTrials.gov integration
- Open Targets disease associations
- WikiPathways expansion
- Enhanced query examples

### v0.4.1 - Pathway Persistence Fix
- Fixed pathway database saving bug
- 4,740 pathway mappings restored
- 43.5% gene coverage achieved

### v0.4.0 - ChEMBL v35 & Pathway Fixes
- ChEMBL v35 integration via pg_restore
- Fixed NCBI ID mapping for pathways
- Comprehensive SOTA query library
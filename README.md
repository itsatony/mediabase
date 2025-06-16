# MEDIABASE: Cancer Transcriptome Base

A comprehensive database for cancer transcriptomics analysis, enriched with gene products, GO terms, pathways, drugs, scientific publications, and cross-database identifiers.

## Overview

MEDIABASE integrates various biological databases to provide a unified interface for cancer transcriptome exploration:

- Gene transcript information from GENCODE
- Gene product classification from UniProt
- GO terms enrichment for functional analysis
- Pathway integration from Reactome
- Drug interactions from DrugCentral and ChEMBL
- Scientific literature from PubMed
- Cross-database identifier mappings (UniProt, NCBI, RefSeq, Ensembl)

## Setup

### Prerequisites

- Python 3.10 or higher
- Poetry 2.0.1 or higher for dependency management
- PostgreSQL 12+

### Environment Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/itsatony/mediabase.git
   cd mediabase
   ```

2. Set up using poetry:
    ```bash
    # Install poetry if not already installed
    curl -sSL https://install.python-poetry.org | python3 -

    # Configure poetry to create virtual environment in project directory
    poetry config virtualenvs.in-project true

    # Install project dependencies
    poetry install
    
    # Activate the poetry environment
    poetry shell
    ```

3. Configure the environment:
   ```bash
   # Copy the example environment file
   cp .env.example .env
   
   # Edit the .env file with your settings
   nano .env
   ```

### Database Setup

1. Create a PostgreSQL database:
   ```bash
   # Using psql command line
   createdb mediabase
   
   # Or initialize the database using our script
   poetry run python scripts/manage_db.py --create-db
   ```

2. Apply the database schema:
   ```bash
   poetry run python scripts/manage_db.py --apply-schema
   ```

### Development

1. Ensure the virtual environment is activated:
   ```bash
   poetry shell
   ```

2. Run tests:
   ```bash
   # Run all tests
   poetry run pytest

   # Run specific test module
   poetry run pytest tests/etl/test_transcript.py

   # Run only integration tests
   poetry run pytest -m integration

   # Run with coverage report
   poetry run pytest --cov=src

   # Run with verbose output
   poetry run pytest -v
   ```

3. Before running tests, ensure your test database is configured:
   ```bash
   # Set up test environment variables
   export MB_POSTGRES_HOST=localhost
   export MB_POSTGRES_PORT=5432
   export MB_POSTGRES_NAME=mediabase_test
   export MB_POSTGRES_USER=postgres
   export MB_POSTGRES_PASSWORD=postgres
   
   # Initialize test database
   poetry run python scripts/manage_db.py --non-interactive
   ```

## Quick Start

After completing the setup, you can:

1. Run the complete ETL pipeline:
   ```bash
   poetry run python scripts/run_etl.py
   ```

2. For testing or development purposes, limit the number of transcripts:
   ```bash
   # Reset the database and process only 100 transcripts
   poetry run python scripts/run_etl.py --reset-db --limit-transcripts 100
   
   # Only process specific modules
   poetry run python scripts/run_etl.py --module transcript,products
   
   # Run with more verbose output
   poetry run python scripts/run_etl.py --log-level DEBUG
   ```

3. Start the API server:
   ```bash
   poetry run python -m src.api.server
   ```

4. Explore example notebooks:
   ```bash
   poetry run jupyter lab notebooks/01_data_exploration.ipynb
   ```

## ETL Processor Modules

### Transcript Processor

The core module that loads gene transcript data from Gencode GTF files into the database.

```bash
# Run only transcript processing
poetry run python scripts/run_etl.py --module transcript
```

Options:
- `--limit-transcripts`: Number of transcripts to process (default: all)
- `--gtf-url`: Custom GTF file URL
- `--force-download`: Force new download of GTF file

### Product Classification

Analyzes and classifies gene products based on UniProt features and GO terms.

```bash
# Run only product classification
poetry run python scripts/run_etl.py --module products
```

Options:
- `--batch-size`: Number of genes to process per batch (default: 100)
- `--process-limit`: Limit number of genes to process

### GO Term Enrichment

Downloads and integrates Gene Ontology (GO) terms with transcripts.

```bash
# Run only GO term enrichment
poetry run python scripts/run_etl.py --module go_terms
```

Options:
- `--force-download`: Force new download of GO.obo file
- `--aspect`: Filter by aspect (molecular_function, biological_process, cellular_component)

### Pathway Enrichment

Integrates Reactome pathway data with transcripts.

```bash
# Run only pathway enrichment
poetry run python scripts/run_etl.py --module pathways
```

Options:
- `--force-download`: Force new download of Reactome data file

### Drug Integration

Adds drug interaction data from either DrugCentral or ChEMBL:

```bash
# Run drug integration with DrugCentral (default)
poetry run python scripts/run_etl.py --module drugs

# Run drug integration with ChEMBL
poetry run python scripts/run_etl.py --module drugs --use-chembl

# Run ChEMBL drug integration directly with filtering for clinical phase
poetry run python scripts/run_chembl_enrichment.py --max-phase-cutoff 1
```

Options for DrugCentral:
- `--force-download`: Force new download of DrugCentral data
- `--skip-scores`: Skip drug score calculation

Options for ChEMBL:
- `--use-chembl`: Use ChEMBL instead of DrugCentral for drug data
- `--chembl-max-phase`: Only include drugs with max phase >= this value (0-4, where 4 is approved)
- `--chembl-schema`: Schema name for ChEMBL data tables (default: chembl_temp)
- `--no-chembl-temp-schema`: Use a persistent schema instead of temporary schema

### Publication Enrichment

Enhances transcript records with publication metadata from PubMed.

```bash
# Run only publication enrichment
poetry run python scripts/run_etl.py --module publications
```

Options:
- `--force-refresh`: Force refresh of all cached publication data
- `--rate-limit`: Adjust API rate limiting (requests per second)

Required environment variables for PubMed API:
```
MB_PUBMED_EMAIL=your.email@example.com  # Required by NCBI
MB_PUBMED_API_KEY=your_api_key          # Optional, allows higher request rates
```

## Patient Copy Functionality

MEDIABASE includes advanced functionality to create patient-specific database copies with custom transcriptome data for oncological analysis.

### Quick Start

```bash
# Create patient-specific database with fold-change data
poetry run python scripts/create_patient_copy.py \
    --patient-id PATIENT123 \
    --csv-file patient_transcriptome.csv

# Validate CSV data without making changes (dry run)
poetry run python scripts/create_patient_copy.py \
    --patient-id PATIENT123 \
    --csv-file patient_data.csv \
    --dry-run

# List all patient databases
poetry run python scripts/manage_patient_databases.py --list

# Delete patient databases with confirmation
poetry run python scripts/manage_patient_databases.py --delete PATIENT123
```

### CSV Data Requirements

Your CSV file must contain at least two columns:

1. **Transcript ID**: Ensembl transcript identifiers (e.g., `ENST00000123456`)
   - Accepted column names: `transcript_id`, `transcript`, `id`, `gene_id`, `ensembl_id`

2. **Cancer Fold-Change**: Numeric expression fold-change values
   - Accepted column names: `cancer_fold`, `fold_change`, `expression_fold_change`, `fold`, `fc`
   - Supports positive, negative, and scientific notation values

### Example CSV Format

```csv
transcript_id,cancer_fold,gene_symbol,p_value,tissue_type
ENST00000269571,8.45,ERBB2,0.000001,tumor
ENST00000484667,6.78,GRB7,0.000012,tumor
ENST00000355349,5.23,PGAP3,0.000045,tumor
ENST00000269305,0.23,ESR1,0.001234,tumor
ENST00000231449,0.18,PGR,0.002345,tumor
```

### Example Patient Data Files

The `examples/` directory contains realistic patient data files for different cancer types:

- `breast_cancer_her2_positive.csv` - HER2-positive breast cancer (55 transcripts)
- `breast_cancer_triple_negative.csv` - Triple-negative breast cancer (55 transcripts) 
- `breast_cancer_luminal_a.csv` - Luminal A breast cancer (55 transcripts)
- `lung_adenocarcinoma_egfr_mutant.csv` - EGFR-mutant lung adenocarcinoma (55 transcripts)
- `colorectal_adenocarcinoma_microsatellite_stable.csv` - Microsatellite stable colorectal cancer (55 transcripts)

### Clinical Workflow

1. **Patient Data Loading**: Upload patient transcriptome CSV data
2. **Database Creation**: Automated creation of patient-specific database copy
3. **Fold-Change Integration**: Batch update of expression values in patient database
4. **Standard Queries**: Run predefined oncological analysis queries
5. **LLM Integration**: Use results for AI-powered clinical discussion and insights

### Features

- **Smart CSV Validation**: Automatic column detection with interactive mapping
- **Safe Database Operations**: Complete schema preservation with transaction safety
- **Batch Processing**: Efficient updates for large datasets (1000 records per batch)
- **Comprehensive Logging**: Detailed progress tracking and error reporting
- **Rich Terminal Interface**: User-friendly CLI with progress bars and statistics

## Documentation

Comprehensive documentation is available in the `docs/` directory:

- [Architecture Overview](docs/architecture.md)
- [API Documentation](docs/api.md)
- [Deployment Guide](docs/deployment.md)
- [Patient Copy Guide](docs/patient_copy_guide.md)

## Project Status and Progress

Current development status and upcoming milestones:
- [x] STEP_AA: Initial project setup (2025-02-02)
- [x] STEP_AB: Basic schema design
- [x] STEP_AC: Project structure implementation
- [x] STEP_AD: DB manager script (connection, check, create, schema, reset) (2025-02-02)
  - Database initialization and reset functionality
  - Schema version tracking
  - Interactive CLI with rich status display
  - Environment-based configuration
- [x] STEP_AE: ETL pipeline - Transcript module (2025-02-02)
  - GTF file download and caching with TTL
  - Transcript data extraction and processing
  - Coordinate parsing and validation
  - Batch database loading
  - Smart caching with metadata tracking
  - Proper PostgreSQL JSONB type handling
  - Comprehensive test suite
  - Integration tests with test database
- [x] STEP_AF: ETL pipeline - Gene-Product Classification (2025-02-02)
  - Automated UniProt data download and processing
  - Smart caching with gzip compression
  - Robust product classification based on:
    - UniProt features
    - GO terms
    - Keywords
    - Function descriptions
  - Batch database updates with temp tables
  - Comprehensive test suite with mocks
  - Integration tests with test database
  - Rich CLI progress display
  - Environment-based configuration
- [x] STEP_AG: Database Schema Update (2025-02-02)
  - Enhanced schema to v0.1.2
  - Added comprehensive UniProt feature storage
  - Added molecular functions array
  - Added proper GIN indices for new columns
  - Migration path for existing data
  - Updated documentation
- [x] STEP_AH: GO Terms & Enrichment (2025-02-02)
  - Automated GO.obo and GOA file downloads with caching
  - GO term hierarchy processing with networkx
  - Ancestor computation and term enrichment
  - Aspect-aware term classification
  - Enhanced schema with dedicated arrays for:
    - molecular_functions: Direct storage of molecular function terms
    - cellular_location: Direct storage of cellular component terms
  - Batch database updates with optimized PostgreSQL queries
  - Proper GIN indices for efficient querying
  - Comprehensive test suite
  - Smart caching with TTL
  - Rich CLI progress display with detailed statistics
  - Proper error handling and recovery
- [x] STEP_AI: ETL pipeline - Drug Integration (2025-02-02)
  - Automated DrugCentral data download and processing
  - Smart drug-target relationship extraction
  - Evidence-based scoring system
  - Reference tracking and validation
  - Batch database updates with temp tables
  - Score calculation using PostgreSQL window functions
  - Rich CLI progress display
  - Comprehensive test suite
  - Integration tests with test database
  - Added drug association view materialization
- [x] STEP_AJ: Pathway Integration (2025-02-02)
  - Automated Reactome data download with caching
  - Gene to pathway/process mapping
  - Standardized format: "Process Name [Reactome:ID]"
  - Smart caching with TTL
  - Batch database updates
  - Comprehensive validation
  - Progress tracking and statistics
- [x] STEP_AK: Added cache validity check (_is_cache_valid) to PathwayProcessor for consistent caching behavior (2025-02-02)
- [x] STEP_AL: Normalized gene_id by stripping version numbers to fix mismatch between NCBI and Ensembl references (2025-02-02)
- [x] STEP_AM: ETL pipeline - Drug Integration (2025-02-02)
  - Added synergy-based scoring referencing pathways and GO terms
  - Utilizes environment variables (e.g., MB_DRUG_PATHWAY_WEIGHT) for weighting
  - Enhanced testing strategy to ensure accurate scoring
- [x] STEP_AN: ETL pipeline - Drug Integration Update (2025-02-02)
  - Added batched drug score calculation
  - Implemented synergy scoring based on pathway and GO term overlaps
  - Added rich progress tracking and validation
  - Fixed older DrugCentral data format compatibility
  - Added comprehensive error handling and debugging
  - Performance optimized through temporary tables and batching
  - Database schema v0.1.3 compatibility ensured
- [x] STEP_AO: Code Cleanup
  - Consolidated database functionality:
    - Merged all database operations into a single DatabaseManager class
    - Centralized schema version control and migrations
    - Improved connection handling and type safety
    - Added comprehensive error handling
    - Implemented proper cursor lifecycle management
    - Added rich status display capabilities
    - Enhanced backup and restore functionality
  - Standardized ETL module database access
    - All ETL modules now use DatabaseManager consistently
    - Improved connection pooling and resource management
    - Added batch processing capabilities
    - Enhanced error recovery mechanisms
- [x] STEP_AP: Enhanced ID Storage and Source References Implementation (2025-02-03)
  - Added comprehensive ID storage support:
    - Alternative transcript IDs (RefSeq, UCSC, etc.)
    - Alternative gene IDs (NCBI, Ensembl, etc.)
    - UniProt IDs
    - NCBI/Entrez IDs
    - RefSeq IDs
  - Implemented source-specific publication references:
    - GO term evidence with PubMed references
    - Drug-target relationships with literature support
    - Pathway evidence with citations
    - UniProt feature annotations with references
  - Enhanced database schema (v0.1.4):
    - Added JSONB columns for flexible ID storage
    - Structured source_references for better organization
    - Optimized indices for efficient querying
  - Updated ETL modules:
    - Improved ID extraction in TranscriptProcessor
    - Enhanced publication tracking in all processors
    - Standardized database access patterns
    - Added comprehensive validation
- [x] STEP_AQ: Introduce config var to limit the pipeline to n transcripts (2025-03-16)
  - Added --limit-transcripts option to run_etl.py
  - Allows limiting the number of transcripts processed
  - Useful for testing and development
  - Best used in conjunction with --reset-db to ensure consistent state
  - Documentation updated with example command usage
- [x] STEP_AR: Implement auto-download of UniProt data in ProductClassifier (2025-03-16)
  - Added automatic download of UniProt data when file is missing
  - Integrates with existing download script functionality
  - Provides clear error messages when download fails
  - Ensures seamless ETL pipeline execution without manual downloads
  - Maintains compatibility with standalone download script
- [x] STEP_AS: Fixed Database Module Connection Errors (2025-03-16)
  - Fixed module import/export structures
  - Added proper error handling for SQL operations
  - Added type-safe connection management
  - Implemented execute_safely helper for robust query execution
  - Ensured proper NULL checks before operations on connections
  - Fixed reset method to properly handle errors
  - Added additional database management utilities
- [x] STEP_AT: Fixed pathway enrichment SQL error (2025-03-16)
  - Fixed array formatting issue in pathway enrichment module
  - Improved connection handling to prevent "connection already closed" errors
  - Added proper exception handling for database operations
  - Enhanced update_batch method to process genes individually
  - Added more robust connection state checking
- [x] STEP_AU: Enhanced Publication Reference Structure (2025-03-16)
  - Defined comprehensive publication reference structure
  - Added support for abstracts, authors, DOIs, and URLs
  - Implemented utility functions for extracting PMIDs from text
  - Added helper methods for creating and merging references
  - Added formatting function for citation display
  - Enhanced PubMed metadata retrieval to include abstracts
  - Improved publication reference storage and retrieval
  - Added documentation for the publication reference structure
- [x] STEP_AV: GO Term Publication Reference Extraction (2025-03-16)
  - Enhanced GO term processor to extract PMIDs from evidence codes
  - Added utility script for extracting PMIDs from existing GO annotations
  - Implemented pattern recognition for multiple evidence code formats
  - Added support for extracting references from ECO-formatted codes
  - Automatic publication reference generation for every GO term
  - Integrated with the publication enrichment pipeline
  - Added comprehensive logging and progress tracking
  - Supported batch processing for high performance
- [x] STEP_AW: Pathway Publication Reference Enhancement (2025-03-16)
  - Added extraction of publication references from Reactome pathway data
  - Created pathway-to-publication mapping infrastructure
  - Implemented pattern recognition for Reactome pathway IDs
  - Enhanced PathwayProcessor to automatically generate publication references
  - Added dedicated script for extracting publication references from existing pathways
  - Implemented caching system for pathway publication mappings
  - Updated run_pathway_enrichment.py to include publication reference extraction
  - Added simulation mode for development and testing without API access
  - Enhanced database update operations to merge and deduplicate references
  - Added comprehensive documentation and logging
- [x] STEP_AX: UniProt Publication Reference Extraction (2025-03-16)
  - Added extraction of publication references from UniProt feature annotations
  - Enhanced ProductClassifier to identify PMIDs in features, citations, and functions
  - Created dedicated utility script for extracting from existing UniProt data
  - Added support for diverse reference formats in UniProt data
  - Integrated with publication enrichment pipeline for metadata enhancement
  - Updated ProductProcessor to track and report on reference extraction
  - Added automatic schema checking and migration
  - Implemented batch processing for optimal performance
  - Enhanced command-line options for publication reference control
- [x] STEP_AY: Drug Publication Reference Extraction (2025-03-16)
  - Enhanced DrugProcessor to extract publication references from drug evidsence data
  - Created dedicated utility script for extracting references from existing drug data
  - Implemented reference extraction from multiple drug evidence fields
  - Added automated reference extraction during drug data integration
  - Enhanced drug integration pipeline to include publication references
  - Updated run_drug_integration.py with publication enrichment options
  - Implemented batch processing for optimal database performance
  - Added status reporting for drug publication extraction
  - Enhanced statistics tracking in drug integration pipeline
- [x] STEP_AZ: ID Enrichment Pre-filtering Optimization (2025-03-16)
  - Added pre-filtering of large database files to human entries only
  - Reduced UniProt idmapping processing time by 90%+ 
  - Reduced NCBI gene info processing time by 95%+
  - Added proper cache management with filter metadata tracking
  - Enhanced progress reporting with filtering statistics
  - Improved memory usage by employing streaming processing
  - Added proper validation of filtered content
  - Maintained data completeness and accuracy while improving performance
- [x] STEP_AQ: Enhanced Publication References Structure (2025-02-04)
  - Added proper JSONB structure for source_references
  - Created publication_reference type for consistent data handling
  - Improved NULL handling for source_references
- [x] STEP_BR: Database Schema Update to v0.1.5 (2025-05-15)
  - Enhanced source_references structure with proper defaults
  - Added publication_reference type for consistent data handling
  - Improved NULL handling for source_references
  - Added data validation for publication references
- [x] STEP_BA: Bug Fix - TranscriptProcessor Limit Handling (2025-03-16)
  - Fixed NoneType multiplication error in transcript limit handling 
  - Improved configuration variable access consistency
  - Enhanced error handling for limit settings
  - Added proper fallback to use all transcripts when limit is not set
  - Updated documentation for limit usage
- [x] STEP_CC: Fixed ID Enrichment Transaction Handling (2023-XX-XX)
  - Fixed transaction handling to ensure ID updates are properly committed
  - Improved case-insensitive gene symbol matching for better coverage
  - Enhanced logging and verification for ID enrichment operations
  - Fixed "set_session cannot be used inside a transaction" error
  - Improved transaction management to be compatible with existing connection states
  - Enhanced error handling with proper rollback support
  - Maintained reliable database updates while avoiding transaction conflicts
- [x] STEP_CD: Fixed Product Processor Temporary Table Handling (2023-XX-XX)
  - Fixed issue with temporary table not existing during batch operations
  - Improved transaction management for temporary table creation and use
  - Enhanced batch processing with proper transaction isolation
  - Added automatic temporary table cleanup with ON COMMIT DROP
  - Improved error handling and rollback support
  - Added verification of product type updates after processing
  - Fixed "relation temp_gene_types does not exist" error
- [x] STEP_CE: Standardized Transaction Handling Across ETL Processors (2023-XX-XX)
  - Fixed transaction handling in GO Terms, Pathways and Drug processors
  - Added robust cleanup of temporary resources

- [x] STEP_CF: ChEMBL Drug Integration (2023-XX-XX)
  - Added support for ChEMBL drug database as an alternative to DrugCentral
  - Enhanced drug information with clinical trials and publication data
  - Added comprehensive pharmacological information including mechanism of action
  - Implemented efficient caching and database optimization for large datasets
  - Included more links to external resources for better cross-referencing

- [x] STEP_CA: ETL Code Refactoring and Optimization
  - [x] Enhanced Logging System (2025-06-01)
    - Created comprehensive logging utility in `src/utils/logging.py`
    - Implemented console logging with rich formatting
    - Added file logging with proper rotation
    - Created standardized progress tracking with tqdm integration
    - Added support for multiple log levels with consistent formatting
  - [x] Enhanced BaseProcessor Class (2025-06-01)
    - Added robust download and caching utilities
    - Implemented cache metadata management with TTL support
    - Added standardized batch processing methods
    - Improved database connection management
    - Added error handling with specialized exception types
    - Implemented file compression/decompression utilities
  - [x] Refactor Processors (2025-06-02)
    - [x] TranscriptProcessor refactored to use BaseProcessor
      - Simplified code by removing duplicate cache and download logic
      - Enhanced error handling with specialized exceptions
      - Improved logging with consistent messages
    - [x] ProductProcessor refactored to use BaseProcessor
      - Added inheritance from BaseProcessor
      - Standardized database operations
      - Enhanced caching and download mechanisms
      - Improved error handling with specialized exception types
    - [x] PathwayProcessor refactored to use BaseProcessor
      - Implemented missing methods
      - Added robust caching with download utilities
      - Enhanced error handling with specialized exceptions
      - Standardized database operations with transaction support
      - Improved publication reference extraction
    - [x] DrugProcessor refactored to use BaseProcessor (2025-06-03)
      - Simplified drug download and caching using base methods
      - Improved database transaction handling with context managers
      - Refactored complex methods into smaller, more focused functions
      - Enhanced error handling with specialized exceptions
      - Standardized database operations with proper transaction support
      - Added robust verification of integration results
  - [x] Enhanced Transaction Management and Schema Validation (2025-06-04)
    - Improved database transaction context manager with cursor validation 
    - Added robust schema version checking and migration support
    - Fixed incompatible method override in DrugProcessor
    - Standardized schema version requirements across processors
    - Added consistent error handling for database operations
    - Improved type safety with property-based cursor access
  - [x] Optimized ID Enrichment Process (2025-06-05)
    - Streamlined to use only UniProt as the universal ID mapping resource
    - Enhanced filtering for human-specific entries for improved performance
    - Expanded ID extraction to fully populate all schema fields
    - Added comprehensive alt_transcript_ids population
    - Improved statistical reporting with coverage metrics
  - [ ] Update Documentation
    - Document changes in README.md
    - Add code comments for new utilities

- [x] STEP_CB: Improved Gene Symbol Matching
  - Added case-insensitive matching for all gene symbols
  - Implemented fuzzy matching with Levenshtein distance for minor variations
  - Created centralized gene matching utilities in `gene_matcher.py`
  - Added match statistics reporting across all ETL modules
  - Fixed gene type filtering issues to ensure all gene types are processed
  - Improved data integration coverage by 300-400%
  - Enhanced diagnostic tracking via detailed matching statistics

- [x] STEP_DA: Patient Copy Functionality (2025-06-16)
  - Created comprehensive patient database copy system for oncological analysis
  - Implemented smart CSV validation with automatic column detection and interactive mapping
  - Added safe database duplication with pg_dump/restore for efficiency
  - Built robust fold-change update system with batch processing (1000 records per batch)
  - Created comprehensive error handling with specific exception types (CSVValidationError, DatabaseCopyError, etc.)
  - Implemented rich terminal interface with progress tracking and detailed feedback
  - Added 26 comprehensive test cases covering all functionality and edge cases
  - Created 5 realistic cancer patient example files (breast cancer subtypes, lung, colorectal)
  - Built patient database management script for listing and deletion
  - Added complete documentation and user guide
  - Integrated with existing MEDIABASE architecture and logging systems
  - Supports clinical workflow: patient data → database copy → analysis → LLM integration

- [ ] STEP_EA: Add ETL for cancer/disease association
- [ ] STEP_FA: AI Agent System Prompt Development
  - Create comprehensive context guide for natural language queries
  - Build oncology-specific terminology mapping (German/English)
  - Document all available data relationships
  - Collect and categorize example queries
  - Create German-English medical term mapping
  - Document query patterns and best practices
  - Create mapping of colloquial to technical terms
- [ ] STEP_FB: Query optimization
- [ ] STEP_FC: LLM-agent integration tests
- [ ] STEP_GA: Documentation
- [ ] STEP_HA: Production deployment

### 2023-XX-XX: Removed Legacy Migration Support

- Removed stepwise migration logic for versions prior to v0.1.5
- Simplified codebase by removing unnecessary migration paths
- Users must now upgrade directly to v0.1.5 or later

### 2023-XX-XX: Enhanced Database Management

- Improved database reset functionality with robust error handling
- Added schema validation to prevent partial migrations
- Enhanced transaction management to properly handle errors
- Simplified migration logic to focus only on v0.1.5 and newer
- Added comprehensive schema validation
- Fixed issues with migration errors in transaction blocks

## Database Management

The project uses a centralized DatabaseManager class that provides:

### Features

- Comprehensive PostgreSQL connection management
- Schema version tracking and migrations
- Rich interactive CLI interface
- Automated backup and restore
- Connection pooling
- Type-safe database operations
- Comprehensive error handling

### Usage

To use the existing management script for backup and restore and stats, run the following commands:

```bash
$ poetry run scripts/manage_db.py
```

1. Basic database operations:
   ```python
   from src.db.database import get_db_manager

   # Initialize database manager
   db_manager = get_db_manager({
       'host': 'localhost',
       'port': 5432,
       'dbname': 'mediabase',
       'user': 'postgres',
       'password': 'postgres'
   })
   
   # Check database status
   db_manager.display_status()
   
   # Perform database operations
   db_manager.cursor.execute("SELECT COUNT(*) FROM cancer_transcript_base")
   count = db_manager.cursor.fetchone()[0]
   ```

2. Schema management:
   ```python
   # Get current version
   current_version = db_manager.get_current_version()
   
   # Migrate to latest version
   latest_version = list(SCHEMA_VERSIONS.keys())[-1]
   db_manager.migrate_to_version(latest_version)
   ```

3. Backup and restore:
   ```python
   # Create backup
   db_manager.dump_database('backup.dump')
   
   # Restore from backup
   db_manager.restore_database('backup.dump')
   ```

### Environment Configuration

The project uses environment variables for configuration. Copy `.env.example` to `.env` and configure:

```bash
# Database Configuration
MB_POSTGRES_HOST=localhost        # PostgreSQL host
MB_POSTGRES_PORT=5432            # PostgreSQL port
MB_POSTGRES_DB=mediabase         # Database name
MB_POSTGRES_USER=postgres        # Database user
MB_POSTGRES_PASSWORD=postgres    # Database password

# API Configuration
MB_API_HOST=0.0.0.0             # API server host
MB_API_PORT=8000                # API server port
MB_API_DEBUG=true               # Enable debug mode

# Data Sources
MB_GENCODE_GTF_URL=...          # Gencode GTF data URL
MB_DRUGCENTRAL_DATA_URL=...     # DrugCentral database URL
MB_GOTERM_DATA_URL=...          # GO terms OBO file URL
MB_UNIPROT_API_URL=...          # UniProt API endpoint
MB_PUBMED_API_URL=...           # PubMed E-utils API
MB_PUBMED_API_KEY=...           # Your PubMed API key
MB_PUBMED_EMAIL=...             # Your email for PubMed API
MB_REACTOME_DOWNLOAD_URL=https://reactome.org/download/current/NCBI2Reactome_All_Levels.txt
MB_CHEMBL_DB_URL=...            # ChEMBL database dump URL
MB_CHEMBL_MAPPING_URL=...       # ChEMBL-UniProt mapping URL

# Cache and Processing
MB_CACHE_DIR=/tmp/mediabase/cache  # Cache directory
MB_CACHE_TTL=86400                 # Cache TTL in seconds
MB_MAX_WORKERS=4                   # Max parallel workers
MB_BATCH_SIZE=1000                # Batch size for processing
MB_MEMORY_LIMIT=8192              # Memory limit in MB

# Security
MB_API_KEY=...                   # API key for authentication
MB_JWT_SECRET=...                # JWT secret for tokens
MB_ALLOWED_ORIGINS=...           # CORS allowed origins
```

## Specialized Schema Support

The project includes specialized schema support for storing and querying ChEMBL data:

```sql
CREATE TABLE chembl_temp.drugs (
    chembl_id TEXT PRIMARY KEY,
    name TEXT,
    synonyms TEXT[],
    max_phase FLOAT,
    drug_type TEXT,
    molecular_weight FLOAT,
    atc_codes TEXT[],
    structure_info JSONB,
    properties JSONB,
    external_links JSONB
);

CREATE TABLE chembl_temp.drug_targets (
    id SERIAL PRIMARY KEY,
    chembl_id TEXT,
    target_id TEXT,
    target_type TEXT,
    target_name TEXT,
    gene_symbol TEXT,
    uniprot_id TEXT,
    action_type TEXT,
    mechanism_of_action TEXT,
    binding_site TEXT,
    confidence_score INTEGER,
    UNIQUE (chembl_id, target_id, gene_symbol, uniprot_id)
);

CREATE TABLE chembl_temp.drug_indications (
    id SERIAL PRIMARY KEY,
    chembl_id TEXT,
    indication TEXT,
    max_phase_for_ind FLOAT,
    mesh_id TEXT,
    efo_id TEXT
);

CREATE TABLE chembl_temp.drug_publications (
    id SERIAL PRIMARY KEY,
    chembl_id TEXT,
    doc_id TEXT,
    pubmed_id TEXT,
    doi TEXT,
    title TEXT,
    year INTEGER,
    journal TEXT,
    authors TEXT
);
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

MIT License. See [LICENSE](LICENSE) for details.

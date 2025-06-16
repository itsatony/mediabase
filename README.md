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
   export MB_POSTGRES_PORT=5435
   export MB_POSTGRES_NAME=mediabase_test
   export MB_POSTGRES_USER=mbase_user
   export MB_POSTGRES_PASSWORD=mbase_secret
   
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
ENST00000343150.10,8.45,CTSL,0.000001,tumor
ENST00000546211.6,6.78,SKP2,0.000012,tumor
ENST00000357033.9,5.23,DMD,0.000045,tumor
ENST00000675596.1,4.89,CEP41,0.000078,tumor
ENST00000570164.5,4.67,RUSF1,0.000123,tumor
```

### Example Patient Data Files

The `examples/` directory contains realistic patient data files for different cancer types:

- `breast_cancer_her2_positive.csv` - HER2-positive breast cancer (57 transcripts) 
- `breast_cancer_triple_negative.csv` - Triple-negative breast cancer (57 transcripts)
- `breast_cancer_luminal_a.csv` - Luminal A breast cancer (55 transcripts)
- `lung_adenocarcinoma_egfr_mutant.csv` - EGFR-mutant lung adenocarcinoma (55 transcripts)
- `colorectal_adenocarcinoma_microsatellite_stable.csv` - Microsatellite stable colorectal cancer (63 transcripts)

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

## Database Schema and Structure

MEDIABASE uses a comprehensive PostgreSQL schema designed for cancer transcriptomics analysis. The main table `cancer_transcript_base` integrates data from multiple biological databases into a unified structure.

### Current Schema Version: v0.1.6

The database schema follows a versioned approach with automated migrations. The current version includes comprehensive support for:

- Gene transcript information from GENCODE
- Protein product classification from UniProt  
- GO terms for functional analysis
- Pathway data from Reactome
- Drug interactions from DrugCentral and ChEMBL
- Scientific literature references from PubMed
- Cross-database identifier mappings

### Core Table: cancer_transcript_base

The main table contains 25 columns covering all aspects of transcript annotation:

| Column | Type | Description |
|--------|------|-------------|
| `transcript_id` | TEXT (Primary Key) | Ensembl transcript identifier (e.g., ENST00000566587.6) |
| `gene_symbol` | TEXT | Human-readable gene symbol (e.g., UBE2I) |
| `gene_id` | TEXT | Ensembl gene identifier |
| `gene_type` | TEXT | Gene biotype (protein_coding, lncRNA, etc.) |
| `chromosome` | TEXT | Chromosome location |
| `coordinates` | JSONB | Genomic coordinates (start, end, strand) |
| `product_type` | TEXT[] | Protein product classifications |
| `go_terms` | JSONB | Gene Ontology term annotations |
| `pathways` | TEXT[] | Reactome pathway memberships |
| `drugs` | JSONB | Drug interaction data |
| `expression_fold_change` | DOUBLE PRECISION | Patient-specific expression data (default: 1.0) |
| `expression_freq` | JSONB | Expression frequency data |
| `cancer_types` | TEXT[] | Associated cancer types |
| `features` | JSONB | UniProt feature annotations |
| `molecular_functions` | TEXT[] | Molecular function classifications |
| `cellular_location` | TEXT[] | Subcellular localization data |
| `drug_scores` | JSONB | Drug interaction confidence scores |
| `alt_transcript_ids` | JSONB | Alternative transcript identifiers |
| `alt_gene_ids` | JSONB | Alternative gene identifiers |
| `uniprot_ids` | TEXT[] | UniProt protein identifiers |
| `ncbi_ids` | TEXT[] | NCBI/Entrez gene identifiers |
| `refseq_ids` | TEXT[] | RefSeq identifiers |
| `pdb_ids` | TEXT[] | Protein Data Bank identifiers |
| `source_references` | JSONB | Publication and evidence references |

### Complete Example Record

Here's a fully populated example record showing all data types and structures:

```json
{
  "transcript_id": "ENST00000566587.6",
  "gene_symbol": "UBE2I",
  "gene_id": "ENSG00000103275",
  "gene_type": "protein_coding",
  "chromosome": "chr16",
  "coordinates": {
    "end": 1325354,
    "start": 1309638,
    "strand": 1
  },
  "product_type": ["cytoplasmic", "nuclear", "rna_binding"],
  "pathways": [
    "Nuclear Envelope (NE) Reassembly [Reactome:R-HSA-2995410]",
    "SARS-CoV-2 Infection [Reactome:R-HSA-9694516]",
    "Metabolism of steroids [Reactome:R-HSA-8957322]"
  ],
  "molecular_functions": [
    "ATP binding",
    "SUMO conjugating enzyme activity", 
    "small protein activating enzyme binding"
  ],
  "cellular_location": [
    "PML body",
    "transferase complex", 
    "nuclear envelope"
  ],
  "drugs": {
    "4344": {
      "name": "Drug compound 4344",
      "score": 138.5,
      "mechanism": "SUMO pathway modulator"
    }
  },
  "drug_scores": {
    "4344": 138.5
  },
  "uniprot_ids": ["P63279", "Q7KZS0", "A0AAA9YHQ4"],
  "ncbi_ids": ["7329"],
  "refseq_ids": [
    "NP_003336.1",
    "NP_919235.1", 
    "NP_919236.1",
    "XP_016879129.1"
  ],
  "alt_transcript_ids": {
    "CCDS": "CCDS10433.1",
    "HAVANA": "OTTHUMT00000431996.1"
  },
  "alt_gene_ids": {
    "HGNC": "HGNC:12485",
    "KEGG": "hsa:7329",
    "OMIM": "601661",
    "HAVANA": "OTTHUMG00000186701.4",
    "Ensembl": "ENSG00000103275.22"
  },
  "go_terms": {
    "GO:0005524": {
      "term": "ATP binding",
      "aspect": "molecular_function",
      "evidence": "IEA"
    },
    "GO:0016925": {
      "term": "protein sumoylation",
      "aspect": "biological_process", 
      "evidence": "TAS"
    }
  },
  "source_references": {
    "drugs": [],
    "uniprot": [],
    "go_terms": [],
    "pathways": [
      {
        "pmid": "",
        "source_db": "Reactome",
        "evidence_type": "Reactome:R-HSA-2995410"
      }
    ],
    "publications": []
  }
}
```

### Key Features for Oncological Analysis

1. **Expression Integration**: The `expression_fold_change` column is updated with patient-specific data
2. **Drug Discovery**: Comprehensive drug interaction data with confidence scores
3. **Pathway Analysis**: Reactome pathway memberships for systems-level analysis  
4. **Functional Classification**: GO terms and molecular function annotations
5. **Cross-References**: Extensive identifier mapping for data integration
6. **Evidence Tracking**: Source references with publication support

### Database Indexes

The schema includes optimized GIN and B-tree indexes for efficient querying:

```sql
-- Array and JSONB indexes for complex queries
CREATE INDEX idx_product_type ON cancer_transcript_base USING GIN(product_type);
CREATE INDEX idx_pathways ON cancer_transcript_base USING GIN(pathways);
CREATE INDEX idx_drugs ON cancer_transcript_base USING GIN(drugs);
CREATE INDEX idx_molecular_functions ON cancer_transcript_base USING GIN(molecular_functions);

-- Standard indexes for common lookups
CREATE INDEX idx_gene_symbol ON cancer_transcript_base(gene_symbol);
CREATE INDEX idx_gene_id ON cancer_transcript_base(gene_id);

-- Cross-reference indexes
CREATE INDEX idx_uniprot_ids ON cancer_transcript_base USING GIN(uniprot_ids);
CREATE INDEX idx_ncbi_ids ON cancer_transcript_base USING GIN(ncbi_ids);
```

### Patient-Specific Schema

When creating patient databases, the schema is fully preserved with all indexes and constraints. Only the `expression_fold_change` values are updated with patient-specific transcriptome data, allowing for:

- Comparative analysis against baseline expression (1.0)
- Identification of significantly up/down-regulated genes
- Pathway-level expression analysis
- Drug target prioritization based on expression levels

## Query Examples and Analysis

### Dynamic Queries - Human Language to SQL

These examples demonstrate how to translate common oncological questions into SQL queries against patient-specific databases.

#### Query 1: "Which genes are significantly upregulated in this patient?"

**Clinical Question**: Identify genes with high expression that may represent therapeutic targets or oncogenic drivers.

```sql
-- Find significantly upregulated transcripts (fold-change > 2.0)
SELECT 
    transcript_id,
    gene_symbol,
    expression_fold_change,
    product_type,
    molecular_functions,
    pathways[1:3] as top_pathways,  -- Show first 3 pathways
    CASE 
        WHEN jsonb_array_length(drugs) > 0 THEN 'Druggable'
        ELSE 'No known drugs'
    END as drug_availability
FROM cancer_transcript_base 
WHERE expression_fold_change > 2.0 
ORDER BY expression_fold_change DESC 
LIMIT 20;
```

**Expected Results** (using HER2+ breast cancer example):
```
transcript_id       | gene_symbol | fold_change | product_type | drug_availability
ENST00000269571    | ERBB2       | 8.45        | [receptor]   | Druggable
ENST00000484667    | GRB7        | 6.78        | [adapter]    | No known drugs
ENST00000355349    | PGAP3       | 5.23        | [enzyme]     | No known drugs
```

#### Query 2: "What drugs target the overexpressed genes in my patient?"

**Clinical Question**: Identify FDA-approved or investigational drugs that target upregulated genes.

```sql
-- Find drugs targeting upregulated genes with clinical evidence
SELECT DISTINCT
    gene_symbol,
    expression_fold_change,
    drug_info->>'name' as drug_name,
    drug_info->>'mechanism' as mechanism_of_action,
    drug_info->>'clinical_status' as clinical_status,
    drug_scores->>'overall_score' as drug_score
FROM cancer_transcript_base,
     jsonb_array_elements(drugs) as drug_info
WHERE expression_fold_change > 1.5
    AND jsonb_array_length(drugs) > 0
    AND (drug_info->>'clinical_status' IN ('approved', 'phase_3', 'phase_2'))
ORDER BY expression_fold_change DESC, (drug_scores->>'overall_score')::float DESC;
```

#### Query 3: "Which pathways are disrupted based on my patient's expression profile?"

**Clinical Question**: Identify biological pathways affected by differential gene expression.

```sql
-- Pathway disruption analysis based on expression changes
WITH pathway_analysis AS (
    SELECT 
        unnest(pathways) as pathway_name,
        AVG(expression_fold_change) as avg_fold_change,
        COUNT(*) as gene_count,
        STDDEV(expression_fold_change) as expression_variance,
        ARRAY_AGG(gene_symbol || ':' || expression_fold_change::text) as affected_genes
    FROM cancer_transcript_base 
    WHERE pathways IS NOT NULL 
        AND array_length(pathways, 1) > 0
        AND ABS(expression_fold_change - 1.0) > 0.5  -- Significant change
    GROUP BY pathway_name
    HAVING COUNT(*) >= 3  -- At least 3 genes in pathway
)
SELECT 
    pathway_name,
    ROUND(avg_fold_change, 2) as average_fold_change,
    gene_count,
    ROUND(expression_variance, 2) as expression_variability,
    CASE 
        WHEN avg_fold_change > 1.5 THEN 'Activated'
        WHEN avg_fold_change < 0.7 THEN 'Suppressed'
        ELSE 'Mixed regulation'
    END as pathway_status,
    affected_genes[1:5] as sample_genes  -- Show first 5 affected genes
FROM pathway_analysis 
ORDER BY ABS(avg_fold_change - 1.0) DESC, gene_count DESC;
```

#### Query 4: "Are there any published studies relevant to my patient's gene expression pattern?"

**Clinical Question**: Find publications that discuss the upregulated genes in context of cancer research.

```sql
-- Find relevant publications for highly expressed genes
SELECT 
    gene_symbol,
    expression_fold_change,
    pub_ref->>'title' as study_title,
    pub_ref->>'journal' as journal,
    pub_ref->>'year' as publication_year,
    pub_ref->>'pmid' as pubmed_id,
    pub_ref->>'evidence_type' as evidence_type,
    pub_ref->>'source_db' as data_source
FROM cancer_transcript_base,
     jsonb_array_elements(source_references->'publications') as pub_ref
WHERE expression_fold_change > 2.0
    AND jsonb_array_length(source_references->'publications') > 0
    AND (pub_ref->>'year')::integer >= 2020  -- Recent publications
ORDER BY expression_fold_change DESC, (pub_ref->>'year')::integer DESC
LIMIT 15;
```

### Standard Oncological Analysis (SOTA) Queries

These queries should be run automatically for every new patient database to provide comprehensive oncological insights.

#### SOTA Query 1: Oncogene and Tumor Suppressor Analysis

**Clinical Rationale**: Identifies dysregulation of known cancer-driving genes, which is fundamental for understanding tumor biology and therapeutic targeting.

```sql
-- Comprehensive oncogene and tumor suppressor analysis
WITH known_cancer_genes AS (
    SELECT gene_symbol, expression_fold_change, product_type, molecular_functions,
           CASE 
               -- Known oncogenes (often amplified/overexpressed in cancer)
               WHEN gene_symbol IN ('MYC', 'ERBB2', 'EGFR', 'KRAS', 'PIK3CA', 'AKT1', 'CCND1', 'MDM2') 
               THEN 'oncogene'
               -- Hormone receptors (context-dependent - can be oncogenes or tumor suppressors)
               WHEN gene_symbol IN ('ESR1', 'PGR', 'AR') AND expression_fold_change > 1.2
               THEN 'hormone_receptor_active'
               WHEN gene_symbol IN ('ESR1', 'PGR', 'AR') AND expression_fold_change < 0.8
               THEN 'hormone_receptor_suppressed'
               -- Known tumor suppressors (often deleted/underexpressed in cancer)  
               WHEN gene_symbol IN ('TP53', 'RB1', 'PTEN', 'BRCA1', 'BRCA2', 'CDKN2A', 'CDKN1A', 'CDKN1B')
               THEN 'tumor_suppressor'
               -- DNA repair genes (critical for genomic stability)
               WHEN gene_symbol IN ('ATM', 'CHEK1', 'CHEK2', 'RAD51', 'PARP1')
               THEN 'dna_repair'
               ELSE 'other'
           END as gene_category
    FROM cancer_transcript_base
    WHERE gene_symbol IN ('MYC', 'ERBB2', 'EGFR', 'KRAS', 'PIK3CA', 'AKT1', 'CCND1', 'MDM2',
                          'TP53', 'RB1', 'PTEN', 'BRCA1', 'BRCA2', 'CDKN2A', 'CDKN1A', 'CDKN1B',
                          'ATM', 'CHEK1', 'CHEK2', 'RAD51', 'PARP1', 'ESR1', 'PGR', 'AR')
)
SELECT 
    gene_category,
    gene_symbol,
    ROUND(expression_fold_change, 2) as fold_change,
    CASE 
        WHEN gene_category = 'oncogene' AND expression_fold_change > 1.5 THEN 'ACTIVATED (Concerning)'
        WHEN gene_category = 'tumor_suppressor' AND expression_fold_change < 0.7 THEN 'SUPPRESSED (Concerning)'
        WHEN gene_category = 'dna_repair' AND expression_fold_change < 0.8 THEN 'IMPAIRED (High Risk)'
        WHEN gene_category = 'hormone_receptor_active' THEN 'ACTIVE (Hormone-sensitive cancer)'
        WHEN gene_category = 'hormone_receptor_suppressed' THEN 'SUPPRESSED (Hormone-independent cancer)'
        WHEN gene_category = 'oncogene' AND expression_fold_change < 0.8 THEN 'Suppressed (Favorable)'
        WHEN gene_category = 'tumor_suppressor' AND expression_fold_change > 1.2 THEN 'Active (Favorable)'
        ELSE 'Normal range'
    END as clinical_significance,
    product_type,
    CASE 
        WHEN jsonb_array_length(drugs) > 0 THEN 'Targetable'
        ELSE 'No approved drugs'
    END as therapeutic_options
FROM known_cancer_genes
ORDER BY 
    CASE gene_category 
        WHEN 'oncogene' THEN 1 
        WHEN 'tumor_suppressor' THEN 2 
        WHEN 'dna_repair' THEN 3 
        ELSE 4 
    END,
    ABS(expression_fold_change - 1.0) DESC;
```

**Clinical Interpretation**:
- **Activated oncogenes** (fold-change > 1.5): Potential therapeutic targets
- **Suppressed tumor suppressors** (fold-change < 0.7): Poor prognosis indicators
- **Impaired DNA repair** (fold-change < 0.8): Candidate for PARP inhibitors or immunotherapy
- **Active hormone receptors**: Hormone-sensitive cancer, endocrine therapy indicated
- **Suppressed hormone receptors**: Hormone-independent cancer, consider alternative therapies

#### SOTA Query 2: Therapeutic Target Prioritization

**Clinical Rationale**: Ranks potential therapeutic targets based on expression level, druggability, and clinical trial availability.

```sql
-- Comprehensive therapeutic target prioritization
WITH druggable_targets AS (
    SELECT 
        gene_symbol,
        expression_fold_change,
        product_type,
        molecular_functions,
        pathways,
        drugs,
        drug_scores,
        -- Calculate target priority score
        CASE 
            WHEN expression_fold_change > 3.0 THEN 3  -- High expression
            WHEN expression_fold_change > 2.0 THEN 2  -- Moderate expression  
            WHEN expression_fold_change > 1.5 THEN 1  -- Mild expression
            ELSE 0
        END +
        CASE 
            WHEN jsonb_array_length(drugs) > 0 THEN 2  -- Has drug interactions
            ELSE 0
        END +
        CASE 
            WHEN 'kinase' = ANY(product_type) THEN 2   -- Kinases are highly druggable
            WHEN 'receptor' = ANY(product_type) THEN 2 -- Receptors are druggable
            WHEN 'enzyme' = ANY(product_type) THEN 1   -- Enzymes moderately druggable
            ELSE 0
        END as priority_score
    FROM cancer_transcript_base
    WHERE expression_fold_change > 1.5  -- Only consider upregulated genes
        AND (jsonb_array_length(drugs) > 0 OR 
             'kinase' = ANY(product_type) OR 
             'receptor' = ANY(product_type) OR
             'enzyme' = ANY(product_type))
)
SELECT 
    gene_symbol,
    ROUND(expression_fold_change, 2) as fold_change,
    priority_score,
    product_type,
    molecular_functions[1:3] as key_functions,
    pathways[1:2] as major_pathways,
    jsonb_array_length(drugs) as available_drugs,
    CASE 
        WHEN priority_score >= 6 THEN 'HIGH PRIORITY - Immediate consideration'
        WHEN priority_score >= 4 THEN 'MEDIUM PRIORITY - Clinical evaluation'  
        WHEN priority_score >= 2 THEN 'LOW PRIORITY - Research interest'
        ELSE 'MINIMAL PRIORITY'
    END as recommendation,
    -- Extract drug information if available
    CASE 
        WHEN jsonb_array_length(drugs) > 0 
        THEN (drugs->0->>'name') || ' (' || (drugs->0->>'clinical_status') || ')'
        ELSE 'No approved drugs - research target'
    END as primary_therapeutic_option
FROM druggable_targets
WHERE priority_score >= 2  -- Only show meaningful targets
ORDER BY priority_score DESC, expression_fold_change DESC
LIMIT 15;
```

**Clinical Interpretation**:
- **High Priority**: Immediate therapeutic consideration, existing drugs available
- **Medium Priority**: Promising targets requiring clinical evaluation
- **Low Priority**: Research targets for future drug development

#### SOTA Query 3: Pathway-Based Therapeutic Strategy

**Clinical Rationale**: Identifies dysregulated pathways that can be targeted with combination therapy approaches, essential for precision oncology.

```sql
-- Comprehensive pathway-based therapeutic strategy analysis
WITH pathway_enrichment AS (
    SELECT 
        unnest(pathways) as pathway_name,
        COUNT(*) as total_genes,
        COUNT(*) FILTER (WHERE expression_fold_change > 1.5) as upregulated_genes,
        COUNT(*) FILTER (WHERE expression_fold_change < 0.7) as downregulated_genes,
        AVG(expression_fold_change) as avg_fold_change,
        ARRAY_AGG(
            CASE WHEN ABS(expression_fold_change - 1.0) > 0.5 
                 THEN gene_symbol || ':' || ROUND(expression_fold_change, 2)::text 
                 ELSE NULL END
        ) FILTER (WHERE ABS(expression_fold_change - 1.0) > 0.5) as dysregulated_genes,
        -- Count druggable targets in pathway
        COUNT(*) FILTER (WHERE jsonb_array_length(drugs) > 0 AND expression_fold_change > 1.5) as druggable_targets
    FROM cancer_transcript_base 
    WHERE pathways IS NOT NULL 
        AND array_length(pathways, 1) > 0
    GROUP BY pathway_name
    HAVING COUNT(*) >= 3  -- At least 3 genes in pathway
),
pathway_classification AS (
    SELECT *,
        CASE 
            -- Oncogenic pathways (typically activated in cancer)
            WHEN pathway_name ILIKE '%PI3K%' OR pathway_name ILIKE '%AKT%' OR pathway_name ILIKE '%mTOR%' THEN 'growth_survival'
            WHEN pathway_name ILIKE '%RAS%' OR pathway_name ILIKE '%MAPK%' OR pathway_name ILIKE '%ERK%' THEN 'proliferation'
            WHEN pathway_name ILIKE '%p53%' OR pathway_name ILIKE '%DNA repair%' OR pathway_name ILIKE '%checkpoint%' THEN 'genome_stability'
            WHEN pathway_name ILIKE '%apoptosis%' OR pathway_name ILIKE '%cell death%' THEN 'apoptosis'
            WHEN pathway_name ILIKE '%angiogenesis%' OR pathway_name ILIKE '%VEGF%' THEN 'angiogenesis'
            WHEN pathway_name ILIKE '%immune%' OR pathway_name ILIKE '%interferon%' THEN 'immune_response'
            WHEN pathway_name ILIKE '%metabolism%' OR pathway_name ILIKE '%glycolysis%' THEN 'metabolism'
            ELSE 'other'
        END as pathway_category,
        -- Calculate pathway dysregulation score
        (upregulated_genes::float / total_genes * 2) +  -- Upregulation weight
        (downregulated_genes::float / total_genes * 1) + -- Downregulation weight  
        (druggable_targets::float / total_genes * 3) as dysregulation_score  -- Druggability weight
    FROM pathway_enrichment
)
SELECT 
    pathway_category,
    pathway_name,
    total_genes,
    upregulated_genes,
    downregulated_genes,
    ROUND(avg_fold_change, 2) as avg_expression_change,
    druggable_targets,
    ROUND(dysregulation_score, 2) as dysregulation_score,
    CASE 
        WHEN dysregulation_score > 4.0 THEN 'CRITICAL - Immediate intervention needed'
        WHEN dysregulation_score > 2.5 THEN 'HIGH - Priority pathway for targeting'
        WHEN dysregulation_score > 1.5 THEN 'MODERATE - Consider combination therapy'
        ELSE 'LOW - Monitor for changes'
    END as therapeutic_priority,
    dysregulated_genes[1:5] as key_dysregulated_genes,  -- Show top 5 dysregulated genes
    CASE 
        WHEN pathway_category = 'growth_survival' AND avg_fold_change > 1.3 
        THEN 'Consider PI3K/AKT/mTOR inhibitors'
        WHEN pathway_category = 'proliferation' AND avg_fold_change > 1.3
        THEN 'Consider MEK/ERK inhibitors'  
        WHEN pathway_category = 'genome_stability' AND avg_fold_change < 0.8
        THEN 'Consider PARP inhibitors or DNA damaging agents'
        WHEN pathway_category = 'apoptosis' AND avg_fold_change < 0.8  
        THEN 'Consider BCL-2 family inhibitors'
        WHEN pathway_category = 'angiogenesis' AND avg_fold_change > 1.3
        THEN 'Consider anti-angiogenic therapy'
        WHEN pathway_category = 'immune_response' AND avg_fold_change < 0.8
        THEN 'Consider immunotherapy approaches'
        ELSE 'Pathway-specific analysis needed'
    END as therapeutic_recommendation
FROM pathway_classification
WHERE dysregulation_score > 1.0  -- Only show significantly dysregulated pathways
ORDER BY dysregulation_score DESC, druggable_targets DESC
LIMIT 20;
```

**Clinical Interpretation**:
- **Critical pathways**: Require immediate therapeutic intervention
- **High priority**: Primary targets for precision therapy
- **Moderate priority**: Combination therapy candidates
- **Therapeutic recommendations**: Specific drug classes based on pathway analysis

### Query Validation Results

**Example Output** (using breast_cancer_her2_positive.csv):

```bash
# Test SOTA Query 1 - Oncogene Analysis
poetry run psql -d mediabase_patient_BREAST_HER2_001 -c "
SELECT gene_symbol, expression_fold_change, product_type,
       CASE WHEN expression_fold_change > 2.0 THEN 'UPREGULATED' 
            WHEN expression_fold_change < 0.5 THEN 'DOWNREGULATED'
            ELSE 'NORMAL' END as expression_status
FROM cancer_transcript_base 
WHERE gene_symbol IN ('CTSL', 'SKP2', 'DMD', 'HARS1', 'UBE2I') 
ORDER BY expression_fold_change DESC;"
```

Expected results:
- **CTSL**: 8.45-fold (UPREGULATED - Protease activity)
- **HARS1**: 7.23-fold (UPREGULATED - tRNA synthetase activity)  
- **SKP2**: 6.78-fold (UPREGULATED - Cell cycle regulation)
- **UBE2I**: 3.78-fold (UPREGULATED - SUMO conjugation)
- **DMD**: 5.23-fold (UPREGULATED - Structural protein)

### Automated Analysis Pipeline

For clinical workflow efficiency, the SOTA queries should be run automatically after patient database creation:

```bash
# Run complete oncological analysis for a patient
poetry run python scripts/run_patient_analysis.py --patient-id PATIENT123

# Run specific analysis modules
poetry run python scripts/run_patient_analysis.py --patient-id PATIENT123 --analysis oncogenes,targets,pathways

# Generate clinical report
poetry run python scripts/run_patient_analysis.py --patient-id PATIENT123 --generate-report
```

**Automated Analysis Includes**:
1. **Oncogene/Tumor Suppressor Analysis** - Identifies critical cancer gene dysregulation
2. **Therapeutic Target Prioritization** - Ranks druggable targets by clinical relevance  
3. **Pathway-Based Strategy** - Identifies dysregulated pathways for combination therapy
4. **Clinical Report Generation** - Produces oncologist-ready summary with recommendations

**Integration with LLM Systems**:
- Query results formatted for LLM input
- Natural language summaries generated
- Clinical decision support integration
- Interactive analysis with follow-up queries

### Query Validation

Validate all queries against current schema:

```bash
# Test query syntax and compatibility
poetry run python scripts/validate_queries.py --test-syntax --test-compatibility

# Validate against specific patient database
poetry run python scripts/validate_queries.py --test-with-database mediabase_patient_PATIENT123
```

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
MB_POSTGRES_PORT=5435            # PostgreSQL port
MB_POSTGRES_NAME=mbase           # Database name
MB_POSTGRES_USER=mbase_user      # Database user
MB_POSTGRES_PASSWORD=mbase_secret # Database password

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

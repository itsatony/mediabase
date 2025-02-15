# MEDIA / Cancer Transcriptome Base

A comprehensive database system for cancer transcriptome analysis with LLM-agent assistance. The system provides a unified PostgreSQL-based resource for querying relationships between transcripts, pathways, and drug interactions.

## Overview

This project creates a pre-joined database table optimized for LLM-agent queries about cancer transcriptome data, enabling:

- Fast pathway analysis
- Drug interaction lookups
- Gene product classification
- Literature-backed insights
- Patient-specific expression analysis

## Setup

### Prerequisites

- Python 3.10 or higher
- Python venv module (`python3-venv` package)
- Git
- PostgreSQL 12+

### Environment Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/itsatony/mediabase.git
   cd mediabase
   ```

2. Set up the virtual environment:
   ```bash
   # Make the setup script executable
   chmod +x setup_venv.sh
   
   # Run the setup script
   ./setup_venv.sh
   
   # Activate the virtual environment
   source mbase/bin/activate
   ```

3. Initialize the project:
   ```bash
   # Make the setup script executable
   chmod +x setup_project.sh
   
   # Run the project setup script
   ./setup_project.sh
   ```

4. Configure the environment:
   ```bash
   # Copy the example environment file
   cp .env.example .env
   
   # Edit the .env file with your settings
   nano .env
   ```

### Development

1. Ensure the virtual environment is activated:
   ```bash
   source mbase/bin/activate
   ```

2. Install dependencies:
   ```bash
   poetry install
   ```

3. Run tests:
   ```bash
   poetry run pytest
   ```

## Quick Start

After completing the setup, you can:

1. Run the ETL pipeline:
   ```bash
   poetry run python scripts/run_etl.py
   ```

2. Start the API server:
   ```bash
   poetry run python -m src.api.server
   ```

3. Explore example notebooks:
   ```bash
   poetry run jupyter lab notebooks/01_data_exploration.ipynb
   ```

## Documentation

Comprehensive documentation is available in the `docs/` directory:

- [Architecture Overview](docs/architecture.md)
- [API Documentation](docs/api.md)
- [Deployment Guide](docs/deployment.md)

## Project Status

Current development status and upcoming milestones:
- [x] Initial project setup (2025-02-02)
- [x] Basic schema design
- [ ] Project structure implementation
- [ ] Data source validation
- [ ] ETL pipeline - Transcript module
- [ ] ETL pipeline - Product Classification
- [ ] ETL pipeline - Pathway Integration
- [ ] ETL pipeline - Drug Integration
- [ ] ETL pipeline - Publication Integration
- [ ] Query optimization
- [ ] LLM-agent integration tests
- [ ] Documentation
- [ ] Production deployment

## Version History

- v0.1.0: Initial MVP plan with public data sources
- v0.1.1: Added publications, patient fold-change support, and ETL sequence
- Repository: [mediabase](https://github.com/itsatony/mediabase)

## Data Flow and Dependencies

```mermaid
graph TD
    A[Gencode GTF] --> B[Base Transcript Table]
    B --> C[Gene Products]
    C --> D[Product Classifications]
    D --> E[Pathways/Processes]
    E --> F[Drug Interactions]
    G[GO Terms] --> E
    H[DrugCentral] --> F
    I[PubMed] --> J[Publications]
    J --> F
    K[Patient Data] --> L[Expression Levels]
    L --> B
```

## Enhanced Database Schema v0.1.1

```sql
CREATE TABLE cancer_transcript_base (
    -- Core identifiers
    transcript_id TEXT PRIMARY KEY,
    gene_symbol TEXT,
    gene_id TEXT,
    
    -- Genomic information
    gene_type TEXT,
    chromosome TEXT,
    coordinates JSONB,  -- {start: int, end: int, strand: int}
    
    -- Classifications
    product_type TEXT[], -- ['enzyme', 'kinase', 'transcription_factor', etc]
    cellular_location TEXT[], -- ['membrane', 'nucleus', 'cytoplasm', etc]
    
    -- Biological context
    go_terms JSONB,    -- {go_id: {term: "", evidence: "", aspect: ""}}
    pathways TEXT[],   -- array of pathway identifiers
    
    -- Drug interactions
    drugs JSONB,       -- {drug_id: {name: "", mechanism: "", evidence: ""}}
    drug_scores JSONB, -- {drug_id: score}
    
    -- Literature
    publications JSONB, -- [{pmid: "", year: "", type: "", relevance: ""}]
    
    -- Expression data
    expression_fold_change FLOAT DEFAULT 1.0,  -- Patient-specific
    expression_freq JSONB DEFAULT '{"high": [], "low": []}',
    
    -- Cancer associations
    cancer_types TEXT[] DEFAULT '{}'
);

-- Indices
CREATE INDEX idx_gene_symbol ON cancer_transcript_base(gene_symbol);
CREATE INDEX idx_gene_id ON cancer_transcript_base(gene_id);
CREATE INDEX idx_drugs ON cancer_transcript_base USING GIN(drugs);
CREATE INDEX idx_product_type ON cancer_transcript_base USING GIN(product_type);
CREATE INDEX idx_pathways ON cancer_transcript_base USING GIN(pathways);
```

## ETL Pipeline Implementation

### 1. Base Transcript Setup

```python
import gtfparse
import pandas as pd

def load_gencode_gtf(file_path):
    df = gtfparse.read_gtf(file_path)
    transcripts = df[df['feature'] == 'transcript']
    return transcripts[['transcript_id', 'gene_id', 'gene_name', 'gene_type']]

def create_base_entries(conn, transcripts_df):
    # Implementation of base table population
    pass
```

### 2. Product Classification

```python
def classify_gene_products(conn):
    """
    Adds product classifications based on GO terms and UniProt features
    """
    sql = """
    UPDATE cancer_transcript_base
    SET product_type = array_append(product_type, 'kinase')
    WHERE gene_symbol IN (
        SELECT DISTINCT gene_symbol 
        FROM cancer_transcript_base 
        WHERE go_terms ? 'GO:0016301'  -- kinase activity
    );
    """
    # Additional classification logic
```

### 3. Pipeline Orchestration

```python
class CancerBaseETL:
    def __init__(self, db_params):
        self.conn = psycopg2.connect(**db_params)
    
    def run_pipeline(self):
        self.load_transcripts()
        self.classify_products()
        self.add_pathways()
        self.add_drugs()
        self.add_publications()
        self.validate()
```

## LLM-Agent Query Examples

### Example 1: Patient-Specific Drug Recommendations

```sql
-- Query: "For my patient's upregulated genes, what drugs might be relevant?"
WITH upregulated_genes AS (
    SELECT gene_symbol, expression_fold_change, drugs
    FROM cancer_transcript_base
    WHERE expression_fold_change > 2.0
),
drug_candidates AS (
    SELECT 
        gene_symbol,
        expression_fold_change,
        jsonb_object_keys(drugs) as drug_id,
        drugs->jsonb_object_keys(drugs)::text as drug_info
    FROM upregulated_genes
    WHERE drugs != '{}'::jsonb
)
SELECT 
    drug_id,
    array_agg(gene_symbol) as target_genes,
    avg(expression_fold_change) as avg_expression_change
FROM drug_candidates
GROUP BY drug_id
ORDER BY avg_expression_change DESC
LIMIT 10;
```

### Example 2: Pathway Analysis

```sql
-- Query: "Which pathways are most affected in my patient's sample?"
WITH affected_pathways AS (
    SELECT 
        unnest(pathways) as pathway,
        expression_fold_change
    FROM cancer_transcript_base
    WHERE expression_fold_change != 1.0
)
SELECT 
    pathway,
    count(*) as gene_count,
    avg(expression_fold_change) as avg_change,
    array_agg(gene_symbol) as genes
FROM affected_pathways
GROUP BY pathway
HAVING count(*) > 3
ORDER BY abs(avg_change) DESC
LIMIT 10;
```

### Example 3: Complex Treatment Insight

```sql
-- Query: "Find drugs that target the most disrupted pathways 
--         and have supporting recent publications"
WITH disrupted_pathways AS (
    -- First find significantly changed pathways
    SELECT unnest(pathways) as pathway_id
    FROM cancer_transcript_base
    WHERE expression_fold_change > 2.0
    GROUP BY pathway_id
    HAVING count(*) > 5
),
relevant_drugs AS (
    -- Find drugs targeting these pathways
    SELECT DISTINCT 
        d.key as drug_id,
        d.value->>'name' as drug_name,
        t.publications
    FROM cancer_transcript_base t,
    jsonb_each(t.drugs) d
    WHERE EXISTS (
        SELECT 1 FROM disrupted_pathways dp
        WHERE dp.pathway_id = ANY(t.pathways)
    )
)
SELECT 
    drug_id,
    drug_name,
    count(DISTINCT p->>'pmid') as recent_publications
FROM relevant_drugs,
jsonb_array_elements(publications) p
WHERE (p->>'year')::int >= 2022
GROUP BY drug_id, drug_name
HAVING count(DISTINCT p->>'pmid') > 2
ORDER BY recent_publications DESC;
```

## Advanced Usage Patterns

### Pattern 1: Multi-Level Drug Discovery

This pattern combines direct drug targets with second-degree pathway interactions:
```sql
WITH target_genes AS (
    SELECT gene_symbol, pathways
    FROM cancer_transcript_base
    WHERE expression_fold_change > 2.0
),
pathway_genes AS (
    SELECT DISTINCT t2.gene_symbol
    FROM target_genes t1
    JOIN cancer_transcript_base t2
    ON t1.pathways && t2.pathways
),
drug_candidates AS (
    SELECT 
        t.gene_symbol as target,
        d.key as drug_id,
        d.value as drug_info
    FROM pathway_genes t,
    jsonb_each(drugs) d
)
SELECT 
    drug_id,
    count(DISTINCT target) as affected_targets,
    array_agg(DISTINCT target) as target_list
FROM drug_candidates
GROUP BY drug_id
ORDER BY affected_targets DESC;
```

### Pattern 2: Mechanistic Insight Query

```sql
-- Find molecular mechanisms potentially explaining expression changes
WITH changed_genes AS (
    SELECT 
        gene_symbol,
        product_type,
        expression_fold_change
    FROM cancer_transcript_base
    WHERE abs(expression_fold_change - 1.0) > 1.0
),
mechanism_analysis AS (
    SELECT 
        unnest(product_type) as mechanism,
        CASE 
            WHEN expression_fold_change > 1.0 THEN 'up'
            ELSE 'down'
        END as direction,
        count(*) as gene_count
    FROM changed_genes
    GROUP BY mechanism, direction
)
SELECT 
    mechanism,
    sum(CASE WHEN direction = 'up' THEN gene_count ELSE 0 END) as upregulated,
    sum(CASE WHEN direction = 'down' THEN gene_count ELSE 0 END) as downregulated
FROM mechanism_analysis
GROUP BY mechanism
HAVING sum(gene_count) > 5
ORDER BY sum(gene_count) DESC;
```

## Known Limitations and Mitigations

1. Expression Fold-Change Sensitivity
   - Issue: Single fold-change value may oversimplify
   - Mitigation: Use confidence intervals in future versions

2. Drug-Target Confidence
   - Issue: Varying levels of evidence
   - Mitigation: Include evidence scores in drug JSONB

3. Pathway Completeness
   - Issue: Missing pathway relationships
   - Mitigation: Regular updates from multiple sources

## Future Query Optimizations

1. Materialized views for common pathway analyses
2. Pre-computed drug rankings
3. Patient cohort comparison views

## Code Style Guide

### General Principles

1. **Clarity Over Cleverness**
   - Code should be immediately comprehensible
   - Avoid complex one-liners
   - Use descriptive names over abbreviated ones

2. **Type Safety**
   - Use Python type hints everywhere
   - Enforce with mypy in strict mode
   ```python
   from typing import List, Dict, Optional
   
   def process_genes(genes: List[str]) -> Dict[str, float]:
       ...
   ```

3. **Documentation**
   - Every module starts with a docstring explaining its purpose
   - Every function/class has a docstring following Google style
   ```python
   def calculate_fold_change(
       base_expression: float,
       sample_expression: float
   ) -> float:
       """Calculate expression fold change between sample and base.
       
       Args:
           base_expression: Base expression level
           sample_expression: Sample expression level
           
       Returns:
           float: Calculated fold change
           
       Raises:
           ValueError: If base_expression is 0
       """
   ```

### Python Specific Rules
1. **Imports**
   ```python
   # Standard library
   from typing import List, Dict
   import json
   
   # Third party
   import pandas as pd
   import numpy as np
   
   # Local
   from src.etl.transcript import TranscriptProcessor
   from src.utils.validation import validate_expression
   ```

2. **Classes**
   ```python
   class GeneProcessor:
       """Process gene-related data and transformations."""
       
       def __init__(self, config: Dict[str, Any]) -> None:
           """Initialize processor with configuration.
           
           Args:
               config: Configuration dictionary
           """
           self.config = config
           self._validate_config()
           
       def _validate_config(self) -> None:
           """Validate configuration settings."""
           ...
   ```

3. **Error Handling**
   ```python
   class ETLError(Exception):
       """Base class for ETL-related errors."""
       
   def process_data(data: pd.DataFrame) -> pd.DataFrame:
       try:
           validated_data = validate_input(data)
           processed_data = transform_data(validated_data)
           return processed_data
       except ValidationError as e:
           logger.error(f"Validation failed: {e}")
           raise ETLError(f"Processing failed: {e}") from e
   ```

4. **Testing**
   ```python
   import pytest
   from src.etl.transcript import TranscriptProcessor
   
   @pytest.fixture
   def processor():
       return TranscriptProcessor(config={'threshold': 0.5})
   
   def test_fold_change_calculation(processor):
       """Test fold change calculation with valid inputs."""
       result = processor.calculate_fold_change(base=1.0, sample=2.0)
       assert result == pytest.approx(2.0)
   ```

### SQL Style

1. **Naming**
   - Tables: singular, lower_snake_case
   - Columns: lower_snake_case
   - Indexes: idx_table_column

2. **Queries**
   ```sql
   -- Multiple lines for complex queries
   SELECT 
       t.gene_symbol,
       t.expression_fold_change,
       jsonb_object_keys(t.drugs) as drug_id
   FROM 
       cancer_transcript_base t
   WHERE 
       t.expression_fold_change > 2.0
   ORDER BY 
       t.expression_fold_change DESC;
   ```

### Version Control

1. **Commit Messages**
   ```
   <type>(<scope>): <description>
   
   [optional body]
   
   [optional footer]
   ```
   Types: feat, fix, docs, style, refactor, test, chore

2. **Branching**
   - main: production code
   - develop: integration branch
   - feature/: new features
   - fix/: bug fixes
   - release/: release preparation


## Project Structure

```tree
mediabase/
├── .github/
│   └── workflows/
│       └── tests.yml
├── src/
│   ├── etl/
│   │   ├── __init__.py
│   │   ├── transcript.py
│   │   ├── products.py
│   │   ├── pathways.py
│   │   ├── drugs.py
│   │   └── publications.py
│   ├── db/
│   │   ├── __init__.py
│   │   ├── schema.py
│   │   ├── migrations/
│   │   └── connection.py
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── logging.py
│   │   └── validation.py
│   └── api/
│       ├── __init__.py
│       └── queries.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_etl/
│   ├── test_db/
│   └── test_api/
├── notebooks/
│   ├── 01_data_exploration.ipynb
│   └── 02_query_examples.ipynb
├── config/
│   ├── __init__.py
│   ├── settings.py
│   └── logging.yml
├── scripts/
│   ├── setup_db.py
│   └── run_etl.py
├── docs/
│   ├── architecture.md
│   ├── api.md
│   └── deployment.md
├── .env.example
├── pyproject.toml
├── poetry.lock
└── README.md
```


## LLM-Agent Integration

The database is optimized for LLM-agent queries. Example usage patterns and common queries are documented in `notebooks/02_query_examples.ipynb`.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

MIT License. See [LICENSE](LICENSE) for details.

# MEDIABASE: Cancer Transcriptome Database

**Version:** 0.4.1 | **Status:** Production-Ready | [CHANGELOG](CHANGELOG.md)

Comprehensive PostgreSQL database for cancer transcriptomics analysis, integrating gene expression data with biological annotations, drug information, disease associations, and scientific literature.

---

## Overview

MEDIABASE combines multiple biological data sources into a unified, queryable database for cancer research:

- **Gene Expression** - GENCODE transcripts with patient-specific fold-change data
- **Biological Context** - GO terms, Reactome pathways, UniProt products
- **Disease Associations** - OpenTargets gene-disease relationships (484K records)
- **Drug Information** - ChEMBL drugs with targets and mechanisms
- **Literature Evidence** - PubMed/PubTator Central (47M+ gene-publication links)
- **Cross-References** - ID mappings across UniProt, NCBI, RefSeq, Ensembl

### Key Features

- **Patient-Specific Analysis**: Create dedicated databases with patient transcriptomics data
- **DESeq2 Support**: Automatic conversion of DESeq2 output (`log2FoldChange` → linear fold-change)
- **RESTful API**: Query endpoints for integration with analysis workflows
- **Production Queries**: 25 validated SQL queries for common analyses
- **Clinical Guides**: HER2+ breast cancer and MSS colorectal cancer examples

---

## Quick Start

### Prerequisites

- Python 3.10+
- Poetry 2.0.1+
- PostgreSQL 12+

### Installation

```bash
# Clone repository
git clone https://github.com/itsatony/mediabase.git
cd mediabase

# Install dependencies
poetry install

# Activate environment
poetry shell
```

### Database Setup

```bash
# Configure environment variables
cp .env.example .env
# Edit .env with your PostgreSQL credentials

# Create database and load schema
poetry run python scripts/manage_db.py --create-db --apply-schema
```

### Run ETL Pipeline

```bash
# Full ETL (downloads ~25 GB data, takes 2-4 hours)
poetry run python scripts/run_etl.py --reset-db --log-level INFO

# Quick test with 100 transcripts (~5 minutes)
poetry run python scripts/run_etl.py --reset-db --limit-transcripts 100 --log-level INFO
```

---

## Usage Examples

### Create Patient-Specific Database

```bash
# From DESeq2 results
poetry run python scripts/create_patient_copy.py \
  --patient-id PATIENT123 \
  --csv-file deseq2_results.csv

# Validate CSV format (dry-run)
poetry run python scripts/create_patient_copy.py \
  --patient-id PATIENT123 \
  --csv-file data.csv \
  --dry-run
```

**CSV Requirements:**
- Columns: `transcript_id` (or `SYMBOL`) and `cancer_fold` (or `log2FoldChange`)
- Format: Standard CSV with header row
- Example: `examples/patient_data_example.csv`

### Query Database

```python
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="mbase",
    user="your_user",
    password="your_password"
)

# Find FDA-approved drugs for overexpressed genes
query = """
SELECT
    g.gene_symbol,
    ctb.expression_fold_change,
    okd.molecule_name as drug_name,
    okd.mechanism_of_action,
    okd.clinical_phase_label
FROM cancer_transcript_base ctb
JOIN genes g ON ctb.gene_symbol = g.gene_symbol
JOIN opentargets_known_drugs okd ON g.gene_id = okd.target_gene_id
WHERE ctb.expression_fold_change > 2.0
  AND okd.is_approved = true
ORDER BY ctb.expression_fold_change DESC
LIMIT 10;
"""

cursor = conn.cursor()
cursor.execute(query)
results = cursor.fetchall()
```

### Start API Server

```bash
# Launch RESTful API
poetry run python -m src.api.server

# API Documentation
open http://localhost:8000/docs

# Search endpoint
curl "http://localhost:8000/api/v1/transcripts?symbol=EGFR"
```

---

## Database Contents

| Data Source | Records | Size | Purpose |
|------------|---------|------|---------|
| **Gene Transcripts** | 78K genes | ~2 GB | Base gene/transcript information |
| **GO Terms** | 1.26M associations | 297 MB | Functional annotations |
| **Pathways** | 113K associations | 39 MB | Reactome pathway memberships |
| **Gene Publications** | 47.4M links | 12 GB | PubMed/PubTator literature |
| **OpenTargets Drugs** | 391K records | 208 MB | Drug-target relationships |
| **OpenTargets Diseases** | 28K diseases | 44 MB | Disease ontology |
| **Gene-Disease Links** | 2.7K associations | 2.2 MB | Evidence-based associations |
| **Target Tractability** | 62K assessments | 66 MB | Druggability scores |

**Total Database Size:** ~23 GB

---

## Documentation

### User Guides
- **[Quick Start](docs/QUICKSTART.md)** - 10-minute hands-on tutorial *(coming soon)*
- **[Schema Reference](docs/MEDIABASE_SCHEMA_REFERENCE.md)** - Complete table documentation
- **[Query Library](docs/MEDIABASE_QUERY_LIBRARY.md)** - 25 validated production queries
- **[OpenTargets Guide](docs/OPENTARGETS_PLATFORM_GUIDE.md)** - Disease associations and drug data
- **[AI Agent Integration](docs/AI_AGENT_INTEGRATION_GUIDE.md)** - LLM integration patterns

### Clinical Examples
- **[HER2+ Breast Cancer](docs/BREAST_CANCER_HER2_GUIDE.md)** - Clinical workflow and queries
- **[MSS Colorectal Cancer](docs/COLORECTAL_CANCER_GUIDE.md)** - Treatment selection examples

### Developer Documentation
- **[CLAUDE.md](CLAUDE.md)** - Development guidelines and common commands
- **[Architecture](docs/architecture.md)** - System design and ETL pipeline
- **[API Documentation](http://localhost:8000/docs)** - Interactive API docs (when server running)

---

## Data Sources

MEDIABASE integrates data from the following sources:

- **GENCODE v47** - Human gene transcripts
- **UniProt 2024_06** - Protein annotations
- **Gene Ontology 2024-09-08** - Functional annotations
- **Reactome v89** - Pathway data
- **OpenTargets Platform v24.09** - Disease associations, drugs, tractability
- **ChEMBL v35** - Drug-target interactions
- **PubTator Central** - Gene-publication associations
- **PubMed** - Scientific literature metadata

---

## Development

### Run Tests

```bash
# All tests
poetry run pytest

# With coverage
poetry run pytest --cov=src

# Specific test suite
poetry run pytest tests/test_deseq2_core_functionality.py -v
```

### Code Quality

```bash
# Format code
poetry run black .

# Type checking
poetry run mypy src

# Lint code
poetry run flake8 src
```

### Common Commands

```bash
# Reset database
poetry run python scripts/manage_db.py --reset

# Run specific ETL modules
poetry run python scripts/run_etl.py --modules transcripts go_terms drugs

# Debug mode
poetry run python scripts/run_etl.py --log-level DEBUG

# Update database to latest schema
poetry run python scripts/manage_db.py --apply-schema
```

---

## Project Structure

```
mediabase/
├── docs/                   # Documentation and guides
├── examples/               # Example patient datasets
├── scripts/                # ETL and management scripts
├── src/
│   ├── api/               # RESTful API server
│   ├── db/                # Database management and schema
│   ├── etl/               # Data extraction, transformation, loading
│   └── utils/             # Shared utilities and logging
├── tests/                 # Test suite
├── .env.example           # Environment configuration template
├── pyproject.toml         # Poetry dependencies
└── README.md              # This file
```

---

## Troubleshooting

### Database Connection Issues

```bash
# Check PostgreSQL is running
systemctl status postgresql

# Test connection
psql -h localhost -p 5432 -U your_user -d mbase -c "\dt"
```

### ETL Errors

```bash
# Check logs for specific module
tail -f logs/etl.log | grep "ERROR"

# Re-run failed module
poetry run python scripts/run_etl.py --modules opentargets --log-level DEBUG
```

### Missing Dependencies

```bash
# Update poetry lock file
poetry lock

# Reinstall all dependencies
rm -rf .venv
poetry install
```

For more troubleshooting guidance, see [CLAUDE.md](CLAUDE.md#troubleshooting).

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes and add tests
4. Run tests and code quality checks
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

**Code Standards:**
- Follow PEP 8 style guidelines
- Add type hints to all functions
- Write tests for new functionality
- Update documentation as needed

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Citation

If you use MEDIABASE in your research, please cite:

```
MEDIABASE: Cancer Transcriptome Database (2025)
Version 0.4.1
https://github.com/itsatony/mediabase
```

---

## Support

- **Issues**: [GitHub Issues](https://github.com/itsatony/mediabase/issues)
- **Documentation**: [docs/](docs/)
- **Examples**: [examples/](examples/)

---

## Acknowledgments

- OpenTargets Platform for disease associations and drug data
- GENCODE for human gene annotations
- UniProt for protein function data
- Reactome for pathway information
- PubTator Central for literature associations
- ChEMBL for drug-target information

---

*Generated with [Claude Code](https://claude.com/claude-code)*

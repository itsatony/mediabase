# Patient Copy Guide

This guide explains how to create patient-specific copies of MEDIABASE with custom transcriptome data for oncological analysis.

## Overview

The patient copy functionality allows oncologists to:
1. Create an independent copy of the MEDIABASE database
2. Load patient-specific fold-change data from transcriptome analysis
3. Query the customized database for patient-specific insights
4. Use the data with LLM agents for clinical discussion

## Quick Start

### Basic Usage

```bash
# Create patient copy with fold-change data
poetry run python scripts/create_patient_copy.py \
    --patient-id PATIENT123 \
    --csv-file patient_transcriptome.csv

# Dry run to validate CSV without making changes
poetry run python scripts/create_patient_copy.py \
    --patient-id PATIENT123 \
    --csv-file patient_transcriptome.csv \
    --dry-run
```

### Advanced Usage

```bash
# Use specific source database
poetry run python scripts/create_patient_copy.py \
    --patient-id PATIENT123 \
    --csv-file patient_data.csv \
    --source-db mediabase_staging

# Enable debug logging
poetry run python scripts/create_patient_copy.py \
    --patient-id PATIENT123 \
    --csv-file patient_data.csv \
    --log-level DEBUG
```

## CSV File Requirements

### Required Columns

The CSV file must contain at least these two columns (exact names or alternatives):

1. **Transcript ID**: Identifies the transcript
   - Required column names: `transcript_id`, `transcript`, `id`, `gene_id`, `ensembl_id`
   - Format: Ensembl transcript IDs (e.g., `ENST00000123456`)

2. **Cancer Fold-Change**: Expression fold-change value
   - Required column names: `cancer_fold`, `fold_change`, `expression_fold_change`, `fold`, `fc`
   - Format: Numeric values (positive, negative, or scientific notation)

### CSV Format Example

```csv
transcript_id,cancer_fold,gene_symbol,p_value
ENST00000456328,2.45,DDX11L1,0.001
ENST00000450305,0.67,WASH7P,0.023
ENST00000488147,1.89,MIR6859-1,0.045
ENST00000619216,3.21,MIR1302-2HG,0.002
ENST00000473358,0.34,MIR1302-2,0.012
```

### Supported Data Types

- **Fold-change values**: Any numeric format including:
  - Positive values: `2.5`, `10.0`
  - Negative values: `-1.5`, `-0.3`
  - Scientific notation: `1.5e-3`, `2.3E+2`
  - Zero values: `0.0`

- **Additional columns**: Any extra columns are ignored but preserved in validation display

### Column Mapping

If your CSV uses different column names, the script will:
1. **Automatically detect** common alternatives (case-insensitive)
2. **Prompt interactively** if automatic detection fails
3. **Show available columns** and ask you to select the correct ones

Example interactive session:
```
Required column: transcript_id
Expected content: Transcript identifier (e.g., ENST00000123456)
Available columns: gene_id, fold, sample_name, pvalue
Select column name: gene_id

Required column: cancer_fold  
Expected content: Fold-change value for cancer expression (numeric)
Available columns: fold, sample_name, pvalue
Select column name: fold
```

## Database Structure

### Target Database

The script creates a new database with the naming pattern:
- **Name**: `mediabase_patient_{PATIENT_ID}`
- **Example**: `mediabase_patient_PATIENT123`

### Data Updates

The script updates the `expression_fold_change` column in the `cancer_transcript_base` table:

```sql
-- Before (default value)
expression_fold_change = 1.0

-- After (with patient data)
expression_fold_change = 2.45  -- From CSV file
```

### Data Preservation

All other data is preserved unchanged:
- Gene annotations
- GO terms
- Pathways
- Drug interactions
- Publication references
- Cross-database IDs

## Environment Setup

### Required Environment Variables

```bash
# Database connection
export MB_POSTGRES_HOST=localhost
export MB_POSTGRES_PORT=5432
export MB_POSTGRES_USER=postgres
export MB_POSTGRES_PASSWORD=your_password

# Source database (optional, defaults to 'mediabase')
export MB_SOURCE_DATABASE=mediabase
```

### Dependencies

Ensure all dependencies are installed:
```bash
poetry install
```

## Validation and Error Handling

### Pre-flight Checks

The script performs comprehensive validation:

1. **File existence**: Verifies CSV file exists and is readable
2. **Database connectivity**: Tests connection to source database
3. **CSV structure**: Validates column names and data types
4. **Data integrity**: Checks for null values and invalid numbers

### Error Recovery

- **Database errors**: Automatic rollback of partial changes
- **CSV errors**: Clear error messages with suggested fixes
- **Missing transcripts**: Logs which transcript IDs were not found in database
- **Partial updates**: Reports successful vs. failed updates

### Validation Output

```
CSV File Information
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
║ Property        ║ Value                                           ║
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ File Path       │ patient_data.csv                                │
│ Rows            │ 15                                              │
│ Columns         │ 5                                               │
│ Available Cols  │ transcript_id, cancer_fold, gene_symbol, p_val  │
└─────────────────┴─────────────────────────────────────────────────┘

Update Statistics
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┓
║ Metric                  ║ Count ║
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━┩
│ CSV rows processed      │ 15    │
│ Valid transcript entries│ 15    │
│ Invalid entries skipped │ 0     │
│ Updates applied         │ 14    │
│ Transcripts not found   │ 1     │
└─────────────────────────┴───────┘
```

## Best Practices

### Data Preparation

1. **Clean your data**: Remove rows with missing transcript IDs or fold-change values
2. **Validate IDs**: Ensure transcript IDs match Ensembl format (ENST...)
3. **Check values**: Verify fold-change values are reasonable (e.g., not extremely large)
4. **Backup source**: Always work from a backed-up source database

### Database Management

1. **Use descriptive patient IDs**: Choose meaningful, unique identifiers
2. **Document metadata**: Keep track of patient database creation dates and source data
3. **Clean up old databases**: Remove patient databases when no longer needed
4. **Monitor disk space**: Patient databases are full copies of the source

### Performance Optimization

1. **Batch processing**: The script automatically processes updates in batches of 1000
2. **Parallel operations**: Use separate patient IDs for concurrent processing
3. **Index maintenance**: Patient databases inherit all indexes from source

## Troubleshooting

### Common Issues

**CSV file not found**
```bash
Error: CSV file not found: patient_data.csv
```
- Solution: Check file path and permissions

**Database connection failed**
```bash
Error: Failed to connect to database
```
- Solution: Verify environment variables and database status

**Column mapping failed**
```bash
Error: Could not automatically detect required columns
```
- Solution: Use interactive mode or rename CSV columns

**Transcript IDs not found**
```bash
Warning: 5 transcripts from CSV were not found in the database
```
- Solution: Verify transcript IDs format and source database content

**Database already exists**
```bash
Database 'mediabase_patient_PATIENT123' already exists. Overwrite? [y/N]
```
- Solution: Choose 'y' to overwrite or use different patient ID

### Debug Mode

Enable detailed logging for troubleshooting:

```bash
poetry run python scripts/create_patient_copy.py \
    --patient-id PATIENT123 \
    --csv-file patient_data.csv \
    --log-level DEBUG
```

### Manual Cleanup

If the script fails partway through:

```sql
-- Drop incomplete patient database
DROP DATABASE IF EXISTS mediabase_patient_PATIENT123;
```

## Integration with Analysis Workflows

### Next Steps After Patient Copy

1. **Connect to patient database**:
   ```bash
   psql -h localhost -U postgres -d mediabase_patient_PATIENT123
   ```

2. **Run standard queries** for oncological analysis (see [Standard Queries Guide](standard_queries.md))

3. **Generate reports** using the patient-specific fold-change data

4. **Use with LLM agents** for interactive analysis and discussion

### Example Queries

```sql
-- Find significantly upregulated transcripts
SELECT 
    transcript_id, 
    gene_symbol, 
    expression_fold_change,
    pathways,
    drugs
FROM cancer_transcript_base 
WHERE expression_fold_change > 2.0 
ORDER BY expression_fold_change DESC 
LIMIT 20;

-- Find downregulated genes with drug targets
SELECT 
    transcript_id,
    gene_symbol,
    expression_fold_change,
    jsonb_pretty(drugs) as drug_targets
FROM cancer_transcript_base 
WHERE expression_fold_change < 0.5 
    AND jsonb_array_length(drugs) > 0
ORDER BY expression_fold_change ASC;
```

## Security Considerations

- **Patient data**: Ensure CSV files are handled according to privacy regulations
- **Database access**: Use appropriate access controls for patient databases  
- **Data retention**: Implement policies for patient database lifecycle management
- **Audit trails**: Log all patient database operations for compliance

## Support

For issues or questions:
1. Check this guide and [troubleshooting section](#troubleshooting)
2. Review the [main README](../README.md) for general setup
3. Check logs in the `logs/` directory
4. Open an issue in the project repository
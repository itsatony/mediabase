#!/bin/bash

# Create Demo Patient Databases Script
# This script creates all demo patient databases with proper environment setup

set -e  # Exit on error

# Set environment variables
export MB_POSTGRES_HOST=localhost
export MB_POSTGRES_PORT=5435
export MB_POSTGRES_USER=mbase_user
export MB_POSTGRES_PASSWORD=mbase_secret

echo "=== Creating Demo Patient Databases ==="
echo "Using database configuration:"
echo "  Host: $MB_POSTGRES_HOST"
echo "  Port: $MB_POSTGRES_PORT"
echo "  User: $MB_POSTGRES_USER"
echo "  Database: mbase"
echo ""

# Function to create patient database non-interactively
create_patient_db() {
    local patient_id=$1
    local csv_file=$2

    echo "Creating patient database: $patient_id"
    echo "Using dataset: $csv_file"

    # Create the database using expect to handle interactive prompt
    expect << EOF
spawn poetry run python scripts/create_patient_copy.py --patient-id "$patient_id" --csv-file "$csv_file" --source-db mbase
expect "Proceed with database creation?" { send "y\r" }
expect eof
EOF

    echo "✓ Completed: $patient_id"
    echo ""
}

# Create all demo patient databases
echo "Creating Breast HER2+ Patient Database..."
create_patient_db "DEMO_BREAST_HER2" "examples/enhanced/demo_breast_her2_enhanced.csv"

echo "Creating Breast Triple-Negative Patient Database..."
create_patient_db "DEMO_BREAST_TNBC" "examples/enhanced/demo_breast_tnbc_enhanced.csv"

echo "Creating Lung EGFR Patient Database..."
create_patient_db "DEMO_LUNG_EGFR" "examples/enhanced/demo_lung_egfr_enhanced.csv"

echo "Creating Colorectal MSI Patient Database..."
create_patient_db "DEMO_COLORECTAL_MSI" "examples/enhanced/demo_colorectal_msi_enhanced.csv"

echo "Creating Pancreatic PDAC Patient Database..."
create_patient_db "DEMO_PANCREATIC_PDAC" "examples/enhanced/demo_pancreatic_pdac_enhanced.csv"

echo "Creating Comprehensive Pan-Cancer Patient Database..."
create_patient_db "DEMO_COMPREHENSIVE" "examples/enhanced/demo_comprehensive_enhanced.csv"

echo "=== All Demo Patient Databases Created Successfully! ==="
echo ""
echo "Available databases:"
PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U mbase_user -d postgres -c "SELECT datname FROM pg_database WHERE datname LIKE 'mediabase_patient_DEMO_%' ORDER BY datname;"

echo ""
echo "Next steps:"
echo "  1. Test SOTA queries on these databases"
echo "  2. Update README with working examples"
echo "  3. Create cancer-specific query examples"
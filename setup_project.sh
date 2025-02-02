#!/bin/bash

# setup_project.sh
# Initializes the Cancer Transcriptome Base project structure
# Must be run from within the mediabase directory

set -e  # Exit on error

# Verify we're in the correct directory
if [[ ! -f "pyproject.toml" && ! -d ".git" ]]; then
    echo "Error: Must be run from the mediabase project root directory"
    exit 1
fi

# Verify virtual environment is activated
if [[ -z "${VIRTUAL_ENV}" ]]; then
    echo "Error: Virtual environment not activated. Please run:"
    echo "source mbase/bin/activate"
    exit 1
fi

echo "Initializing Cancer Transcriptome Base project structure..."

# Create directory structure
echo "Creating directory structure..."

# GitHub workflows
mkdir -p .github/workflows
cat > .github/workflows/tests.yml << 'EOL'
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install poetry
          poetry install
      - name: Run tests
        run: poetry run pytest
EOL

# Source directory
mkdir -p src/{etl,db,utils,api}

# Create __init__.py files
find . -type d -not -path "*/.git*" -exec touch {}/__init__.py \;

# ETL modules
for module in transcript products pathways drugs publications; do
    cat > src/etl/${module}.py << EOL
"""
${module^} processing module for Cancer Transcriptome Base.

This module handles the ETL operations for ${module} data.
"""
from typing import Dict, List, Optional

class ${module^}Processor:
    """Process ${module}-related data and transformations."""
    
    def __init__(self, config: Dict[str, any]) -> None:
        """Initialize processor with configuration."""
        self.config = config
EOL
done

# Database modules
cat > src/db/schema.py << 'EOL'
"""
Database schema definitions for Cancer Transcriptome Base.
"""
from typing import List, Dict
import psycopg2

def create_tables() -> None:
    """Create all required database tables."""
    pass
EOL

mkdir -p src/db/migrations

cat > src/db/connection.py << 'EOL'
"""
Database connection management.
"""
from typing import Optional
import psycopg2
from psycopg2.extensions import connection

def get_connection() -> connection:
    """Get a database connection."""
    pass
EOL

# Utils modules
for util in logging validation; do
    cat > src/utils/${util}.py << EOL
"""
${util^} utilities for Cancer Transcriptome Base.
"""
EOL
done

# API module
cat > src/api/queries.py << 'EOL'
"""
Query definitions and execution for Cancer Transcriptome Base.
"""
from typing import List, Dict, Optional
EOL

# Tests
mkdir -p tests/{test_etl,test_db,test_api}
cat > tests/conftest.py << 'EOL'
"""
PyTest configuration and fixtures.
"""
import pytest
EOL

# Create test files
for dir in test_etl test_db test_api; do
    touch tests/$dir/__init__.py
    cat > tests/$dir/test_basic.py << EOL
"""
Basic tests for ${dir#test_} module.
"""
import pytest
EOL
done

# Notebooks
mkdir -p notebooks
for nb in "01_data_exploration" "02_query_examples"; do
    cat > notebooks/${nb}.ipynb << EOL
{
 "cells": [],
 "metadata": {
  "kernelspec": {
   "display_name": "Python 3",
   "language": "python",
   "name": "python3"
  }
 },
 "nbformat": 4,
 "nbformat_minor": 4
}
EOL
done

# Config
mkdir -p config
cat > config/settings.py << 'EOL'
"""
Configuration settings for Cancer Transcriptome Base.
"""
from typing import Dict, Any

def get_config() -> Dict[str, Any]:
    """Get configuration settings."""
    return {}
EOL

cat > config/logging.yml << 'EOL'
version: 1
formatters:
  default:
    format: '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
handlers:
  console:
    class: logging.StreamHandler
    formatter: default
root:
  level: INFO
  handlers: [console]
EOL

# Scripts
mkdir -p scripts
for script in setup_db run_etl; do
    cat > scripts/${script}.py << EOL
#!/usr/bin/env python3
"""
${script} script for Cancer Transcriptome Base.
"""
import sys
import logging
from pathlib import Path

def main():
    """Main function."""
    pass

if __name__ == "__main__":
    main()
EOL
    chmod +x scripts/${script}.py
done

# Docs
mkdir -p docs
for doc in architecture api deployment; do
    cat > docs/${doc}.md << EOL
# ${doc^} Documentation

## Overview

EOL
done

# Project root files
cat > pyproject.toml << 'EOL'
[tool.poetry]
name = "cancer-transcriptome-base"
version = "0.1.0"
description = "Cancer Transcriptome Base for LLM-agent assistance"
authors = ["Your Name <your.email@example.com>"]

[tool.poetry.dependencies]
python = "^3.10"
pandas = "^2.0.0"
psycopg2-binary = "^2.9.5"
pyyaml = "^6.0"

[tool.poetry.dev-dependencies]
pytest = "^7.3.1"
pytest-cov = "^4.0.0"
black = "^23.3.0"
mypy = "^1.3.0"
pylint = "^2.17.3"

[build-system]
requires = ["poetry-core>=1.0.0"]
build-backend = "poetry.core.masonry.api"

[tool.black]
line-length = 88
include = '\.pyi?$'

[tool.mypy]
python_version = "3.10"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
EOL

cat > .env.example << 'EOL'
# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=cancer_transcriptome
DB_USER=postgres
DB_PASSWORD=password

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
EOL

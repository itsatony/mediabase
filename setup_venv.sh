#!/bin/bash

# setup_venv.sh
# Creates and configures the virtual environment for the Cancer Transcriptome Base project

set -e  # Exit on error

echo "Setting up virtual environment for Cancer Transcriptome Base..."

# Check if python3 is installed
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is required but not installed. Please install Python 3 first."
    exit 1
fi

# Check if venv module is available
python3 -c "import venv" &> /dev/null || {
    echo "Python venv module is required but not installed."
    echo "Please install python3-venv package for your system."
    exit 1
}

# Create virtual environment
echo "Creating virtual environment 'mbase'..."
python3 -m venv mbase

# Activate virtual environment
echo "Activating virtual environment..."
source mbase/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install poetry
echo "Installing poetry..."
pip install poetry

echo "Virtual environment setup complete!"
echo ""
echo "To activate the virtual environment, run:"
echo "source mbase/bin/activate"
echo ""
echo "Next steps:"
echo "1. Activate the virtual environment (command above)"
echo "2. Run './init.sh' to initialize the project"
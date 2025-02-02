#!/bin/bash

# setup_venv.sh
# Creates and configures the virtual environment for the Cancer Transcriptome Base project

set -e  # Exit on error

echo "Setting up Cancer Transcriptome Base development environment..."

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

# Check if virtualenv exists
if [ ! -d "mbase" ]; then
    echo "Creating virtual environment..."
    python3 -m venv mbase || { echo "Failed to create virtual environment"; exit 1; }
fi

# Activate virtual environment
echo "Activating virtual environment..."
source mbase/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install poetry if not present
if ! command -v poetry &> /dev/null; then
    echo "Installing poetry..."
    pip install poetry
fi

# Install project dependencies
echo "Installing project dependencies..."
poetry install

# Copy environment file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
fi

echo "Setup complete! Activate the environment with: source mbase/bin/activate"
echo ""
echo "Next steps:"
echo "1. Activate the virtual environment (command above)"
echo "2. Run './setup_project.sh' to initialize the project"
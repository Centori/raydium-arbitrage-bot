#!/bin/bash

# Raydium Arbitrage Bot - Installation Script
# This script installs all dependencies for both Python and Node.js

set -e

echo "=== Installing Node.js dependencies ==="
npm install

echo ""
echo "=== Setting up Python virtual environment ==="
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "Virtual environment created"
else
    echo "Virtual environment already exists"
fi

echo ""
echo "=== Activating virtual environment and installing Python packages ==="
source venv/bin/activate

# Upgrade pip first
pip install --upgrade pip

# Install requirements
# Note: numba may fail on Python 3.14+, consider using Python 3.13 or removing numba if not needed
pip install -r requirements.txt

echo ""
echo "=== Installation complete ==="
echo ""
echo "To activate the Python virtual environment, run:"
echo "  source venv/bin/activate"
echo ""
echo "Note: If numba installation fails due to Python 3.14, you may need to:"
echo "  1. Use Python 3.13 or earlier, or"
echo "  2. Remove numba from requirements.txt if not essential"

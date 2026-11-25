#!/bin/bash

# BlackMarket AI - Unix Test Script
# For macOS and Linux systems

set -e  # Exit on any error

echo "BlackMarket AI - Running Tests"
echo "==============================="

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Error: Virtual environment not found"
    echo "Please run install_unix.sh first"
    exit 1
fi

# Activate virtual environment
echo -e "\nActivating virtual environment..."
source venv/bin/activate

# Run tests
echo -e "\nRunning test suite..."
echo "===================="

python -m pytest tests/ -v

if [ $? -eq 0 ]; then
    echo -e "\nAll tests passed! ✅"
else
    echo -e "\nSome tests failed ❌"
    echo "Check the output above for details"
fi

echo -e "\nTest execution complete"
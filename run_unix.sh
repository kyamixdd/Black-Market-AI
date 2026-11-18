#!/bin/bash

# BlackMarket AI - Unix Run Script
# For macOS and Linux systems

set -e  # Exit on any error

echo "BlackMarket AI - Starting Application"
echo "====================================="

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Error: Virtual environment not found"
    echo "Please run install_unix.sh first"
    exit 1
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "Warning: .env file not found"
    echo "Creating from template..."
    cp .env.example .env
    echo "Please edit .env file with your configuration"
    read -p "Press Enter to continue or Ctrl+C to exit"
fi

# Activate virtual environment
echo -e "\nActivating virtual environment..."
source venv/bin/activate

# Check if database exists, if not initialize it
if [ ! -f "data/blackmarket.db" ]; then
    echo -e "\nDatabase not found. Initializing..."
    python -c "from database.connection import Database; Database('sqlite:///data/blackmarket.db').init_db()"
fi

# Run the application
echo -e "\nStarting BlackMarket AI..."
echo "Press Ctrl+C to stop"
echo "========================"

python main.py
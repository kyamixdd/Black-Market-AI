#!/bin/bash

# BlackMarket AI - Unix Installation Script
# For macOS and Linux systems

set -e  # Exit on any error

echo "BlackMarket AI - Unix Installation"
echo "=================================="

# Check Python version
echo -e "\nChecking Python installation..."
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "Error: Python is not installed"
    echo "Please install Python 3.10+ from https://python.org"
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD --version 2>&1)
echo "Python version: $PYTHON_VERSION"

# Extract version number
VERSION_MAJOR=$($PYTHON_CMD -c "import sys; print(sys.version_info.major)")
VERSION_MINOR=$($PYTHON_CMD -c "import sys; print(sys.version_info.minor)")

if [ "$VERSION_MAJOR" -lt 3 ] || ([ "$VERSION_MAJOR" -eq 3 ] && [ "$VERSION_MINOR" -lt 10 ]); then
    echo "Error: Python 3.10 or higher is required"
    echo "Please download from https://python.org"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "\nCreating virtual environment..."
    $PYTHON_CMD -m venv venv
fi

# Activate virtual environment
echo -e "\nActivating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo -e "\nUpgrading pip..."
pip install --upgrade pip

# Install dependencies
echo -e "\nInstalling dependencies..."
pip install -r src_tauri/backend/requirements.txt

# Create required directories
echo -e "\nCreating required directories..."
mkdir -p data models logs backups historical cache

# Copy environment file if it doesn't exist
if [ ! -f ".env" ]; then
    echo -e "\nCreating .env file from template..."
    cp .env.example .env
    echo -e "\nPlease edit .env file with your configuration"
    echo "Telegram bot setup:"
    echo "1. Create a bot with @BotFather"
    echo "2. Get your bot token"
    echo "3. Get your chat ID:"
    echo "   curl -s \"https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates\" | jq '.result[0].message.chat.id'"
fi

# Initialize database
echo -e "\nInitializing database..."
$PYTHON_CMD -c "from database.connection import Database; Database('sqlite:///data/blackmarket.db').init_db()"

# Create run script
echo -e "\nCreating run script..."
cat > run_unix.sh << 'EOF'
#!/bin/bash
echo "Starting BlackMarket AI..."
echo
echo "Make sure you are in the correct directory:"
echo "  cd /path/to/BlackMarket-AI"
echo
echo "Activating virtual environment..."
source venv/bin/activate
echo
echo "Running application..."
python main.py
EOF
chmod +x run_unix.sh

# Create test script
echo -e "\nCreating test script..."
cat > test_unix.sh << 'EOF'
#!/bin/bash
echo "Running BlackMarket AI tests..."
echo
echo "Make sure you are in the correct directory:"
echo "  cd /path/to/BlackMarket-AI"
echo
echo "Activating virtual environment..."
source venv/bin/activate
echo
echo "Running tests..."
python -m pytest tests/ -v
EOF
chmod +x test_unix.sh

echo -e "\n\nInstallation complete!"
echo "======================"
echo "To run BlackMarket AI:"
echo "  1. Open terminal in this directory"
echo "  2. Run: ./run_unix.sh"
echo "  3. Or directly: source venv/bin/activate && python main.py"
echo
echo "To run tests:"
echo "  1. Open terminal in this directory"
echo "  2. Run: ./test_unix.sh"
echo
echo "Telegram setup:"
echo "  Edit .env file with your bot token and chat ID"
echo
echo "Happy trading! (Paper trading only)"
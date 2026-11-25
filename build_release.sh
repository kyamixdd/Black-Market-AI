#!/bin/bash

# BlackMarket AI - Release Build Script
# Creates a clean distribution package

set -e

VERSION="1.0.0"
DIST_DIR="dist/blackmarket-ai-${VERSION}"

echo "Building BlackMarket AI v${VERSION} release package..."
echo "=================================================="

# Clean previous builds
rm -rf dist/
mkdir -p "${DIST_DIR}"

# Copy source files using find + tar (works without rsync)
echo "Copying source files..."
# Create a tar archive of source files, excluding patterns
find . -type f \
  ! -path "./venv/*" \
  ! -path "./env/*" \
  ! -path "./.venv/*" \
  ! -path "./__pycache__/*" \
  ! -name "*.pyc" \
  ! -path "./.pytest_cache/*" \
  ! -path "./.git/*" \
  ! -name ".gitignore" \
  ! -path "./data/blackmarket.db" \
  ! -path "./data/blackmarket.db-*" \
  ! -path "./data/backups/*" \
  ! -path "./data/historical/*" \
  ! -path "./data/cache/*" \
  ! -path "./models/*.joblib" \
  ! -path "./models/*.pkl" \
  ! -path "./models/registry/*" \
  ! -path "./logs/*.log" \
  ! -path "./logs/*.log.*" \
  ! -name ".env" \
  ! -name ".env.local" \
  ! -path "./dist/*" \
  ! -path "./build/*" \
  ! -path "./*.egg-info/*" \
  ! -name "*.tmp" \
  ! -name "*.temp" \
  ! -name ".DS_Store" \
  ! -name "Thumbs.db" \
  ! -path "./.vscode/*" \
  ! -path "./.idea/*" \
  -print0 | tar --null -cf - -T - | tar -xf - -C "${DIST_DIR}/"

# Create required directories in distribution
mkdir -p "${DIST_DIR}/data/backups"
mkdir -p "${DIST_DIR}/data/historical"
mkdir -p "${DIST_DIR}/data/cache"
mkdir -p "${DIST_DIR}/models"
mkdir -p "${DIST_DIR}/logs"

# Create .gitignore
cp .gitignore "${DIST_DIR}/.gitignore"

# Create .env template
cp .env.example "${DIST_DIR}/.env.example"

# Create version file
echo "${VERSION}" > "${DIST_DIR}/VERSION"

# Create README copy
cp README.md "${DIST_DIR}/README.md"

# Create license
cat > "${DIST_DIR}/LICENSE" << 'EOF'
BlackMarket AI - Local Paper Trading Research System
Version 1.0.0

This software is provided for educational and research purposes only.
No real money is ever at risk. Paper trading only.

Use at your own risk.
EOF

# Create archive
echo "Creating archive..."
cd dist
tar -czf "blackmarket-ai-${VERSION}.tar.gz" "blackmarket-ai-${VERSION}/"
zip -r "blackmarket-ai-${VERSION}.zip" "blackmarket-ai-${VERSION}/" > /dev/null
cd ..

echo ""
echo "Build complete!"
echo "=================="
echo "Distribution package: dist/blackmarket-ai-${VERSION}.tar.gz"
echo "Distribution package: dist/blackmarket-ai-${VERSION}.zip"
echo ""
echo "Contents:"
ls -la dist/
echo ""
echo "Package size:"
du -h "dist/blackmarket-ai-${VERSION}.tar.gz"
du -h "dist/blackmarket-ai-${VERSION}.zip"
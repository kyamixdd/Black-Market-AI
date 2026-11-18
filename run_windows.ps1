#!/usr/bin/env pwsh

<#
.SYNOPSIS
    BlackMarket AI - Windows Run Script
.DESCRIPTION
    This script runs BlackMarket AI on Windows systems.
#>

# Set error preference
$ErrorActionPreference = "Stop"

Write-Host "BlackMarket AI - Starting Application" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Green

# Check if virtual environment exists
if (-not (Test-Path "venv")) {
    Write-Host "Error: Virtual environment not found" -ForegroundColor Red
    Write-Host "Please run install_windows.ps1 first" -ForegroundColor Red
    exit 1
}

# Check if .env file exists
if (-not (Test-Path ".env")) {
    Write-Host "Warning: .env file not found" -ForegroundColor Yellow
    Write-Host "Creating from template..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "Please edit .env file with your configuration" -ForegroundColor Yellow
    Read-Host "Press Enter to continue or Ctrl+C to exit"
}

# Activate virtual environment
Write-Host "`nActivating virtual environment..." -ForegroundColor Yellow
& .\venv\Scripts\Activate.ps1

# Check if database exists, if not initialize it
if (-not (Test-Path "data\blackmarket.db")) {
    Write-Host "`nDatabase not found. Initializing..." -ForegroundColor Yellow
    python -c "from database.connection import Database; Database('sqlite:///data/blackmarket.db').init_db()"
}

# Run the application
Write-Host "`nStarting BlackMarket AI..." -ForegroundColor Yellow
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host "========================" -ForegroundColor Yellow

python main.py
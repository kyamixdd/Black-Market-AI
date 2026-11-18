#!/usr/bin/env pwsh

<#
.SYNOPSIS
    BlackMarket AI - Windows Test Script
.DESCRIPTION
    This script runs BlackMarket AI tests on Windows systems.
#>

# Set error preference
$ErrorActionPreference = "Stop"

Write-Host "BlackMarket AI - Running Tests" -ForegroundColor Green
Write-Host "===============================" -ForegroundColor Green

# Check if virtual environment exists
if (-not (Test-Path "venv")) {
    Write-Host "Error: Virtual environment not found" -ForegroundColor Red
    Write-Host "Please run install_windows.ps1 first" -ForegroundColor Red
    exit 1
}

# Activate virtual environment
Write-Host "`nActivating virtual environment..." -ForegroundColor Yellow
& .\venv\Scripts\Activate.ps1

# Run tests
Write-Host "`nRunning test suite..." -ForegroundColor Yellow
Write-Host "====================" -ForegroundColor Yellow

python -m pytest tests/ -v

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nAll tests passed! ✅" -ForegroundColor Green
} else {
    Write-Host "`nSome tests failed ❌" -ForegroundColor Red
    Write-Host "Check the output above for details" -ForegroundColor Yellow
}

Write-Host "`nTest execution complete" -ForegroundColor Cyan
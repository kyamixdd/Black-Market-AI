#!/usr/bin/env pwsh

<#
.SYNOPSIS
    BlackMarket AI - Windows Installation Script
.DESCRIPTION
    This script installs BlackMarket AI on Windows systems.
#>

# Set error preference
$ErrorActionPreference = "Stop"

Write-Host "BlackMarket AI - Windows Installation" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Green

# Check Python version
Write-Host "`nChecking Python installation..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "Python version: $pythonVersion" -ForegroundColor Green

    # Extract version number
    $versionMatch = [regex]::Match($pythonVersion, "(\d+\.\d+)")
    if ($versionMatch.Success) {
        $majorMinor = $versionMatch.Groups[1].Value
        $versionParts = $majorMinor.Split('.')
        $major = [int]$versionParts[0]
        $minor = [int]$versionParts[1]

        if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
            Write-Host "Error: Python 3.10 or higher is required" -ForegroundColor Red
            Write-Host "Please download from https://python.org" -ForegroundColor Red
            exit 1
        }
    }
} catch {
    Write-Host "Error: Python is not installed or not in PATH" -ForegroundColor Red
    Write-Host "Please download Python 3.10+ from https://python.org" -ForegroundColor Red
    exit 1
}

# Check if virtual environment exists
if (-not (Test-Path "venv")) {
    Write-Host "`nCreating virtual environment..." -ForegroundColor Yellow
    python -m venv venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Failed to create virtual environment" -ForegroundColor Red
        exit 1
    }
}

# Activate virtual environment
Write-Host "`nActivating virtual environment..." -ForegroundColor Yellow
& .\venv\Scripts\Activate.ps1

# Upgrade pip
Write-Host "`nUpgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip

# Install dependencies
Write-Host "`nInstalling dependencies..." -ForegroundColor Yellow
pip install -r src_tauri/backend/requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: Failed to install dependencies" -ForegroundColor Red
    exit 1
}

# Create required directories
Write-Host "`nCreating required directories..." -ForegroundColor Yellow
$directories = @("data", "models", "logs", "backups", "historical", "cache")
foreach ($dir in $directories) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null
    }
}

# Copy environment file if it doesn't exist
if (-not (Test-Path ".env")) {
    Write-Host "`nCreating .env file from template..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "`nPlease edit .env file with your configuration" -ForegroundColor Yellow
    Write-Host "Telegram bot setup:" -ForegroundColor Cyan
    Write-Host "1. Create a bot with @BotFather" -ForegroundColor Cyan
    Write-Host "2. Get your bot token" -ForegroundColor Cyan
    Write-Host "3. Get your chat ID:" -ForegroundColor Cyan
    Write-Host "   curl -s `"https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`" | jq '.result[0].message.chat.id'" -ForegroundColor Cyan
}

# Initialize database
Write-Host "`nInitializing database..." -ForegroundColor Yellow
python -c "from database.connection import Database; Database('sqlite:///data/blackmarket.db').init_db()"

# Create test script
Write-Host "`nCreating test script..." -ForegroundColor Yellow
@"
@echo off
echo Running BlackMarket AI tests...
echo.
echo Make sure you are in the correct directory:
echo   cd /path/to/BlackMarket-AI
echo.
echo Activating virtual environment...
call venv\Scripts\activate.bat
echo.
echo Running tests...
python -m pytest tests/ -v
"@ | Out-File -FilePath "test_windows.bat" -Encoding ASCII

# Create desktop shortcut (optional)
Write-Host "`nWould you like to create a desktop shortcut?" -ForegroundColor Yellow
$createShortcut = Read-Host "Create shortcut? (y/N)"
if ($createShortcut -eq "y" -or $createShortcut -eq "Y") {
    $desktopExecutables = @(
        (Join-Path $PSScriptRoot "blackmarket-desktop\src-tauri\target\release\BlackMarket AI.exe"),
        (Join-Path $PSScriptRoot "blackmarket-desktop\src-tauri\target\release\app.exe"),
        (Join-Path $PSScriptRoot "blackmarket-desktop\src-tauri\target\debug\BlackMarket AI.exe"),
        (Join-Path $PSScriptRoot "blackmarket-desktop\src-tauri\target\debug\app.exe")
    )
    $desktopExecutable = $desktopExecutables | Where-Object { Test-Path $_ } | Select-Object -First 1

    if (-not $desktopExecutable) {
        Write-Host "Desktop executable not found; no shortcut was created." -ForegroundColor Yellow
        Write-Host "Build or install the Tauri desktop app first. START_BLACKMARKET.bat is only a fallback." -ForegroundColor Yellow
    } else {
        $desktopPath = [Environment]::GetFolderPath("Desktop")
        $shortcutPath = Join-Path $desktopPath "BlackMarket AI.lnk"

        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = $desktopExecutable
        $shortcut.WorkingDirectory = Split-Path -Parent $desktopExecutable
        $shortcut.Description = "BlackMarket AI Desktop"
        $shortcut.Save()

        Write-Host "Desktop application shortcut created" -ForegroundColor Green
    }
}

Write-Host "`n`nInstallation complete!" -ForegroundColor Green
Write-Host "========================" -ForegroundColor Green
Write-Host "Primary desktop experience:" -ForegroundColor Yellow
Write-Host "  Launch the BlackMarket AI desktop executable or its shortcut." -ForegroundColor White
Write-Host "Fallback/development tools:" -ForegroundColor Yellow
Write-Host "  START_BLACKMARKET.bat  - Launch the desktop app or Tauri development app" -ForegroundColor White
Write-Host "  STOP_BLACKMARKET.bat   - Request graceful desktop shutdown" -ForegroundColor White
Write-Host "  CHECK_BLACKMARKET.bat  - Inspect backend readiness" -ForegroundColor White
Write-Host "  .\run_windows.ps1      - Run the legacy terminal dashboard" -ForegroundColor White
Write-Host ""
Write-Host "To run tests:" -ForegroundColor Yellow
Write-Host "  1. Open PowerShell/CMD in this directory" -ForegroundColor White
Write-Host "  2. Run: test_windows.bat" -ForegroundColor White
Write-Host ""
Write-Host "Telegram setup:" -ForegroundColor Yellow
Write-Host "  Edit .env file with your bot token and chat ID" -ForegroundColor White
Write-Host ""
Write-Host "Happy trading! (Paper trading only)" -ForegroundColor Cyan
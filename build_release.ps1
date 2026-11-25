#!/usr/bin/env pwsh

param(
    [string]$Version = "1.0.0",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$repoRoot = $PSScriptRoot
$outputRoot = Join-Path $repoRoot "release-output"
$packageName = "blackmarket-ai-$Version"
$packagePath = Join-Path $outputRoot $packageName
$zipPath = Join-Path $outputRoot "$packageName.zip"
$tarPath = Join-Path $outputRoot "$packageName.tar.gz"

if ((Test-Path -LiteralPath $packagePath) -or (Test-Path -LiteralPath $zipPath) -or (Test-Path -LiteralPath $tarPath)) {
    throw "Release $Version already exists. Existing versioned releases are never overwritten."
}

$excludedDirectories = @(
    ".git", ".claude", ".vscode", ".idea",
    "node_modules", "venv", ".venv", "env",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".nox",
    "target", "build", "tests", "backups", "cache", "data", "historical", "logs",
    "release-output"
)
$excludedFileNames = @(
    ".env", ".env.local", ".env.development", ".env.production",
    ".pypirc", "Thumbs.db", ".DS_Store"
)
$excludedExtensions = @(
    ".pyc", ".pyo", ".tmp", ".temp", ".log",
    ".db", ".sqlite", ".sqlite3", ".joblib", ".pkl",
    ".pem", ".key", ".secret"
)

$files = [System.Collections.Generic.List[System.IO.FileInfo]]::new()
$directories = [System.Collections.Generic.Stack[string]]::new()
$directories.Push($repoRoot)

while ($directories.Count -gt 0) {
    $currentDirectory = $directories.Pop()
    foreach ($item in Get-ChildItem -LiteralPath $currentDirectory -Force) {
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            continue
        }

        $relativePath = $item.FullName.Substring($repoRoot.Length).TrimStart('\')
        $segments = $relativePath -split '[\\/]'
        if ($segments | Where-Object { $excludedDirectories -contains $_ }) {
            continue
        }

        if ($item.PSIsContainer) {
            if ($relativePath -eq "dist") {
                continue
            }
            $directories.Push($item.FullName)
            continue
        }

        if ($excludedFileNames -contains $item.Name) {
            continue
        }
        if ($item.Name -like ".env.*" -and $item.Name -ne ".env.example") {
            continue
        }
        if ($excludedExtensions -contains $item.Extension.ToLowerInvariant() -or $item.Name -match '(?i)\.(db|sqlite|sqlite3)(-|$)') {
            continue
        }
        $files.Add($item)
    }
}

Write-Host "Release: $packageName" -ForegroundColor Green
Write-Host "Output:  $outputRoot" -ForegroundColor Cyan
Write-Host "Files:   $($files.Count)" -ForegroundColor Cyan

if ($DryRun) {
    Write-Host "Dry run only; no files or directories were created." -ForegroundColor Yellow
    $files | ForEach-Object {
        Write-Host ("  " + $_.FullName.Substring($repoRoot.Length).TrimStart('\'))
    }
    return
}

New-Item -ItemType Directory -Path $packagePath | Out-Null
foreach ($file in $files) {
    $relativePath = $file.FullName.Substring($repoRoot.Length).TrimStart('\')
    $destination = Join-Path $packagePath $relativePath
    $destinationDirectory = Split-Path -Parent $destination
    New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null
    Copy-Item -LiteralPath $file.FullName -Destination $destination
}

@"
BlackMarket AI - Local Paper Trading Research System
Version $Version

This software is provided for educational and research purposes only.
No real money is ever at risk. Paper trading only.

Use at your own risk.
"@ | Set-Content -LiteralPath (Join-Path $packagePath "LICENSE") -Encoding ASCII
$Version | Set-Content -LiteralPath (Join-Path $packagePath "VERSION") -Encoding ASCII

New-Item -ItemType Directory -Path (Join-Path $packagePath "data\backups") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $packagePath "logs") -Force | Out-Null

Compress-Archive -Path $packagePath -DestinationPath $zipPath
if (Get-Command tar -ErrorAction SilentlyContinue) {
    & tar -czf $tarPath -C $outputRoot $packageName
    if ($LASTEXITCODE -ne 0) {
        throw "tar failed to create $tarPath"
    }
}

Write-Host "Release package created:" -ForegroundColor Green
Write-Host "  $zipPath" -ForegroundColor Cyan
if (Test-Path -LiteralPath $tarPath) {
    Write-Host "  $tarPath" -ForegroundColor Cyan
}

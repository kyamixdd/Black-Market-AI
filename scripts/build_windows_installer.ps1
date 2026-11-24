param([switch]$SkipNpmInstall)
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DesktopRoot = Join-Path $RepoRoot "blackmarket-desktop"

& (Join-Path $PSScriptRoot "build_windows_backend.ps1")
if ($LASTEXITCODE -ne 0) { throw "Bundled backend build failed." }

Push-Location $DesktopRoot
try {
    if (-not $SkipNpmInstall) {
        npm ci
        if ($LASTEXITCODE -ne 0) { throw "npm ci failed." }
    }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "Desktop frontend build failed." }
    npm run tauri:build
    if ($LASTEXITCODE -ne 0) { throw "Tauri NSIS installer build failed." }
} finally { Pop-Location }
Write-Host "Windows NSIS installer build completed." -ForegroundColor Green

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DesktopRoot = Join-Path $RepoRoot "blackmarket-desktop"
$TauriRoot = Join-Path $DesktopRoot "src-tauri"
$OutputRoot = Join-Path $TauriRoot "resources\backend"
$BuildRoot = Join-Path $env:TEMP "blackmarket-backend-pyinstaller"

Write-Host "Building self-contained BlackMarket AI Windows backend..." -ForegroundColor Cyan

$Python = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    try { & py -3.12 --version *> $null; if ($LASTEXITCODE -eq 0) { $Python = "py -3.12" } } catch {}
}
if (-not $Python -and (Get-Command python -ErrorAction SilentlyContinue)) {
    & python --version
    if ($LASTEXITCODE -eq 0) { $Python = "python" }
}
if (-not $Python) { throw "Python 3.12 is required on the BUILD machine. The installed app will not require Python." }

if (Test-Path $BuildRoot) { Remove-Item $BuildRoot -Recurse -Force }
New-Item -ItemType Directory -Path $BuildRoot -Force | Out-Null
$Venv = Join-Path $BuildRoot "venv"
if ($Python -eq "py -3.12") { & py -3.12 -m venv $Venv } else { & python -m venv $Venv }
if ($LASTEXITCODE -ne 0) { throw "Could not create backend build environment." }
$VenvPython = Join-Path $Venv "Scripts\python.exe"

& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip bootstrap failed." }
& $VenvPython -m pip install -r (Join-Path $RepoRoot "src_tauri\backend\requirements.txt") pyinstaller==6.14.2
if ($LASTEXITCODE -ne 0) { throw "Backend dependency installation failed." }

$env:PYTHONPATH = $RepoRoot
$PyInstallerArgs = @(
    "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
    "--name", "BlackMarketBackend",
    "--distpath", (Join-Path $BuildRoot "dist"),
    "--workpath", (Join-Path $BuildRoot "work"),
    "--specpath", $BuildRoot,
    "--paths", $RepoRoot,
    "--hidden-import", "uvicorn.logging",
    "--hidden-import", "uvicorn.loops.auto",
    "--hidden-import", "uvicorn.protocols.http.auto",
    "--hidden-import", "uvicorn.protocols.websockets.auto",
    "--hidden-import", "uvicorn.lifespan.on",
    (Join-Path $RepoRoot "src_tauri\backend\main.py")
)
& $VenvPython @PyInstallerArgs
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed to freeze the backend." }

$BuiltBackend = Join-Path $BuildRoot "dist\BlackMarketBackend"
$Executable = Join-Path $BuiltBackend "BlackMarketBackend.exe"
if (-not (Test-Path $Executable)) { throw "PyInstaller output executable was not created." }
if (Test-Path $OutputRoot) { Remove-Item $OutputRoot -Recurse -Force }
New-Item -ItemType Directory -Path (Split-Path -Parent $OutputRoot) -Force | Out-Null
Copy-Item $BuiltBackend $OutputRoot -Recurse -Force
$PackagedSizeMB = [math]::Round((Get-ChildItem $OutputRoot -File -Recurse | Measure-Object Length -Sum).Sum / 1MB, 1)
Write-Host "Packaged backend ready: $Executable ($PackagedSizeMB MB)" -ForegroundColor Green

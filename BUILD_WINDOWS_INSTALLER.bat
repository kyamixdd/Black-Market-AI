@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo BlackMarket AI - Check and Build Installer
echo ============================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: .venv\Scripts\python.exe was not found.
    echo Create the project virtual environment and install backend dependencies first.
    echo See README.md - Desktop development.
    goto :failed
)

where node >nul 2>nul
if errorlevel 1 (
    echo ERROR: Node.js is required but was not found on PATH.
    goto :failed
)
where npm >nul 2>nul
if errorlevel 1 (
    echo ERROR: npm is required but was not found on PATH.
    goto :failed
)
where py >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python Launcher is required to select the Python 3.12 backend build toolchain.
    goto :failed
)
py -3.12 --version >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python 3.12 was not found. Install Python 3.12 for the installer build.
    goto :failed
)
where cargo >nul 2>nul
if errorlevel 1 (
    echo ERROR: Rust/Cargo is required for the Tauri installer build.
    goto :failed
)

echo [1/6] Compile Python backend...
".venv\Scripts\python.exe" -m compileall -q core exchange market intelligence strategies learning paper_trading database src_tauri\backend
if errorlevel 1 goto :failed

echo.
echo [2/6] Run Python regression tests (live exchange tests excluded)...
".venv\Scripts\python.exe" -m pytest -q -m "not live"
if errorlevel 1 goto :failed

echo.
echo [3/6] Install locked desktop dependencies...
pushd "blackmarket-desktop"
call npm ci
if errorlevel 1 goto :desktop_failed

echo.
echo [4/6] Run desktop tests and lint...
call npm test
if errorlevel 1 goto :desktop_failed
call npm run lint
if errorlevel 1 goto :desktop_failed
popd

echo.
echo [5/6] Verify product version metadata...
".venv\Scripts\python.exe" scripts\verify_release_version.py
if errorlevel 1 goto :failed

echo.
echo [6/6] Build the self-contained backend and Windows NSIS installer...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\build_windows_installer.ps1 -SkipNpmInstall
if errorlevel 1 goto :failed

echo.
echo Generate installer checksum and release manifest...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $bundle='blackmarket-desktop\src-tauri\target\release\bundle\nsis'; $installer=Get-ChildItem -LiteralPath $bundle -Filter '*_x64-setup.exe' | Sort-Object LastWriteTime -Descending | Select-Object -First 1; if (-not $installer) { throw 'Tauri build completed but no x64 NSIS installer was found.' }; & '.\scripts\write_release_manifest.ps1' -InstallerPath $installer.FullName -OutputDirectory '.\release-output'; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; Write-Host ('Installer: ' + $installer.FullName)"
if errorlevel 1 goto :failed

echo.
echo SUCCESS: checks passed and the Windows installer was created.
echo See blackmarket-desktop\src-tauri\target\release\bundle\nsis\
echo Checksum and release metadata are in release-output\
pause
exit /b 0

:desktop_failed
popd
goto :failed

:failed
echo.
echo FAILED: a check or build step returned an error. Review the output above.
pause
exit /b 1

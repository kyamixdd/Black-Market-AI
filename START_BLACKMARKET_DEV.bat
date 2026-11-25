@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "PROJECT_DIR=%~dp0"
set "DESKTOP_DIR=%PROJECT_DIR%blackmarket-desktop"

if not exist "%DESKTOP_DIR%\package.json" (
    echo ERROR: BlackMarket desktop project was not found:
    echo   %DESKTOP_DIR%
    pause
    exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
    echo ERROR: Node.js and npm are required. Install Node.js, then reopen this file.
    pause
    exit /b 1
)

pushd "%DESKTOP_DIR%"
if errorlevel 1 (
    echo ERROR: Could not open the desktop project directory.
    pause
    exit /b 1
)

if not exist "package-lock.json" (
    echo ERROR: Desktop package-lock.json is missing; refusing an unpinned install.
    goto :failed
)

if not exist "node_modules\.bin\tauri.cmd" (
    echo Installing locked desktop dependencies...
    call npm ci
    if errorlevel 1 (
        set "EXIT_CODE=!ERRORLEVEL!"
        goto :failed
    )
)

echo.
echo Running desktop lint...
call npm run lint
if errorlevel 1 (
    set "EXIT_CODE=!ERRORLEVEL!"
    goto :failed
)

echo.
echo Running desktop tests...
call npm test
if errorlevel 1 (
    set "EXIT_CODE=!ERRORLEVEL!"
    goto :failed
)

echo.
echo Building the desktop frontend...
call npm run build
if errorlevel 1 (
    set "EXIT_CODE=!ERRORLEVEL!"
    goto :failed
)

echo.
echo Starting BlackMarket AI with its Tauri-managed backend...
echo For browser access, open http://localhost:3000 while this launcher is running.
echo If port 8765 reports HTTP 500, quit any older BlackMarket AI instance from the system tray and retry.
call npm run tauri:dev
set "EXIT_CODE=!ERRORLEVEL!"
popd
if not "!EXIT_CODE!"=="0" (
    echo ERROR: BlackMarket AI startup failed with exit code !EXIT_CODE!.
    pause
)
exit /b %EXIT_CODE%

:failed
if not defined EXIT_CODE set "EXIT_CODE=1"
echo.
echo ERROR: Preflight failed; BlackMarket AI was not started.
popd
pause
exit /b %EXIT_CODE%

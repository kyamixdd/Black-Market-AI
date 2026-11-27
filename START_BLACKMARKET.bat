@echo off
setlocal

set "PROJECT_DIR=%~dp0"
set "DESKTOP_DIR=%PROJECT_DIR%blackmarket-desktop"
set "DESKTOP_EXE="

if defined BLACKMARKET_DESKTOP_EXE (
    if not exist "%BLACKMARKET_DESKTOP_EXE%" goto invalid_custom_executable
    set "DESKTOP_EXE=%BLACKMARKET_DESKTOP_EXE%"
    goto launch_desktop
)

for %%E in (
    "%DESKTOP_DIR%\src-tauri\target\release\BlackMarket AI.exe"
    "%DESKTOP_DIR%\src-tauri\target\release\app.exe"
    "%DESKTOP_DIR%\src-tauri\target\debug\BlackMarket AI.exe"
    "%DESKTOP_DIR%\src-tauri\target\debug\app.exe"
) do (
    if not defined DESKTOP_EXE if exist "%%~E" set "DESKTOP_EXE=%%~E"
)

if defined DESKTOP_EXE goto launch_desktop

if not exist "%DESKTOP_DIR%\node_modules\.bin\tauri.cmd" goto desktop_executable_missing

echo No built desktop executable was found. Starting the Tauri development app.
echo This console remains open to show build and runtime errors.
pushd "%DESKTOP_DIR%"
call ".\node_modules\.bin\tauri.cmd" dev --config src-tauri/tauri.dev.conf.json
set "LAUNCH_RESULT=%ERRORLEVEL%"
popd
if not "%LAUNCH_RESULT%"=="0" (
    echo ERROR: Tauri development startup failed with exit code %LAUNCH_RESULT%.
    pause
)
exit /b %LAUNCH_RESULT%

:launch_desktop
for %%I in ("%DESKTOP_EXE%") do set "DESKTOP_WORKDIR=%%~dpI"
set "BLACKMARKET_LAUNCH_EXE=%DESKTOP_EXE%"
set "BLACKMARKET_LAUNCH_DIR=%DESKTOP_WORKDIR%"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference = 'Stop'; try { $process = Start-Process -FilePath $env:BLACKMARKET_LAUNCH_EXE -WorkingDirectory $env:BLACKMARKET_LAUNCH_DIR -PassThru -ErrorAction Stop; Start-Sleep -Seconds 2; if ($process.HasExited) { Write-Error ('BlackMarket AI exited during startup with code ' + $process.ExitCode); exit 1 } } catch { Write-Error ('Unable to launch BlackMarket AI: ' + $_.Exception.Message); exit 1 }"
if errorlevel 1 goto desktop_start_failed
echo BlackMarket AI desktop startup requested. The launcher will now close.
exit /b 0

:invalid_custom_executable
echo ERROR: BLACKMARKET_DESKTOP_EXE does not exist:
echo   %BLACKMARKET_DESKTOP_EXE%
pause
exit /b 1

:desktop_executable_missing
echo ERROR: No BlackMarket AI desktop executable was found.
echo Launch the installed desktop shortcut, set BLACKMARKET_DESKTOP_EXE,
echo or install the desktop development dependencies before using this fallback.
pause
exit /b 1

:desktop_start_failed
echo ERROR: Desktop startup failed. Review the error above.
pause
exit /b 1

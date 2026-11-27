@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py --tui %*
) else if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" main.py --tui %*
) else (
    python main.py --tui %*
)

endlocal

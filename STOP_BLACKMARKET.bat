@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference = 'Stop'; try { $apps = @(Get-Process | Where-Object { $_.MainWindowTitle -eq 'BlackMarket AI' }); if ($apps.Count -eq 0) { Write-Output 'BlackMarket AI desktop is not running.'; exit 0 }; foreach ($app in $apps) { if (-not $app.CloseMainWindow()) { Write-Error ('Could not request a graceful close for process ' + $app.Id); exit 1 }; if (-not $app.WaitForExit(15000)) { Write-Error ('Desktop process ' + $app.Id + ' did not exit within 15 seconds. It was not force-terminated.'); exit 1 } }; Write-Output 'BlackMarket AI closed. Its desktop supervisor stops the backend it owns.' } catch { Write-Error ('Unable to close BlackMarket AI gracefully: ' + $_.Exception.Message); exit 1 }"
if errorlevel 1 (
    echo ERROR: BlackMarket AI did not close cleanly. The backend was not force-terminated.
    pause
    exit /b 1
)
exit /b 0

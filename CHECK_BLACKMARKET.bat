@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference = 'Stop'; $apps = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -eq 'BlackMarket AI' }); if ($apps.Count -gt 0) { Write-Output 'Desktop app: RUNNING' } else { Write-Output 'Desktop app: NOT RUNNING' }; try { $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/health' -TimeoutSec 3 } catch { Write-Output ('Backend API: UNAVAILABLE (' + $_.Exception.Message + ')'); exit 1 }; if ($null -eq $health -or $null -eq $health.PSObject.Properties['backend_ready']) { Write-Output 'Backend API: RESPONDING, but this is not a BlackMarket AI health response.'; exit 2 }; Write-Output ('Backend: ' + $(if ($health.backend_ready -eq $true) { 'READY' } else { 'NOT READY' })); Write-Output ('Database: ' + $(if ($health.database_connected -eq $true) { 'CONNECTED' } else { 'NOT CONNECTED' })); Write-Output ('WebSocket service: ' + $(if ($health.websocket_connected -eq $true) { 'READY' } else { 'NOT READY' })); Write-Output ('Market data: ' + $(if ($health.market_data_active -eq $true) { 'ACTIVE' } else { 'INACTIVE' })); if ($health.backend_ready -eq $true -and $health.database_connected -eq $true -and $health.websocket_connected -eq $true) { exit 0 }; exit 2"
set "CHECK_RESULT=%ERRORLEVEL%"
echo.
pause
exit /b %CHECK_RESULT%

@echo off
title Stop TradingGuard
echo Stopping TradingGuard HITL Service...
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*hitl/bot.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo TradingGuard stopped successfully.
timeout /t 2 >nul

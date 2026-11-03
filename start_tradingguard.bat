@echo off
title TradingGuard HITL Daemon
cd /d "g:\Code\TradingGuard"
echo Starting TradingGuard HITL Daemon...
"C:\Users\Javad\AppData\Local\Programs\Python\Python314\python.exe" -u hitl/bot.py
pause

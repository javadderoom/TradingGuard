@echo off
title Soli-Trader Chrome Profile Launcher
echo ============================================================
echo Launching Google Chrome for Soli-Trader Signal Extraction...
echo ============================================================
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%~dp0soli_chrome_profile" "https://soli-trader.com/signals"
echo Chrome launched on port 9222 with persistent profile.
echo Please log in to Soli-Trader in the opened browser.
exit

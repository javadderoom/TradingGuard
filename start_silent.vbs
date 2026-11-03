Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c ""g:\Code\TradingGuard\start_tradingguard.bat""", 0, False
Set WshShell = Nothing

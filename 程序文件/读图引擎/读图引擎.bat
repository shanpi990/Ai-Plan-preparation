@echo off
chcp 65001 >nul
"%~dp0运行库\python.exe" -B -X utf8 "%~dpn0.py" %*
exit /b %errorlevel%

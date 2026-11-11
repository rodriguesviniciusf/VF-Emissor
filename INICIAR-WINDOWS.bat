@echo off
setlocal
cd /d "%~dp0"
"portable\python.exe" "desktop_launcher.py"
if errorlevel 1 pause

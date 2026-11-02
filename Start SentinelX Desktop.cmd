@echo off
setlocal
cd /d "%~dp0"
title SentinelX Desktop

if not exist "runtime\.venv\Scripts\python.exe" goto setup
if not exist "runtime\deps-ready.txt" goto setup
goto launch

:setup
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.12 or newer is required.
  echo Install it from https://www.python.org/downloads/ and run this file again.
  pause
  exit /b 1
)
python bootstrap.py
if errorlevel 1 (
  echo.
  echo SentinelX Desktop setup did not finish. Review the message above.
  pause
  exit /b 1
)

:launch
start "" "%~dp0runtime\.venv\Scripts\pythonw.exe" "%~dp0SentinelX Desktop.pyw"
exit /b 0

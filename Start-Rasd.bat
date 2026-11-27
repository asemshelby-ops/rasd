@echo off
chcp 65001 >nul
title Rasd - starter
cd /d "%~dp0"

echo.
echo  ===== Rasd demo starter =====
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo  Python is not installed on this laptop.
  echo  1. Open https://www.python.org/downloads/ and install Python 3.12 or newer.
  echo  2. IMPORTANT: on the first install screen, tick "Add python.exe to PATH".
  echo  3. Then double-click this file again.
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo  First run: setting things up. This takes 2 to 5 minutes, only once.
  python -m venv .venv
  if errorlevel 1 goto fail
)

echo  Checking the required packages...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto fail

if not exist ".env" (
  echo RASD_PIN=2468> .env
  echo  Created the private settings file with PIN 2468.
)

echo.
echo  Starting Rasd. A second black window will open: keep it open while you use Rasd.
echo  To stop Rasd, close that second window.
echo.
start "Rasd server - keep this window open" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > server-log.txt 2>&1"
timeout /t 6 /nobreak >nul
start "" "http://localhost:8000/board"
timeout /t 1 /nobreak >nul
start "" "http://localhost:8000/operator"
echo  The server writes its messages to server-log.txt in this folder.
echo  Opened the board and the operator page in your browser.
echo  Operator PIN: 2468
echo.
pause
exit /b 0

:fail
echo.
echo  Something went wrong. Take a screenshot of this window and send it to Claude.
pause
exit /b 1

@echo off
title Signal Workshop Launcher
echo ========================================================
echo Starting Signal Workshop (Backend + Frontend)
echo ========================================================

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

echo [1/2] Launching Backend API Server (port 8000)...
start "Signal Workshop - Backend API" cmd /k "cd /d "%PROJECT_DIR%" && ".\.venv\Scripts\python.exe" -m uvicorn app:app --app-dir backend --host 127.0.0.1 --port 8000"

echo [2/2] Launching Frontend UI (port 5173)...
set "PATH=C:\Program Files\nodejs;%PATH%"
start "Signal Workshop - Frontend UI" cmd /k "cd /d "%PROJECT_DIR%" && npm --prefix frontend run dev"

echo.
echo Waiting 5 seconds for backend to initialize...
timeout /t 5 >nul

echo Opening http://127.0.0.1:5173 in browser...
start http://127.0.0.1:5173

echo.
echo ========================================================
echo Signal Workshop is running!
echo Keep both Backend and Frontend command windows open.
echo To stop everything, close them or run stop.bat.
echo ========================================================
pause

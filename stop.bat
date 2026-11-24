@echo off
title Stop Signal Workshop
echo Stopping Signal Workshop servers...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo Stopping backend process (PID %%a)...
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173" ^| findstr "LISTENING"') do (
    echo Stopping frontend process (PID %%a)...
    taskkill /F /PID %%a >nul 2>&1
)
echo Done! Servers stopped.
pause

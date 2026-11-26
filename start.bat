@echo off
title FlowStudio Pro Server
cd /d "%~dp0"

echo ============================================================
echo               Launching FlowStudio Pro Engine
echo ============================================================
echo.

:: Check if server is already running on port 8765
netstat -ano | findstr 127.0.0.1:8765 | findstr LISTENING >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] FlowStudio server is already running on http://127.0.0.1:8765!
    echo [INFO] Opening Web UI in your default browser...
    start http://127.0.0.1:8765
    timeout /t 2 /nobreak >nul
    exit /b 0
)

set PY_EXE=python
if exist "%~dp0.venv\Scripts\python.exe" (
    set PY_EXE="%~dp0.venv\Scripts\python.exe"
    echo [INFO] Using portable virtual environment: %PY_EXE%
) else (
    echo [INFO] Using system python interpreter...
)

:: Auto-launch browser after 2 seconds
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:8765"

echo [SERVER] Starting FlowStudio FastAPI backend on http://127.0.0.1:8765...
%PY_EXE% -m uvicorn server.app:app --host 127.0.0.1 --port 8765
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Server terminated unexpectedly.
    pause
)

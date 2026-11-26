@echo off
title Stop FlowStudio Server
cd /d "%~dp0"

echo [FlowStudio] Stopping FlowStudio server on port 8765...

:: 1. Attempt graceful shutdown via REST API
where curl >nul 2>&1
if %errorlevel% equ 0 (
    curl -s -X POST http://127.0.0.1:8765/api/system/shutdown >nul 2>&1
    timeout /t 1 /nobreak >nul
)

:: 2. Terminate any remaining process listening on port 8765
for /f "tokens=5" %%a in ('netstat -ano ^| findstr 127.0.0.1:8765 ^| findstr LISTENING') do (
    echo [FlowStudio] Terminating server process PID %%a...
    taskkill /PID %%a /F >nul 2>&1
)

echo [FlowStudio] Server stopped cleanly.
timeout /t 1 /nobreak >nul

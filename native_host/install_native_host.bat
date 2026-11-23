@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0..\.venv\Scripts\python.exe" (
    "%~dp0..\.venv\Scripts\python.exe" "%~dp0install_native_host.py"
) else (
    python "%~dp0install_native_host.py"
)

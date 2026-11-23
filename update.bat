@echo off
setlocal enabledelayedexpansion
title FlowStudio 1-Click Updater
cd /d "%~dp0"

echo ============================================================
echo               FlowStudio - 1-Click Updater
echo ============================================================
echo.

:: 1. Gracefully stop active background server
if not exist "%~dp0stop_server.bat" goto :check_git
echo [1/3] Stopping active FlowStudio server...
call "%~dp0stop_server.bat"

:check_git
:: 2. Find git and fetch / reset if .git exists
if not exist "%~dp0.git" goto :run_setup

set "PATH=%LOCALAPPDATA%\Programs\Git\cmd;%LOCALAPPDATA%\Programs\Git\ucrt64\bin;C:\Program Files\Git\cmd;%PATH%"

echo [2/3] Fetching latest updates from GitHub (force-push safe)...
git fetch origin main
if errorlevel 1 goto :git_fetch_warn
git reset --hard origin/main
goto :run_setup

:git_fetch_warn
echo [WARN] git fetch encountered an issue. Proceeding with local setup...

:run_setup
:: 3. Re-run setup_portable.bat (fast package check & native host refresh)
echo [3/3] Refreshing environment, packages, and native host...
call "%~dp0setup_portable.bat" --nopause
if errorlevel 1 goto :update_failed

echo.
echo ============================================================
echo   FlowStudio is now up to date!
echo   Open chrome://extensions and click Reload on FlowStudio.
echo ============================================================
echo.
pause
exit /b 0

:update_failed
echo.
echo [ERROR] Update failed during setup.
pause
exit /b 1

@echo off
setlocal enabledelayedexpansion
title FlowStudio 1-Click Updater
cd /d "%~dp0"

echo ============================================================
echo               FlowStudio - 1-Click Updater
echo ============================================================
echo.

:: 1. Gracefully stop active background server and unlock .pyd files
if exist "%~dp0stop_server.bat" (
    echo [1/3] Stopping active FlowStudio server...
    call "%~dp0stop_server.bat"
)
powershell -NoProfile -Command "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { ($_.Name -match '^python.*\.exe$') -and ($_.CommandLine -match 'tray_app|server\.app|uvicorn') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
timeout /t 2 /nobreak >nul

:: 2. Update via git (force-push / orphan safe) or pure-PowerShell ZIP file merge
set "UPDATED=0"
set "PATH=%LOCALAPPDATA%\Programs\Git\cmd;%LOCALAPPDATA%\Programs\Git\ucrt64\bin;C:\Program Files\Git\cmd;%PATH%"
set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"

if exist "%ROOT_DIR%\.git" (
    where git >nul 2>&1
    if not errorlevel 1 (
        echo [2/3] Fetching latest updates from GitHub ^(force-push safe^)...
        git -C "%ROOT_DIR%" fetch --depth 1 origin main
        if not errorlevel 1 (
            git -C "%ROOT_DIR%" reset --hard origin/main
            if not errorlevel 1 set "UPDATED=1"
        )
    )
)

if "%UPDATED%"=="0" (
    echo [2/3] Updating via GitHub ZIP download fallback...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%\scripts\self_update.ps1" -InstallDir "%ROOT_DIR%" -SkipRelaunch
    if not errorlevel 1 set "UPDATED=1"
)

:: 3. Re-run setup_portable.bat (fast package check, native host, and desktop shortcut refresh)
echo [3/3] Refreshing environment, packages, native host, and shortcut...
call "%ROOT_DIR%\setup_portable.bat" --nopause
if errorlevel 1 goto :update_failed

:: 4. Dynamic version banner from version.json
for /f "tokens=*" %%v in ('powershell -NoProfile -Command "(Get-Content -LiteralPath '%ROOT_DIR%\version.json' -Raw | ConvertFrom-Json).version"') do set "VER=%%v"
if "%VER%"=="" set "VER=4.0.4"

echo.
echo ============================================================
echo   FlowStudio v%VER% is now up to date!
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

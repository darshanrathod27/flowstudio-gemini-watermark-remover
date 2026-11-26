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

:: 2. Update via git (force-push / orphan safe) or pure-PowerShell ZIP fallback
set "UPDATED=0"
set "PATH=%LOCALAPPDATA%\Programs\Git\cmd;%LOCALAPPDATA%\Programs\Git\ucrt64\bin;C:\Program Files\Git\cmd;%PATH%"

if exist "%~dp0.git" (
    where git >nul 2>&1
    if not errorlevel 1 (
        echo [2/3] Fetching latest updates from GitHub (force-push safe)...
        git fetch origin main
        if not errorlevel 1 (
            git reset --hard origin/main
            if not errorlevel 1 set "UPDATED=1"
        )
    )
)

if "%UPDATED%"=="0" (
    echo [2/3] Updating via GitHub ZIP download fallback...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $zipUrl='https://github.com/darshanrathod27/flowstudio-gemini-watermark-remover/archive/refs/heads/main.zip?t=' + [System.Guid]::NewGuid().ToString('N'); $zipFile=\"$env:TEMP\fs_update_%RANDOM%.zip\"; $extDir=\"$env:TEMP\fs_update_ext_%RANDOM%\"; try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri $zipUrl -OutFile $zipFile -UseBasicParsing; Expand-Archive -Path $zipFile -DestinationPath $extDir -Force; robocopy \"$extDir\flowstudio-gemini-watermark-remover-main\" '%~dp0' /E /IS /IT /XD .venv bin models workspace .git /NFL /NDL /NJH /NJS; } finally { Remove-Item -Force $zipFile -ErrorAction SilentlyContinue; Remove-Item -Recurse -Force $extDir -ErrorAction SilentlyContinue; }"
)

:: 3. Re-run setup_portable.bat (fast package check, native host, and desktop shortcut refresh)
echo [3/3] Refreshing environment, packages, native host, and shortcut...
call "%~dp0setup_portable.bat" --nopause
if errorlevel 1 goto :update_failed

:: 4. Dynamic version banner from version.json
for /f "tokens=*" %%v in ('powershell -NoProfile -Command "(Get-Content '%~dp0version.json' -Raw | ConvertFrom-Json).version"') do set "VER=%%v"
if "%VER%"=="" set "VER=4.0.0"

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

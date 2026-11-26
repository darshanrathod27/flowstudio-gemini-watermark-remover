@echo off
setlocal
title FlowStudio Chrome Extension Setup Helper
cd /d "%~dp0"

echo ============================================================
echo         FlowStudio - Chrome Extension Setup Helper
echo ============================================================
echo.

:: 1. Copy extension path to Windows Clipboard
set "EXT_DIR=%~dp0extension"
powershell -NoProfile -Command "Set-Clipboard -Value '%EXT_DIR%'" >nul 2>&1

echo [OK] Extension folder path copied to your clipboard:
echo      %EXT_DIR%
echo.

:: 2. Launch Chrome to extensions page
start chrome.exe "chrome://extensions" >nul 2>&1

echo NEXT STEPS IN CHROME (Takes 15 seconds):
echo   1. Turn ON "Developer mode" (toggle in the top-right corner).
echo   2. Click "Load unpacked" button (top-left).
echo   3. In the folder path address bar, press Ctrl+V and hit Enter!
echo   4. Pin FlowStudio to your Chrome toolbar.
echo.
echo That's it! FlowStudio's Native Auto-Start is already linked.
echo ============================================================
echo.
pause

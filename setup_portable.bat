@echo off
setlocal EnableDelayedExpansion
title FlowStudio Portable Kit Setup
cd /d "%~dp0"

echo ============================================================
echo           FlowStudio Pro - 1-Click Environment Setup
echo ============================================================
echo.

:: 1. Block System32 / Windows Install Path
echo %~dp0 | findstr /i "\\Windows\\System32" >nul 2>&1
if not errorlevel 1 goto :block_system32
goto :check_venv

:block_system32
echo ============================================================
echo [ERROR] CRITICAL: System32 Installation Blocked!
echo ============================================================
echo FlowStudio detected that it is running inside System32:
echo   %~dp0
echo.
echo Please do NOT clone or install FlowStudio inside C:\Windows\System32.
echo Please install to your user directory instead:
echo   %%USERPROFILE%%\FlowStudio
echo or run the recommended one-click installer:
echo   powershell -c "irm https://raw.githubusercontent.com/darshanrathod27/flowstudio-gemini-watermark-remover/main/install.ps1 | iex"
echo.
if "%FLOWSTUDIO_AUTO%"=="1" exit /b 1
pause
exit /b 1

:check_venv
set "VENV_DIR=%~dp0.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

if not exist "%VENV_PY%" goto :find_base_python

:: Existing .venv found - check pip
"%VENV_PY%" -m pip --version >nul 2>&1
if not errorlevel 1 goto :verify_venv_version

echo [WARN] pip is missing inside existing .venv. Attempting ensurepip...
"%VENV_PY%" -m ensurepip --upgrade >nul 2>&1
"%VENV_PY%" -m pip --version >nul 2>&1
if not errorlevel 1 goto :verify_venv_version

echo [WARN] ensurepip failed. Removing broken .venv and recreating...
rmdir /s /q "%VENV_DIR%"
goto :find_base_python

:verify_venv_version
"%VENV_PY%" -c "import sys; assert sys.version_info[:2]==(3,12)" >nul 2>&1
if errorlevel 1 (
    echo [WARN] Existing .venv is not Python 3.12! Removing and recreating...
    rmdir /s /q "%VENV_DIR%"
    goto :find_base_python
)

:: Fast-path check: if torch, fastapi, spandrel, and pystray are already healthy, skip 3GB PyTorch redownload!
"%VENV_PY%" -c "import torch, fastapi, spandrel, pystray" >nul 2>&1
if not errorlevel 1 goto :fast_update

goto :check_gpu

:fast_update
echo.
echo [INFO] Existing healthy Python 3.12 + PyTorch environment detected.
echo [INFO] Performing fast ~10s incremental update...
if exist "%~dp0requirements.txt" (
    "%VENV_PY%" -m pip install --quiet -r "%~dp0requirements.txt"
)
goto :verify_ffmpeg

:find_base_python
echo [INFO] Locating or creating Python 3.12 virtual environment...

py -3.12 --version >nul 2>&1
if not errorlevel 1 goto :create_with_py

where uv >nul 2>&1
if not errorlevel 1 goto :create_with_uv

python -c "import sys; sys.exit(0 if sys.version_info[:2]==(3,12) else 1)" >nul 2>&1
if not errorlevel 1 goto :create_with_python

if exist "%LOCALAPPDATA%\uv\python\cpython-3.12-windows-x86_64-none\python.exe" goto :create_with_uv_cpython

where winget >nul 2>&1
if not errorlevel 1 goto :install_via_winget

goto :python_not_found

:create_with_py
echo [INFO] Creating .venv using py -3.12...
py -3.12 -m venv "%VENV_DIR%"
goto :verify_created_venv

:create_with_uv
echo [INFO] Creating .venv using uv venv --python 3.12 --seed...
uv venv "%VENV_DIR%" --python 3.12 --seed
goto :verify_created_venv

:create_with_python
echo [INFO] Creating .venv using system python 3.12...
python -m venv "%VENV_DIR%"
goto :verify_created_venv

:create_with_uv_cpython
echo [INFO] Creating .venv using uv-managed CPython 3.12...
"%LOCALAPPDATA%\uv\python\cpython-3.12-windows-x86_64-none\python.exe" -m venv "%VENV_DIR%"
goto :verify_created_venv

:install_via_winget
echo [INFO] Installing Python 3.12 via winget...
winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
py -3.12 --version >nul 2>&1
if not errorlevel 1 goto :create_with_py
goto :python_not_found

:verify_created_venv
if not exist "%VENV_PY%" goto :setup_failed

:: Verify pip inside newly created .venv
"%VENV_PY%" -m pip --version >nul 2>&1
if not errorlevel 1 goto :verify_created_version

echo [INFO] Restoring pip inside .venv via ensurepip...
"%VENV_PY%" -m ensurepip --upgrade >nul 2>&1
"%VENV_PY%" -m pip --version >nul 2>&1
if not errorlevel 1 goto :verify_created_version

echo [ERROR] CRITICAL: pip is missing inside .venv and could not be installed!
goto :setup_failed

:verify_created_version
"%VENV_PY%" -c "import sys; assert sys.version_info[:2]==(3,12)" >nul 2>&1
if errorlevel 1 goto :wrong_py_version
goto :check_gpu

:wrong_py_version
echo [ERROR] CRITICAL: .venv Python is not strictly Python 3.12!
goto :setup_failed

:python_not_found
echo [ERROR] Python 3.12 (64-bit) could not be found or installed automatically.
echo FlowStudio native acceleration binaries require Python 3.12.
echo Please install Python 3.12 from https://www.python.org/downloads/ and rerun setup.
if "%FLOWSTUDIO_AUTO%"=="1" exit /b 1
pause
exit /b 1

:check_gpu
echo.
echo [INFO] Probing graphics hardware...
nvidia-smi >nul 2>&1
if errorlevel 1 goto :install_cpu

:install_gpu
echo [GPU] NVIDIA GPU detected - installing CUDA 12.8 PyTorch...
"%VENV_PY%" -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
if errorlevel 1 goto :setup_failed
goto :install_deps

:install_cpu
echo [CPU] No NVIDIA GPU detected - installing universal CPU PyTorch...
"%VENV_PY%" -m pip install torch torchvision
if errorlevel 1 goto :setup_failed
goto :install_deps

:install_deps
echo.
echo [INFO] Installing FlowStudio requirements...
if not exist "%~dp0requirements.txt" goto :install_spandrel
"%VENV_PY%" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 goto :setup_failed

:install_spandrel
"%VENV_PY%" -m pip install spandrel
if errorlevel 1 goto :setup_failed

:verify_ffmpeg
echo.
echo [INFO] Verifying FFmpeg...
if not exist "%~dp0scripts\download_ffmpeg.py" goto :link_native_host
"%VENV_PY%" "%~dp0scripts\download_ffmpeg.py"
if errorlevel 1 goto :setup_failed

:link_native_host
echo.
echo [INFO] Linking Chrome Native Messaging Auto-Start Bridge...
if not exist "%~dp0native_host\install_native_host.py" goto :create_shortcut
"%VENV_PY%" "%~dp0native_host\install_native_host.py"
if errorlevel 1 goto :setup_failed

:create_shortcut
echo.
echo [INFO] Refreshing Desktop Shortcut Icon...
if exist "%~dp0scripts\create_shortcut.py" (
    "%VENV_PY%" "%~dp0scripts\create_shortcut.py"
)

:self_test
echo.
echo [INFO] Running End-of-Setup Engine Self-Test...
"%VENV_PY%" -c "import fastapi, uvicorn, cv2, torch, spandrel, pystray; from engine.watermark_remover import WatermarkRemover; wr = WatermarkRemover(); print('[VERIFY] Engine OK | Masks:', len(wr.masks), '| CUDA:', torch.cuda.is_available(), '| GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
if errorlevel 1 goto :setup_failed

echo.
echo ============================================================
echo   [SUCCESS] FlowStudio Setup Complete!
echo   Desktop Shortcut: Created on Desktop (runs silently in System Tray)
echo   Run 'setup_chrome_extension.bat' to link extension in Chrome.
echo ============================================================
echo.
if "%FLOWSTUDIO_AUTO%"=="1" goto :exit_ok
if "%1"=="--nopause" goto :exit_ok
pause
:exit_ok
exit /b 0

:setup_failed
echo.
echo ============================================================
echo   [ERROR] Setup encountered a critical failure.
echo ============================================================
echo.
if "%FLOWSTUDIO_AUTO%"=="1" goto :exit_err
if "%1"=="--nopause" goto :exit_err
pause
:exit_err
exit /b 1

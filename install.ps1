# FlowStudio 1-Command Automated PowerShell Installer (v3.4.0)
$ErrorActionPreference = "Stop"

$repoSlug = "darshanrathod27/flowstudio-gemini-watermark-remover"
$remoteUrl = "https://github.com/$repoSlug.git"
$zipUrl = "https://github.com/$repoSlug/archive/refs/heads/main.zip"
$target = "$env:USERPROFILE\FlowStudio"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "          FlowStudio Pro - Fast Automated Installer        " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Ensure git can be located
$gitCmd = "git"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    if (Test-Path "$env:LOCALAPPDATA\Programs\Git\cmd\git.exe") {
        $gitCmd = "$env:LOCALAPPDATA\Programs\Git\cmd\git.exe"
        $env:Path = "$env:LOCALAPPDATA\Programs\Git\cmd;" + $env:Path
    } elseif (Test-Path "C:\Program Files\Git\cmd\git.exe") {
        $gitCmd = "C:\Program Files\Git\cmd\git.exe"
        $env:Path = "C:\Program Files\Git\cmd;" + $env:Path
    }
}
$hasGit = (Get-Command $gitCmd -ErrorAction SilentlyContinue) -ne $null

# 1. Fetch Source Code (Force-Push Safe)
if (Test-Path "$target\.git") {
    Write-Host "[1/3] Existing installation detected. Fetching latest updates..." -ForegroundColor Green
    if ($hasGit) {
        & $gitCmd -C $target fetch origin main
        & $gitCmd -C $target reset --hard origin/main
    } else {
        Write-Host "Git not found in session, proceeding with local files..." -ForegroundColor Yellow
    }
} elseif ($hasGit) {
    Write-Host "[1/3] Git detected. Cloning repository to $target..." -ForegroundColor Green
    & $gitCmd clone $remoteUrl $target
} else {
    Write-Host "[1/3] Git not found. Downloading repository archive..." -ForegroundColor Green
    $zipPath = "$env:TEMP\flowstudio_main.zip"
    Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing
    
    if (Test-Path $target) { Remove-Item -Recurse -Force $target }
    Expand-Archive -Path $zipPath -DestinationPath "$env:TEMP\fs_extract" -Force
    Move-Item -Path "$env:TEMP\fs_extract\flowstudio-gemini-watermark-remover-main" -Destination $target
    Remove-Item -Force $zipPath
    Remove-Item -Recurse -Force "$env:TEMP\fs_extract"
}

# 2. Check broken .venv if missing pip
if (Test-Path "$target\.venv") {
    if (-not (Test-Path "$target\.venv\Scripts\pip.exe")) {
        Write-Host "[!] Broken .venv detected (pip missing). Removing to guarantee clean recreation..." -ForegroundColor Yellow
        Remove-Item -Recurse -Force "$target\.venv"
    }
}

# 3. Run Portable Setup (100% Inline Live Execution)
Write-Host "[2/3] Configuring environment, AI models & Native Bridge..." -ForegroundColor Green
$env:FLOWSTUDIO_AUTO = "1"
Push-Location $target
try {
    & cmd.exe /c "setup_portable.bat"
} finally {
    Pop-Location
}

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Red
    Write-Host " [ERROR] Setup encountered an issue (Exit Code: $LASTEXITCODE)" -ForegroundColor Red
    Write-Host " Note: If Windows 11 Smart App Control blocked python or binaries," -ForegroundColor Yellow
    Write-Host " please see the Smart App Control section in README.md." -ForegroundColor Yellow
    Write-Host "============================================================" -ForegroundColor Red
    exit 1
}

# 4. Copy Extension Path Silently & Print Summary
try { Set-Clipboard "$target\extension" } catch {}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  FlowStudio v3.3.0 Installed & Ready!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "Extension Folder Path:" -ForegroundColor Cyan
Write-Host "  $target\extension" -ForegroundColor Yellow
Write-Host ""
Write-Host "Chrome Setup (15 seconds):" -ForegroundColor Cyan
Write-Host "  1. Open chrome://extensions in Chrome" -ForegroundColor White
Write-Host "  2. Turn ON `"Developer mode`" (top-right)" -ForegroundColor White
Write-Host "  3. Click `"Load unpacked`" -> select/paste the path above" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor Green

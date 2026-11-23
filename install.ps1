# FlowStudio 1-Command Automated PowerShell Installer (v3.6.1)
$ErrorActionPreference = "Stop"

$repoSlug = "darshanrathod27/flowstudio-gemini-watermark-remover"
$remoteUrl = "https://github.com/$repoSlug.git"
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

# Helper: Download and extract GitHub ZIP archive preserving preserved dirs
function Sync-FromZipArchive {
    param ([string]$destPath)
    Write-Host "Downloading latest repository archive from GitHub..." -ForegroundColor Yellow
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $zipUrl = "https://github.com/$repoSlug/archive/refs/heads/main.zip?t=" + [System.Guid]::NewGuid().ToString("N")
    $zipPath = "$env:TEMP\flowstudio_install_$([System.Guid]::NewGuid().ToString('N')).zip"
    $extDir = "$env:TEMP\fs_install_ext_$([System.Guid]::NewGuid().ToString('N'))"

    try {
        Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing
        Expand-Archive -Path $zipPath -DestinationPath $extDir -Force
        $extractedRoot = "$extDir\flowstudio-gemini-watermark-remover-main"

        if (-not (Test-Path $destPath)) {
            New-Item -ItemType Directory -Path $destPath -Force | Out-Null
        }

        # Sync files preserving .venv, bin, models, workspace, .git
        robocopy $extractedRoot $destPath /E /IS /IT /XD .venv bin models workspace .git /NFL /NDL /NJH /NJS | Out-Null
        if ($LASTEXITCODE -ge 8) {
            # Fallback pure PowerShell copy if robocopy returns error
            $preserveDirs = @(".venv", "bin", "models", "workspace", ".git")
            Get-ChildItem -Path $extractedRoot -Force | ForEach-Object {
                if ($preserveDirs -notcontains $_.Name) {
                    $itemDest = Join-Path $destPath $_.Name
                    if ($_.PSIsContainer) {
                        Copy-Item -Path $_.FullName -Destination $itemDest -Recurse -Force
                    } else {
                        Copy-Item -Path $_.FullName -Destination $itemDest -Force
                    }
                }
            }
        }
    } finally {
        Remove-Item -Force $zipPath -ErrorAction SilentlyContinue
        Remove-Item -Recurse -Force $extDir -ErrorAction SilentlyContinue
    }
}

# 1. Stop active server and unlock .pyd files if existing installation
if (Test-Path $target) {
    Write-Host "[1/3] Existing installation detected. Checking and unlocking engine files..." -ForegroundColor Green
    try {
        $null = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/system/shutdown" -Method Post -Body "{}" -ContentType "application/json" -TimeoutSec 1 -ErrorAction SilentlyContinue
    } catch {}
    Start-Sleep -Milliseconds 500

    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        ($_.Name -match '^python.*\.exe$') -and ($_.CommandLine -match 'tray_app|server\.app|uvicorn')
    } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 1000

    # Fetch updates: try git fetch + reset first, fallback to zip
    $gitSuccess = $false
    if ((Test-Path "$target\.git") -and $hasGit) {
        Write-Host "Fetching updates via git (force-push safe)..." -ForegroundColor Green
        & $gitCmd -C $target fetch origin main
        if ($LASTEXITCODE -eq 0) {
            & $gitCmd -C $target reset --hard origin/main
            if ($LASTEXITCODE -eq 0) {
                $gitSuccess = $true
            }
        }
    }

    if (-not $gitSuccess) {
        Sync-FromZipArchive -destPath $target
    }
} else {
    Write-Host "[1/3] Fresh installation. Acquiring FlowStudio..." -ForegroundColor Green
    $cloneSuccess = $false
    if ($hasGit) {
        Write-Host "Cloning repository via git to $target..." -ForegroundColor Green
        & $gitCmd clone $remoteUrl $target
        if ($LASTEXITCODE -eq 0) {
            $cloneSuccess = $true
        }
    }
    if (-not $cloneSuccess) {
        Sync-FromZipArchive -destPath $target
    }
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
    & cmd.exe /c "setup_portable.bat --nopause"
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

# 4. Copy Extension Path Silently & Print Dynamic Summary
try { Set-Clipboard "$target\extension" } catch {}

$actualVersion = "3.6.1"
if (Test-Path "$target\version.json") {
    try {
        $actualVersion = (Get-Content "$target\version.json" -Raw | ConvertFrom-Json).version
    } catch {}
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  FlowStudio v$actualVersion Installed & Ready!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "Extension Folder Path:" -ForegroundColor Cyan
Write-Host "  $target\extension" -ForegroundColor Yellow
Write-Host ""
Write-Host "Chrome Setup (15 seconds):" -ForegroundColor Cyan
Write-Host "  1. Open chrome://extensions in Chrome" -ForegroundColor White
Write-Host "  2. Turn ON `"Developer mode`" (top-right)" -ForegroundColor White
Write-Host "  3. Click `"Load unpacked`" -> select/paste the path above" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor Green

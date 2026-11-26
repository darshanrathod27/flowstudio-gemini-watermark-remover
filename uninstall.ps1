# FlowStudio Pro - Clean 1-Click Uninstaller (v3.9.0)
param(
    [string]$InstallDir = "$env:USERPROFILE\FlowStudio",
    [object]$CleanCaches = $true,
    [switch]$Silent
)

$ErrorActionPreference = "Stop"

$doCleanCaches = $true
if ($CleanCaches -is [bool]) {
    $doCleanCaches = $CleanCaches
} elseif ($CleanCaches -is [int] -or $CleanCaches -is [long]) {
    $doCleanCaches = ([int]$CleanCaches -ne 0)
} else {
    $rawClean = [string]$CleanCaches
    if ($rawClean.Trim().TrimStart(':') -imatch '^(0|false|\$false|no|off)$') {
        $doCleanCaches = $false
    }
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "            FlowStudio Pro - Clean Uninstaller              " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

if ([string]::IsNullOrWhiteSpace($InstallDir)) {
    Write-Host "[ABORT] InstallDir cannot be empty." -ForegroundColor Red
    exit 2
}

$targetDir = $InstallDir.Trim().TrimEnd('\', '/')
try {
    $targetDir = [System.IO.Path]::GetFullPath($targetDir).TrimEnd('\', '/')
} catch {}

# ------------------------------------------------------------------
# CRITICAL DEVELOPER SAFETY GUARD
# ------------------------------------------------------------------
$protectedRoots = @(
    $env:USERPROFILE.TrimEnd('\', '/'),
    $env:SystemRoot.TrimEnd('\', '/'),
    $env:ProgramFiles.TrimEnd('\', '/'),
    $env:TEMP.TrimEnd('\', '/')
)

if ($targetDir -match '^[A-Za-z]:$' -or ($protectedRoots -contains $targetDir)) {
    Write-Host "[SAFETY REFUSAL] Protected system/root path cannot be uninstalled: $targetDir" -ForegroundColor Red
    exit 2
}

if ($targetDir -imatch 'PRIVATE_SOURCE') {
    Write-Host "[SAFETY REFUSAL] Developer private source directory detected ($targetDir). Aborting!" -ForegroundColor Red
    exit 2
}

if (-not (Test-Path -LiteralPath $targetDir -PathType Container)) {
    Write-Host "[ERROR] FlowStudio install directory not found: $targetDir" -ForegroundColor Yellow
    exit 1
}

if ((Test-Path -LiteralPath (Join-Path $targetDir "cloud_backend")) -or (Test-Path -LiteralPath (Join-Path $targetDir "assets\masks"))) {
    Write-Host "[SAFETY REFUSAL] Private repository artifacts (cloud_backend / assets\masks) detected in $targetDir. Aborting!" -ForegroundColor Red
    exit 2
}

$hasTray = Test-Path -LiteralPath (Join-Path $targetDir "tray_app.py")
$hasVenv = Test-Path -LiteralPath (Join-Path $targetDir ".venv")
if (-not ($hasTray -and $hasVenv)) {
    Write-Host "[SAFETY REFUSAL] '$targetDir' is not a valid FlowStudio runtime install (requires tray_app.py + .venv). Aborting!" -ForegroundColor Red
    exit 2
}

if (-not $Silent) {
    Write-Host "Target Directory : $targetDir" -ForegroundColor Yellow
    Write-Host "Will Remove      : App, Server, .venv (PyTorch/CUDA), Models, FFmpeg, Shortcut & Native Bridge" -ForegroundColor White
    if ($doCleanCaches) {
        Write-Host "Package Caches   : pip & uv caches in %LOCALAPPDATA% will also be cleared" -ForegroundColor White
    }
    Write-Host ""
    $answer = Read-Host "Type YES to permanently uninstall FlowStudio"
    if ($answer -notin @("YES", "yes", "Y", "y")) {
        Write-Host "Uninstall cancelled." -ForegroundColor Cyan
        exit 0
    }
}

$removedItems = New-Object System.Collections.Generic.List[string]

# 1. Gracefully shut down running API server, then terminate remaining FlowStudio processes
Write-Host "[1/6] Stopping FlowStudio server and tray processes..." -ForegroundColor Green
try {
    $null = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/system/shutdown" -Method Post -Body "{}" -ContentType "application/json" -TimeoutSec 2 -ErrorAction SilentlyContinue
} catch {}

try {
    $escapedDir = [Regex]::Escape($targetDir)
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        ($_.Name -match '^python.*\.exe$') -and
        ($_.CommandLine -notmatch 'PRIVATE_SOURCE') -and
        (
            ($_.CommandLine -match $escapedDir) -or
            (($targetDir -ieq "$env:USERPROFILE\FlowStudio") -and ($_.CommandLine -match 'tray_app\.py|server\.app:app|uvicorn'))
        )
    } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
} catch {}

# 2. Wait 1.5s for Windows file/DLL handles to release
Write-Host "[2/6] Waiting for file handles to release..." -ForegroundColor Green
Start-Sleep -Milliseconds 1500

# 3. Remove Chrome Native Messaging Host registry key
Write-Host "[3/6] Removing Chrome Native Messaging Bridge registry key..." -ForegroundColor Green
$regPath = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.flowstudio.bridge"
if (Test-Path $regPath) {
    try {
        $regVal = (Get-ItemProperty -Path $regPath -ErrorAction SilentlyContinue).'(default)'
        $isDefaultInstall = $targetDir -ieq "$env:USERPROFILE\FlowStudio"
        $pointsInsideTarget = $regVal -and ($regVal -like "$targetDir*")
        $regTargetMissing = $regVal -and (-not (Test-Path -LiteralPath $regVal))
        if ($isDefaultInstall -or $pointsInsideTarget -or $regTargetMissing -or (-not $regVal)) {
            Remove-Item -Path $regPath -Force -ErrorAction SilentlyContinue
            $removedItems.Add("Chrome Native Messaging Registry ($regPath)")
        }
    } catch {}
}

# 4. Remove Desktop shortcut from OneDrive-safe Desktop and %USERPROFILE%\Desktop
Write-Host "[4/6] Removing Desktop shortcut..." -ForegroundColor Green
$desktopPaths = @(
    [Environment]::GetFolderPath('Desktop'),
    (Join-Path $env:USERPROFILE "Desktop")
) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique

$wsh = $null
try { $wsh = New-Object -ComObject WScript.Shell } catch {}

foreach ($desk in $desktopPaths) {
    $lnkPath = Join-Path $desk "FlowStudio.lnk"
    if (Test-Path -LiteralPath $lnkPath) {
        $shouldDeleteLnk = $targetDir -ieq "$env:USERPROFILE\FlowStudio"
        if (-not $shouldDeleteLnk -and $wsh) {
            try {
                $sc = $wsh.CreateShortcut($lnkPath)
                if (
                    ($sc.WorkingDirectory -like "$targetDir*") -or
                    ($sc.Arguments -like "*$targetDir*") -or
                    ($sc.TargetPath -like "$targetDir*")
                ) {
                    $shouldDeleteLnk = $true
                }
            } catch {}
        }
        if ($shouldDeleteLnk) {
            Remove-Item -LiteralPath $lnkPath -Force -ErrorAction SilentlyContinue
            if (-not (Test-Path -LiteralPath $lnkPath)) {
                $removedItems.Add("Desktop Shortcut ($lnkPath)")
            }
        }
    }
}

# 5. Delete entire FlowStudio installation folder (.venv, PyTorch, models, bin, assets, extension, workspace)
Write-Host "[5/6] Removing FlowStudio directory & Python environment ($targetDir)..." -ForegroundColor Green
try {
    $curLoc = (Get-Location).Path.TrimEnd('\', '/')
    if ($curLoc -like "$targetDir*") {
        Set-Location $env:TEMP
    }
} catch {}

$deletedDir = $false
for ($attempt = 1; $attempt -le 4; $attempt++) {
    try {
        if (Test-Path -LiteralPath $targetDir) {
            Remove-Item -LiteralPath $targetDir -Recurse -Force -ErrorAction Stop
        }
        if (-not (Test-Path -LiteralPath $targetDir)) {
            $deletedDir = $true
            break
        }
    } catch {
        Start-Sleep -Milliseconds 600
    }
}

if (-not $deletedDir -and (Test-Path -LiteralPath $targetDir)) {
    # Fallback via cmd rmdir /s /q for stubborn long paths / read-only .git objects
    & cmd.exe /c "rmdir /s /q `"$targetDir`"" 2>$null | Out-Null
    $deletedDir = -not (Test-Path -LiteralPath $targetDir)
}

if ($deletedDir) {
    $removedItems.Add("FlowStudio App, .venv (PyTorch/CUDA), Models, FFmpeg & Workspace ($targetDir)")
} else {
    Write-Host "[WARN] Some files in $targetDir could not be removed automatically." -ForegroundColor Yellow
}

# 6. Optional pip & uv cache cleanup
if ($doCleanCaches) {
    Write-Host "[6/6] Clearing pip & uv package caches..." -ForegroundColor Green
    $cacheDirs = @(
        (Join-Path $env:LOCALAPPDATA "pip\cache"),
        (Join-Path $env:LOCALAPPDATA "uv\cache")
    )
    foreach ($cd in $cacheDirs) {
        if (Test-Path -LiteralPath $cd) {
            try {
                Remove-Item -LiteralPath $cd -Recurse -Force -ErrorAction SilentlyContinue
                if (-not (Test-Path -LiteralPath $cd)) {
                    $removedItems.Add("Package Cache ($cd)")
                }
            } catch {}
        }
    }
} else {
    Write-Host "[6/6] Skipping pip & uv cache cleanup (-CleanCaches:`$false)." -ForegroundColor DarkGray
}

# 7. Summary
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  FlowStudio Uninstall Complete!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
if ($removedItems.Count -gt 0) {
    Write-Host "Removed Components:" -ForegroundColor Cyan
    foreach ($ri in $removedItems) {
        Write-Host "  - $ri" -ForegroundColor White
    }
}
Write-Host ""
Write-Host "Reminder: Open chrome://extensions and click 'Remove' on FlowStudio Local Bridge." -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Green

# FlowStudio 1-Command Automated PowerShell Installer (v4.0.2)
param(
    [string]$InstallDir = "",
    [switch]$SkipLaunch
)

$ErrorActionPreference = "Stop"

$repoSlug = "darshanrathod27/flowstudio-gemini-watermark-remover"
$remoteUrl = "https://github.com/$repoSlug.git"
$rawTarget = if (-not [string]::IsNullOrWhiteSpace($InstallDir)) {
    $InstallDir
} elseif (-not [string]::IsNullOrWhiteSpace($env:FLOWSTUDIO_DIR)) {
    $env:FLOWSTUDIO_DIR
} else {
    "$env:USERPROFILE\FlowStudio"
}
$target = [System.IO.Path]::GetFullPath($rawTarget).TrimEnd('\', '/')

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

function Merge-DirectoryTree {
    param(
        [string]$SrcRoot,
        [string]$DstRoot,
        [string[]]$PreserveTop
    )
    $srcClean = [System.IO.Path]::GetFullPath($SrcRoot).TrimEnd('\', '/')
    $dstClean = [System.IO.Path]::GetFullPath($DstRoot).TrimEnd('\', '/')
    $files = Get-ChildItem -LiteralPath $srcClean -Recurse -File -Force
    foreach ($f in $files) {
        $rel = $f.FullName.Substring($srcClean.Length).TrimStart('\', '/')
        if ([string]::IsNullOrWhiteSpace($rel)) { continue }
        $topSeg = ($rel -split '[\\/]', 2)[0]
        if ($PreserveTop -contains $topSeg) { continue }

        $dstFile = Join-Path $dstClean $rel
        $dstParent = Split-Path -Path $dstFile -Parent
        if (-not (Test-Path -LiteralPath $dstParent -PathType Container)) {
            [System.IO.Directory]::CreateDirectory($dstParent) | Out-Null
        }
        for ($attempt = 0; $attempt -lt 8; $attempt++) {
            try {
                if (Test-Path -LiteralPath $dstFile -PathType Leaf) {
                    $attr = [System.IO.File]::GetAttributes($dstFile)
                    if (($attr -band [System.IO.FileAttributes]::ReadOnly) -ne 0) {
                        [System.IO.File]::SetAttributes($dstFile, ($attr -band (-bnot [System.IO.FileAttributes]::ReadOnly)))
                    }
                }
                [System.IO.File]::Copy($f.FullName, $dstFile, $true)
                break
            } catch {
                if ($attempt -eq 7) { throw }
                Start-Sleep -Milliseconds 350
            }
        }
    }
}

# Helper: Download and extract GitHub ZIP archive cleanly file-by-file (zero WinError 183)
function Sync-FromZipArchive {
    param ([string]$destPath)
    $destClean = [System.IO.Path]::GetFullPath($destPath).TrimEnd('\', '/')
    Write-Host "Downloading latest repository archive from GitHub..." -ForegroundColor Yellow
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $zipUrl = "https://github.com/$repoSlug/archive/refs/heads/main.zip?t=" + [System.Guid]::NewGuid().ToString("N")
    $zipPath = Join-Path $env:TEMP ("flowstudio_install_" + [System.Guid]::NewGuid().ToString("N") + ".zip")
    $extDir = Join-Path $env:TEMP ("fs_install_ext_" + [System.Guid]::NewGuid().ToString("N"))

    try {
        Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing
        Expand-Archive -LiteralPath $zipPath -DestinationPath $extDir -Force
        $extractedRoot = Join-Path $extDir "flowstudio-gemini-watermark-remover-main"
        if (-not (Test-Path -LiteralPath $extractedRoot)) {
            $firstDir = Get-ChildItem -LiteralPath $extDir -Directory | Select-Object -First 1
            if ($firstDir) { $extractedRoot = $firstDir.FullName } else { $extractedRoot = $extDir }
        }
        $srcClean = [System.IO.Path]::GetFullPath($extractedRoot).TrimEnd('\', '/')

        if (-not (Test-Path -LiteralPath $destClean)) {
            New-Item -ItemType Directory -Path $destClean -Force | Out-Null
        }

        $preserveDirs = @(".venv", "bin", "models", "workspace", ".git")
        & robocopy $srcClean $destClean /E /IS /IT /XD .venv bin models workspace .git /NFL /NDL /NJH /NJS /R:5 /W:1 | Out-Null
        if ($LASTEXITCODE -ge 8) {
            Merge-DirectoryTree -SrcRoot $srcClean -DstRoot $destClean -PreserveTop $preserveDirs
        }
    } finally {
        Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $extDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# 1. Stop active server and unlock .pyd files scoped to target install
if (Test-Path -LiteralPath $target) {
    Write-Host "[1/3] Existing installation detected. Checking and unlocking engine files..." -ForegroundColor Green
    $dirOwnsPort = $false
    try {
        $conn = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($conn -and $conn.OwningProcess) {
            $lp = Get-CimInstance Win32_Process -Filter "ProcessId = $($conn.OwningProcess)" -ErrorAction SilentlyContinue
            if ($lp -and (($lp.CommandLine -like "*$target*") -or ($lp.ExecutablePath -like "*$target*"))) {
                $dirOwnsPort = $true
            }
        }
    } catch {}
    if ($dirOwnsPort) {
        try {
            $null = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/system/shutdown" -Method Post -Body "{}" -ContentType "application/json" -TimeoutSec 2 -ErrorAction SilentlyContinue
        } catch {}
        Start-Sleep -Milliseconds 700
    }

    $escapedTarget = [Regex]::Escape($target)
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        ($_.Name -match '^python.*\.exe$') -and
        ($_.CommandLine -notmatch 'PRIVATE_SOURCE') -and
        (($_.CommandLine -match $escapedTarget) -or ($_.ExecutablePath -match $escapedTarget))
    } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 1000

    # Wait up to 6s for compiled .pyd files to become writable
    for ($w = 0; $w -lt 18; $w++) {
        $locked = $false
        $engDir = Join-Path $target "engine"
        if (Test-Path -LiteralPath $engDir) {
            foreach ($pyd in (Get-ChildItem -LiteralPath $engDir -Filter "*.pyd" -ErrorAction SilentlyContinue)) {
                try {
                    $fs = [System.IO.File]::Open($pyd.FullName, 'Open', 'ReadWrite', 'None')
                    $fs.Close()
                } catch {
                    $locked = $true
                    break
                }
            }
        }
        if (-not $locked) { break }
        Start-Sleep -Milliseconds 350
    }

    # Fetch updates: try git fetch + reset first, fallback to zip merge
    $gitSuccess = $false
    if ((Test-Path -LiteralPath (Join-Path $target ".git")) -and $hasGit) {
        Write-Host "Fetching updates via git (force-push safe)..." -ForegroundColor Green
        $idxLock = Join-Path $target ".git\index.lock"
        if (Test-Path -LiteralPath $idxLock) {
            Remove-Item -LiteralPath $idxLock -Force -ErrorAction SilentlyContinue
        }
        & $gitCmd -C $target fetch --depth 1 origin main
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
        & $gitCmd clone --depth 1 $remoteUrl $target
        if ($LASTEXITCODE -eq 0) {
            $cloneSuccess = $true
        }
    }
    if (-not $cloneSuccess) {
        Sync-FromZipArchive -destPath $target
    }
}

# 2. Check broken .venv if missing pip
if (Test-Path -LiteralPath (Join-Path $target ".venv")) {
    if (-not (Test-Path -LiteralPath (Join-Path $target ".venv\Scripts\pip.exe"))) {
        Write-Host "[!] Broken .venv detected (pip missing). Removing to guarantee clean recreation..." -ForegroundColor Yellow
        Remove-Item -LiteralPath (Join-Path $target ".venv") -Recurse -Force
    }
}

# 3. Run Portable Setup (100% Inline Live Execution)
Write-Host "[2/3] Configuring environment, AI models & Native Bridge..." -ForegroundColor Green
$env:FLOWSTUDIO_AUTO = "1"
Push-Location $target
try {
    & cmd.exe /d /c "`"$target\setup_portable.bat`" --nopause"
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

# 4. Copy Extension Path Silently & Post-Install Self-Check
Write-Host "[3/3] Running post-install self-check..." -ForegroundColor Green
try { Set-Clipboard (Join-Path $target "extension") } catch {}

$vFile = Join-Path $target "version.json"
$actualVersion = "4.0.2"
if (Test-Path -LiteralPath $vFile) {
    try {
        $actualVersion = [string](Get-Content -LiteralPath $vFile -Raw | ConvertFrom-Json).version
        $actualVersion = $actualVersion.Trim().TrimStart('v')
    } catch {}
} else {
    Write-Host "[ERROR] Missing version.json in $target" -ForegroundColor Red
    exit 1
}

# Verify Native Messaging Host manifest + launcher + HKCU exist cleanly
$nhJson = Join-Path $target "native_host\com.flowstudio.bridge.json"
$nhBat = Join-Path $target "native_host\flowstudio_host.bat"
$nhLegacyBat = Join-Path $target "native_host\host.bat"
$nhReg = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.flowstudio.bridge"
$venvPy = Join-Path $target ".venv\Scripts\python.exe"
$venvPyw = Join-Path $target ".venv\Scripts\pythonw.exe"
if ((-not (Test-Path -LiteralPath $nhJson)) -or (-not (Test-Path -LiteralPath $nhBat)) -or (-not (Test-Path -LiteralPath $nhLegacyBat)) -or (-not (Test-Path $nhReg))) {
    $regPy = Join-Path $target "native_host\register_host.py"
    if ((Test-Path -LiteralPath $regPy) -and (Test-Path -LiteralPath $venvPy)) {
        & $venvPy $regPy --install-dir $target
    }
}
if ((-not (Test-Path -LiteralPath $nhJson)) -or (-not (Test-Path -LiteralPath $nhBat)) -or (-not (Test-Path $nhReg))) {
    Write-Host "[ERROR] Chrome Native Messaging registration incomplete ($nhReg)." -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Verified Chrome Native Messaging Host: $nhBat" -ForegroundColor Green

# Start background server cleanly and verify /api/health ONLINE
if ((-not $SkipLaunch) -and ($env:FLOWSTUDIO_NO_LAUNCH -ne "1")) {
    $trayPy = Join-Path $target "tray_app.py"
    $launchExe = if (Test-Path -LiteralPath $venvPyw) { $venvPyw } else { $venvPy }
    if ((Test-Path -LiteralPath $trayPy) -and (Test-Path -LiteralPath $launchExe)) {
        $alreadyUp = $false
        try {
            $h0 = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/health" -TimeoutSec 1 -ErrorAction Stop
            if ($h0.status -eq "ONLINE") { $alreadyUp = $true }
        } catch {}
        if (-not $alreadyUp) {
            $launched = $false
            try {
                $cmdLine = "`"$launchExe`" `"$trayPy`" --silent"
                $wmiRes = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $cmdLine; CurrentDirectory = $target }
                if ($wmiRes.ReturnValue -eq 0) { $launched = $true }
            } catch {}
            if (-not $launched) {
                Start-Process -FilePath $launchExe -ArgumentList "`"$trayPy`" --silent" -WorkingDirectory $target -WindowStyle Hidden
            }
        }
        $onlineOk = $false
        for ($i = 0; $i -lt 30; $i++) {
            try {
                $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/health" -TimeoutSec 1 -ErrorAction Stop
                if ($resp.status -eq "ONLINE") {
                    Write-Host "[OK] Server verified ONLINE (v$($resp.version))" -ForegroundColor Green
                    $onlineOk = $true
                    break
                }
            } catch {}
            Start-Sleep -Milliseconds 500
        }
        if (-not $onlineOk) {
            Write-Host "[WARN] Tray launched; waiting for /api/health took >15s. Check workspace\server.log if needed." -ForegroundColor Yellow
        }
    }
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

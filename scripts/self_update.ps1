param(
    [Parameter(Mandatory = $true)]
    [string]$InstallDir,
    [string]$Branch = "main",
    [switch]$SkipRelaunch
)

$ErrorActionPreference = "Continue"

$absDir = [System.IO.Path]::GetFullPath($InstallDir).TrimEnd('\', '/')
if (
    ($absDir -imatch 'PRIVATE_SOURCE') -or
    (Test-Path (Join-Path $absDir 'cloud_backend')) -or
    (Test-Path (Join-Path $absDir 'assets\masks')) -or
    (Test-Path (Join-Path $absDir 'build_scripts\build_protected_release.py')) -or
    (-not (Test-Path (Join-Path $absDir 'tray_app.py'))) -or
    (-not (Test-Path (Join-Path $absDir '.venv')))
) {
    exit 2
}

$logDir = Join-Path $absDir 'workspace\logs'
New-Item -ItemType Directory -Path $logDir -Force -ErrorAction SilentlyContinue | Out-Null
$logPath = Join-Path $logDir 'updater.log'

function Write-UpdateLog([string]$msg) {
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    try {
        Add-Content -Path $logPath -Value "[$ts] $msg" -Encoding UTF8 -ErrorAction SilentlyContinue
    } catch {}
}

Write-UpdateLog "=== FlowStudio HTTP Self-Updater started for $absDir (branch=$Branch) ==="

# 1. Stop server and tray processes scoped STRICTLY to $absDir
try {
    $null = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/system/shutdown' -Method Post -Body '{}' -ContentType 'application/json' -TimeoutSec 2 -ErrorAction SilentlyContinue
} catch {}
Start-Sleep -Milliseconds 900

$escapedDir = [Regex]::Escape($absDir)
for ($pass = 0; $pass -lt 4; $pass++) {
    $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        ($_.Name -match '^python.*\.exe$') -and
        ($_.CommandLine -notmatch 'PRIVATE_SOURCE') -and
        (($_.CommandLine -match $escapedDir) -or ($_.ExecutablePath -match $escapedDir))
    }
    if (-not $procs) { break }
    foreach ($p in $procs) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 600
}

# Wait briefly for compiled .pyd files to become writable
$pydFiles = @(
    'watermark_remover.cp312-win_amd64.pyd',
    'video_pipeline.cp312-win_amd64.pyd',
    'upscaler.cp312-win_amd64.pyd',
    'project_processor.cp312-win_amd64.pyd'
)
for ($w = 0; $w -lt 15; $w++) {
    $locked = $false
    foreach ($pf in $pydFiles) {
        $fullP = Join-Path $absDir ("engine\" + $pf)
        if (Test-Path -LiteralPath $fullP) {
            try {
                $fs = [System.IO.File]::Open($fullP, 'Open', 'ReadWrite', 'None')
                $fs.Close()
            } catch {
                $locked = $true
                break
            }
        }
    }
    if (-not $locked) { break }
    Start-Sleep -Milliseconds 300
}

# Record requirements.txt hash before update
$reqPath = Join-Path $absDir 'requirements.txt'
$reqHashFile = Join-Path $absDir 'workspace\.requirements.sha256'
$prevReqHash = ''
if (Test-Path -LiteralPath $reqHashFile) {
    $prevReqHash = (Get-Content -LiteralPath $reqHashFile -Raw -ErrorAction SilentlyContinue).Trim()
} elseif (Test-Path -LiteralPath $reqPath) {
    $prevReqHash = (Get-FileHash -LiteralPath $reqPath -Algorithm SHA256).Hash
}

# 2. Sync latest release files in-place (preserving .venv, bin, models, workspace, .git, and keeping extension/ directory identity)
$repoSlug = 'darshanrathod27/flowstudio-gemini-watermark-remover'
$gitCmd = $null
foreach ($gc in @(
    (Get-Command git -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
    (Join-Path $env:LOCALAPPDATA 'Programs\Git\cmd\git.exe'),
    'C:\Program Files\Git\cmd\git.exe'
)) {
    if ($gc -and (Test-Path -LiteralPath $gc)) {
        $gitCmd = $gc
        break
    }
}

$updated = $false
if ($gitCmd -and (Test-Path -LiteralPath (Join-Path $absDir '.git'))) {
    Write-UpdateLog "Syncing via git: $gitCmd"
    $idxLock = Join-Path $absDir '.git\index.lock'
    if (Test-Path -LiteralPath $idxLock) {
        Remove-Item -LiteralPath $idxLock -Force -ErrorAction SilentlyContinue
    }
    & $gitCmd -C $absDir fetch --depth 1 origin $Branch 2>&1 | ForEach-Object { Write-UpdateLog "git: $_" }
    if ($LASTEXITCODE -eq 0) {
        & $gitCmd -C $absDir reset --hard "origin/$Branch" 2>&1 | ForEach-Object { Write-UpdateLog "git: $_" }
        if ($LASTEXITCODE -eq 0) {
            $updated = $true
            Write-UpdateLog "Git in-place reset succeeded."
        }
    }
}

if (-not $updated) {
    Write-UpdateLog "Git unavailable or failed; falling back to GitHub ZIP in-place sync..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $zipUrl = "https://github.com/$repoSlug/archive/refs/heads/$Branch.zip?t=" + [System.Guid]::NewGuid().ToString('N')
    $tmpZip = Join-Path $env:TEMP ("flowstudio_up_" + [System.Guid]::NewGuid().ToString('N') + ".zip")
    $tmpExt = Join-Path $env:TEMP ("flowstudio_up_ext_" + [System.Guid]::NewGuid().ToString('N'))
    try {
        Invoke-WebRequest -Uri $zipUrl -OutFile $tmpZip -UseBasicParsing
        Expand-Archive -Path $tmpZip -DestinationPath $tmpExt -Force
        $extRoot = Join-Path $tmpExt "flowstudio-gemini-watermark-remover-$Branch"
        if (-not (Test-Path -LiteralPath $extRoot)) {
            $firstDir = Get-ChildItem -Path $tmpExt -Directory | Select-Object -First 1
            if ($firstDir) { $extRoot = $firstDir.FullName }
        }
        & robocopy $extRoot $absDir /E /IS /IT /XD .venv bin models workspace .git /NFL /NDL /NJH /NJS | Out-Null
        if ($LASTEXITCODE -ge 8) {
            $preserveDirs = @('.venv', 'bin', 'models', 'workspace', '.git')
            Get-ChildItem -Path $extRoot -Force | ForEach-Object {
                if ($preserveDirs -notcontains $_.Name) {
                    $dest = Join-Path $absDir $_.Name
                    if ($_.PSIsContainer) {
                        Copy-Item -Path $_.FullName -Destination $dest -Recurse -Force
                    } else {
                        Copy-Item -Path $_.FullName -Destination $dest -Force
                    }
                }
            }
        }
        $updated = $true
        Write-UpdateLog "ZIP in-place sync completed."
    } catch {
        Write-UpdateLog "ZIP sync failed: $($_.Exception.Message)"
    } finally {
        Remove-Item -LiteralPath $tmpZip -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $tmpExt -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# 3. Incremental requirements update ONLY if requirements.txt hash changed (preserves CUDA cu128 PyTorch!)
$venvPy = Join-Path $absDir '.venv\Scripts\python.exe'
$venvPyw = Join-Path $absDir '.venv\Scripts\pythonw.exe'
if ((Test-Path -LiteralPath $reqPath) -and (Test-Path -LiteralPath $venvPy)) {
    $newReqHash = (Get-FileHash -LiteralPath $reqPath -Algorithm SHA256).Hash
    if ($newReqHash -ne $prevReqHash) {
        Write-UpdateLog "requirements.txt changed ($prevReqHash -> $newReqHash); installing incremental packages..."
        & $venvPy -m pip install --quiet -r $reqPath 2>&1 | ForEach-Object { Write-UpdateLog "pip: $_" }
    }
    try { Set-Content -Path $reqHashFile -Value $newReqHash -Encoding ASCII -NoNewline } catch {}
}

# 4. Always re-register Native Messaging Host & refresh Desktop Shortcut
$regScript = Join-Path $absDir 'native_host\register_host.py'
if (-not (Test-Path -LiteralPath $regScript)) {
    $regScript = Join-Path $absDir 'native_host\install_native_host.py'
}
if ((Test-Path -LiteralPath $regScript) -and (Test-Path -LiteralPath $venvPy)) {
    & $venvPy $regScript --install-dir $absDir 2>&1 | ForEach-Object { Write-UpdateLog $_ }
}

$shortcutScript = Join-Path $absDir 'scripts\create_shortcut.py'
if ((Test-Path -LiteralPath $shortcutScript) -and (Test-Path -LiteralPath $venvPy)) {
    & $venvPy $shortcutScript 2>&1 | ForEach-Object { Write-UpdateLog $_ }
}

# 5. Relaunch hidden tray_app.py --silent cleanly
if (-not $SkipRelaunch) {
    $trayPy = Join-Path $absDir 'tray_app.py'
    $launchExe = if (Test-Path -LiteralPath $venvPyw) { $venvPyw } else { $venvPy }
    if ((Test-Path -LiteralPath $trayPy) -and (Test-Path -LiteralPath $launchExe)) {
        $launched = $false
        try {
            $cmdLine = "`"$launchExe`" `"$trayPy`" --silent"
            $wmiRes = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $cmdLine; CurrentDirectory = $absDir }
            if ($wmiRes.ReturnValue -eq 0) {
                $launched = $true
                Write-UpdateLog "Relaunched tray_app.py --silent via WMI (PID=$($wmiRes.ProcessId))"
            }
        } catch {}
        if (-not $launched) {
            Start-Process -FilePath $launchExe -ArgumentList "`"$trayPy`" --silent" -WorkingDirectory $absDir -WindowStyle Hidden
            Write-UpdateLog "Relaunched tray_app.py --silent via Start-Process Hidden"
        }

        for ($h = 0; $h -lt 30; $h++) {
            try {
                $resp = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/health' -TimeoutSec 1 -ErrorAction Stop
                if ($resp.status -eq 'ONLINE') {
                    Write-UpdateLog "Verified restarted server ONLINE on v$($resp.version)"
                    break
                }
            } catch {}
            Start-Sleep -Milliseconds 400
        }
    }
}

Write-UpdateLog "=== FlowStudio Self-Updater finished ==="
if ($PSCommandPath -like "$env:TEMP*flowstudio_self_update_*") {
    Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
}
exit 0

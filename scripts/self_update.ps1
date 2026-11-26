param(
    [Parameter(Mandatory = $true)]
    [string]$InstallDir,
    [string]$Branch = "main",
    [string]$SourceZip = "",
    [switch]$SkipRelaunch
)

$ErrorActionPreference = "Continue"

$absDir = [System.IO.Path]::GetFullPath($InstallDir).TrimEnd('\', '/')
$parentDir = Split-Path -Path $absDir -Parent
$isSiblingDev = $false
if (-not [string]::IsNullOrWhiteSpace($parentDir)) {
    $isSiblingDev = Test-Path -LiteralPath (Join-Path $parentDir 'FlowStudio_PRIVATE_SOURCE')
}

if (
    ($absDir -imatch 'PRIVATE_SOURCE') -or
    $isSiblingDev -or
    (Test-Path -LiteralPath (Join-Path $absDir 'cloud_backend')) -or
    (Test-Path -LiteralPath (Join-Path $absDir 'assets\masks')) -or
    (Test-Path -LiteralPath (Join-Path $absDir 'build_scripts\build_protected_release.py')) -or
    (-not (Test-Path -LiteralPath (Join-Path $absDir 'tray_app.py'))) -or
    (-not (Test-Path -LiteralPath (Join-Path $absDir '.venv')))
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

function Merge-DirectoryTree([string]$SrcRoot, [string]$DstRoot, [string[]]$PreserveTop) {
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

Write-UpdateLog "=== FlowStudio HTTP Self-Updater started for $absDir (branch=$Branch) ==="

# 1. Stop server and tray processes scoped STRICTLY to $absDir
$pidFile = Join-Path $absDir 'workspace\server.pid'
$dirHoldingPort = $false
try {
    $conn = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn -and $conn.OwningProcess) {
        $lp = Get-CimInstance Win32_Process -Filter "ProcessId = $($conn.OwningProcess)" -ErrorAction SilentlyContinue
        if ($lp -and (($lp.CommandLine -like "*$absDir*") -or ($lp.ExecutablePath -like "*$absDir*"))) {
            $dirHoldingPort = $true
        }
    }
} catch {}

if ($dirHoldingPort) {
    try {
        $null = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/system/shutdown' -Method Post -Body '{}' -ContentType 'application/json' -TimeoutSec 2 -ErrorAction SilentlyContinue
    } catch {}
    Start-Sleep -Milliseconds 900
}

if (Test-Path -LiteralPath $pidFile) {
    try {
        $rawPid = (Get-Content -LiteralPath $pidFile -Raw -ErrorAction SilentlyContinue).Trim()
        if ($rawPid -match '^\d+$') {
            Stop-Process -Id ([int]$rawPid) -Force -ErrorAction SilentlyContinue
        }
    } catch {}
}

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

# Wait up to 8s for compiled .pyd files to become writable
$pydFiles = @(
    'watermark_remover.cp312-win_amd64.pyd',
    'video_pipeline.cp312-win_amd64.pyd',
    'upscaler.cp312-win_amd64.pyd',
    'project_processor.cp312-win_amd64.pyd'
)
for ($w = 0; $w -lt 24; $w++) {
    $locked = $false
    foreach ($pf in $pydFiles) {
        $fullP = Join-Path $absDir ("engine\" + $pf)
        if (Test-Path -LiteralPath $fullP -PathType Leaf) {
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
    Start-Sleep -Milliseconds 350
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
$useLocalZip = (-not [string]::IsNullOrWhiteSpace($SourceZip)) -and (Test-Path -LiteralPath $SourceZip -PathType Leaf)

if ((-not $useLocalZip) -and $gitCmd -and (Test-Path -LiteralPath (Join-Path $absDir '.git'))) {
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
    Write-UpdateLog "Syncing via ZIP file-by-file atomic merge..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $tmpZip = if ($useLocalZip) { $SourceZip } else { Join-Path $env:TEMP ("flowstudio_up_" + [System.Guid]::NewGuid().ToString('N') + ".zip") }
    $tmpExt = Join-Path $env:TEMP ("flowstudio_up_ext_" + [System.Guid]::NewGuid().ToString('N'))
    try {
        if (-not $useLocalZip) {
            $zipUrl = "https://github.com/$repoSlug/archive/refs/heads/$Branch.zip?t=" + [System.Guid]::NewGuid().ToString('N')
            Invoke-WebRequest -Uri $zipUrl -OutFile $tmpZip -UseBasicParsing
        }
        Expand-Archive -LiteralPath $tmpZip -DestinationPath $tmpExt -Force
        $extRoot = Join-Path $tmpExt "flowstudio-gemini-watermark-remover-$Branch"
        if (-not (Test-Path -LiteralPath $extRoot)) {
            $firstDir = Get-ChildItem -LiteralPath $tmpExt -Directory | Select-Object -First 1
            if ($firstDir) { $extRoot = $firstDir.FullName } else { $extRoot = $tmpExt }
        }
        $extRootNoSlash = [System.IO.Path]::GetFullPath($extRoot).TrimEnd('\', '/')
        $preserveDirs = @('.venv', 'bin', 'models', 'workspace', '.git')
        & robocopy $extRootNoSlash $absDir /E /IS /IT /XD .venv bin models workspace .git /NFL /NDL /NJH /NJS /R:5 /W:1 | Out-Null
        if ($LASTEXITCODE -ge 8) {
            Write-UpdateLog "robocopy returned $LASTEXITCODE; running file-by-file Merge-DirectoryTree..."
            Merge-DirectoryTree -SrcRoot $extRootNoSlash -DstRoot $absDir -PreserveTop $preserveDirs
        }
        $updated = $true
        Write-UpdateLog "ZIP in-place sync completed cleanly."
    } catch {
        Write-UpdateLog "ZIP sync failed: $($_.Exception.Message)"
        exit 1
    } finally {
        if (-not $useLocalZip) {
            Remove-Item -LiteralPath $tmpZip -Force -ErrorAction SilentlyContinue
        }
        Remove-Item -LiteralPath $tmpExt -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# 3. Incremental requirements update ONLY if requirements.txt hash changed (preserves CUDA cu128 PyTorch!)
$venvPy = Join-Path $absDir '.venv\Scripts\python.exe'
$venvPyw = Join-Path $absDir '.venv\Scripts\pythonw.exe'
if ((Test-Path -LiteralPath $reqPath) -and (Test-Path -LiteralPath $venvPy)) {
    $newReqHash = (Get-FileHash -LiteralPath $reqPath -Algorithm SHA256).Hash
    if ($newReqHash -ne $prevReqHash) {
        & $venvPy -m pip --version 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-UpdateLog "requirements.txt changed ($prevReqHash -> $newReqHash); installing incremental packages..."
            & $venvPy -m pip install --quiet -r $reqPath 2>&1 | ForEach-Object { Write-UpdateLog "pip: $_" }
        }
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

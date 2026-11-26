import os
import sys
import json
import time
import socket
import struct
import shutil
import ctypes
import subprocess
import urllib.request

# Ensure binary mode on Windows immediately
if sys.platform == "win32":
    import msvcrt
    msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
    msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)

HOST_DIR = os.path.dirname(os.path.abspath(__file__))
FLOWSTUDIO_DIR = os.path.dirname(HOST_DIR)
if FLOWSTUDIO_DIR not in sys.path:
    sys.path.insert(0, FLOWSTUDIO_DIR)
try:
    from engine.hardware import get_subprocess_kwargs
except ImportError:
    def get_subprocess_kwargs(extra_flags: int = 0, hide_window: bool = False) -> dict:
        if sys.platform == "win32":
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) | int(extra_flags or 0)
            kw = {"creationflags": flags}
            if hide_window:
                si_cls = getattr(subprocess, "STARTUPINFO", None)
                if si_cls is not None:
                    si = si_cls()
                    si.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0x00000001)
                    si.wShowWindow = 0
                    kw["startupinfo"] = si
            return kw
        return {}

WORKSPACE_DIR = os.path.join(FLOWSTUDIO_DIR, "workspace")
os.makedirs(WORKSPACE_DIR, exist_ok=True)

PID_FILE = os.path.join(WORKSPACE_DIR, "server.pid")
SERVER_LOG = os.path.join(WORKSPACE_DIR, "server.log")
NATIVE_LOG = os.path.join(WORKSPACE_DIR, "native_host.log")
HEALTH_URL = "http://127.0.0.1:8765/api/health"
SHUTDOWN_URL = "http://127.0.0.1:8765/api/system/shutdown"


def is_developer_source_dir(install_root: str = FLOWSTUDIO_DIR) -> bool:
    """Developer Safety Guard: returns True for PRIVATE_SOURCE or its sibling dev build ./FlowStudio."""
    abs_root = os.path.abspath(install_root or "").rstrip("\\/")
    parent_root = os.path.dirname(abs_root)
    return (
        "PRIVATE_SOURCE" in abs_root.upper()
        or os.path.isdir(os.path.join(abs_root, "FlowStudio_PRIVATE_SOURCE"))
        or (bool(parent_root) and os.path.isdir(os.path.join(parent_root, "FlowStudio_PRIVATE_SOURCE")))
        or os.path.isfile(os.path.join(abs_root, "build_scripts", "build_protected_release.py"))
        or os.path.isdir(os.path.join(abs_root, "cloud_backend"))
        or os.path.isdir(os.path.join(abs_root, "assets", "masks"))
    )

def log_msg(msg: str):
    """Logs to native_host.log (NEVER to stdout, to protect Chrome stdio protocol)."""
    try:
        os.makedirs(WORKSPACE_DIR, exist_ok=True)
        with open(NATIVE_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass

def get_python_exe() -> str:
    if sys.platform == "darwin":
        for cand in (
            os.path.join(FLOWSTUDIO_DIR, ".venv", "bin", "python"),
            os.path.join(FLOWSTUDIO_DIR, ".venv", "bin", "python3"),
        ):
            if os.path.exists(cand):
                return cand
        return sys.executable

    venv_py = os.path.join(FLOWSTUDIO_DIR, ".venv", "Scripts", "python.exe")
    if os.path.exists(venv_py):
        return venv_py
    return sys.executable

def get_pythonw_exe() -> str:
    if sys.platform == "darwin":
        return get_python_exe()

    venv_pyw = os.path.join(FLOWSTUDIO_DIR, ".venv", "Scripts", "pythonw.exe")
    if os.path.exists(venv_pyw):
        return venv_pyw
    exe_dir_pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if os.path.exists(exe_dir_pyw):
        return exe_dir_pyw
    return get_python_exe()

def find_git_exe():
    if sys.platform == "darwin":
        candidates = [
            shutil.which("git"),
            "/usr/bin/git",
            "/opt/homebrew/bin/git",
            "/usr/local/bin/git",
        ]
    else:
        candidates = [
            shutil.which("git"),
            r"C:\Program Files\Git\cmd\git.exe",
            r"C:\Program Files\Git\bin\git.exe",
            r"C:\Program Files (x86)\Git\cmd\git.exe",
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Git", "cmd", "git.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Git", "bin", "git.exe"),
        ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None

def get_health_data(timeout: float = 0.5):
    try:
        req = urllib.request.Request(HEALTH_URL, headers={"User-Agent": "FlowStudio-NativeHost"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception:
        pass
    return None

def check_server_health(timeout: float = 0.5) -> bool:
    return get_health_data(timeout=timeout) is not None

def read_message():
    raw_length = sys.stdin.buffer.read(4)
    if not raw_length or len(raw_length) < 4:
        return None
    message_length = struct.unpack("<I", raw_length)[0]
    raw_data = sys.stdin.buffer.read(message_length)
    if len(raw_data) < message_length:
        return None
    return json.loads(raw_data.decode("utf-8"))

def send_message(obj):
    encoded = json.dumps(obj).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(encoded)))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()

def is_port_listening(port: int = 8765, timeout: float = 0.08) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def is_pythonw_alive(pyw_exe: str = "") -> bool:
    """Checks whether a FlowStudio tray_app/server process is actually alive."""
    if sys.platform != "win32":
        pgrep_bin = shutil.which("pgrep")
        if not pgrep_bin:
            return False
        try:
            res = subprocess.run(
                [pgrep_bin, "-f", r"tray_app\.py|server\.app|uvicorn"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2,
            )
            return res.returncode == 0
        except Exception:
            return False
    try:
        ps_cmd = (
            "$p = Get-CimInstance Win32_Process | Where-Object { "
            "($_.Name -like 'python*.exe') -and ($_.CommandLine -match 'tray_app|server\\.app|uvicorn') "
            "} | Select-Object -First 1 -ExpandProperty ProcessId; "
            "if ($p) { exit 0 } else { exit 1 }"
        )
        res = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", ps_cmd],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
            **get_subprocess_kwargs(),
        )
        return res.returncode == 0
    except Exception:
        return False


def cleanup_stale_tray_if_port_dead():
    """Cleans up any stale/hung tray_app.py or orphaned server process ONLY when port 8765 is NOT listening."""
    if is_port_listening(8765, timeout=0.06):
        return

    sub_kwargs = get_subprocess_kwargs()
    # Fast path (<40ms): clean up leftover server.pid directly without PowerShell unless mutex is still held
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r", encoding="utf-8") as f:
                stale_pid = f.read().strip()
            if stale_pid.isdigit() and int(stale_pid) != os.getpid():
                if sys.platform == "win32":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", stale_pid],
                        capture_output=True,
                        timeout=2,
                        **sub_kwargs,
                    )
                else:
                    import signal
                    pid_int = int(stale_pid)
                    os.kill(pid_int, signal.SIGTERM)
                    time.sleep(0.2)
                    try:
                        os.kill(pid_int, 0)
                        os.kill(pid_int, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
        except Exception:
            pass
        try:
            os.remove(PID_FILE)
        except Exception:
            pass

    mutex_held = False
    if sys.platform == "win32":
        try:
            SYNCHRONIZE = 0x00100000
            h = ctypes.windll.kernel32.OpenMutexW(SYNCHRONIZE, False, "FlowStudio_SystemTray_Mutex_v360")
            if h:
                mutex_held = True
                ctypes.windll.kernel32.CloseHandle(h)
        except Exception:
            pass

    if not mutex_held:
        return

    log_msg("Port 8765 dead while tray mutex is held; cleaning stale tray processes...")
    my_pid = os.getpid()
    ps_cmd = (
        f"Get-CimInstance Win32_Process | Where-Object {{ "
        f"($_.Name -match '^python.*\\.exe$') -and ($_.ProcessId -ne {my_pid}) -and "
        f"($_.CommandLine -notmatch 'host\\.py') -and "
        f"($_.CommandLine -match 'tray_app|server\\.app|uvicorn') "
        f"}} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}"
    )
    try:
        subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", ps_cmd],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=4,
            **sub_kwargs,
        )
    except Exception as e:
        log_msg(f"Stale tray cleanup error: {e}")
    time.sleep(0.1)


def launch_tray_popen(pyw_exe: str, tray_py: str, mode: str = "--silent") -> bool:
    """Immediate subprocess.Popen detached fallback (Win32 flags on Windows; start_new_session on POSIX)."""
    if sys.platform == "win32":
        CREATE_BREAKAWAY_FROM_JOB = 0x01000000
        new_pg = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        for extra_flag in (CREATE_BREAKAWAY_FROM_JOB, 0):
            try:
                proc_kwargs = get_subprocess_kwargs(extra_flags=new_pg | extra_flag, hide_window=True)
                proc = subprocess.Popen(
                    [pyw_exe, tray_py, mode],
                    cwd=FLOWSTUDIO_DIR,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                    **proc_kwargs,
                )
                log_msg(f"Popen fallback launched PID {proc.pid} (flags={hex(proc_kwargs.get('creationflags', 0))})")
                return True
            except Exception as e:
                log_msg(f"Popen launch attempt failed (extra_flag={hex(extra_flag)}): {e}")
        return False

    try:
        proc = subprocess.Popen(
            [pyw_exe, tray_py, mode],
            cwd=FLOWSTUDIO_DIR,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
        log_msg(f"POSIX detached Popen launched PID {proc.pid} ({pyw_exe} {mode})")
        return True
    except Exception as e:
        log_msg(f"POSIX Popen failed: {e}")
        return False


def launch_tray_detached(pyw_exe: str, tray_py: str, mode: str = "--silent") -> bool:
    """Spawns tray_app.py detached (WMI on Windows with Popen fallback; Popen start_new_session on POSIX)."""
    if sys.platform == "win32":
        # 1. Primary: WMI Win32_Process.Create (spawns under WmiPrvSE.exe, Job Object immune)
        try:
            clean_dir = FLOWSTUDIO_DIR.rstrip("\\/").replace("'", "''")
            esc_pyw = pyw_exe.replace("'", "''")
            esc_tray = tray_py.replace("'", "''")
            esc_mode = str(mode or "--silent").replace("'", "''")
            ps_cmd = (
                f"$exe = '{esc_pyw}'; "
                f"$arg = '{esc_tray}'; "
                f"$mode = '{esc_mode}'; "
                "$cmd = '\"' + $exe + '\" \"' + $arg + '\" ' + $mode; "
                f"$dir = '{clean_dir}'; "
                "$res = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $cmd; CurrentDirectory = $dir }; "
                "exit $res.ReturnValue"
            )
            p = subprocess.run(
                ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", ps_cmd],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                **get_subprocess_kwargs(),
            )
            if p.returncode == 0:
                log_msg(f"WMI process creation launched: {pyw_exe} {mode} (RC: 0)")
                return True
            log_msg(f"WMI process creation returned code {p.returncode}; falling back to Popen")
        except Exception as e:
            log_msg(f"WMI launcher failed/timed out ({e}); falling back to Popen")

    # 2. Immediate fallback (or primary on macOS/Linux)
    return launch_tray_popen(pyw_exe, tray_py, mode=mode)


def handle_start():
    log_msg("handle_start requested")
    t0 = time.perf_counter()
    os.makedirs(WORKSPACE_DIR, exist_ok=True)

    if is_port_listening(8765, timeout=0.08):
        health = get_health_data(timeout=0.7)
        if health:
            ver = health.get("version", "4.0.2")
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            log_msg(f"Server already running on port 8765 (version: {ver}, {elapsed_ms}ms)")
            return {
                "ok": True,
                "status": "online",
                "version": ver,
                "elapsed_ms": elapsed_ms,
                "error": None,
                "already_running": True,
            }
        # Port 8765 open but unresponsive -> reap stale FlowStudio listener scoped to this install
        unlock_and_stop_server(target_dir=FLOWSTUDIO_DIR, only_if_owned=True)

    # Prevent zombie tray holding mutex from blocking a fresh wake when port 8765 is dead
    cleanup_stale_tray_if_port_dead()

    pyw_exe = get_pythonw_exe()
    tray_py = os.path.join(FLOWSTUDIO_DIR, "tray_app.py")
    if not os.path.exists(tray_py):
        log_msg("tray_app.py not found")
        return {
            "ok": False,
            "status": "error",
            "version": "",
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
            "error": "tray_app.py not found",
        }

    launched = launch_tray_detached(pyw_exe, tray_py, mode="--silent")
    if not launched:
        log_msg("Failed to launch detached tray_app")
        return {
            "ok": False,
            "status": "error",
            "version": "",
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
            "error": "Process launch failed",
        }

    # Poll /api/health every 200ms up to 12.0s; trigger 1 fallback spawn at 4s if no FlowStudio pythonw alive
    fallback_triggered = False
    while (time.perf_counter() - t0) < 12.0:
        if is_port_listening(8765, timeout=0.08):
            health = get_health_data(timeout=0.6)
            if health:
                ver = health.get("version", "4.0.0")
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                log_msg(f"Server verified online in {elapsed_ms / 1000.0:.2f}s (version: {ver})")
                return {
                    "ok": True,
                    "status": "online",
                    "version": ver,
                    "elapsed_ms": elapsed_ms,
                    "error": None,
                }
        time.sleep(0.12)

        if not fallback_triggered and (time.perf_counter() - t0) >= 4.0:
            fallback_triggered = True
            if not is_pythonw_alive(pyw_exe):
                log_msg("No FlowStudio pythonw.exe alive after 4s; triggering automatic fallback spawn...")
                launch_tray_popen(pyw_exe, tray_py, mode="--silent")

    # On failure: return last 5 lines from server.log + tray.log
    err_lines = []
    for log_path in [
        SERVER_LOG,
        os.path.join(WORKSPACE_DIR, "logs", "tray.log"),
        os.path.join(WORKSPACE_DIR, "tray.log"),
    ]:
        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = [l.strip() for l in f if l.strip()]
                    if lines:
                        err_lines.extend(lines[-5:])
            except Exception:
                pass
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    err_msg = " | ".join(err_lines) if err_lines else "Server health check timed out after 12s"
    log_msg(f"Server startup failed ({elapsed_ms}ms): {err_msg}")
    return {
        "ok": False,
        "status": "error",
        "version": "",
        "elapsed_ms": elapsed_ms,
        "error": err_msg,
    }

def _dir_owns_port_8765(target_dir: str) -> bool:
    abs_target = os.path.abspath(target_dir).rstrip("\\/")
    pid_file = os.path.join(abs_target, "workspace", "server.pid")
    if os.path.exists(pid_file):
        return True
    if sys.platform != "win32":
        pgrep_bin = shutil.which("pgrep")
        if pgrep_bin:
            try:
                res = subprocess.run(
                    [pgrep_bin, "-f", abs_target],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=1.5,
                )
                return res.returncode == 0
            except Exception:
                return False
        return False
    try:
        esc_dir = abs_target.replace("'", "''")
        ps_cmd = (
            "$conn = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; "
            "if ($conn -and $conn.OwningProcess) { "
            "$p = Get-CimInstance Win32_Process -Filter \"ProcessId = $($conn.OwningProcess)\" -ErrorAction SilentlyContinue; "
            f"$t = '{esc_dir}'; "
            "if ($p -and (($p.CommandLine -like \"*$t*\") -or ($p.ExecutablePath -like \"*$t*\"))) { exit 0 } "
            "}; exit 1"
        )
        r = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", ps_cmd],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
            **get_subprocess_kwargs(),
        )
        return r.returncode == 0
    except Exception:
        return False


def unlock_and_stop_server(target_dir: str = FLOWSTUDIO_DIR, only_if_owned: bool = False):
    """Unlocks server/tray processes scoped to target_dir and verifies .pyd files are writable."""
    abs_target = os.path.abspath(target_dir).rstrip("\\/")
    target_pid_file = os.path.join(abs_target, "workspace", "server.pid")
    log_msg(f"Stopping server and unlocking engine files for {abs_target}...")

    owns_port = _dir_owns_port_8765(abs_target)
    if (not only_if_owned) or owns_port:
        if owns_port or os.path.normcase(abs_target) == os.path.normcase(os.path.abspath(FLOWSTUDIO_DIR).rstrip("\\/")):
            if not only_if_owned or owns_port:
                try:
                    req = urllib.request.Request(SHUTDOWN_URL, data=b"{}", headers={"Content-Type": "application/json"})
                    urllib.request.urlopen(req, timeout=2.0)
                    time.sleep(0.4)
                except Exception:
                    pass

    my_pid = os.getpid()
    sub_kwargs = get_subprocess_kwargs()

    # Stop exact PID from workspace/server.pid first if present
    if os.path.exists(target_pid_file):
        try:
            with open(target_pid_file, "r", encoding="utf-8") as f:
                p = f.read().strip()
            if p.isdigit() and int(p) != my_pid:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/PID", p, "/T"], capture_output=True, timeout=3, **sub_kwargs)
                else:
                    import signal
                    pid_int = int(p)
                    os.kill(pid_int, signal.SIGTERM)
                    deadline = time.time() + 2.5
                    while time.time() < deadline:
                        try:
                            os.kill(pid_int, 0)
                            time.sleep(0.1)
                        except ProcessLookupError:
                            break
                    else:
                        os.kill(pid_int, signal.SIGKILL)
        except Exception:
            pass
        try:
            os.remove(target_pid_file)
        except Exception:
            pass

    if sys.platform == "win32":
        esc_ps = abs_target.replace("'", "''")
        ps_cmd = (
            f"$target = [Regex]::Escape('{esc_ps}'); "
            "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { "
            f"($_.Name -match '^python.*\\.exe$') -and ($_.ProcessId -ne {my_pid}) -and "
            "($_.CommandLine -notmatch 'host\\.py') -and "
            "($_.CommandLine -match 'tray_app|server\\.app|uvicorn') -and "
            "(($_.CommandLine -match $target) -or ($_.ExecutablePath -match $target)) "
            "} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
        )
        try:
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_cmd],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                **sub_kwargs,
            )
        except Exception as e:
            log_msg(f"Process cleanup PowerShell error: {e}")

        # Kill listener on 8765 ONLY if it runs out of abs_target
        if owns_port:
            try:
                esc_ps = abs_target.replace("'", "''")
                kill_8765_ps = (
                    "$conn = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; "
                    "if ($conn -and $conn.OwningProcess) { "
                    f"$pidVal = [int]$conn.OwningProcess; "
                    f"if ($pidVal -ne {my_pid}) {{ "
                    "$pr = Get-CimInstance Win32_Process -Filter \"ProcessId = $pidVal\" -ErrorAction SilentlyContinue; "
                    f"if ($pr -and (($pr.CommandLine -like \"*{esc_ps}*\") -or ($pr.ExecutablePath -like \"*{esc_ps}*\"))) {{ Stop-Process -Id $pidVal -Force -ErrorAction SilentlyContinue }} "
                    "} }"
                )
                subprocess.run(
                    ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", kill_8765_ps],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=4,
                    **sub_kwargs,
                )
            except Exception:
                pass
    else:
        pkill_bin = shutil.which("pkill")
        if pkill_bin:
            import re as _re
            pat = f"{_re.escape(abs_target)}/.*(tray_app\\.py|server\\.app|uvicorn)"
            for sig_flag in ("-TERM", "-KILL"):
                try:
                    subprocess.run([pkill_bin, sig_flag, "-f", pat], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
                except Exception:
                    pass
                time.sleep(0.3)

    # Wait up to 8s verifying .pyd files are writable/unlocked
    engine_dir = os.path.join(abs_target, "engine")
    pyds = []
    if os.path.isdir(engine_dir):
        for fname in os.listdir(engine_dir):
            if fname.endswith((".pyd", ".so")):
                pyds.append(os.path.join(engine_dir, fname))

    t0 = time.time()
    while time.time() - t0 < 8.0:
        all_writable = True
        for pyd in pyds:
            if os.path.exists(pyd):
                try:
                    with open(pyd, "a+b"):
                        pass
                except IOError:
                    all_writable = False
                    break
        if all_writable:
            log_msg("Target processes stopped and engine binaries verified writable/unlocked.")
            return True
        time.sleep(0.3)
    log_msg("Warning: timeout waiting 8s for engine file locks to release; continuing with retry-safe merge.")
    return True

def handle_stop():
    log_msg("handle_stop requested")
    unlock_and_stop_server(target_dir=FLOWSTUDIO_DIR)
    if os.path.exists(PID_FILE):
        try:
            os.remove(PID_FILE)
        except Exception:
            pass
    log_msg("Server stopped")
    return {"ok": True, "status": "stopped"}


def _atomic_copy_file(src_file: str, dst_file: str, retries: int = 8):
    """Copies src_file over dst_file atomically inside dst parent dir (never throws WinError 183)."""
    import stat
    import uuid
    dst_parent = os.path.dirname(dst_file)
    os.makedirs(dst_parent, exist_ok=True)
    tmp_dest = os.path.join(dst_parent, f".fs_upd_{uuid.uuid4().hex[:8]}.tmp")
    last_err = None
    for attempt in range(retries):
        try:
            shutil.copy2(src_file, tmp_dest)
            if os.path.exists(dst_file):
                try:
                    os.chmod(dst_file, stat.S_IWRITE | stat.S_IREAD)
                except Exception:
                    pass
            os.replace(tmp_dest, dst_file)
            return
        except (PermissionError, OSError) as e:
            last_err = e
            try:
                if os.path.exists(tmp_dest):
                    os.remove(tmp_dest)
            except Exception:
                pass
            time.sleep(0.35)
    raise last_err


def _merge_tree_inplace(src_root: str, dst_root: str, preserve_top: set):
    """
    File-by-file in-place merge (100% immune to [WinError 183 Cannot create a file when that file already exists]).
    NEVER calls os.rename/shutil.move or shutil.copytree(src, dst) onto existing directories.
    """
    src_abs = os.path.abspath(src_root)
    dst_abs = os.path.abspath(dst_root)
    for root, dirs, files in os.walk(src_abs):
        rel_dir = os.path.relpath(root, src_abs)
        if rel_dir != ".":
            top_seg = rel_dir.replace("\\", "/").split("/", 1)[0]
            if top_seg in preserve_top:
                dirs[:] = []
                continue
        else:
            dirs[:] = [d for d in dirs if d not in preserve_top]

        dst_dir = dst_abs if rel_dir == "." else os.path.join(dst_abs, rel_dir)
        os.makedirs(dst_dir, exist_ok=True)
        for fname in files:
            src_f = os.path.join(root, fname)
            dst_f = os.path.join(dst_dir, fname)
            _atomic_copy_file(src_f, dst_f)


def update_via_zip(source_zip_path: str = ""):
    import uuid
    import zipfile
    temp_dir = os.path.join(FLOWSTUDIO_DIR, "workspace", "temp")
    os.makedirs(temp_dir, exist_ok=True)
    own_zip = False
    if source_zip_path and os.path.isfile(source_zip_path):
        log_msg(f"Updating via local ZIP archive merge: {source_zip_path}")
        temp_zip = source_zip_path
    else:
        log_msg("Updating via GitHub ZIP download fallback (file-by-file merge)...")
        zip_url = f"https://github.com/darshanrathod27/flowstudio-gemini-watermark-remover/archive/refs/heads/main.zip?t={uuid.uuid4().hex}"
        temp_zip = os.path.join(temp_dir, f"update_download_{uuid.uuid4().hex[:8]}.zip")
        own_zip = True

    extract_dir = os.path.join(temp_dir, f"fs_zip_extract_{uuid.uuid4().hex[:8]}")
    try:
        if own_zip:
            req = urllib.request.Request(zip_url, headers={"User-Agent": "FlowStudio-Updater"})
            with urllib.request.urlopen(req, timeout=45) as resp, open(temp_zip, "wb") as out_f:
                shutil.copyfileobj(resp, out_f, 1024 * 1024)

        with zipfile.ZipFile(temp_zip, "r") as zf:
            zf.extractall(extract_dir)

        extracted_root = None
        for item in os.listdir(extract_dir):
            p = os.path.join(extract_dir, item)
            if os.path.isdir(p) and "flowstudio" in item.lower():
                extracted_root = p
                break
        if not extracted_root:
            sub_dirs = [os.path.join(extract_dir, d) for d in os.listdir(extract_dir) if os.path.isdir(os.path.join(extract_dir, d))]
            extracted_root = sub_dirs[0] if len(sub_dirs) == 1 else extract_dir

        preserve = {".venv", "bin", "models", "workspace", ".git"}
        _merge_tree_inplace(extracted_root, FLOWSTUDIO_DIR, preserve)

        log_msg("ZIP file-by-file atomic merge completed cleanly.")
        return True
    except Exception as e:
        log_msg(f"ZIP update extraction error: {e}")
        raise
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)
        if own_zip and os.path.exists(temp_zip):
            try:
                os.remove(temp_zip)
            except Exception:
                pass


def handle_update(source_zip_path: str = "", skip_relaunch: bool = False):
    log_msg("handle_update requested")
    if is_developer_source_dir(FLOWSTUDIO_DIR):
        msg = "Developer safety guard refused self-update inside private/dev workspace."
        log_msg(msg)
        return {"ok": False, "status": "error", "error": msg}

    source_zip_path = source_zip_path or os.environ.get("FLOWSTUDIO_TEST_ZIP", "").strip()
    if not skip_relaunch:
        skip_relaunch = os.environ.get("FLOWSTUDIO_TEST_SKIP_RELAUNCH", "").strip() == "1"

    py_exe = get_python_exe()
    pyw_exe = get_pythonw_exe()
    tray_py = os.path.join(FLOWSTUDIO_DIR, "tray_app.py")
    sub_kwargs = get_subprocess_kwargs()

    req_path = os.path.join(FLOWSTUDIO_DIR, "requirements.txt")
    req_hash_file = os.path.join(WORKSPACE_DIR, ".requirements.sha256")
    prev_req_hash = ""
    try:
        import hashlib
        if os.path.isfile(req_hash_file):
            with open(req_hash_file, "r", encoding="utf-8") as hf:
                prev_req_hash = hf.read().strip()
        elif os.path.isfile(req_path):
            with open(req_path, "rb") as rf:
                prev_req_hash = hashlib.sha256(rf.read()).hexdigest()
    except Exception:
        pass

    try:
        # Step A: Unlock server and .pyd/.so files scoped to FLOWSTUDIO_DIR
        unlock_and_stop_server(target_dir=FLOWSTUDIO_DIR)

        # Step B: Update via git (when no explicit local zip given) or file-by-file ZIP merge fallback
        method = "none"
        if not source_zip_path:
            git_dir = os.path.join(FLOWSTUDIO_DIR, ".git")
            git_exe = find_git_exe()

            if os.path.exists(git_dir) and git_exe:
                log_msg(f"Attempting git update using: {git_exe}")
                try:
                    idx_lock = os.path.join(git_dir, "index.lock")
                    if os.path.exists(idx_lock):
                        os.remove(idx_lock)
                    env = os.environ.copy()
                    git_parent = os.path.dirname(git_exe)
                    env["PATH"] = git_parent + os.pathsep + env.get("PATH", "")
                    subprocess.run([git_exe, "fetch", "--depth", "1", "origin", "main"], cwd=FLOWSTUDIO_DIR, env=env, check=True, capture_output=True, **sub_kwargs)
                    subprocess.run([git_exe, "reset", "--hard", "origin/main"], cwd=FLOWSTUDIO_DIR, env=env, check=True, capture_output=True, **sub_kwargs)
                    method = "git"
                    log_msg("Git reset --hard origin/main succeeded")
                except Exception as e:
                    log_msg(f"Git update failed: {e}. Falling back to ZIP file-by-file merge...")
                    method = "none"

        if method == "none":
            update_via_zip(source_zip_path=source_zip_path)
            method = "zip"

        # Step C: SHA256-gated dependencies (preserves CUDA/MPS PyTorch), Native Host, and Shortcut/.app
        if os.path.exists(req_path):
            try:
                import hashlib
                with open(req_path, "rb") as rf:
                    new_req_hash = hashlib.sha256(rf.read()).hexdigest()
                if new_req_hash != prev_req_hash:
                    pip_chk = subprocess.run([py_exe, "-m", "pip", "--version"], capture_output=True, **sub_kwargs)
                    if pip_chk.returncode == 0:
                        subprocess.run([py_exe, "-m", "pip", "install", "--quiet", "-r", req_path], cwd=FLOWSTUDIO_DIR, capture_output=True, **sub_kwargs)
                with open(req_hash_file, "w", encoding="utf-8") as hf:
                    hf.write(new_req_hash)
            except Exception as e:
                log_msg(f"pip requirements step warning: {e}")

        shortcut_created = False
        if sys.platform == "darwin":
            for rel_sh in (
                os.path.join(FLOWSTUDIO_DIR, "install.sh"),
                os.path.join(FLOWSTUDIO_DIR, "uninstall.sh"),
                os.path.join(HOST_DIR, "flowstudio_host.sh"),
                os.path.join(FLOWSTUDIO_DIR, "scripts", "self_update.sh"),
            ):
                if os.path.isfile(rel_sh):
                    try:
                        os.chmod(rel_sh, 0o755)
                    except Exception:
                        pass
            register_py = os.path.join(HOST_DIR, "register_host.py")
            if not os.path.exists(register_py):
                register_py = os.path.join(HOST_DIR, "register_host_mac.py")
            if os.path.exists(register_py):
                try:
                    subprocess.run([py_exe, register_py, "--install-dir", FLOWSTUDIO_DIR], cwd=FLOWSTUDIO_DIR, capture_output=True, **sub_kwargs)
                except Exception as e:
                    log_msg(f"macOS host registration failed: {e}")

            mac_app_script = os.path.join(FLOWSTUDIO_DIR, "scripts", "create_mac_app.py")
            if os.path.exists(mac_app_script):
                try:
                    res = subprocess.run([py_exe, mac_app_script], cwd=FLOWSTUDIO_DIR, capture_output=True, **sub_kwargs)
                    shortcut_created = (res.returncode == 0)
                    log_msg("macOS FlowStudio.app bundle refreshed successfully during update")
                except Exception as e:
                    log_msg(f"create_mac_app failed: {e}")
        else:
            reg_script = os.path.join(HOST_DIR, "register_host.py")
            if os.path.exists(reg_script):
                try:
                    subprocess.run([py_exe, reg_script, "--install-dir", FLOWSTUDIO_DIR], cwd=FLOWSTUDIO_DIR, capture_output=True, **sub_kwargs)
                except Exception as e:
                    log_msg(f"register_host failed: {e}")
            else:
                legacy_reg = os.path.join(HOST_DIR, "install_native_host.py")
                if os.path.exists(legacy_reg):
                    try:
                        subprocess.run([py_exe, legacy_reg], cwd=FLOWSTUDIO_DIR, capture_output=True, **sub_kwargs)
                    except Exception as e:
                        log_msg(f"install_native_host failed: {e}")

            if os.environ.get("FLOWSTUDIO_SKIP_SHORTCUT", "") != "1":
                shortcut_script = os.path.join(FLOWSTUDIO_DIR, "scripts", "create_shortcut.py")
                if os.path.exists(shortcut_script):
                    try:
                        res = subprocess.run([py_exe, shortcut_script], cwd=FLOWSTUDIO_DIR, capture_output=True, **sub_kwargs)
                        shortcut_created = (res.returncode == 0)
                        log_msg("Desktop shortcut recreated successfully during update")
                    except Exception as e:
                        log_msg(f"create_shortcut failed: {e}")

        # Step D: Read disk version, relaunch server detached and verify live backend version
        disk_ver = "4.0.2"
        v_file = os.path.join(FLOWSTUDIO_DIR, "version.json")
        if os.path.exists(v_file):
            try:
                with open(v_file, "r", encoding="utf-8") as f:
                    disk_ver = str(json.load(f).get("version", disk_ver)).strip().lstrip("v")
            except Exception:
                pass

        if skip_relaunch:
            return {
                "ok": True,
                "status": "updated",
                "version": disk_ver,
                "server_version": disk_ver,
                "server_verified": True,
                "method": method,
                "shortcut": shortcut_created,
            }

        start_res = handle_start()
        server_ver = start_res.get("version", disk_ver)
        if start_res.get("ok"):
            return {
                "ok": True,
                "status": "updated",
                "version": disk_ver,
                "server_version": server_ver,
                "server_verified": (str(server_ver).lstrip("v") == disk_ver),
                "method": method,
                "shortcut": shortcut_created,
            }
        return {
            "ok": False,
            "status": "error",
            "version": disk_ver,
            "error": f"Updated files to {disk_ver} but server health check failed: {start_res.get('error', 'timeout')}",
        }
    except Exception as e:
        log_msg(f"Fatal error in handle_update: {e}")
        if not skip_relaunch:
            try:
                launch_tray_detached(pyw_exe, tray_py, mode="--silent")
            except Exception:
                pass
        return {"ok": False, "status": "error", "error": str(e)}

def main():
    try:
        msg = read_message()
        if msg is None:
            sys.exit(0)

        cmd = msg.get("cmd") or msg.get("action") or msg.get("command") or ""
        log_msg(f"Received native command: {cmd}")

        if cmd == "start":
            res = handle_start()
            send_message(res)
            sys.exit(0)
        elif cmd == "stop":
            res = handle_stop()
            send_message(res)
            sys.exit(0)
        elif cmd == "update":
            res = handle_update(
                source_zip_path=str(msg.get("zip_path") or "").strip(),
                skip_relaunch=bool(msg.get("skip_relaunch", False)),
            )
            send_message(res)
            sys.exit(0)
        elif cmd == "status":
            health = get_health_data(timeout=0.3)
            pid = None
            if os.path.exists(PID_FILE):
                try:
                    with open(PID_FILE, "r", encoding="utf-8") as f:
                        pid = int(f.read().strip())
                except Exception:
                    pass
            send_message({
                "ok": True,
                "status": "running" if health else "stopped",
                "version": health.get("version", "") if health else "",
                "pid": pid,
                "port": 8765
            })
            sys.exit(0)
        elif cmd == "ping":
            send_message({"ok": True, "status": "pong"})
            sys.exit(0)
        else:
            send_message({"ok": False, "status": "error", "error": f"Unknown command: {cmd}"})
            sys.exit(0)
    except Exception as e:
        log_msg(f"Fatal error in host.py main: {e}")
        try:
            send_message({"ok": False, "status": "error", "error": str(e)})
        except Exception:
            pass
        sys.exit(1)

if __name__ == "__main__":
    main()

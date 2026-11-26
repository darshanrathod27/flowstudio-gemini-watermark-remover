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
WORKSPACE_DIR = os.path.join(FLOWSTUDIO_DIR, "workspace")
os.makedirs(WORKSPACE_DIR, exist_ok=True)

PID_FILE = os.path.join(WORKSPACE_DIR, "server.pid")
SERVER_LOG = os.path.join(WORKSPACE_DIR, "server.log")
NATIVE_LOG = os.path.join(WORKSPACE_DIR, "native_host.log")
HEALTH_URL = "http://127.0.0.1:8765/api/health"
SHUTDOWN_URL = "http://127.0.0.1:8765/api/system/shutdown"

def log_msg(msg: str):
    """Logs to native_host.log (NEVER to stdout, to protect Chrome stdio protocol)."""
    try:
        os.makedirs(WORKSPACE_DIR, exist_ok=True)
        with open(NATIVE_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass

def get_python_exe() -> str:
    venv_py = os.path.join(FLOWSTUDIO_DIR, ".venv", "Scripts", "python.exe")
    if os.path.exists(venv_py):
        return venv_py
    return sys.executable

def get_pythonw_exe() -> str:
    venv_pyw = os.path.join(FLOWSTUDIO_DIR, ".venv", "Scripts", "pythonw.exe")
    if os.path.exists(venv_pyw):
        return venv_pyw
    exe_dir_pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if os.path.exists(exe_dir_pyw):
        return exe_dir_pyw
    return get_python_exe()

def find_git_exe():
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
    """Checks whether a FlowStudio tray_app/server pythonw.exe process is actually alive."""
    if sys.platform != "win32":
        return False
    cflags = subprocess.CREATE_NO_WINDOW
    try:
        ps_cmd = (
            "$p = Get-CimInstance Win32_Process | Where-Object { "
            "($_.Name -like 'python*.exe') -and ($_.CommandLine -match 'tray_app|server\\.app|uvicorn') "
            "} | Select-Object -First 1 -ExpandProperty ProcessId; "
            "if ($p) { exit 0 } else { exit 1 }"
        )
        res = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", ps_cmd],
            creationflags=cflags,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
        return res.returncode == 0
    except Exception:
        return False


def cleanup_stale_tray_if_port_dead():
    """Cleans up any stale/hung tray_app.py or orphaned server process ONLY when port 8765 is NOT listening."""
    if is_port_listening(8765, timeout=0.06):
        return

    cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    # Fast path (<40ms): clean up leftover server.pid directly without PowerShell unless mutex is still held
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r", encoding="utf-8") as f:
                stale_pid = f.read().strip()
            if stale_pid.isdigit() and int(stale_pid) != os.getpid():
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", stale_pid],
                    capture_output=True,
                    timeout=2,
                    creationflags=cflags,
                )
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
        f"($_.CommandLine -match 'tray_app|server\\.app|uvicorn') "
        f"}} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}"
    )
    try:
        subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", ps_cmd],
            creationflags=cflags,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=4,
        )
    except Exception as e:
        log_msg(f"Stale tray cleanup error: {e}")
    time.sleep(0.1)


def launch_tray_popen(pyw_exe: str, tray_py: str, mode: str = "--silent") -> bool:
    """Immediate subprocess.Popen detached fallback with CREATE_NO_WINDOW and SW_HIDE."""
    if sys.platform == "win32":
        CREATE_BREAKAWAY_FROM_JOB = 0x01000000
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE
        for extra_flag in (CREATE_BREAKAWAY_FROM_JOB, 0):
            try:
                flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP | extra_flag
                proc = subprocess.Popen(
                    [pyw_exe, tray_py, mode],
                    cwd=FLOWSTUDIO_DIR,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                    creationflags=flags,
                    startupinfo=startupinfo,
                )
                log_msg(f"Popen fallback launched PID {proc.pid} (flags={hex(flags)})")
                return True
            except Exception as e:
                log_msg(f"Popen launch attempt failed (extra_flag={hex(extra_flag)}): {e}")
        return False

    try:
        subprocess.Popen(
            [pyw_exe, tray_py, mode],
            cwd=FLOWSTUDIO_DIR,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        return True
    except Exception as e:
        log_msg(f"POSIX Popen failed: {e}")
        return False


def launch_tray_detached(pyw_exe: str, tray_py: str, mode: str = "--silent") -> bool:
    """Spawns pythonw.exe tray_app.py outside Chrome's Job Object with immediate Popen fallback."""
    cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

    # 1. Primary: WMI Win32_Process.Create (spawns under WmiPrvSE.exe, Job Object immune)
    try:
        clean_dir = FLOWSTUDIO_DIR.rstrip("\\/").replace("'", "''")
        ps_cmd = (
            f"$cmd = '\"{pyw_exe}\" \"{tray_py}\" {mode}'; "
            f"$dir = '{clean_dir}'; "
            f"$res = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{{ CommandLine = $cmd; CurrentDirectory = $dir }}; "
            f"exit $res.ReturnValue"
        )
        p = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", ps_cmd],
            creationflags=cflags,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        if p.returncode == 0:
            log_msg(f"WMI process creation launched: {pyw_exe} {mode} (RC: 0)")
            return True
        log_msg(f"WMI process creation returned code {p.returncode}; falling back to Popen")
    except Exception as e:
        log_msg(f"WMI launcher failed/timed out ({e}); falling back to Popen")

    # 2. Immediate fallback: Popen with CREATE_BREAKAWAY_FROM_JOB & SW_HIDE
    return launch_tray_popen(pyw_exe, tray_py, mode=mode)


def handle_start():
    log_msg("handle_start requested")
    t0 = time.perf_counter()
    os.makedirs(WORKSPACE_DIR, exist_ok=True)

    if is_port_listening(8765, timeout=0.08):
        health = get_health_data(timeout=0.6)
        if health:
            ver = health.get("version", "3.9.0")
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
                ver = health.get("version", "3.9.0")
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
    for log_path in [SERVER_LOG, os.path.join(WORKSPACE_DIR, "tray.log")]:
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

def unlock_and_stop_server():
    """Unlocks all server/tray processes and verifies .pyd files are unlocked."""
    log_msg("Stopping server and unlocking .pyd files...")
    # 1. Graceful API shutdown
    try:
        req = urllib.request.Request(SHUTDOWN_URL, data=b"{}", headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=2.0)
    except Exception:
        pass

    # 2. Targeted hidden process cleanup killing ONLY python processes running tray_app or server.app (excluding our own PID)
    my_pid = os.getpid()
    cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    ps_cmd = (
        f"Get-CimInstance Win32_Process | Where-Object {{ "
        f"($_.Name -match '^python.*\\.exe$') -and ($_.ProcessId -ne {my_pid}) -and "
        f"($_.CommandLine -match 'tray_app|server\\.app|uvicorn') "
        f"}} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}"
    )
    try:
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_cmd],
            creationflags=cflags,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5
        )
    except Exception as e:
        log_msg(f"Process cleanup PowerShell error: {e}")

    # Also clean netstat port 8765 if any process remains
    try:
        res = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, creationflags=cflags)
        for line in res.stdout.splitlines():
            if ":8765 " in line and "LISTENING" in line:
                p = line.strip().split()[-1]
                if p.isdigit() and int(p) != my_pid:
                    log_msg(f"Killing listener PID {p} on port 8765")
                    subprocess.run(["taskkill", "/F", "/PID", p, "/T"], capture_output=True, creationflags=cflags)
    except Exception:
        pass

    if os.path.exists(PID_FILE):
        try:
            os.remove(PID_FILE)
        except Exception:
            pass

    # Wait up to 4s verifying port 8765 is closed and .pyd files are writable
    t0 = time.time()
    while time.time() - t0 < 4.0:
        if not check_server_health(timeout=0.2):
            pyds = [
                os.path.join(FLOWSTUDIO_DIR, "engine", f)
                for f in [
                    "watermark_remover.cp312-win_amd64.pyd",
                    "video_pipeline.cp312-win_amd64.pyd",
                    "upscaler.cp312-win_amd64.pyd",
                    "project_processor.cp312-win_amd64.pyd",
                ]
            ]
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
                log_msg("Server stopped and .pyd files verified writable/unlocked.")
                return True
        time.sleep(0.3)
    return True

def handle_stop():
    log_msg("handle_stop requested")
    unlock_and_stop_server()
    if os.path.exists(PID_FILE):
        try:
            os.remove(PID_FILE)
        except Exception:
            pass
    log_msg("Server stopped")
    return {"ok": True, "status": "stopped"}

def update_via_zip():
    log_msg("Updating via GitHub ZIP download fallback...")
    zip_url = "https://github.com/darshanrathod27/flowstudio-gemini-watermark-remover/archive/refs/heads/main.zip"
    temp_zip = os.path.join(FLOWSTUDIO_DIR, "workspace", "update_download.zip")
    extract_dir = os.path.join(FLOWSTUDIO_DIR, "workspace", "fs_zip_extract")
    try:
        import zipfile
        if os.path.exists(temp_zip):
            try: os.remove(temp_zip)
            except Exception: pass
        if os.path.exists(extract_dir):
            try: shutil.rmtree(extract_dir, ignore_errors=True)
            except Exception: pass

        urllib.request.urlretrieve(zip_url, temp_zip)
        with zipfile.ZipFile(temp_zip, 'r') as zf:
            zf.extractall(extract_dir)

        extracted_root = None
        for item in os.listdir(extract_dir):
            p = os.path.join(extract_dir, item)
            if os.path.isdir(p) and "flowstudio" in item.lower():
                extracted_root = p
                break
        if not extracted_root:
            extracted_root = extract_dir

        preserve = {".venv", "bin", "models", "workspace"}
        for item in os.listdir(extracted_root):
            if item in preserve:
                continue
            src = os.path.join(extracted_root, item)
            dst = os.path.join(FLOWSTUDIO_DIR, item)
            if os.path.isdir(src):
                if os.path.exists(dst):
                    shutil.rmtree(dst, ignore_errors=True)
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)

        shutil.rmtree(extract_dir, ignore_errors=True)
        if os.path.exists(temp_zip):
            try: os.remove(temp_zip)
            except Exception: pass
        log_msg("ZIP update extraction completed successfully.")
        return True
    except Exception as e:
        log_msg(f"ZIP update extraction error: {e}")
        raise

def handle_update():
    log_msg("handle_update requested")
    py_exe = get_python_exe()
    pyw_exe = get_pythonw_exe()
    tray_py = os.path.join(FLOWSTUDIO_DIR, "tray_app.py")
    cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

    try:
        # Step A: Unlock server and .pyd files
        unlock_and_stop_server()

        # Step B: Update via git or pure-Python ZIP fallback
        method = "none"
        git_dir = os.path.join(FLOWSTUDIO_DIR, ".git")
        git_exe = find_git_exe()

        if os.path.exists(git_dir) and git_exe:
            log_msg(f"Attempting git update using: {git_exe}")
            try:
                env = os.environ.copy()
                git_parent = os.path.dirname(git_exe)
                env["PATH"] = git_parent + os.pathsep + env.get("PATH", "")
                subprocess.run([git_exe, "fetch", "origin", "main"], cwd=FLOWSTUDIO_DIR, env=env, check=True, capture_output=True, creationflags=cflags)
                subprocess.run([git_exe, "reset", "--hard", "origin/main"], cwd=FLOWSTUDIO_DIR, env=env, check=True, capture_output=True, creationflags=cflags)
                method = "git"
                log_msg("Git reset --hard origin/main succeeded")
            except Exception as e:
                log_msg(f"Git update failed: {e}. Falling back to ZIP...")
                method = "none"

        if method == "none":
            update_via_zip()
            method = "zip"

        # Step C: Dependencies, Native Host, and Desktop Shortcut
        req_file = os.path.join(FLOWSTUDIO_DIR, "requirements.txt")
        if os.path.exists(req_file):
            try:
                subprocess.run([py_exe, "-m", "pip", "install", "--quiet", "-r", req_file], cwd=FLOWSTUDIO_DIR, capture_output=True, creationflags=cflags)
            except Exception as e:
                log_msg(f"pip install requirements failed: {e}")

        install_host_py = os.path.join(HOST_DIR, "install_native_host.py")
        if os.path.exists(install_host_py):
            try:
                subprocess.run([py_exe, install_host_py], cwd=FLOWSTUDIO_DIR, capture_output=True, creationflags=cflags)
            except Exception as e:
                log_msg(f"install_native_host failed: {e}")

        shortcut_script = os.path.join(FLOWSTUDIO_DIR, "scripts", "create_shortcut.py")
        shortcut_created = False
        if os.path.exists(shortcut_script):
            try:
                res = subprocess.run([py_exe, shortcut_script], cwd=FLOWSTUDIO_DIR, capture_output=True, creationflags=cflags)
                shortcut_created = (res.returncode == 0)
                log_msg("Desktop shortcut recreated successfully during update")
            except Exception as e:
                log_msg(f"create_shortcut failed: {e}")

        # Step D: Read disk version, relaunch server detached and verify live backend version
        disk_ver = "3.9.0"
        v_file = os.path.join(FLOWSTUDIO_DIR, "version.json")
        if os.path.exists(v_file):
            try:
                with open(v_file, "r", encoding="utf-8") as f:
                    disk_ver = str(json.load(f).get("version", disk_ver)).strip().lstrip("v")
            except Exception:
                pass

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
                "shortcut": shortcut_created
            }
        else:
            return {
                "ok": False,
                "status": "error",
                "version": disk_ver,
                "error": f"Updated files to {disk_ver} but server health check failed: {start_res.get('error', 'timeout')}"
            }
    except Exception as e:
        log_msg(f"Fatal error in handle_update: {e}")
        # Always attempt to relaunch server silently so user is never stranded
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
            res = handle_update()
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

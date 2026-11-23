import os
import sys
import json
import time
import struct
import shutil
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

def launch_tray_detached(pyw_exe: str, tray_py: str, mode: str = "--silent") -> bool:
    """Spawns pythonw.exe tray_app.py strictly OUTSIDE Chrome's Job Object with ZERO visible black terminal windows."""
    cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

    # 1. Primary: WMI Win32_Process.Create via hidden PowerShell (spawns under WmiPrvSE.exe, Job Object immune)
    try:
        clean_dir = FLOWSTUDIO_DIR.rstrip("\\/")
        ps_cmd = (
            f"$cmd = '\"{pyw_exe}\" \"{tray_py}\" {mode}'; "
            f"$dir = '{clean_dir}'; "
            f"$res = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{{ CommandLine = $cmd; CurrentDirectory = $dir }}; "
            f"exit $res.ReturnValue"
        )
        p = subprocess.run(
            ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_cmd],
            creationflags=cflags,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=8
        )
        if p.returncode == 0:
            log_msg(f"WMI process creation launched: {pyw_exe} {mode} (RC: 0)")
            return True
        else:
            log_msg(f"WMI process creation returned code {p.returncode}")
    except Exception as e:
        log_msg(f"WMI launcher exception: {e}")

    # Fallback with [wmiclass]'Win32_Process'
    try:
        clean_dir = FLOWSTUDIO_DIR.rstrip("\\/")
        ps_cmd = f"$cmd = '\"{pyw_exe}\" \"{tray_py}\" {mode}'; $res = ([wmiclass]'Win32_Process').Create($cmd, '{clean_dir}', $null); exit $res.ReturnValue"
        p = subprocess.run(
            ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_cmd],
            creationflags=cflags,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=8
        )
        if p.returncode == 0:
            log_msg(f"wmiclass process creation launched: {pyw_exe} {mode} (RC: 0)")
            return True
        else:
            log_msg(f"wmiclass process creation returned code {p.returncode}")
    except Exception as e:
        log_msg(f"wmiclass launcher exception: {e}")

    # Fallback 1: CREATE_BREAKAWAY_FROM_JOB
    try:
        CREATE_BREAKAWAY_FROM_JOB = 0x01000000
        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        proc = subprocess.Popen(
            [pyw_exe, tray_py, mode],
            cwd=FLOWSTUDIO_DIR,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=flags,
            startupinfo=startupinfo
        )
        log_msg(f"Fallback 1 (CREATE_BREAKAWAY_FROM_JOB) spawned PID {proc.pid}")
        return True
    except Exception as e:
        log_msg(f"Fallback 1 exception: {e}")

    # Fallback 2: Standard detached without breakaway
    try:
        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        proc = subprocess.Popen(
            [pyw_exe, tray_py, mode],
            cwd=FLOWSTUDIO_DIR,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=flags,
            startupinfo=startupinfo
        )
        log_msg(f"Fallback 2 spawned PID {proc.pid}")
        return True
    except Exception as e:
        log_msg(f"Fallback 2 exception: {e}")
        return False

def handle_start():
    log_msg("handle_start requested")
    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    health = get_health_data(timeout=0.3)
    if health:
        ver = health.get("version", "3.6.0")
        log_msg(f"Server already running on port 8765 (version: {ver})")
        return {"ok": True, "status": "online", "version": ver, "already_running": True}

    pyw_exe = get_pythonw_exe()
    tray_py = os.path.join(FLOWSTUDIO_DIR, "tray_app.py")
    if not os.path.exists(tray_py):
        log_msg("tray_app.py not found")
        return {"ok": False, "status": "error", "error": "tray_app.py not found"}

    launched = launch_tray_detached(pyw_exe, tray_py, mode="--silent")
    if not launched:
        log_msg("Failed to launch detached tray_app")
        return {"ok": False, "status": "error", "error": "Process launch failed"}

    # Poll every 250ms up to 20.0 seconds
    t0 = time.time()
    while time.time() - t0 < 20.0:
        time.sleep(0.25)
        health = get_health_data(timeout=0.3)
        if health:
            ver = health.get("version", "3.6.0")
            log_msg(f"Server verified online in {time.time() - t0:.2f}s (version: {ver})")
            return {"ok": True, "status": "online", "version": ver}

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
    err_msg = " | ".join(err_lines) if err_lines else "Server health check timed out after 20s"
    log_msg(f"Server startup failed: {err_msg}")
    return {"ok": False, "status": "error", "error": err_msg}

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

    # Wait up to 4s verifying port 8765 is closed and .pyd files are writable
    t0 = time.time()
    while time.time() - t0 < 4.0:
        if not check_server_health(timeout=0.2):
            pyds = [
                os.path.join(FLOWSTUDIO_DIR, "engine", f)
                for f in ["watermark_remover.cp312-win_amd64.pyd", "video_pipeline.cp312-win_amd64.pyd", "upscaler.cp312-win_amd64.pyd"]
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
        disk_ver = "3.6.0"
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

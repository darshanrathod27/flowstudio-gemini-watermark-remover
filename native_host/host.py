import os
import sys
import json
import time
import struct
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

def check_server_health(timeout: float = 0.5) -> bool:
    try:
        req = urllib.request.Request(HEALTH_URL, headers={"User-Agent": "FlowStudio-NativeHost"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False

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

def handle_start():
    log_msg("handle_start requested")
    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    if check_server_health(timeout=0.3):
        pid = None
        if os.path.exists(PID_FILE):
            try:
                with open(PID_FILE, "r", encoding="utf-8") as f:
                    pid = int(f.read().strip())
            except Exception:
                pass
        log_msg(f"Server already running on port 8765 (PID: {pid})")
        return {"ok": True, "status": "running", "pid": pid, "already_running": True}

    py_exe = get_python_exe()
    pyw_exe = get_pythonw_exe()
    flags = 0
    if sys.platform == "win32":
        # Critical: Completely detach process so it outlives host.py and does not hold pipes
        flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

    tray_py = os.path.join(FLOWSTUDIO_DIR, "tray_app.py")
    if os.path.exists(tray_py):
        cmd = [pyw_exe, tray_py]
        log_msg(f"Spawning tray_app: {' '.join(cmd)}")
    else:
        cmd = [py_exe, "-m", "uvicorn", "server.app:app", "--host", "127.0.0.1", "--port", "8765"]
        log_msg(f"Spawning uvicorn fallback: {' '.join(cmd)}")

    try:
        os.makedirs(WORKSPACE_DIR, exist_ok=True)
        log_out = open(SERVER_LOG, "ab")
        proc = subprocess.Popen(
            cmd,
            cwd=FLOWSTUDIO_DIR,
            stdin=subprocess.DEVNULL,
            stdout=log_out,
            stderr=subprocess.STDOUT,
            close_fds=True,
            creationflags=flags
        )
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(proc.pid))
        log_msg(f"Spawned uvicorn with PID {proc.pid}. Polling health...")

        # Poll every 250ms for up to 25 seconds (allows cold CUDA driver & Defender initialization)
        start_t = time.time()
        while time.time() - start_t < 25.0:
            time.sleep(0.25)
            if check_server_health(timeout=0.3):
                log_msg(f"Server is healthy at 127.0.0.1:8765 after {time.time() - start_t:.2f}s")
                return {"ok": True, "status": "running", "pid": proc.pid}

        log_msg("Server health check timed out after 25s")
        # Read last 3 lines of workspace/server.log
        last_error = ""
        if os.path.exists(SERVER_LOG):
            try:
                with open(SERVER_LOG, "r", encoding="utf-8", errors="replace") as f:
                    lines = [line.strip() for line in f if line.strip()]
                    if lines:
                        last_error = " | ".join(lines[-3:])
            except Exception as e:
                last_error = f"Log read error: {e}"

        err_detail = last_error if last_error else "Server failed to start within 25s timeout"
        return {"ok": False, "status": "error", "error": err_detail, "pid": proc.pid}
    except Exception as e:
        log_msg(f"Error spawning server: {e}")
        return {"ok": False, "status": "error", "error": str(e)}

def handle_stop():
    log_msg("handle_stop requested")
    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    # 1. Graceful shutdown API
    try:
        req = urllib.request.Request(SHUTDOWN_URL, data=b"{}", headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=1.0)
    except Exception:
        pass

    # Wait up to 1.5s for graceful shutdown
    t0 = time.time()
    while time.time() - t0 < 1.5:
        if not check_server_health(timeout=0.2):
            break
        time.sleep(0.2)

    # 2. Fallback kill via PID
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r", encoding="utf-8") as f:
                pid_str = f.read().strip()
            if pid_str:
                log_msg(f"Terminating PID tree: {pid_str}")
                subprocess.run(["taskkill", "/F", "/PID", pid_str, "/T"], capture_output=True)
        except Exception as e:
            log_msg(f"Error killing PID from file: {e}")
        try:
            os.remove(PID_FILE)
        except Exception:
            pass

    # 3. Clean any process still on port 8765
    try:
        res = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
        for line in res.stdout.splitlines():
            if ":8765 " in line and "LISTENING" in line:
                p = line.strip().split()[-1]
                log_msg(f"Killing remaining listener PID {p} on port 8765")
                subprocess.run(["taskkill", "/F", "/PID", p, "/T"], capture_output=True)
    except Exception as e:
        log_msg(f"Error during netstat port cleanup: {e}")

    log_msg("Server stopped")
    return {"ok": True, "status": "stopped"}

def handle_update():
    log_msg("handle_update requested")
    # 1. Stop running server cleanly
    handle_stop()

    # 2. Update files in FLOWSTUDIO_DIR
    git_dir = os.path.join(FLOWSTUDIO_DIR, ".git")
    if os.path.exists(git_dir):
        log_msg("Updating via git fetch and reset --hard origin/main")
        env = os.environ.copy()
        git_paths = [
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Git", "cmd"),
            r"C:\Program Files\Git\cmd"
        ]
        env["PATH"] = os.pathsep.join(git_paths) + os.pathsep + env.get("PATH", "")
        try:
            subprocess.run(["git", "fetch", "origin", "main"], cwd=FLOWSTUDIO_DIR, env=env, check=True, capture_output=True)
            subprocess.run(["git", "reset", "--hard", "origin/main"], cwd=FLOWSTUDIO_DIR, env=env, check=True, capture_output=True)
        except Exception as e:
            log_msg(f"Git update failed: {e}")
            return {"ok": False, "status": "error", "error": f"Git update failed: {e}"}
    else:
        log_msg("Updating via GitHub ZIP download")
        zip_url = "https://github.com/darshanrathod27/flowstudio-gemini-watermark-remover/archive/refs/heads/main.zip"
        temp_zip = os.path.join(FLOWSTUDIO_DIR, "workspace", "update.zip")
        extract_dir = os.path.join(FLOWSTUDIO_DIR, "workspace", "fs_update_extract")
        try:
            import zipfile
            import shutil
            urllib.request.urlretrieve(zip_url, temp_zip)
            with zipfile.ZipFile(temp_zip, 'r') as zf:
                zf.extractall(extract_dir)

            extracted_root = os.path.join(extract_dir, "flowstudio-gemini-watermark-remover-main")
            preserve = {".venv", "bin", "models", "workspace"}
            for item in os.listdir(extracted_root):
                if item in preserve:
                    continue
                s = os.path.join(extracted_root, item)
                d = os.path.join(FLOWSTUDIO_DIR, item)
                if os.path.isdir(s):
                    if os.path.exists(d):
                        shutil.rmtree(d, ignore_errors=True)
                    shutil.copytree(s, d)
                else:
                    shutil.copy2(s, d)

            shutil.rmtree(extract_dir, ignore_errors=True)
            if os.path.exists(temp_zip):
                os.remove(temp_zip)
        except Exception as e:
            log_msg(f"ZIP update failed: {e}")
            return {"ok": False, "status": "error", "error": f"ZIP update failed: {e}"}

    # 3. Refresh pip requirements and re-run native host installer
    py_exe = get_python_exe()
    req_file = os.path.join(FLOWSTUDIO_DIR, "requirements.txt")
    if os.path.exists(req_file):
        try:
            subprocess.run([py_exe, "-m", "pip", "install", "--quiet", "-r", req_file], cwd=FLOWSTUDIO_DIR, check=True, capture_output=True)
        except Exception as e:
            log_msg(f"pip install requirements failed: {e}")

    install_host_py = os.path.join(HOST_DIR, "install_native_host.py")
    if os.path.exists(install_host_py):
        try:
            subprocess.run([py_exe, install_host_py], cwd=FLOWSTUDIO_DIR, check=True, capture_output=True)
        except Exception as e:
            log_msg(f"install_native_host failed: {e}")

    # 4. Read new version from version.json
    new_ver = "3.1.0"
    v_file = os.path.join(FLOWSTUDIO_DIR, "version.json")
    if os.path.exists(v_file):
        try:
            with open(v_file, "r", encoding="utf-8") as f:
                v_data = json.load(f)
                new_ver = v_data.get("version", new_ver)
        except Exception:
            pass

    # 5. Restart server detached & wait up to 25s for /api/health
    start_res = handle_start()
    if start_res.get("ok"):
        return {"ok": True, "status": "updated", "version": new_ver}
    else:
        return {"ok": False, "status": "error", "error": f"Updated to {new_ver} but server restart failed: {start_res.get('error', 'timeout')}"}

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
            alive = check_server_health(timeout=0.3)
            pid = None
            if os.path.exists(PID_FILE):
                try:
                    with open(PID_FILE, "r", encoding="utf-8") as f:
                        pid = int(f.read().strip())
                except Exception:
                    pass
            send_message({"ok": True, "status": "running" if alive else "stopped", "pid": pid, "port": 8765})
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

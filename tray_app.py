import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.join(BASE_DIR, "workspace")
os.makedirs(WORKSPACE_DIR, exist_ok=True)

PID_FILE = os.path.join(WORKSPACE_DIR, "server.pid")
SERVER_LOG = os.path.join(WORKSPACE_DIR, "server.log")
TRAY_LOG = os.path.join(WORKSPACE_DIR, "tray.log")

# Redirect sys.stdout & sys.stderr at the VERY TOP before importing pystray, PIL, or uvicorn
try:
    if "--run-server" in sys.argv:
        _log_target = open(SERVER_LOG, "a", encoding="utf-8", buffering=1)
    else:
        _log_target = open(TRAY_LOG, "a", encoding="utf-8", buffering=1)
    sys.stdout = _log_target
    sys.stderr = _log_target
except Exception:
    pass

import time
import json
import socket
import ctypes
import urllib.request
import webbrowser
import subprocess
import threading

HEALTH_URL = "http://127.0.0.1:8765/api/health"
SHUTDOWN_URL = "http://127.0.0.1:8765/api/system/shutdown"
STUDIO_URL = "http://127.0.0.1:8765"
RELEASES_URL = "https://github.com/darshanrathod27/flowstudio-gemini-watermark-remover/releases"

server_proc = None

def get_pythonw_exe() -> str:
    venv_pyw = os.path.join(BASE_DIR, ".venv", "Scripts", "pythonw.exe")
    if os.path.exists(venv_pyw):
        return venv_pyw
    exe_dir_pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if os.path.exists(exe_dir_pyw):
        return exe_dir_pyw
    return sys.executable

def is_port_listening(port: int = 8765, timeout: float = 0.08) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False

def check_server_health(timeout: float = 0.4) -> bool:
    if not is_port_listening(8765, timeout=min(0.08, timeout)):
        return False
    try:
        req = urllib.request.Request(HEALTH_URL, headers={"User-Agent": "FlowStudio-Tray"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False

def get_gpu_status_text() -> str:
    try:
        req = urllib.request.Request(HEALTH_URL, headers={"User-Agent": "FlowStudio-Tray"})
        with urllib.request.urlopen(req, timeout=0.6) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("cuda_available"):
                    name = data.get("gpu_name", "NVIDIA GPU")
                    short = name.replace("NVIDIA ", "").replace("GeForce ", "").replace("Laptop GPU", "").strip()
                    vram = data.get("vram_gb", "")
                    vram_str = f" {vram}GB" if vram else ""
                    return f"Status: Running ({short}{vram_str})"
                return "Status: Running (CPU Mode)"
    except Exception:
        pass
    return "Status: Engine Starting..."

def run_server_mode():
    """Runs uvicorn directly inside pythonw.exe with stdout/stderr redirected to workspace/server.log."""
    with open(PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))

    try:
        import uvicorn
        uvicorn.run("server.app:app", host="127.0.0.1", port=8765, log_config=None, access_log=False)
    finally:
        if os.path.exists(PID_FILE):
            try:
                os.remove(PID_FILE)
            except Exception:
                pass

def start_backend(skip_health_check: bool = False):
    """Spawns hidden pythonw.exe tray_app.py --run-server with zero black console window."""
    global server_proc
    if not skip_health_check and check_server_health(timeout=0.3):
        return

    pyw = get_pythonw_exe()
    tray_py = os.path.join(BASE_DIR, "tray_app.py")
    cmd = [pyw, tray_py, "--run-server"]

    flags = 0
    startupinfo = None
    if sys.platform == "win32":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0

    log_out = open(SERVER_LOG, "a", encoding="utf-8")
    server_proc = subprocess.Popen(
        cmd,
        cwd=BASE_DIR,
        stdin=subprocess.DEVNULL,
        stdout=log_out,
        stderr=subprocess.STDOUT,
        close_fds=True,
        creationflags=flags,
        startupinfo=startupinfo
    )
    log_out.close()
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Spawned --run-server PID {server_proc.pid} ({pyw})")

def stop_backend():
    global server_proc
    try:
        req = urllib.request.Request(SHUTDOWN_URL, data=b"{}", headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=1.0)
    except Exception:
        pass

    if server_proc:
        try:
            server_proc.terminate()
        except Exception:
            pass

    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r", encoding="utf-8") as f:
                pid = int(f.read().strip())
            cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, creationflags=cflags)
            os.remove(PID_FILE)
        except Exception:
            pass

def restart_backend(icon=None, item=None):
    stop_backend()
    time.sleep(1.0)
    start_backend()

def open_studio(icon=None, item=None):
    if not check_server_health(timeout=0.3):
        start_backend()
        for _ in range(30):
            if check_server_health(0.3):
                break
            time.sleep(0.3)
    webbrowser.open(STUDIO_URL)

def check_updates(icon=None, item=None):
    webbrowser.open(RELEASES_URL)

def open_uninstall(icon=None, item=None):
    if not check_server_health(timeout=0.3):
        start_backend()
        for _ in range(30):
            if check_server_health(0.3):
                break
            time.sleep(0.3)
    webbrowser.open(f"{STUDIO_URL}/?uninstall=1")

def quit_app(icon=None, item=None):
    stop_backend()
    if icon:
        icon.stop()
    sys.exit(0)

def load_icon_image():
    from PIL import Image
    ico_path = os.path.join(BASE_DIR, "assets", "flowstudio.ico")
    if not os.path.exists(ico_path):
        from scripts.create_shortcut import ensure_ico_exists
        ico_path = ensure_ico_exists(BASE_DIR)

    if os.path.exists(ico_path):
        try:
            return Image.open(ico_path)
        except Exception:
            pass

    from PIL import ImageDraw
    img = Image.new("RGBA", (64, 64), (31, 111, 235, 255))
    d = ImageDraw.Draw(img)
    d.text((12, 16), "FS", fill=(255, 255, 255, 255))
    return img

def main():
    args = sys.argv[1:]

    # Mode 1: --run-server (binds 127.0.0.1:8765 immediately before any heavy background imports)
    if "--run-server" in args:
        run_server_mode()
        sys.exit(0)

    want_open = "--open" in args
    server_alive = check_server_health(timeout=0.4)

    # If --open and server is already healthy, just open browser and exit
    if want_open and server_alive:
        webbrowser.open(STUDIO_URL)
        sys.exit(0)

    # If server port 8765 is dead, spawn --run-server IMMEDIATELY and verify port is alive BEFORE acquiring mutex!
    # Prevents a prior dead/hung tray holding the mutex from silently aborting server startup.
    if not server_alive:
        start_backend(skip_health_check=True)
        t_wait = time.time()
        while time.time() - t_wait < 8.0:
            if check_server_health(timeout=0.3):
                server_alive = True
                break
            time.sleep(0.10)

    # Acquire mutex ONLY after verifying port 8765 is actually alive (or backend spawn attempted)
    if sys.platform == "win32":
        kernel32 = ctypes.windll.kernel32
        mutex = kernel32.CreateMutexW(None, False, "FlowStudio_SystemTray_Mutex_v360")
        if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            if want_open:
                if not server_alive:
                    for _ in range(25):
                        if check_server_health(0.25):
                            break
                        time.sleep(0.2)
                webbrowser.open(STUDIO_URL)
            sys.exit(0)

    # If --open was requested, open browser once ready
    if want_open:
        if server_alive:
            webbrowser.open(STUDIO_URL)
        else:
            def open_when_ready():
                for _ in range(30):
                    if check_server_health(0.25):
                        webbrowser.open(STUDIO_URL)
                        return
                    time.sleep(0.2)
                webbrowser.open(STUDIO_URL)
            threading.Thread(target=open_when_ready, daemon=True).start()

    # Setup pystray tray icon (Silent mode: NEVER auto-opens browser tab!)
    import pystray
    from pystray import MenuItem as item, Menu

    image = load_icon_image()

    def get_status_label(item_obj):
        return get_gpu_status_text()

    menu = Menu(
        item("Open FlowStudio (Batch & Personal Upscaler)", open_studio, default=True),
        item(get_status_label, None, enabled=False),
        Menu.SEPARATOR,
        item("Check for Updates", check_updates),
        item("Restart Engine", restart_backend),
        item("Uninstall FlowStudio...", open_uninstall),
        Menu.SEPARATOR,
        item("Quit FlowStudio", quit_app)
    )

    icon = pystray.Icon("FlowStudio", image, "FlowStudio Pro", menu)
    icon.run()

if __name__ == "__main__":
    main()

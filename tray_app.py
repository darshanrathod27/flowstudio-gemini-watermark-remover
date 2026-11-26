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
    return sys.executable

def check_server_health(timeout: float = 0.4) -> bool:
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

def start_backend():
    """Spawns hidden pythonw.exe tray_app.py --run-server with zero black console window."""
    global server_proc
    if check_server_health(timeout=0.3):
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

    # Mode 1: --run-server (internal worker spawned under pythonw.exe)
    if "--run-server" in args:
        run_server_mode()
        sys.exit(0)

    want_open = "--open" in args

    # If --open and server is already healthy, just open browser and exit
    if want_open and check_server_health(timeout=0.4):
        webbrowser.open(STUDIO_URL)
        sys.exit(0)

    # Windows Mutex single-instance lock for system tray:
    # ONLY exit early if BOTH mutex is already held AND server is healthy!
    if sys.platform == "win32":
        kernel32 = ctypes.windll.kernel32
        mutex = kernel32.CreateMutexW(None, False, "FlowStudio_SystemTray_Mutex_v360")
        if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            if check_server_health(timeout=0.4):
                if want_open:
                    webbrowser.open(STUDIO_URL)
                sys.exit(0)

    # Spawn --run-server child IMMEDIATELY before initializing tray loop so /api/health responds in < 2.5s
    if not check_server_health(timeout=0.3):
        start_backend()

    # If --open was requested, wait for server to become healthy before opening browser
    if want_open:
        def open_when_ready():
            for _ in range(40):
                if check_server_health(0.3):
                    webbrowser.open(STUDIO_URL)
                    return
                time.sleep(0.3)
            # Fallback open anyway
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
        Menu.SEPARATOR,
        item("Quit FlowStudio", quit_app)
    )

    icon = pystray.Icon("FlowStudio", image, "FlowStudio Pro", menu)
    icon.run()

if __name__ == "__main__":
    main()

import os
import sys
import time
import json
import ctypes
import urllib.request
import webbrowser
import subprocess
import threading
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.join(BASE_DIR, "workspace")
os.makedirs(WORKSPACE_DIR, exist_ok=True)

PID_FILE = os.path.join(WORKSPACE_DIR, "server.pid")
SERVER_LOG = os.path.join(WORKSPACE_DIR, "server.log")
HEALTH_URL = "http://127.0.0.1:8765/api/health"
SHUTDOWN_URL = "http://127.0.0.1:8765/api/system/shutdown"
STUDIO_URL = "http://127.0.0.1:8765"
RELEASES_URL = "https://github.com/darshanrathod27/flowstudio-gemini-watermark-remover/releases"

server_proc = None

def check_server_health(timeout: float = 0.6) -> bool:
    try:
        req = urllib.request.Request(HEALTH_URL, headers={"User-Agent": "FlowStudio-Tray"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False

def get_gpu_status_text() -> str:
    try:
        req = urllib.request.Request(HEALTH_URL, headers={"User-Agent": "FlowStudio-Tray"})
        with urllib.request.urlopen(req, timeout=0.8) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("cuda_available"):
                    name = data.get("gpu_name", "NVIDIA GPU")
                    short = name.replace("NVIDIA ", "").replace("GeForce ", "").replace("Laptop GPU", "").strip()
                    return f"Status: Running ({short})"
                return "Status: Running (CPU Mode)"
    except Exception:
        pass
    return "Status: Engine Starting..."

def start_backend():
    global server_proc
    if check_server_health(timeout=0.4):
        return

    venv_py = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
    py_exe = venv_py if os.path.exists(venv_py) else sys.executable

    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

    cmd = [py_exe, "-m", "uvicorn", "server.app:app", "--host", "127.0.0.1", "--port", "8765"]
    log_out = open(SERVER_LOG, "ab")
    server_proc = subprocess.Popen(
        cmd,
        cwd=BASE_DIR,
        stdin=subprocess.DEVNULL,
        stdout=log_out,
        stderr=subprocess.STDOUT,
        close_fds=True,
        creationflags=flags
    )

    with open(PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(server_proc.pid))

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
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
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
    webbrowser.open(STUDIO_URL)

def check_updates(icon=None, item=None):
    webbrowser.open(RELEASES_URL)

def quit_app(icon=None, item=None):
    stop_backend()
    if icon:
        icon.stop()
    sys.exit(0)

def load_icon_image():
    ico_path = os.path.join(BASE_DIR, "assets", "flowstudio.ico")
    if not os.path.exists(ico_path):
        from scripts.create_shortcut import ensure_ico_exists
        ico_path = ensure_ico_exists(BASE_DIR)

    if os.path.exists(ico_path):
        try:
            return Image.open(ico_path)
        except Exception:
            pass

    # Fallback in-memory image
    from PIL import ImageDraw
    img = Image.new("RGBA", (64, 64), (31, 111, 235, 255))
    d = ImageDraw.Draw(img)
    d.text((12, 16), "FS", fill=(255, 255, 255, 255))
    return img

def main():
    # 1. Single-Instance Check
    # If server is already healthy, open browser and exit
    if check_server_health(timeout=0.4):
        webbrowser.open(STUDIO_URL)
        sys.exit(0)

    # Windows Mutex single-instance lock
    if sys.platform == "win32":
        kernel32 = ctypes.windll.kernel32
        mutex = kernel32.CreateMutexW(None, False, "FlowStudio_SystemTray_Mutex_v330")
        if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            webbrowser.open(STUDIO_URL)
            sys.exit(0)

    # 2. Start server in background
    start_backend()

    # 3. Setup pystray tray icon
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

    # Automatically open Studio upon initial launch once healthy
    def initial_launch():
        for _ in range(30):
            if check_server_health(0.5):
                webbrowser.open(STUDIO_URL)
                break
            time.sleep(0.5)

    threading.Thread(target=initial_launch, daemon=True).start()

    icon.run()

if __name__ == "__main__":
    main()

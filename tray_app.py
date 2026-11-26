import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.join(BASE_DIR, "workspace")
os.makedirs(WORKSPACE_DIR, exist_ok=True)

PID_FILE = os.path.join(WORKSPACE_DIR, "server.pid")
SERVER_LOG = os.path.join(WORKSPACE_DIR, "server.log")
if sys.platform == "darwin":
    _LOGS_DIR = os.path.join(WORKSPACE_DIR, "logs")
    os.makedirs(_LOGS_DIR, exist_ok=True)
    TRAY_LOG = os.path.join(_LOGS_DIR, "tray.log")
else:
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
import signal
import socket
import ctypes
import tempfile
import traceback
import urllib.request
import webbrowser
import subprocess
import threading

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
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

HEALTH_URL = "http://127.0.0.1:8765/api/health"
SHUTDOWN_URL = "http://127.0.0.1:8765/api/system/shutdown"
STUDIO_URL = "http://127.0.0.1:8765"
RELEASES_URL = "https://github.com/darshanrathod27/flowstudio-gemini-watermark-remover/releases"

server_proc = None
_TRAY_LOCK_HANDLE = None


def get_pythonw_exe() -> str:
    if sys.platform == "darwin":
        for candidate in (
            os.path.join(BASE_DIR, ".venv", "bin", "python"),
            os.path.join(BASE_DIR, ".venv", "bin", "python3"),
        ):
            if os.path.exists(candidate):
                return candidate
        return sys.executable

    venv_pyw = os.path.join(BASE_DIR, ".venv", "Scripts", "pythonw.exe")
    if os.path.exists(venv_pyw):
        return venv_pyw
    exe_dir_pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if os.path.exists(exe_dir_pyw):
        return exe_dir_pyw
    return sys.executable


def acquire_darwin_lock() -> bool:
    """Acquires an exclusive non-blocking POSIX flock for single-instance macOS tray."""
    global _TRAY_LOCK_HANDLE
    import fcntl

    lock_path = os.path.join(tempfile.gettempdir(), "flowstudio_tray.lock")
    fh = open(lock_path, "a+", encoding="utf-8")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fh.seek(0)
        fh.truncate()
        fh.write(str(os.getpid()))
        fh.flush()
        _TRAY_LOCK_HANDLE = fh
        return True
    except (BlockingIOError, OSError):
        try:
            fh.close()
        except Exception:
            pass
        return False


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
        if not is_port_listening(8765, timeout=0.06):
            return "Status: Standby (Sleeping)"
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
                if data.get("mps_available"):
                    name = data.get("gpu_name", "Apple Silicon")
                    vram = data.get("vram_gb", "")
                    vram_str = f" {vram}GB" if vram else ""
                    return f"Status: Running ({name}{vram_str} MPS)"
                return "Status: Running (CPU Mode)"
    except Exception:
        pass
    return "Status: Engine Starting..."


def _is_dev_workspace(path_dir: str = BASE_DIR) -> bool:
    abs_base = os.path.abspath(path_dir or "").rstrip("\\/")
    parent_dir = os.path.dirname(abs_base)
    return (
        "PRIVATE_SOURCE" in abs_base.upper()
        or (bool(parent_dir) and os.path.isdir(os.path.join(parent_dir, "FlowStudio_PRIVATE_SOURCE")))
        or os.path.isdir(os.path.join(abs_base, "cloud_backend"))
        or os.path.isdir(os.path.join(abs_base, "assets", "masks"))
        or os.path.isfile(os.path.join(abs_base, "build_scripts", "build_protected_release.py"))
    )


def _cleanup_unresponsive_port_listener():
    """If port 8765 is open yet /api/health fails, stop any stale same-install FlowStudio server."""
    if not is_port_listening(8765, timeout=0.08):
        return
    if check_server_health(timeout=0.7):
        return

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Port 8765 open but unresponsive; cleaning stale same-install listener...")
    stop_backend()
    if sys.platform == "win32":
        try:
            abs_esc = os.path.abspath(BASE_DIR).rstrip("\\/").replace("'", "''")
            ps_cmd = (
                "$conn = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; "
                "if ($conn -and $conn.OwningProcess) { "
                "$p = Get-CimInstance Win32_Process -Filter \"ProcessId = $($conn.OwningProcess)\" -ErrorAction SilentlyContinue; "
                f"$t = '{abs_esc}'; "
                "if ($p -and (($p.CommandLine -like \"*$t*\") -or ($p.ExecutablePath -like \"*$t*\"))) { Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue } "
                "}"
            )
            subprocess.run(
                ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", ps_cmd],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
                **get_subprocess_kwargs(),
            )
        except Exception:
            pass
    deadline = time.time() + 2.5
    while time.time() < deadline:
        if not is_port_listening(8765, timeout=0.08):
            break
        time.sleep(0.1)


def run_server_mode():
    """Runs uvicorn directly inside pythonw.exe / .venv/bin/python with stdout/stderr redirected to workspace/server.log."""
    if check_server_health(timeout=0.3):
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Healthy FlowStudio server already active on 127.0.0.1:8765; skipping duplicate bind.")
        return

    _cleanup_unresponsive_port_listener()
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
    """Spawns hidden pythonw.exe (Windows) or detached .venv/bin/python (macOS) tray_app.py --run-server."""
    global server_proc
    if not skip_health_check and check_server_health(timeout=0.3):
        return

    pyw = get_pythonw_exe()
    tray_py = os.path.join(BASE_DIR, "tray_app.py")
    cmd = [pyw, tray_py, "--run-server"]

    if sys.platform == "win32":
        new_pg = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        proc_kwargs = get_subprocess_kwargs(extra_flags=new_pg, hide_window=True)
    else:
        proc_kwargs = {"start_new_session": True}

    log_out = open(SERVER_LOG, "a", encoding="utf-8")
    server_proc = subprocess.Popen(
        cmd,
        cwd=BASE_DIR,
        stdin=subprocess.DEVNULL,
        stdout=log_out,
        stderr=subprocess.STDOUT,
        close_fds=True,
        **proc_kwargs,
    )
    log_out.close()
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Spawned --run-server PID {server_proc.pid} ({pyw})")


def _terminate_pid_posix(pid: int):
    """Gracefully terminates a POSIX process via SIGTERM -> wait -> SIGKILL."""
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except Exception:
        return

    deadline = time.time() + 3.0
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
            time.sleep(0.1)
        except ProcessLookupError:
            return
        except Exception:
            break

    try:
        os.kill(pid, signal.SIGKILL)
    except Exception:
        pass


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
            if sys.platform == "darwin":
                try:
                    server_proc.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    server_proc.kill()
        except Exception:
            pass

    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r", encoding="utf-8") as f:
                pid = int(f.read().strip())
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, **get_subprocess_kwargs())
            else:
                _terminate_pid_posix(pid)
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


def open_outputs_folder(icon=None, item=None):
    outputs_dir = os.path.join(WORKSPACE_DIR, "outputs")
    os.makedirs(outputs_dir, exist_ok=True)
    if sys.platform == "darwin":
        subprocess.Popen(["open", outputs_dir])
    elif sys.platform == "win32":
        os.startfile(outputs_dir)
    else:
        subprocess.Popen(["xdg-open", outputs_dir])


def _boot_self_heal_native_host():
    """Silently verifies and self-heals Chrome Native Messaging Host (<50ms on normal installs)."""
    try:
        from native_host.register_host import ensure_native_host_registered
        ensure_native_host_registered(install_root=BASE_DIR, quiet=True)
    except Exception:
        pass


def check_updates(icon=None, item=None):
    """Triggers HTTP-first / detached self-update + native host repair (fallback: releases URL)."""
    def _do_update():
        try:
            abs_base = os.path.abspath(BASE_DIR).rstrip("\\/")
            if _is_dev_workspace(abs_base) or not os.path.isdir(os.path.join(abs_base, ".venv")):
                webbrowser.open(RELEASES_URL)
                return

            if check_server_health(timeout=0.5):
                try:
                    req = urllib.request.Request(
                        f"{STUDIO_URL}/api/system/update",
                        data=b"{}",
                        headers={"Content-Type": "application/json", "User-Agent": "FlowStudio-Tray"},
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=3.0) as resp:
                        if resp.status == 200:
                            return
                except Exception:
                    pass

            if sys.platform == "darwin":
                sh_src = os.path.join(abs_base, "scripts", "self_update.sh")
                if os.path.isfile(sh_src):
                    import shutil
                    import uuid
                    tmp_sh = os.path.join(tempfile.gettempdir(), f"flowstudio_self_update_{uuid.uuid4().hex[:8]}.sh")
                    shutil.copy2(sh_src, tmp_sh)
                    os.chmod(tmp_sh, 0o755)
                    subprocess.Popen(["bash", tmp_sh, abs_base, "main"], cwd=tempfile.gettempdir(), start_new_session=True, close_fds=True)
                    return
            else:
                ps_src = os.path.join(abs_base, "scripts", "self_update.ps1")
                if os.path.isfile(ps_src):
                    import shutil
                    import uuid
                    tmp_ps1 = os.path.join(tempfile.gettempdir(), f"flowstudio_self_update_{uuid.uuid4().hex[:8]}.ps1")
                    shutil.copy2(ps_src, tmp_ps1)
                    new_pg = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
                    subprocess.Popen(
                        [
                            "powershell.exe",
                            "-NoProfile",
                            "-NonInteractive",
                            "-ExecutionPolicy", "Bypass",
                            "-WindowStyle", "Hidden",
                            "-File", tmp_ps1,
                            "-InstallDir", abs_base,
                        ],
                        cwd=tempfile.gettempdir(),
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        close_fds=True,
                        **get_subprocess_kwargs(extra_flags=new_pg, hide_window=True),
                    )
                    return
            webbrowser.open(RELEASES_URL)
        except Exception:
            webbrowser.open(RELEASES_URL)

    threading.Thread(target=_do_update, daemon=True).start()


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

    if sys.platform == "darwin":
        candidates = [
            os.path.join(BASE_DIR, "extension", "icons", "icon128.png"),
            os.path.join(BASE_DIR, "extension", "icons", "icon48.png"),
            os.path.join(BASE_DIR, "assets", "flowstudio.ico"),
        ]
        for path in candidates:
            if os.path.exists(path):
                try:
                    img = Image.open(path).convert("RGBA")
                    resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.BICUBIC)
                    if img.size != (64, 64):
                        img = img.resize((64, 64), resample=resample)
                    return img
                except Exception:
                    pass
    else:
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


def _run_darwin_tray(want_open: bool):
    """macOS AppKit-safe entry point: runs pystray.Icon.run() strictly on the main thread."""
    if not acquire_darwin_lock():
        if want_open:
            for _ in range(25):
                if check_server_health(0.25):
                    break
                time.sleep(0.2)
            webbrowser.open(STUDIO_URL)
        sys.exit(0)

    def _bg_boot():
        _boot_self_heal_native_host()
        try:
            alive = check_server_health(timeout=0.4)
            if not alive:
                start_backend(skip_health_check=True)
                t_wait = time.time()
                while time.time() - t_wait < 8.0:
                    if check_server_health(timeout=0.3):
                        alive = True
                        break
                    time.sleep(0.15)
            if want_open:
                if not alive:
                    for _ in range(25):
                        if check_server_health(0.25):
                            break
                        time.sleep(0.2)
                webbrowser.open(STUDIO_URL)
        except Exception as e:
            print(f"[Tray] Background startup error: {e}")

    threading.Thread(target=_bg_boot, daemon=True).start()

    try:
        import pystray
        from pystray import MenuItem as item, Menu

        image = load_icon_image()

        def get_status_label(item_obj):
            return get_gpu_status_text()

        menu = Menu(
            item(get_status_label, None, enabled=False),
            Menu.SEPARATOR,
            item("Open Batch Studio", open_studio, default=True),
            item("Start / Wake Server", lambda icon=None, item_obj=None: threading.Thread(target=start_backend, daemon=True).start()),
            item("Sleep Server (Free RAM/GPU)", lambda icon=None, item_obj=None: threading.Thread(target=stop_backend, daemon=True).start()),
            item("Open Outputs Folder", open_outputs_folder),
            Menu.SEPARATOR,
            item("Check for Updates", check_updates),
            item("Restart Engine", lambda icon=None, item_obj=None: threading.Thread(target=restart_backend, daemon=True).start()),
            item("Uninstall FlowStudio...", open_uninstall),
            Menu.SEPARATOR,
            item("Quit FlowStudio", quit_app),
        )

        icon = pystray.Icon("FlowStudio", image, "FlowStudio Pro", menu)
        icon.run()
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [Tray] pystray initialization/run failed: {e}")
        traceback.print_exc()


def main():
    args = sys.argv[1:]

    # Mode 1: --run-server (binds 127.0.0.1:8765 immediately before any heavy background imports)
    if "--run-server" in args:
        run_server_mode()
        sys.exit(0)

    want_open = "--open" in args

    if sys.platform == "darwin":
        _run_darwin_tray(want_open=want_open)
        return

    server_alive = check_server_health(timeout=0.4)

    # If --open and server is already healthy, just open browser and exit
    if want_open and server_alive:
        webbrowser.open(STUDIO_URL)
        sys.exit(0)

    # If server port 8765 is dead or unresponsive, clean any stale listener and spawn --run-server BEFORE acquiring mutex!
    # Prevents a prior dead/hung tray holding the mutex from silently aborting server startup.
    if not server_alive:
        _cleanup_unresponsive_port_listener()
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

    threading.Thread(target=_boot_self_heal_native_host, daemon=True).start()

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

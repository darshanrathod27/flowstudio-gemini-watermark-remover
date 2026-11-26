import os
import sys
import subprocess
from PIL import Image

def get_install_dir():
    # scripts/ -> parent
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_desktop_dir() -> str:
    """
    Dynamically resolves real Windows Desktop folder (OneDrive-safe).
    Handles both standard C:\\Users\\<User>\\Desktop and OneDrive\\Desktop seamlessly.
    """
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    # 1. Query .NET Environment.GetFolderPath('Desktop') via PowerShell
    try:
        cmd = ["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True, creationflags=creationflags)
        out = res.stdout.strip()
        if out and os.path.isdir(out):
            return out
    except Exception:
        pass

    # 2. Check %OneDrive% environment variable
    user_prof = os.environ.get("USERPROFILE", os.path.expanduser("~"))
    onedrive = os.environ.get("OneDrive", "")
    if onedrive and os.path.isdir(os.path.join(onedrive, "Desktop")):
        return os.path.join(onedrive, "Desktop")

    # 3. Check OneDrive subfolder in user profile
    one_desk = os.path.join(user_prof, "OneDrive", "Desktop")
    if os.path.isdir(one_desk):
        return one_desk

    # 4. Standard user profile desktop
    std_desk = os.path.join(user_prof, "Desktop")
    if os.path.isdir(std_desk):
        return std_desk

    return user_prof

def ensure_ico_exists(install_dir: str) -> str:
    assets_dir = os.path.join(install_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)
    ico_path = os.path.join(assets_dir, "flowstudio.ico")

    if os.path.exists(ico_path) and os.path.getsize(ico_path) > 0:
        return ico_path

    # Source PNG candidates
    png_candidates = [
        os.path.join(install_dir, "extension", "icons", "icon128.png"),
        os.path.join(install_dir, "extension", "icons", "icon48.png"),
        os.path.join(install_dir, "extension", "icons", "icon16.png")
    ]

    src_png = None
    for p in png_candidates:
        if os.path.exists(p):
            src_png = p
            break

    if src_png:
        try:
            img = Image.open(src_png).convert("RGBA")
            sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
            img.save(ico_path, format="ICO", sizes=sizes)
            print(f"[FlowStudio] Generated icon: {ico_path}")
            return ico_path
        except Exception as e:
            print(f"[FlowStudio] Icon generation from PNG failed: {e}")

    # Fallback programmatic icon if PNG missing
    try:
        from PIL import ImageDraw
        img = Image.new("RGBA", (256, 256), color=(31, 111, 235, 255))
        draw = ImageDraw.Draw(img)
        draw.text((45, 60), "FS", fill=(255, 255, 255, 255), font_size=120)
        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        img.save(ico_path, format="ICO", sizes=sizes)
        print(f"[FlowStudio] Generated fallback icon: {ico_path}")
        return ico_path
    except Exception as e:
        print(f"[FlowStudio] Fallback icon generation failed: {e}")
        return ico_path

def create_desktop_shortcut(install_dir: str):
    desktop = get_desktop_dir()
    os.makedirs(desktop, exist_ok=True)
    lnk_path = os.path.join(desktop, "FlowStudio.lnk")
    ico_path = ensure_ico_exists(install_dir)

    # Locate pythonw.exe (windowless python)
    venv_pythonw = os.path.join(install_dir, ".venv", "Scripts", "pythonw.exe")
    if not os.path.exists(venv_pythonw):
        cand = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if os.path.exists(cand):
            venv_pythonw = cand
    if not os.path.exists(venv_pythonw):
        venv_pythonw = os.path.join(install_dir, ".venv", "Scripts", "python.exe")
    if not os.path.exists(venv_pythonw):
        venv_pythonw = sys.executable

    tray_app_py = os.path.join(install_dir, "tray_app.py")

    ps_script = f'''
    $wscript = New-Object -ComObject WScript.Shell
    $shortcut = $wscript.CreateShortcut("{lnk_path}")
    $shortcut.TargetPath = "{venv_pythonw}"
    $shortcut.Arguments = "`"{tray_app_py}`" --open"
    $shortcut.WorkingDirectory = "{install_dir}"
    if (Test-Path "{ico_path}") {{
        $shortcut.IconLocation = "{ico_path},0"
    }}
    $shortcut.Description = "FlowStudio - Local AI Watermark Remover & Upscaler"
    $shortcut.Save()
    '''

    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True, text=True, check=True, creationflags=creationflags)
        print(f"[FlowStudio] Desktop shortcut created: {lnk_path}")
        return True, lnk_path
    except Exception as e:
        print(f"[FlowStudio] Error creating Desktop shortcut: {e}")
        return False, lnk_path

if __name__ == "__main__":
    base = get_install_dir()
    create_desktop_shortcut(base)

import os
import tempfile
import subprocess
from typing import Optional
from PIL import Image

try:
    from engine.hardware import get_subprocess_kwargs
except ImportError:
    from .hardware import get_subprocess_kwargs


def _escape_applescript_str(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def copy_image_to_macos_clipboard(image_path: str) -> bool:
    """
    Silently copies an image file to the macOS System Clipboard via native osascript
    in «class PNGf» format. Converts non-PNG images (JPG/WebP) to a temporary PNG
    and cleans up the temp file in a finally block.
    """
    if not image_path or not os.path.exists(image_path):
        return False

    abs_path = os.path.abspath(image_path)
    ext = os.path.splitext(abs_path)[1].lower()
    tmp_png: Optional[str] = None
    target_png = abs_path

    try:
        if ext != ".png":
            fd, tmp_png = tempfile.mkstemp(prefix="fs_clip_", suffix=".png")
            os.close(fd)
            with Image.open(abs_path) as im:
                im.convert("RGBA").save(tmp_png, "PNG")
            target_png = tmp_png

        escaped = _escape_applescript_str(target_png)
        script = f'set the clipboard to (read (POSIX file "{escaped}") as «class PNGf»)'
        res = subprocess.run(
            ["osascript", "-e", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            **get_subprocess_kwargs(),
        )
        return res.returncode == 0
    except Exception as e:
        print(f"[Clipboard] Error copying image to macOS clipboard: {e}")
        return False
    finally:
        if tmp_png and os.path.exists(tmp_png):
            try:
                os.remove(tmp_png)
            except Exception:
                pass


def verify_macos_clipboard_has_image() -> bool:
    """Checks whether the macOS clipboard currently contains image data."""
    try:
        res = subprocess.run(
            ["osascript", "-e", "clipboard info"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=3,
            **get_subprocess_kwargs(),
        )
        if res.returncode != 0:
            return False
        info = (res.stdout or "").lower()
        return any(tok in info for tok in ("pngf", "tiff", "jpeg", "picture"))
    except Exception:
        return False


# Signature parity aliases matching engine/clipboard_win.py
copy_image_to_windows_clipboard = copy_image_to_macos_clipboard
verify_windows_clipboard_has_image = verify_macos_clipboard_has_image

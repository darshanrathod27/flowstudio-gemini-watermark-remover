import sys


def copy_image_to_clipboard(image_path: str) -> bool:
    """
    Cross-platform image clipboard dispatch:
    - win32: native Win32 CF_DIB clipboard (engine/clipboard_win.py)
    - darwin: native osascript PNGf clipboard (engine/clipboard_mac.py)
    - other: logs warning and returns False
    """
    if sys.platform == "win32":
        try:
            from engine.clipboard_win import copy_image_to_windows_clipboard
        except ImportError:
            from .clipboard_win import copy_image_to_windows_clipboard
        return copy_image_to_windows_clipboard(image_path)

    if sys.platform == "darwin":
        try:
            from engine.clipboard_mac import copy_image_to_macos_clipboard
        except ImportError:
            from .clipboard_mac import copy_image_to_macos_clipboard
        return copy_image_to_macos_clipboard(image_path)

    print(f"[Clipboard] Warning: clipboard image copy is not supported on platform '{sys.platform}'.")
    return False

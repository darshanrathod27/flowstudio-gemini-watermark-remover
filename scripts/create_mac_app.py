import os
import sys
import json
import shutil
import tempfile
import argparse
import subprocess
from xml.sax.saxutils import escape as xml_escape


def get_repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read_version(repo_root: str) -> str:
    v_file = os.path.join(repo_root, "version.json")
    if os.path.exists(v_file):
        try:
            with open(v_file, "r", encoding="utf-8") as f:
                return str(json.load(f).get("version", "4.0.4")).strip().lstrip("v") or "4.0.4"
        except Exception:
            pass
    return "4.0.4"


def resolve_app_bundle_path(target_dir: str = None) -> str:
    if target_dir:
        expanded = os.path.abspath(os.path.expanduser(target_dir))
        if expanded.endswith(".app"):
            return expanded
        return os.path.join(expanded, "FlowStudio.app")

    sys_apps = "/Applications"
    if os.path.isdir(sys_apps) and os.access(sys_apps, os.W_OK):
        return os.path.join(sys_apps, "FlowStudio.app")

    user_apps = os.path.expanduser("~/Applications")
    os.makedirs(user_apps, exist_ok=True)
    return os.path.join(user_apps, "FlowStudio.app")


def _build_icns(src_png: str, dest_icns: str) -> bool:
    """Uses native macOS sips + iconutil when running on darwin to create AppIcon.icns."""
    if sys.platform != "darwin":
        return False
    if not (shutil.which("sips") and shutil.which("iconutil")):
        return False

    tmp_dir = tempfile.mkdtemp(prefix="fs_iconset_")
    iconset_dir = os.path.join(tmp_dir, "AppIcon.iconset")
    os.makedirs(iconset_dir, exist_ok=True)
    try:
        hi_dpi = "@" + "2x"
        sizes = [
            (16, "icon_16x16.png"),
            (32, f"icon_16x16{hi_dpi}.png"),
            (32, "icon_32x32.png"),
            (64, f"icon_32x32{hi_dpi}.png"),
            (128, "icon_128x128.png"),
            (256, f"icon_128x128{hi_dpi}.png"),
            (256, "icon_256x256.png"),
            (512, f"icon_256x256{hi_dpi}.png"),
            (512, "icon_512x512.png"),
        ]
        for px, fname in sizes:
            out_png = os.path.join(iconset_dir, fname)
            subprocess.run(
                ["sips", "-z", str(px), str(px), src_png, "--out", out_png],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
        subprocess.run(
            ["iconutil", "-c", "icns", iconset_dir, "-o", dest_icns],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return os.path.isfile(dest_icns)
    except Exception:
        return False
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def create_mac_app(target_dir: str = None, repo_root: str = None) -> str:
    repo = os.path.abspath(repo_root or get_repo_root())
    app_path = resolve_app_bundle_path(target_dir)
    contents_dir = os.path.join(app_path, "Contents")
    macos_dir = os.path.join(contents_dir, "MacOS")
    resources_dir = os.path.join(contents_dir, "Resources")

    os.makedirs(macos_dir, exist_ok=True)
    os.makedirs(resources_dir, exist_ok=True)

    # Copy icon into Contents/Resources and optionally generate AppIcon.icns on darwin
    icon_file_key = "icon128.png"
    src_png = None
    for cand in (
        os.path.join(repo, "extension", "icons", "icon128.png"),
        os.path.join(repo, "extension", "icons", "icon48.png"),
    ):
        if os.path.isfile(cand):
            src_png = cand
            break

    if src_png:
        dst_png = os.path.join(resources_dir, os.path.basename(src_png))
        shutil.copy2(src_png, dst_png)
        icon_file_key = os.path.basename(src_png)
        dst_icns = os.path.join(resources_dir, "AppIcon.icns")
        if _build_icns(src_png, dst_icns):
            icon_file_key = "AppIcon"

    src_ico = os.path.join(repo, "assets", "flowstudio.ico")
    if os.path.isfile(src_ico):
        shutil.copy2(src_ico, os.path.join(resources_dir, "flowstudio.ico"))

    version = _read_version(repo)
    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>FlowStudio</string>
    <key>CFBundleDisplayName</key>
    <string>FlowStudio</string>
    <key>CFBundleIdentifier</key>
    <string>com.flowstudio.app</string>
    <key>CFBundleExecutable</key>
    <string>FlowStudio</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>{xml_escape(version)}</string>
    <key>CFBundleVersion</key>
    <string>{xml_escape(version)}</string>
    <key>CFBundleIconFile</key>
    <string>{xml_escape(icon_file_key)}</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
"""
    plist_path = os.path.join(contents_dir, "Info.plist")
    with open(plist_path, "wb") as f:
        f.write(plist_content.encode("utf-8"))

    escaped_repo = repo.replace('"', '\\"')
    launcher_script = (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n\n"
        f'REPO_ROOT="{escaped_repo}"\n'
        'if [ -x "$REPO_ROOT/.venv/bin/python" ]; then\n'
        '  PYTHON_BIN="$REPO_ROOT/.venv/bin/python"\n'
        'elif [ -x "$REPO_ROOT/.venv/bin/python3" ]; then\n'
        '  PYTHON_BIN="$REPO_ROOT/.venv/bin/python3"\n'
        "else\n"
        '  PYTHON_BIN="$(command -v python3 || echo python3)"\n'
        "fi\n\n"
        'cd "$REPO_ROOT"\n'
        'if [ "$#" -eq 0 ]; then\n'
        '  exec "$PYTHON_BIN" "$REPO_ROOT/tray_app.py" --open\n'
        "else\n"
        '  exec "$PYTHON_BIN" "$REPO_ROOT/tray_app.py" "$@"\n'
        "fi\n"
    )
    launcher_path = os.path.join(macos_dir, "FlowStudio")
    with open(launcher_path, "wb") as f:
        f.write(launcher_script.encode("utf-8"))

    if os.name != "nt":
        os.chmod(launcher_path, 0o755)

    print(f"[FlowStudio] Created macOS app bundle: {app_path}")
    return app_path


def main():
    parser = argparse.ArgumentParser(description="Create FlowStudio.app macOS launcher bundle")
    parser.add_argument("--target-dir", default=None, help="Parent Applications directory (or .app path)")
    args = parser.parse_args()
    create_mac_app(target_dir=args.target_dir)


if __name__ == "__main__":
    main()

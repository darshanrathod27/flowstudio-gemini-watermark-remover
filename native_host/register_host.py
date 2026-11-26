"""Unified cross-platform Chrome Native Messaging Host registrar & startup auto-healer."""

import os
import sys
import json
import base64
import hashlib
import argparse
from typing import Dict, Any, Optional, List

HOST_NAME = "com.flowstudio.bridge"
EXPECTED_EXTENSION_ID = "kajblpfihdgbaeimfjnbcbmljndjhepe"


def is_developer_source_dir(install_root: str) -> bool:
    """Returns True if install_root is the private developer workspace rather than a standalone install."""
    abs_root = os.path.abspath(install_root or "").rstrip("\\/")
    return (
        "PRIVATE_SOURCE" in abs_root.upper()
        or os.path.isdir(os.path.join(abs_root, "FlowStudio_PRIVATE_SOURCE"))
        or os.path.isfile(os.path.join(abs_root, "build_scripts", "build_protected_release.py"))
        or os.path.isdir(os.path.join(abs_root, "cloud_backend"))
        or os.path.isdir(os.path.join(abs_root, "assets", "masks"))
    )


def get_python_exe(flowstudio_dir: str) -> str:
    if sys.platform == "darwin":
        for cand in (
            os.path.join(flowstudio_dir, ".venv", "bin", "python"),
            os.path.join(flowstudio_dir, ".venv", "bin", "python3"),
        ):
            if os.path.exists(cand):
                return cand
        return sys.executable

    venv_py = os.path.join(flowstudio_dir, ".venv", "Scripts", "python.exe")
    if os.path.exists(venv_py):
        return venv_py
    return sys.executable


def derive_extension_id(flowstudio_dir: str) -> str:
    manifest_path = os.path.join(flowstudio_dir, "extension", "manifest.json")
    if not os.path.exists(manifest_path):
        return EXPECTED_EXTENSION_ID

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        b64_key = manifest.get("key")
        if not b64_key:
            return EXPECTED_EXTENSION_ID
        der_bytes = base64.b64decode(b64_key)
        hex32 = hashlib.sha256(der_bytes).hexdigest()[:32]
        return "".join(chr(ord("a") + int(ch, 16)) for ch in hex32)
    except Exception:
        return EXPECTED_EXTENSION_ID


def _read_json_safe(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _norm_abs(path: str) -> str:
    return os.path.normcase(os.path.abspath(str(path or "")))


def _ensure_mac_browser_manifests(
    resolved_home: str,
    manifest: Dict[str, Any],
    force: bool = False,
) -> List[str]:
    chrome_hosts_dir = os.path.join(
        resolved_home,
        "Library",
        "Application Support",
        "Google",
        "Chrome",
        "NativeMessagingHosts",
    )
    candidate_dirs = [chrome_hosts_dir]
    for app_rel in (
        ("Chromium",),
        ("Microsoft Edge",),
        ("BraveSoftware", "Brave-Browser"),
    ):
        app_support = os.path.join(resolved_home, "Library", "Application Support", *app_rel)
        if os.path.isdir(app_support):
            candidate_dirs.append(os.path.join(app_support, "NativeMessagingHosts"))

    written: List[str] = []
    for hdir in candidate_dirs:
        os.makedirs(hdir, exist_ok=True)
        dest = os.path.join(hdir, f"{HOST_NAME}.json")
        existing = _read_json_safe(dest)
        if not force and existing == manifest:
            continue
        with open(dest, "w", encoding="utf-8", newline="\n") as f:
            json.dump(manifest, f, indent=2)
            f.write("\n")
        written.append(dest)
    return written


def ensure_native_host_registered(
    install_root: Optional[str] = None,
    force: bool = False,
    write_registry: bool = True,
    home_dir: Optional[str] = None,
    quiet: bool = True,
) -> Dict[str, Any]:
    """
    Fast (<15ms) idempotent self-heal for Chrome Native Messaging Host (`com.flowstudio.bridge`).
    Skips cleanly when running inside FlowStudio_PRIVATE_SOURCE or when FLOWSTUDIO_SKIP_AUTO_REG=1
    (unless force=True for explicit test/setup calls).
    """
    if install_root is None:
        host_dir = os.path.dirname(os.path.abspath(__file__))
        install_root = os.path.dirname(host_dir)
    abs_root = os.path.abspath(install_root)

    if not force:
        if os.environ.get("FLOWSTUDIO_SKIP_AUTO_REG", "").strip() == "1":
            return {"ok": True, "repaired": False, "skipped": "env_guard"}
        if is_developer_source_dir(abs_root):
            return {"ok": True, "repaired": False, "skipped": "developer_source_guard"}

    nh_dir = os.path.join(abs_root, "native_host")
    os.makedirs(nh_dir, exist_ok=True)
    ext_id = derive_extension_id(abs_root)
    expected_origin = f"chrome-extension://{ext_id}/"

    if sys.platform == "darwin":
        sh_path = os.path.abspath(os.path.join(nh_dir, "flowstudio_host.sh"))
        if not os.path.isfile(sh_path):
            sh_content = (
                "#!/usr/bin/env bash\n"
                'DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
                'ROOT_DIR="$(cd "$DIR/.." && pwd)"\n'
                'PY_BIN="$ROOT_DIR/.venv/bin/python"\n'
                'if [ ! -x "$PY_BIN" ]; then\n'
                '  PY_BIN="$(command -v python3.12 || command -v python3 || echo python3)"\n'
                "fi\n"
                'exec "$PY_BIN" "$DIR/host.py" "$@"\n'
            )
            with open(sh_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(sh_content)
        if os.name != "nt":
            try:
                os.chmod(sh_path, 0o755)
            except Exception:
                pass

        manifest = {
            "name": HOST_NAME,
            "description": "FlowStudio Native Messaging Host Bridge",
            "path": sh_path,
            "type": "stdio",
            "allowed_origins": [expected_origin],
        }
        resolved_home = os.path.abspath(os.path.expanduser(home_dir or "~"))
        if not write_registry:
            local_manifest = os.path.join(nh_dir, f"{HOST_NAME}.json")
            with open(local_manifest, "w", encoding="utf-8", newline="\n") as f:
                json.dump(manifest, f, indent=2)
                f.write("\n")
            return {"ok": True, "repaired": True, "manifest_path": local_manifest, "launcher_path": sh_path}

        written = _ensure_mac_browser_manifests(resolved_home, manifest, force=force)
        primary_manifest = os.path.join(
            resolved_home,
            "Library",
            "Application Support",
            "Google",
            "Chrome",
            "NativeMessagingHosts",
            f"{HOST_NAME}.json",
        )
        if not quiet:
            print(f"[NativeHost] Registered macOS Chrome host manifest: {primary_manifest}")
            print(f"[NativeHost] Host executable: {sh_path}")
            print(f"[NativeHost] Allowed origin: {expected_origin}")
        return {
            "ok": True,
            "repaired": bool(written) or force,
            "manifest_path": primary_manifest,
            "launcher_path": sh_path,
        }

    # Windows (`win32`): canonical launcher is `flowstudio_host.bat`, with legacy `host.bat` mirrored cleanly.
    py_exe = get_python_exe(abs_root)
    canonical_bat = os.path.abspath(os.path.join(nh_dir, "flowstudio_host.bat"))
    legacy_bat = os.path.abspath(os.path.join(nh_dir, "host.bat"))
    manifest_path = os.path.abspath(os.path.join(nh_dir, f"{HOST_NAME}.json"))
    bat_content = f'@echo off\r\n"{py_exe}" "%~dp0host.py"\r\n'

    manifest = {
        "name": HOST_NAME,
        "description": "FlowStudio Native Messaging Host Bridge",
        "path": canonical_bat,
        "type": "stdio",
        "allowed_origins": [expected_origin],
    }

    chrome_reg = rf"Software\Google\Chrome\NativeMessagingHosts\{HOST_NAME}"
    extra_regs = [
        (r"Software\Microsoft\Edge", rf"Software\Microsoft\Edge\NativeMessagingHosts\{HOST_NAME}"),
        (r"Software\BraveSoftware\Brave-Browser", rf"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts\{HOST_NAME}"),
    ]

    if not force:
        try:
            bat_ok = os.path.isfile(canonical_bat) and open(canonical_bat, "r", encoding="utf-8", errors="ignore").read() == bat_content
            m_data = _read_json_safe(manifest_path)
            manifest_ok = (
                isinstance(m_data, dict)
                and _norm_abs(m_data.get("path", "")) == _norm_abs(canonical_bat)
                and m_data.get("allowed_origins") == [expected_origin]
            )
            reg_ok = True
            if write_registry and sys.platform == "win32":
                import winreg
                reg_ok = False
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, chrome_reg) as k:
                        val, _ = winreg.QueryValueEx(k, "")
                        reg_ok = (_norm_abs(val) == _norm_abs(manifest_path))
                except OSError:
                    reg_ok = False
            if bat_ok and manifest_ok and reg_ok:
                return {
                    "ok": True,
                    "repaired": False,
                    "manifest_path": manifest_path,
                    "launcher_path": canonical_bat,
                }
        except Exception:
            pass

    for bat_file in (canonical_bat, legacy_bat):
        with open(bat_file, "w", encoding="utf-8", newline="") as f:
            f.write(bat_content)
        if not os.path.isfile(bat_file) or os.path.getsize(bat_file) <= 0:
            raise RuntimeError(f"Failed to verify Native Host launcher on disk: {bat_file}")

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")

    reg_written = []
    if write_registry and sys.platform == "win32":
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, chrome_reg) as key:
            winreg.SetValue(key, "", winreg.REG_SZ, manifest_path)
        reg_written.append(chrome_reg)
        for parent_key, sub_reg in extra_regs:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, parent_key):
                    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, sub_reg) as key:
                        winreg.SetValue(key, "", winreg.REG_SZ, manifest_path)
                    reg_written.append(sub_reg)
            except OSError:
                pass

    if not quiet:
        print(f"[NativeHost] Launcher verified: {canonical_bat}")
        print(f"[NativeHost] Manifest created: {manifest_path}")
        if reg_written:
            print(f"[NativeHost] Registered HKCU keys: {', '.join(reg_written)}")

    return {
        "ok": True,
        "repaired": True,
        "manifest_path": manifest_path,
        "launcher_path": canonical_bat,
        "reg_keys": reg_written,
    }


def main():
    parser = argparse.ArgumentParser(description="Register FlowStudio Chrome Native Messaging Host")
    parser.add_argument("--install-dir", default=None, help="Explicit FlowStudio install directory")
    parser.add_argument("--home-dir", default=None, help="Override home directory on macOS (for testing)")
    parser.add_argument("--no-registry", action="store_true", help="Write files without modifying OS registry")
    args = parser.parse_args()

    res = ensure_native_host_registered(
        install_root=args.install_dir,
        force=True,
        write_registry=not args.no_registry,
        home_dir=args.home_dir,
        quiet=False,
    )
    sys.exit(0 if res.get("ok") else 1)


if __name__ == "__main__":
    main()

import os
import sys
import json
import base64
import hashlib
import winreg

def get_python_exe():
    host_dir = os.path.dirname(os.path.abspath(__file__))
    flowstudio_dir = os.path.dirname(host_dir)
    venv_py = os.path.join(flowstudio_dir, ".venv", "Scripts", "python.exe")
    if os.path.exists(venv_py):
        return venv_py
    return sys.executable

def derive_extension_id():
    host_dir = os.path.dirname(os.path.abspath(__file__))
    flowstudio_dir = os.path.dirname(host_dir)
    manifest_path = os.path.join(flowstudio_dir, "extension", "manifest.json")
    if not os.path.exists(manifest_path):
        raise FileNotFoundError(f"manifest.json not found at: {manifest_path}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    b64_key = manifest.get("key")
    if not b64_key:
        raise ValueError("No 'key' found in extension/manifest.json")

    der_bytes = base64.b64decode(b64_key)
    hex32 = hashlib.sha256(der_bytes).hexdigest()[:32]
    permanent_id = "".join(chr(ord("a") + int(ch, 16)) for ch in hex32)
    return permanent_id

def install_host():
    host_dir = os.path.dirname(os.path.abspath(__file__))
    bat_path = os.path.join(host_dir, "host.bat")
    manifest_path = os.path.join(host_dir, "com.flowstudio.bridge.json")
    python_exe = get_python_exe()
    permanent_id = derive_extension_id()

    # 1. Update host.bat with active Python
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(f'@echo off\n"{python_exe}" "%~dp0host.py"\n')
    print(f"[NativeHost] Updated host.bat with Python: {python_exe}")

    # 2. Write Chrome Native Messaging Manifest
    manifest = {
        "name": "com.flowstudio.bridge",
        "description": "FlowStudio Native Messaging Host Bridge",
        "path": bat_path,
        "type": "stdio",
        "allowed_origins": [
            f"chrome-extension://{permanent_id}/"
        ]
    }

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"[NativeHost] Derived Permanent Extension ID: {permanent_id}")
    print(f"[NativeHost] Created manifest at: {manifest_path}")

    # 3. Register in Windows HKCU registry
    reg_key = r"Software\Google\Chrome\NativeMessagingHosts\com.flowstudio.bridge"
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, reg_key) as key:
            winreg.SetValue(key, "", winreg.REG_SZ, manifest_path)
        print(f"[NativeHost] Successfully registered in HKCU\\{reg_key}")
        return True
    except Exception as e:
        print(f"[NativeHost] Registry installation error: {e}")
        return False

if __name__ == "__main__":
    success = install_host()
    sys.exit(0 if success else 1)

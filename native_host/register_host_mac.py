import os
import json
import base64
import hashlib
import argparse

HOST_NAME = "com.flowstudio.bridge"
EXPECTED_EXTENSION_ID = "kajblpfihdgbaeimfjnbcbmljndjhepe"


def derive_extension_id(flowstudio_dir: str) -> str:
    manifest_path = os.path.join(flowstudio_dir, "extension", "manifest.json")
    if not os.path.exists(manifest_path):
        return EXPECTED_EXTENSION_ID

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    b64_key = manifest.get("key")
    if not b64_key:
        return EXPECTED_EXTENSION_ID

    der_bytes = base64.b64decode(b64_key)
    hex32 = hashlib.sha256(der_bytes).hexdigest()[:32]
    return "".join(chr(ord("a") + int(ch, 16)) for ch in hex32)


def register_mac_native_host(home_dir: str = None) -> str:
    host_dir = os.path.dirname(os.path.abspath(__file__))
    flowstudio_dir = os.path.dirname(host_dir)
    sh_path = os.path.abspath(os.path.join(host_dir, "flowstudio_host.sh"))

    if os.path.exists(sh_path) and os.name != "nt":
        os.chmod(sh_path, 0o755)

    ext_id = derive_extension_id(flowstudio_dir)
    resolved_home = os.path.abspath(os.path.expanduser(home_dir or "~"))
    chrome_hosts_dir = os.path.join(
        resolved_home,
        "Library",
        "Application Support",
        "Google",
        "Chrome",
        "NativeMessagingHosts",
    )
    os.makedirs(chrome_hosts_dir, exist_ok=True)

    manifest_dest = os.path.join(chrome_hosts_dir, f"{HOST_NAME}.json")
    manifest = {
        "name": HOST_NAME,
        "description": "FlowStudio Native Messaging Host Bridge",
        "path": sh_path,
        "type": "stdio",
        "allowed_origins": [
            f"chrome-extension://{ext_id}/"
        ],
    }

    with open(manifest_dest, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")

    print(f"[NativeHost] Registered macOS Chrome host manifest: {manifest_dest}")
    print(f"[NativeHost] Host executable: {sh_path}")
    print(f"[NativeHost] Allowed origin: chrome-extension://{ext_id}/")
    return manifest_dest


def main():
    parser = argparse.ArgumentParser(description="Register FlowStudio Chrome Native Messaging Host on macOS")
    parser.add_argument("--home-dir", default=None, help="Override home directory (for testing)")
    args = parser.parse_args()
    register_mac_native_host(home_dir=args.home_dir)


if __name__ == "__main__":
    main()

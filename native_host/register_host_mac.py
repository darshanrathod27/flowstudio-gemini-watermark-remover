import os
import sys
import argparse

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from register_host import (  # noqa: E402
    HOST_NAME,
    EXPECTED_EXTENSION_ID,
    derive_extension_id,
    ensure_native_host_registered,
)


def register_mac_native_host(home_dir: str = None) -> str:
    host_dir = os.path.dirname(os.path.abspath(__file__))
    flowstudio_dir = os.path.dirname(host_dir)
    res = ensure_native_host_registered(
        install_root=flowstudio_dir,
        force=True,
        write_registry=True,
        home_dir=home_dir,
        quiet=False,
    )
    return str(res.get("manifest_path", ""))


def main():
    parser = argparse.ArgumentParser(description="Register FlowStudio Chrome Native Messaging Host on macOS")
    parser.add_argument("--home-dir", default=None, help="Override home directory (for testing)")
    args = parser.parse_args()
    register_mac_native_host(home_dir=args.home_dir)


if __name__ == "__main__":
    main()

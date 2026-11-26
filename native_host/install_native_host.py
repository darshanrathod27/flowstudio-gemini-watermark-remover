import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from register_host import (  # noqa: E402
    derive_extension_id as _derive_ext_id,
    ensure_native_host_registered,
    get_python_exe as _get_python_exe,
)


def get_python_exe():
    return _get_python_exe(os.path.dirname(_HERE))


def derive_extension_id():
    return _derive_ext_id(os.path.dirname(_HERE))


def install_host():
    res = ensure_native_host_registered(
        install_root=os.path.dirname(_HERE),
        force=True,
        write_registry=True,
        quiet=False,
    )
    return bool(res.get("ok"))


if __name__ == "__main__":
    success = install_host()
    sys.exit(0 if success else 1)

#!/usr/bin/env bash
set -euo pipefail

# FlowStudio Pro - Clean 1-Click macOS Uninstaller
YES_MODE=0
CLEAN_CACHES=1
INSTALL_ARG=""

for arg in "$@"; do
  case "$arg" in
    -y|--yes)
      YES_MODE=1
      ;;
    --keep-caches)
      CLEAN_CACHES=0
      ;;
    *)
      if [ -z "$INSTALL_ARG" ] && [[ "$arg" != -* ]]; then
        INSTALL_ARG="$arg"
      fi
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
if [ -n "$INSTALL_ARG" ]; then
  TARGET_RAW="$INSTALL_ARG"
elif [ -n "${FLOWSTUDIO_DIR:-}" ]; then
  TARGET_RAW="$FLOWSTUDIO_DIR"
elif [ -f "$SCRIPT_DIR/tray_app.py" ] && [ -d "$SCRIPT_DIR/.venv" ]; then
  TARGET_RAW="$SCRIPT_DIR"
else
  TARGET_RAW="$HOME/FlowStudio"
fi

if [ -z "$TARGET_RAW" ]; then
  echo "[ABORT] Target directory cannot be empty."
  exit 2
fi

if [ -d "$TARGET_RAW" ]; then
  TARGET_DIR="$(cd "$TARGET_RAW" && pwd -P)"
else
  TARGET_DIR="${TARGET_RAW%/}"
fi

echo "============================================================"
echo "            FlowStudio Pro - macOS Uninstaller              "
echo "============================================================"
echo ""

# ------------------------------------------------------------------
# CRITICAL DEVELOPER SAFETY GUARD
# ------------------------------------------------------------------
case "$TARGET_DIR" in
  ""|"/"|"/Applications"|"/System"|"/usr"|"/bin"|"/sbin"|"/var"|"/tmp"|"/private/tmp"|"$HOME")
    echo "[SAFETY REFUSAL] Protected system/home path cannot be uninstalled: $TARGET_DIR"
    exit 2
    ;;
esac

if printf "%s" "$TARGET_DIR" | grep -qi "PRIVATE_SOURCE"; then
  echo "[SAFETY REFUSAL] Developer private source directory detected ($TARGET_DIR). Aborting!"
  exit 2
fi

if [ ! -d "$TARGET_DIR" ]; then
  echo "[ERROR] FlowStudio install directory not found: $TARGET_DIR"
  exit 1
fi

if [ -d "$TARGET_DIR/FlowStudio_PRIVATE_SOURCE" ] || \
   [ -f "$TARGET_DIR/build_scripts/build_protected_release.py" ] || \
   [ -d "$TARGET_DIR/cloud_backend" ] || \
   [ -d "$TARGET_DIR/assets/masks" ]; then
  echo "[SAFETY REFUSAL] Developer/private artifacts detected in $TARGET_DIR. Aborting!"
  exit 2
fi

if [ ! -f "$TARGET_DIR/tray_app.py" ] || [ ! -d "$TARGET_DIR/.venv" ]; then
  echo "[SAFETY REFUSAL] '$TARGET_DIR' is not a valid FlowStudio runtime install (requires tray_app.py + .venv). Aborting!"
  exit 2
fi

if [ "$YES_MODE" -ne 1 ]; then
  echo "Target Directory : $TARGET_DIR"
  echo "Will Remove      : App, Server, .venv (PyTorch/MPS), Models, FlowStudio.app & Native Bridge"
  echo "Preserved        : \$HOME/Downloads and \$HOME/Desktop outputs are never touched"
  echo ""
  printf "Type YES to permanently uninstall FlowStudio: "
  read -r ANSWER
  case "$ANSWER" in
    YES|yes|Y|y) ;;
    *)
      echo "Uninstall cancelled."
      exit 0
      ;;
  esac
fi

# 1. Gracefully stop running FlowStudio processes scoped strictly to TARGET_DIR
echo "[1/5] Stopping FlowStudio server and menu bar tray..."
curl -fsS -m 2 -X POST "http://127.0.0.1:8765/api/system/shutdown" -H "Content-Type: application/json" -d '{}' >/dev/null 2>&1 || true
sleep 0.8

pkill -TERM -f "${TARGET_DIR}/.*(tray_app\.py|server\.app|uvicorn)" >/dev/null 2>&1 || true
if [ "$TARGET_DIR" = "$HOME/FlowStudio" ]; then
  for pid in $(pgrep -f "tray_app\.py|server\.app:app" 2>/dev/null || true); do
    cmd_line="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    if [ -n "$cmd_line" ] && ! printf "%s" "$cmd_line" | grep -qi "PRIVATE_SOURCE"; then
      kill -TERM "$pid" >/dev/null 2>&1 || true
    fi
  done
fi
sleep 1.2
pkill -KILL -f "${TARGET_DIR}/.*(tray_app\.py|server\.app|uvicorn)" >/dev/null 2>&1 || true

# 2. Remove Chrome Native Messaging manifest
echo "[2/5] Removing Chrome Native Messaging Bridge manifest..."
CHROME_HOST_JSON="$HOME/Library/Application Support/Google/Chrome/NativeMessagingHosts/com.flowstudio.bridge.json"
if [ -f "$CHROME_HOST_JSON" ]; then
  rm -f "$CHROME_HOST_JSON"
fi

# 3. Remove FlowStudio.app bundles (/Applications if writable + ~/Applications)
echo "[3/5] Removing FlowStudio.app launcher..."
if [ -d "/Applications/FlowStudio.app" ] && [ -w "/Applications" ]; then
  rm -rf "/Applications/FlowStudio.app"
fi
if [ -d "$HOME/Applications/FlowStudio.app" ]; then
  rm -rf "$HOME/Applications/FlowStudio.app"
fi

# 4. Remove tray single-instance temp lockfile
echo "[4/5] Cleaning temporary lockfiles..."
rm -f "/tmp/flowstudio_tray.lock" "${TMPDIR:-/tmp}/flowstudio_tray.lock" >/dev/null 2>&1 || true

# 5. Remove FlowStudio install directory (never touching ~/Downloads or ~/Desktop)
echo "[5/5] Removing FlowStudio directory ($TARGET_DIR)..."
cd /tmp
rm -rf "$TARGET_DIR"

if [ "$CLEAN_CACHES" -eq 1 ]; then
  rm -rf "$HOME/Library/Caches/pip" "$HOME/Library/Caches/uv" >/dev/null 2>&1 || true
fi

echo ""
echo "============================================================"
echo "  FlowStudio Uninstall Complete!"
echo "  User outputs in \$HOME/Downloads and \$HOME/Desktop were preserved."
echo "  Reminder: Remove FlowStudio Local Bridge in chrome://extensions."
echo "============================================================"

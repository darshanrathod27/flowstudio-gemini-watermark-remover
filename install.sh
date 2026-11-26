#!/usr/bin/env bash
set -euo pipefail

# FlowStudio Pro - 1-Command Automated macOS Installer (Apple Silicon MPS & Intel fallback)
REPO_SLUG="darshanrathod27/flowstudio-gemini-watermark-remover"
REMOTE_URL="https://github.com/${REPO_SLUG}.git"
INSTALL_DIR="${FLOWSTUDIO_DIR:-$HOME/FlowStudio}"

echo "============================================================"
echo "       FlowStudio Pro - Automated macOS Installer"
echo "============================================================"
echo ""

OS_NAME="$(uname -s)"
if [ "$OS_NAME" != "Darwin" ]; then
  echo "[ERROR] This installer is for macOS only (detected: $OS_NAME)."
  echo "On Windows, use install.ps1 instead."
  exit 1
fi

ARCH="$(uname -m)"
if [ "$ARCH" = "arm64" ]; then
  echo "[OK] Apple Silicon (arm64) detected - Metal (MPS) & VideoToolbox enabled."
else
  echo "[WARN] Non-arm64 architecture detected ($ARCH)."
  echo "       If running on an Apple Silicon Mac under Rosetta 2, open a native arm64 Terminal for Metal MPS speed."
  echo "       Proceeding safely in CPU compatibility mode..."
fi

# Ensure Homebrew PATH entries are visible in non-interactive shells
if [ -x "/opt/homebrew/bin/brew" ]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
elif [ -x "/usr/local/bin/brew" ]; then
  eval "$(/usr/local/bin/brew shellenv)"
fi

# Check / install prerequisites (Homebrew, Python 3.12, FFmpeg, Git)
find_python312() {
  for cand in \
    "$(command -v python3.12 2>/dev/null || true)" \
    "/opt/homebrew/opt/python@3.12/libexec/bin/python" \
    "/opt/homebrew/bin/python3.12" \
    "/usr/local/opt/python@3.12/libexec/bin/python" \
    "/usr/local/bin/python3.12" \
    "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12" \
    "$(command -v python3 2>/dev/null || true)"; do
    if [ -n "$cand" ] && [ -x "$cand" ]; then
      if "$cand" -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)' >/dev/null 2>&1; then
        echo "$cand"
        return 0
      fi
    fi
  done
  return 1
}

HAS_BREW=0
if command -v brew >/dev/null 2>&1; then
  HAS_BREW=1
fi

PY312_BIN="$(find_python312 || true)"
if [ -z "$PY312_BIN" ]; then
  if [ "$HAS_BREW" -eq 1 ]; then
    echo "[INFO] Installing Python 3.12 via Homebrew (required for native engine binaries)..."
    brew install python@3.12
    PY312_BIN="$(find_python312 || true)"
  fi
fi

if [ -z "$PY312_BIN" ]; then
  echo "[ERROR] Python 3.12 is required and could not be located."
  if [ "$HAS_BREW" -eq 0 ]; then
    echo "Install Homebrew first in one command, then re-run this installer:"
    echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
  else
    echo "Please run: brew install python@3.12"
  fi
  exit 1
fi
echo "[OK] Using Python 3.12: $PY312_BIN"

if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  if [ "$HAS_BREW" -eq 1 ]; then
    echo "[INFO] Installing FFmpeg via Homebrew..."
    brew install ffmpeg
  else
    echo "[ERROR] FFmpeg is required and Homebrew is not installed."
    echo "Install Homebrew first in one command, then re-run this installer:"
    echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
    exit 1
  fi
fi
echo "[OK] FFmpeg ready: $(command -v ffmpeg)"

sync_from_zip() {
  local dest="$1"
  local tmp_zip tmp_ext extracted_root
  tmp_zip="$(mktemp -t flowstudio_dl).zip"
  tmp_ext="$(mktemp -d -t flowstudio_ext)"
  trap 'rm -rf "$tmp_zip" "$tmp_ext"' RETURN

  echo "[INFO] Downloading FlowStudio archive from GitHub..."
  curl -fsSL "https://github.com/${REPO_SLUG}/archive/refs/heads/main.zip" -o "$tmp_zip"
  unzip -q "$tmp_zip" -d "$tmp_ext"
  extracted_root="$tmp_ext/flowstudio-gemini-watermark-remover-main"
  if [ ! -d "$extracted_root" ]; then
    extracted_root="$(find "$tmp_ext" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
  fi
  mkdir -p "$dest"
  rsync -a --exclude='.venv' --exclude='bin' --exclude='models' --exclude='workspace' --exclude='.git' "$extracted_root/" "$dest/"
}

# 1. Stop any running FlowStudio processes before updating files
if [ -d "$INSTALL_DIR" ]; then
  echo "[1/4] Existing installation detected at $INSTALL_DIR. Stopping running engine..."
  curl -fsS -m 2 -X POST "http://127.0.0.1:8765/api/system/shutdown" -H "Content-Type: application/json" -d '{}' >/dev/null 2>&1 || true
  sleep 0.5
  pkill -TERM -f "${INSTALL_DIR}/.*(tray_app\.py|server\.app|uvicorn)" >/dev/null 2>&1 || true
  if [ "$INSTALL_DIR" = "$HOME/FlowStudio" ]; then
    for pid in $(pgrep -f "tray_app\.py|server\.app:app" 2>/dev/null || true); do
      cmd_line="$(ps -p "$pid" -o command= 2>/dev/null || true)"
      if [ -n "$cmd_line" ] && ! printf "%s" "$cmd_line" | grep -qi "PRIVATE_SOURCE"; then
        kill -TERM "$pid" >/dev/null 2>&1 || true
      fi
    done
  fi
  sleep 1.2

  GIT_OK=0
  if [ -d "$INSTALL_DIR/.git" ] && command -v git >/dev/null 2>&1; then
    echo "[INFO] Updating via git (orphan force-push safe)..."
    rm -f "$INSTALL_DIR/.git/index.lock" 2>/dev/null || true
    if git -C "$INSTALL_DIR" fetch --depth 1 origin main && git -C "$INSTALL_DIR" reset --hard origin/main; then
      GIT_OK=1
    fi
  fi
  if [ "$GIT_OK" -eq 0 ]; then
    sync_from_zip "$INSTALL_DIR"
  fi
else
  echo "[1/4] Installing FlowStudio to $INSTALL_DIR..."
  CLONE_OK=0
  if command -v git >/dev/null 2>&1; then
    if git clone --depth 1 "$REMOTE_URL" "$INSTALL_DIR"; then
      CLONE_OK=1
    fi
  fi
  if [ "$CLONE_OK" -eq 0 ]; then
    sync_from_zip "$INSTALL_DIR"
  fi
fi

INSTALL_DIR="$(cd "$INSTALL_DIR" && pwd -P)"

# 2. Create or verify Python 3.12 virtual environment
echo "[2/4] Setting up Python 3.12 virtual environment..."
VENV_DIR="$INSTALL_DIR/.venv"
VENV_PY="$VENV_DIR/bin/python"

if [ -d "$VENV_DIR" ]; then
  if [ ! -x "$VENV_PY" ] || \
     ! "$VENV_PY" -c 'import sys; assert sys.version_info[:2] == (3, 12)' >/dev/null 2>&1 || \
     ! "$VENV_PY" -m pip --version >/dev/null 2>&1; then
    echo "[WARN] Existing .venv is incompatible or missing pip. Recreating..."
    rm -rf "$VENV_DIR"
  fi
fi

if [ ! -d "$VENV_DIR" ]; then
  "$PY312_BIN" -m venv "$VENV_DIR"
  if ! "$VENV_PY" -m pip --version >/dev/null 2>&1; then
    "$VENV_PY" -m ensurepip --upgrade >/dev/null 2>&1 || true
  fi
fi

# Install PyTorch (native macOS MPS wheel on arm64; never CUDA cu128 on macOS) + requirements + spandrel
echo "[3/4] Installing PyTorch (Metal MPS) and FlowStudio dependencies..."
"$VENV_PY" -m pip install --quiet --upgrade pip
if ! "$VENV_PY" -c "import torch, torchvision" >/dev/null 2>&1; then
  "$VENV_PY" -m pip install --quiet torch torchvision
fi
if [ -f "$INSTALL_DIR/requirements.txt" ]; then
  "$VENV_PY" -m pip install --quiet -r "$INSTALL_DIR/requirements.txt"
fi
"$VENV_PY" -m pip install --quiet spandrel

# 3. Executable permissions, Native Messaging Host & FlowStudio.app
echo "[4/4] Registering Chrome Native Messaging Bridge & FlowStudio.app..."
chmod +x "$INSTALL_DIR/install.sh" "$INSTALL_DIR/uninstall.sh" "$INSTALL_DIR/native_host/flowstudio_host.sh"
if [ -f "$INSTALL_DIR/scripts/self_update.sh" ]; then
  chmod +x "$INSTALL_DIR/scripts/self_update.sh"
fi
if [ -f "$INSTALL_DIR/native_host/register_host.py" ]; then
  "$VENV_PY" "$INSTALL_DIR/native_host/register_host.py" --install-dir "$INSTALL_DIR"
else
  "$VENV_PY" "$INSTALL_DIR/native_host/register_host_mac.py"
fi
CHROME_NH_JSON="$HOME/Library/Application Support/Google/Chrome/NativeMessagingHosts/com.flowstudio.bridge.json"
if [ ! -f "$CHROME_NH_JSON" ] || [ ! -x "$INSTALL_DIR/native_host/flowstudio_host.sh" ]; then
  echo "[ERROR] Chrome Native Messaging verification failed ($CHROME_NH_JSON)"
  exit 1
fi
"$VENV_PY" "$INSTALL_DIR/scripts/create_mac_app.py"

# End-of-setup self-test (space & quote safe via argv)
"$VENV_PY" -c "import os, sys, json; root = sys.argv[1]; sys.path.insert(0, root); import fastapi, uvicorn, cv2, torch, spandrel, pystray; from engine.watermark_remover import WatermarkRemover; wr = WatermarkRemover(); mps = hasattr(torch.backends, 'mps') and torch.backends.mps.is_available(); assert os.path.isfile(os.path.join(root, 'version.json')); print(f'[VERIFY] Engine OK | Masks: {len(wr.master_masks)} | MPS: {mps}')" "$INSTALL_DIR"

# Copy extension folder path silently to macOS clipboard if pbcopy exists
if command -v pbcopy >/dev/null 2>&1; then
  printf "%s" "$INSTALL_DIR/extension" | pbcopy || true
fi

ACTUAL_VERSION="4.0.2"
if [ -f "$INSTALL_DIR/version.json" ]; then
  ACTUAL_VERSION="$("$VENV_PY" -c "import json, sys; print(str(json.load(open(sys.argv[1], encoding='utf-8')).get('version','4.0.2')).lstrip('v'))" "$INSTALL_DIR/version.json" 2>/dev/null || echo "4.0.2")"
fi

# Launch FlowStudio Menu Bar silently in background & verify /api/health ONLINE
if [ "${FLOWSTUDIO_NO_LAUNCH:-0}" != "1" ]; then
  if [ -d "/Applications/FlowStudio.app" ]; then
    open -a "/Applications/FlowStudio.app" --args --silent >/dev/null 2>&1 || true
  elif [ -d "$HOME/Applications/FlowStudio.app" ]; then
    open -a "$HOME/Applications/FlowStudio.app" --args --silent >/dev/null 2>&1 || true
  else
    nohup "$VENV_PY" "$INSTALL_DIR/tray_app.py" --silent >/dev/null 2>&1 &
  fi

  SERVER_READY=0
  for _ in $(seq 1 30); do
    if curl -fsS -m 1 "http://127.0.0.1:8765/api/health" >/dev/null 2>&1; then
      SERVER_READY=1
      echo "[OK] FlowStudio backend verified ONLINE at http://127.0.0.1:8765"
      break
    fi
    sleep 0.5
  done
  if [ "$SERVER_READY" -ne 1 ]; then
    echo "[WARN] Backend startup exceeded 15s; check $INSTALL_DIR/workspace/server.log"
  fi
fi

echo ""
echo "============================================================"
echo "  FlowStudio v${ACTUAL_VERSION} Installed & Ready!"
echo "============================================================"
echo "Extension Folder Path (copied to clipboard):"
echo "  $INSTALL_DIR/extension"
echo ""
echo "Chrome Setup (15 seconds):"
echo "  1. Open chrome://extensions in Google Chrome"
echo "  2. Turn ON \"Developer mode\" (top-right)"
echo "  3. Click \"Load unpacked\" and select:"
echo "     $INSTALL_DIR/extension"
echo "============================================================"

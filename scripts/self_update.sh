#!/usr/bin/env bash
set -euo pipefail

# FlowStudio macOS Detached In-Place Self-Updater (strict Unix LF)
INSTALL_DIR="${1:-${FLOWSTUDIO_DIR:-$HOME/FlowStudio}}"
BRANCH="${2:-main}"
SOURCE_ZIP="${3:-}"
SKIP_RELAUNCH="${FLOWSTUDIO_SKIP_RELAUNCH:-0}"
REPO_SLUG="darshanrathod27/flowstudio-gemini-watermark-remover"

INSTALL_DIR="$(cd "$INSTALL_DIR" 2>/dev/null && pwd -P || printf '%s' "${INSTALL_DIR%/}")"
PARENT_DIR="$(dirname "$INSTALL_DIR")"
UPPER_DIR="$(printf '%s' "$INSTALL_DIR" | tr '[:lower:]' '[:upper:]')"

if [[ "$UPPER_DIR" == *"PRIVATE_SOURCE"* ]] || \
   [ -d "$PARENT_DIR/FlowStudio_PRIVATE_SOURCE" ] || \
   [ -d "$INSTALL_DIR/cloud_backend" ] || \
   [ -d "$INSTALL_DIR/assets/masks" ] || \
   [ -f "$INSTALL_DIR/build_scripts/build_protected_release.py" ] || \
   [ ! -f "$INSTALL_DIR/tray_app.py" ] || \
   [ ! -d "$INSTALL_DIR/.venv" ]; then
  exit 2
fi

LOG_DIR="$INSTALL_DIR/workspace/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/updater.log"

log_line() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >> "$LOG_FILE" 2>/dev/null || true
}

log_line "=== FlowStudio macOS Self-Updater started for $INSTALL_DIR ($BRANCH) ==="

LOCK_FILE="$INSTALL_DIR/workspace/updater.lock"
NOW_TS="$(date +%s)"
if [ -f "$LOCK_FILE" ]; then
  LOCK_STATUS="$(python3 - "$LOCK_FILE" "$$" "$NOW_TS" 2>/dev/null <<'PY'
import json, os, sys
p, my_pid, now_s = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
try:
    d = json.load(open(p, encoding="utf-8"))
    pid = int(d.get("pid") or 0)
    ts = float(d.get("ts") or 0)
    age = now_s - ts
    if 0 <= age < 300 and pid > 0 and pid != my_pid:
        try:
            os.kill(pid, 0)
            print(f"BUSY:{pid}")
            sys.exit(0)
        except ProcessLookupError:
            pass
        except PermissionError:
            print(f"BUSY:{pid}")
            sys.exit(0)
except Exception:
    pass
print("FREE")
PY
)"
  if [[ "$LOCK_STATUS" == BUSY:* ]]; then
    log_line "Another active updater ($LOCK_STATUS) already owns $LOCK_FILE; exiting cleanly."
    exit 0
  fi
fi

printf '{"pid":%s,"ts":%s,"owner":"sh"}\n' "$$" "$NOW_TS" > "$LOCK_FILE"
cleanup_updater() {
  rm -f "$LOCK_FILE" 2>/dev/null || true
  if [[ "$0" == /tmp/flowstudio_self_update_* ]]; then
    rm -f "$0" 2>/dev/null || true
  fi
}
trap cleanup_updater EXIT

# 1. Gracefully stop server & tray scoped strictly to $INSTALL_DIR
curl -fsS -m 2 -X POST "http://127.0.0.1:8765/api/system/shutdown" -H "Content-Type: application/json" -d '{}' >/dev/null 2>&1 || true
sleep 0.8
pkill -TERM -f "${INSTALL_DIR}/.*(tray_app\.py|server\.app|uvicorn)" >/dev/null 2>&1 || true
sleep 0.8
pkill -KILL -f "${INSTALL_DIR}/.*(tray_app\.py|server\.app|uvicorn)" >/dev/null 2>&1 || true
sleep 0.4

REQ_FILE="$INSTALL_DIR/requirements.txt"
HASH_FILE="$INSTALL_DIR/workspace/.requirements.sha256"
PREV_HASH=""
if [ -f "$HASH_FILE" ]; then
  PREV_HASH="$(cat "$HASH_FILE" 2>/dev/null || true)"
elif [ -f "$REQ_FILE" ]; then
  PREV_HASH="$(shasum -a 256 "$REQ_FILE" | awk '{print $1}' 2>/dev/null || true)"
fi

VENV_PY="$INSTALL_DIR/.venv/bin/python"

# 2. In-place sync preserving .venv, bin, models, workspace, .git, and keeping extension/ directory intact
UPDATED=0
if [ -z "$SOURCE_ZIP" ] && [ -d "$INSTALL_DIR/.git" ] && command -v git >/dev/null 2>&1; then
  rm -f "$INSTALL_DIR/.git/index.lock" 2>/dev/null || true
  if git -C "$INSTALL_DIR" fetch --depth 1 origin "$BRANCH" >> "$LOG_FILE" 2>&1 && \
     git -C "$INSTALL_DIR" reset --hard "origin/$BRANCH" >> "$LOG_FILE" 2>&1; then
    UPDATED=1
    log_line "Git in-place reset succeeded."
  fi
fi

if [ "$UPDATED" -eq 0 ]; then
  log_line "Syncing via archive file-by-file merge..."
  TMP_ZIP=""
  CLEAN_ZIP=0
  if [ -n "$SOURCE_ZIP" ] && [ -f "$SOURCE_ZIP" ]; then
    TMP_ZIP="$SOURCE_ZIP"
  else
    TMP_ZIP="$(mktemp -t flowstudio_up).zip"
    CLEAN_ZIP=1
    curl -fsSL "https://github.com/${REPO_SLUG}/archive/refs/heads/${BRANCH}.zip" -o "$TMP_ZIP"
  fi
  TMP_EXT="$(mktemp -d -t flowstudio_up_ext)"
  if unzip -q "$TMP_ZIP" -d "$TMP_EXT"; then
    EXT_ROOT="$TMP_EXT/flowstudio-gemini-watermark-remover-${BRANCH}"
    if [ ! -d "$EXT_ROOT" ]; then
      EXT_ROOT="$(find "$TMP_EXT" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
    fi
    if command -v rsync >/dev/null 2>&1; then
      rsync -a --exclude='.venv' --exclude='bin' --exclude='models' --exclude='workspace' --exclude='.git' "$EXT_ROOT/" "$INSTALL_DIR/" >> "$LOG_FILE" 2>&1
    else
      cp -Rf "$EXT_ROOT/"* "$INSTALL_DIR/" 2>/dev/null || true
    fi
    UPDATED=1
    log_line "ZIP archive in-place merge succeeded."
  fi
  if [ "$CLEAN_ZIP" -eq 1 ] && [ -n "$TMP_ZIP" ]; then
    rm -f "$TMP_ZIP" 2>/dev/null || true
  fi
  rm -rf "$TMP_EXT" 2>/dev/null || true
fi

# 3. Incremental requirements check (preserves PyTorch MPS installation!)
if [ -f "$REQ_FILE" ] && [ -x "$VENV_PY" ]; then
  NEW_HASH="$(shasum -a 256 "$REQ_FILE" | awk '{print $1}' 2>/dev/null || true)"
  if [ -n "$NEW_HASH" ] && [ "$NEW_HASH" != "$PREV_HASH" ]; then
    log_line "requirements.txt changed; updating Python packages..."
    "$VENV_PY" -m pip install --quiet -r "$REQ_FILE" >> "$LOG_FILE" 2>&1 || true
  fi
  printf '%s' "$NEW_HASH" > "$HASH_FILE" 2>/dev/null || true
fi

# 4. Permissions, Chrome Native Host re-registration, and FlowStudio.app refresh
chmod +x "$INSTALL_DIR/install.sh" "$INSTALL_DIR/uninstall.sh" "$INSTALL_DIR/native_host/flowstudio_host.sh" "$INSTALL_DIR/scripts/self_update.sh" 2>/dev/null || true
if [ -f "$INSTALL_DIR/native_host/register_host.py" ] && [ -x "$VENV_PY" ]; then
  "$VENV_PY" "$INSTALL_DIR/native_host/register_host.py" --install-dir "$INSTALL_DIR" >> "$LOG_FILE" 2>&1 || true
elif [ -f "$INSTALL_DIR/native_host/register_host_mac.py" ] && [ -x "$VENV_PY" ]; then
  "$VENV_PY" "$INSTALL_DIR/native_host/register_host_mac.py" >> "$LOG_FILE" 2>&1 || true
fi
if [ -f "$INSTALL_DIR/scripts/create_mac_app.py" ] && [ -x "$VENV_PY" ]; then
  "$VENV_PY" "$INSTALL_DIR/scripts/create_mac_app.py" >> "$LOG_FILE" 2>&1 || true
fi

# 5. Relaunch Menu Bar / Tray silently
if [ "$SKIP_RELAUNCH" != "1" ]; then
  if [ -d "/Applications/FlowStudio.app" ]; then
    open -a "/Applications/FlowStudio.app" --args --silent >/dev/null 2>&1 || true
  elif [ -d "$HOME/Applications/FlowStudio.app" ]; then
    open -a "$HOME/Applications/FlowStudio.app" --args --silent >/dev/null 2>&1 || true
  elif [ -x "$VENV_PY" ]; then
    nohup "$VENV_PY" "$INSTALL_DIR/tray_app.py" --silent >/dev/null 2>&1 &
  fi

  for _ in $(seq 1 30); do
    if curl -fsS -m 1 "http://127.0.0.1:8765/api/health" >/dev/null 2>&1; then
      log_line "Verified restarted server ONLINE."
      break
    fi
    sleep 0.4
  done
fi

log_line "=== FlowStudio macOS Self-Updater finished ==="
exit 0

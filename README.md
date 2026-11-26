<div align="center">

# FlowStudio (`v4.0.4`)

### Ultra-Clean Watermark Remover & Neural AI Upscaler for Google Flow Media

[![Release v4.0.4](https://img.shields.io/badge/Release-v4.0.4-3fb950.svg)](https://github.com/darshanrathod27/flowstudio-gemini-watermark-remover/releases/tag/v4.0.4)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/darshanrathod27/flowstudio-gemini-watermark-remover/blob/main/LICENSE)
[![Python 3.12](https://img.shields.io/badge/Python-3.12%20(64--bit)-brightgreen.svg)](https://www.python.org/downloads/release/python-3120/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![CUDA](https://img.shields.io/badge/CUDA-12.8%20Ready-76B900.svg)](https://developer.nvidia.com/cuda-zone)
[![Apple Silicon](https://img.shields.io/badge/Apple%20Silicon-Metal%20MPS-000000.svg)](https://developer.apple.com/metal/)
[![Platform: Windows | macOS](https://img.shields.io/badge/Platform-Windows%2010%2F11%20%7C%20macOS%20arm64-0078D6.svg)](https://github.com/darshanrathod27/flowstudio-gemini-watermark-remover)

**100% Offline • Zero Inpainting Blur • Exact Mathematical Reverse-Alpha • Auto-Scaling Hardware Engine**

</div>

---

## 🔗 Quick Links (PC & Mac)

| Resource | Windows (PC) | macOS (Apple Silicon) |
| :--- | :--- | :--- |
| **GitHub Repository** | [flowstudio-gemini-watermark-remover](https://github.com/darshanrathod27/flowstudio-gemini-watermark-remover) | [flowstudio-gemini-watermark-remover](https://github.com/darshanrathod27/flowstudio-gemini-watermark-remover) |
| **Latest Release (`v4.0.4`)** | [Releases / Latest](https://github.com/darshanrathod27/flowstudio-gemini-watermark-remover/releases/latest) · [Tag `v4.0.4`](https://github.com/darshanrathod27/flowstudio-gemini-watermark-remover/releases/tag/v4.0.4) | [Releases / Latest](https://github.com/darshanrathod27/flowstudio-gemini-watermark-remover/releases/latest) · [Tag `v4.0.4`](https://github.com/darshanrathod27/flowstudio-gemini-watermark-remover/releases/tag/v4.0.4) |
| **Download Archive (`.zip`)** | [Download `main.zip`](https://github.com/darshanrathod27/flowstudio-gemini-watermark-remover/archive/refs/heads/main.zip) | [Download `main.zip`](https://github.com/darshanrathod27/flowstudio-gemini-watermark-remover/archive/refs/heads/main.zip) |
| **1-Command Installer** | [`install.ps1`](https://raw.githubusercontent.com/darshanrathod27/flowstudio-gemini-watermark-remover/main/install.ps1) | [`install.sh`](https://raw.githubusercontent.com/darshanrathod27/flowstudio-gemini-watermark-remover/main/install.sh) |
| **In-Place Updater Script** | [`scripts/self_update.ps1`](https://raw.githubusercontent.com/darshanrathod27/flowstudio-gemini-watermark-remover/main/scripts/self_update.ps1) | [`scripts/self_update.sh`](https://raw.githubusercontent.com/darshanrathod27/flowstudio-gemini-watermark-remover/main/scripts/self_update.sh) |
| **Clean Uninstaller Script** | [`uninstall.ps1`](https://raw.githubusercontent.com/darshanrathod27/flowstudio-gemini-watermark-remover/main/uninstall.ps1) | [`uninstall.sh`](https://raw.githubusercontent.com/darshanrathod27/flowstudio-gemini-watermark-remover/main/uninstall.sh) |
| **Live Version Metadata** | [`version.json`](https://raw.githubusercontent.com/darshanrathod27/flowstudio-gemini-watermark-remover/main/version.json) · [Version API](https://flowstudio-api.flowstudio-app.workers.dev/api/version) | [`version.json`](https://raw.githubusercontent.com/darshanrathod27/flowstudio-gemini-watermark-remover/main/version.json) · [Version API](https://flowstudio-api.flowstudio-app.workers.dev/api/version) |
| **Supported Web App** | [Google Flow (`flow.google.com`)](https://flow.google.com) | [Google Flow (`flow.google.com`)](https://flow.google.com) |
| **Local UI & Extension** | Studio: `http://127.0.0.1:8765` · Ext: `chrome://extensions` | Studio: `http://127.0.0.1:8765` · Ext: `chrome://extensions` |

---

## ✨ Highlights (`v4.0.4`)

- **Exact Reverse-Alpha Reconstruction**: Unlike AI inpainters that blur and hallucinate pixels, FlowStudio mathematically inverts the semi-transparent alpha overlay, restoring original underlying detail with zero blur and zero outward bleed (`0.0` outside max pixel diff).
- **Colon-Safe & Collision-Free Project ZIPs (`v4.0.4`)**: Never drops Google Flow video or folder titles containing colons or special characters (such as `Scene 1: Bear cub holding lantern.mp4`), preserves long tail prompt IDs (`_2`, `_3` auto-deduplication for same-name entries), recovers extensionless media via magic-byte sniffing, and stages temporary renders strictly inside `workspace/temp/` (zero `.TMP` clutter in `Downloads`).
- **Damage-Only Veto Smart Image Guard (`v4.0.4`)**: Unconditionally cleans `100%` of videos and detects watermarked images across bright sunsets and high-texture fur/foliage without false negatives, while keeping genuinely logo-free reference images `100%` untouched (`✓ X cleaned · Y kept`).
- **Cross-Platform Desktop Experience (Windows PC + macOS Apple Silicon)**: Runs windowlessly via System Tray & Desktop Shortcut on Windows (`pythonw.exe tray_app.py`) and as a native Menu Bar app (`FlowStudio.app`) on macOS M1/M2/M3/M4, shipping compiled Dual-OS binaries (`*.cp312-win_amd64.pyd` + `*.cpython-312-darwin.so`).
- **Neural AI 1080p / 2K / 4K Upscaler & Hardware Video Encoding**: Real-ESRGAN accelerated by CUDA FP16 + `h264_nvenc` / `h264_qsv` on Windows PC and Metal MPS FP16 + Apple Media Engine `h264_videotoolbox` on macOS, with tuned `libx264` fallback.
- **Always-Alive Multi-Profile Chrome Bridge & Self-Healing 1-Click Updater**: Chrome Native Messaging (`com.flowstudio.bridge`) auto-repairs on boot, supports multi-profile Chrome auto-sync when FlowStudio updates on disk, opens **"Show in Folder"** in the foreground, and updates cleanly with a single-flight lock (`workspace/updater.lock`).
- **Instant Clipboard Copy**: Places cleaned full-resolution images straight into your system clipboard (`CF_DIB` on Windows, native `NSPasteboard` on macOS) so you can paste (`Ctrl+V` / `Cmd+V`) directly into Flow Chat, Discord, or Photoshop.

---

## ⚡ Windows (PC) — Install, Update & Uninstall

### 1-Command Fast Install (PowerShell)
Open **PowerShell** and run:

```powershell
irm https://raw.githubusercontent.com/darshanrathod27/flowstudio-gemini-watermark-remover/main/install.ps1 | iex
```

What [`install.ps1`](https://raw.githubusercontent.com/darshanrathod27/flowstudio-gemini-watermark-remover/main/install.ps1) sets up automatically:
1. Installs or updates FlowStudio in `%USERPROFILE%\FlowStudio` (customizable via `-InstallDir`).
2. Configures Python 3.12, PyTorch (CUDA / CPU), and FFmpeg binaries.
3. Creates the **FlowStudio Desktop Shortcut** pointing to the hidden System Tray launcher.
4. Registers the Chrome Native Messaging host (`HKCU\Software\Google\Chrome\NativeMessagingHosts\com.flowstudio.bridge`).
5. Copies `%USERPROFILE%\FlowStudio\extension` to your clipboard ready for `chrome://extensions`.

### Fast Update (Windows PC)
- Click **Update Now** inside the Chrome extension popup, **Check for Updates** in the system tray, double-click `update.bat`, re-run the `install.ps1` one-liner, or run:
  ```powershell
  powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\FlowStudio\scripts\self_update.ps1" -InstallDir "$env:USERPROFILE\FlowStudio"
  ```

### Clean Uninstall (Windows PC)
- Click **Uninstall** in the Batch Studio Web UI, **Uninstall FlowStudio...** in the tray menu, or run:
  ```powershell
  powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\FlowStudio\uninstall.ps1"
  ```

### Manual Installation (Windows PC)
> **Requirement:** [Python 3.12 (64-bit)](https://www.python.org/downloads/release/python-3120/) is required for native `.pyd` engine modules.

```cmd
git clone https://github.com/darshanrathod27/flowstudio-gemini-watermark-remover.git %USERPROFILE%\FlowStudio
cd /d %USERPROFILE%\FlowStudio
setup_portable.bat
```

---

## 🍎 macOS (Apple Silicon M1/M2/M3/M4) — Install, Update & Uninstall

### 1-Command Fast Install (macOS Terminal)
Open **Terminal** on macOS and run:

```bash
curl -fsSL https://raw.githubusercontent.com/darshanrathod27/flowstudio-gemini-watermark-remover/main/install.sh | bash
```

What [`install.sh`](https://raw.githubusercontent.com/darshanrathod27/flowstudio-gemini-watermark-remover/main/install.sh) sets up automatically:
1. Clones or syncs FlowStudio into `~/FlowStudio` (override with `FLOWSTUDIO_DIR`).
2. Ensures [Homebrew](https://brew.sh/) `python@3.12` and `ffmpeg` are installed and configures a Python 3.12 `.venv` with PyTorch Metal **MPS** GPU support.
3. Builds `/Applications/FlowStudio.app` (or `~/Applications/FlowStudio.app`) Menu Bar launcher and registers `~/Library/Application Support/Google/Chrome/NativeMessagingHosts/com.flowstudio.bridge.json`.
4. Launches `FlowStudio.app` silently and copies `~/FlowStudio/extension` via `pbcopy`.

### Fast Update (macOS)
- Click **Update Now** inside the Chrome extension popup, **Check for Updates** in the Menu Bar, re-run `install.sh`, or run:
  ```bash
  curl -fsSL https://raw.githubusercontent.com/darshanrathod27/flowstudio-gemini-watermark-remover/main/scripts/self_update.sh | bash
  ```

### Clean Uninstall (macOS)
- Click **Uninstall** in the Batch Studio Web UI, use **Uninstall FlowStudio...** in the Menu Bar, or run:
  ```bash
  bash ~/FlowStudio/uninstall.sh
  ```

### Manual Installation (macOS)
```bash
git clone https://github.com/darshanrathod27/flowstudio-gemini-watermark-remover.git ~/FlowStudio
bash ~/FlowStudio/install.sh
```

---

## 🧩 Chrome Extension Setup (Windows PC & macOS)

1. Open Google Chrome and navigate to `chrome://extensions`.
2. Turn ON **Developer mode** (top-right).
3. Click **Load unpacked**, paste the copied extension folder path (`Ctrl+V` on Windows / `Cmd+V` on macOS — `%USERPROFILE%\FlowStudio\extension` or `~/FlowStudio/extension`), and press Enter.
4. Pin **FlowStudio Local Bridge** to your Chrome toolbar, open [Google Flow (`https://flow.google.com`)](https://flow.google.com), and open Batch Studio anytime at `http://127.0.0.1:8765`.

---

## 🛠️ Troubleshooting: Windows 11 "Smart App Control Blocked"

Windows 11 may display **"Smart App Control blocked an app"** when running local `python.exe`, `ffmpeg.exe`, `ffprobe.exe`, or compiled `.pyd` binaries without commercial EV code signing.

1. Open **Windows Security** from the Start Menu.
2. Go to **App & browser control** → **Smart App Control settings**.
3. Set **Smart App Control** to **Off** and restart Chrome / Terminal.

> **Security Note:** Leave Microsoft Defender Virus & Threat Protection **ON**; only Smart App Control needs to be turned off for unsigned local tools.

---

## 🔄 Extension Workflow

```
[Google Flow Web App (https://flow.google.com)]
         │
         ▼  (Image / Video / Project .zip download triggered)
[Chrome Extension (MV3)]
         │
         ├── Server Standby? ──► [Native Host Bridge] ──► Wakes Tray / FlowStudio.app (127.0.0.1:8765)
         │
         ▼
[Localhost FastAPI Engine]
         │
         ├── 1. Safe ZIP Extract (Colons preserved, duplicates -> _2/_3, magic-byte recovery)
         ├── 2. Reverse-Alpha Watermark Removal (Damage-Only Veto for logo-free image refs)
         ├── 3. Optional Neural Upscaling (1080p / 2K / 4K via CUDA FP16 or Apple Metal MPS)
         ├── 4. Clean Output Save + Foreground "Show in Folder" + Activity Summary Badge
         └── 5. Native System Clipboard Copy (CF_DIB on Windows / NSPasteboard on macOS)
```

---

## 🖥️ Hardware Tiers & Performance

| GPU / Hardware | Memory / VRAM | Tile Size | Worker Threads | Precision |
| :--- | :--- | :--- | :--- | :--- |
| **RTX 4090 / 5090 / 5080** | 16 GB+ VRAM | 640 px | 4 Parallel Workers | CUDA FP16 |
| **RTX 5050 / 4060 / 3060** | 8 GB VRAM | 400 px | 4 Logo / 2 Upscale | CUDA FP16 |
| **RTX 3050 Laptop / 2060** | 4–7.5 GB VRAM | 320 px | 2 Parallel Workers | CUDA FP16 |
| **Apple Silicon Pro/Max/Ultra** | ≥ 24 GB Unified | 512 px | 4 Logo / 1 Upscale | Metal MPS FP16 |
| **Apple Silicon M1/M2/M3/M4** | 8–16 GB Unified | 384 px | 2 Logo / 1 Upscale | Metal MPS FP16 |
| **Universal CPU (Win / Intel Mac)** | System RAM | 192 px | 2 Parallel Workers | FP32 |

---

## 🔒 Privacy & Offline Guarantee

- **Zero Cloud Uploads**: All media processing, neural upscaling, and watermark removal run `100%` locally on your machine.
- **Zero Telemetry**: No user analytics, tracking cookies, or media telemetry.
- **User-Mode Only**: Requires no Administrator or `sudo` rights (`HKCU` registry on Windows; user `NativeMessagingHosts` on macOS).

---

## 📄 License

Distributed under the [MIT License](https://github.com/darshanrathod27/flowstudio-gemini-watermark-remover/blob/main/LICENSE).
Created and maintained by [darshanrathod27](https://github.com/darshanrathod27).

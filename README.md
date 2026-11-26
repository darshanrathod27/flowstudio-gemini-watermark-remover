<div align="center">

# FlowStudio

### Ultra-Clean Watermark Remover & Neural AI Upscaler for Google Flow Media

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/Python-3.12%20(64--bit)-brightgreen.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![CUDA](https://img.shields.io/badge/CUDA-12.8%20Ready-76B900.svg)](https://developer.nvidia.com/cuda-zone)
[![Apple Silicon](https://img.shields.io/badge/Apple%20Silicon-Metal%20MPS-000000.svg)](https://developer.apple.com/metal/)
[![Platform: Windows | macOS](https://img.shields.io/badge/Platform-Windows%2010%2F11%20%7C%20macOS%20arm64-0078D6.svg)](https://github.com/darshanrathod27/flowstudio-gemini-watermark-remover)

**100% Offline • Zero Inpainting Blur • Exact Mathematical Reverse-Alpha • Auto-Scaling Hardware Engine**

</div>

---

## Highlights

- **Exact Reverse-Alpha Reconstruction**: Unlike typical AI inpainters that blur and hallucinate background pixels, FlowStudio mathematically inverts the semi-transparent alpha overlay, restoring pristine underlying pixels with zero blur and zero outward bleed.
- **Cross-Platform Desktop Experience (Windows + macOS Apple Silicon)**: Runs windowlessly via System Tray & Desktop Shortcut on Windows (`pythonw.exe tray_app.py`) and as a native Menu Bar app (`FlowStudio.app`) on macOS M1/M2/M3/M4.
- **Neural AI 1080p / 2K / 4K Upscaler**: Integrated Real-ESRGAN pipeline accelerated by CUDA FP16 on NVIDIA GPUs and Metal MPS FP16 on Apple Silicon.
- **Hardware Video Encoding**: Automatically selects `h264_nvenc` / `h264_qsv` on Windows or native Apple Media Engine `h264_videotoolbox` on macOS, with tuned `libx264` fallback.
- **Always-Alive Extension Bridge & Show in Folder**: Chrome Extension communicates via Native Messaging stdio to auto-boot the local engine on port `8765`, featuring zero-skip download interception, safe download settle guards, 1-click **"Show in Folder"** reveal buttons per completed job, and 1-click in-popup updater.
- **Smart Project ZIP & In-Place Folder Clean**: Automatically extracts Flow project `.zip` exports cleanly into `Downloads/<ProjectName>` or updates local project folders **in-place** via `workspace/temp/`, cleaning 100% of videos and watermarked images while preserving logo-free reference images and `.txt`/`.json` metadata untouched.
- **Instant Clipboard Copy**: Places cleaned full-resolution images straight into your system clipboard (`CF_DIB` on Windows, native `NSPasteboard` on macOS) so you can paste (`Ctrl+V` / `Cmd+V`) directly into Discord, Photoshop, or Slack.

---

## ⚡ 1-Command Fast Install (Windows PowerShell)

Open PowerShell and paste:

```powershell
irm https://raw.githubusercontent.com/darshanrathod27/flowstudio-gemini-watermark-remover/main/install.ps1 | iex
```

The installer will:
1. Clone or download the repository to `%USERPROFILE%\FlowStudio`.
2. Configure Python 3.12, PyTorch (CUDA / CPU), and verify FFmpeg binaries.
3. Auto-create the **FlowStudio Desktop Shortcut Icon** pointing to the hidden System Tray app.
4. Register the Native Messaging Auto-Start bridge in your user registry (`HKCU`).
5. Copy the extension folder path to your clipboard.

---

## 🍎 1-Command Fast Install (macOS Apple Silicon M1/M2/M3/M4)

Open **Terminal** on macOS and paste:

```bash
curl -fsSL https://raw.githubusercontent.com/darshanrathod27/flowstudio-gemini-watermark-remover/main/install.sh | bash
```

The installer will:
1. Clone or sync FlowStudio into `~/FlowStudio` (override with `FLOWSTUDIO_DIR`).
2. Ensure Homebrew `python@3.12` and `ffmpeg` are installed and configure a dedicated Python 3.12 virtual environment with PyTorch Metal **MPS** GPU support.
3. Build `FlowStudio.app` (Menu Bar launcher) and register the Chrome Native Messaging host (`~/Library/Application Support/Google/Chrome/NativeMessagingHosts/com.flowstudio.bridge.json`).
4. Launch the Menu Bar app silently and copy `~/FlowStudio/extension` to your clipboard via `pbcopy`.

### macOS Features & 1-Click Uninstall
- **Apple Silicon Acceleration**: Uses PyTorch Metal (`mps`) FP16 batched upscaling + Apple Media Engine `h264_videotoolbox` encoding, native `NSPasteboard` image clipboard copy, and Finder folder picking.
- **Clean Uninstall**: Click **Uninstall** in the Batch Studio Web UI, use the Menu Bar **Uninstall FlowStudio...** action, or run:
  ```bash
  bash ~/FlowStudio/uninstall.sh
  ```

---

## Chrome Extension Setup (Windows & macOS)

1. Navigate to `chrome://extensions` in Google Chrome and turn on **Developer mode** (top-right).
2. Click **Load unpacked**, paste the copied extension folder path (`Ctrl+V` on Windows / `Cmd+V` on macOS), and hit Enter.
3. Pin **FlowStudio** to your Chrome toolbar!

---

## 🚀 Fast Re-Install & Updates (~10 Seconds)

- **Windows**: Re-run `install.ps1` or `setup_portable.bat`, or click **Update Now** inside the extension popup.
- **macOS**: Re-run the `curl ... | bash` install command or click **Update Now** inside the extension popup — your existing Python 3.12 `.venv` and models are preserved cleanly.

---

## 🛠️ Manual Installation

> **Requirement:** Python 3.12 (64-bit on Windows; `python@3.12` on macOS) is required for native compiled engine acceleration (`.pyd` / `.so`).

- **Windows**:
  ```cmd
  git clone https://github.com/darshanrathod27/flowstudio-gemini-watermark-remover.git
  cd flowstudio-gemini-watermark-remover
  setup_portable.bat
  ```
- **macOS**:
  ```bash
  git clone https://github.com/darshanrathod27/flowstudio-gemini-watermark-remover.git ~/FlowStudio
  bash ~/FlowStudio/install.sh
  ```

---

## Troubleshooting: Windows 11 "Smart App Control Blocked"

Windows 11 may occasionally display a **"Smart App Control blocked an app"** notification when executing FlowStudio components (`python.exe`, `ffmpeg.exe`, `ffprobe.exe`, or local native `.pyd` modules).

### Why this appears
Windows 11 Smart App Control automatically blocks newly compiled or unsigned open-source developer binaries that do not have commercial EV code signing certificates.

### How to fix it (3 steps)
1. Open **Windows Security** from the Start Menu.
2. Go to **App & browser control** → **Smart App Control settings**.
3. Set **Smart App Control** to **Off** and restart Chrome / Terminal.

> **Important Security Note:** **Do NOT turn off Windows Defender / Antivirus!** Your regular Microsoft Defender Virus & Threat Protection remains 100% ON and keeps your PC protected.

---

## 🧩 Extension Workflow

```
[Google Flow Web App]
         │
         ▼  (Download triggered)
[Chrome Extension (MV3)]
         │
         ├── Server Offline? ──► [Native Host Bridge] ──► Auto-Spawns Tray / Menu Bar (Port 8765)
         │
         ▼
[Localhost FastAPI Engine]
         │
         ├── 1. Mathematical Reverse-Alpha Watermark Removal (0 ms blur)
         ├── 2. Optional Neural Upscaling (1080p / 2K / 4K via CUDA / MPS)
         ├── 3. Direct Save to Downloads / Project Folder (In-Place or Renamed)
         └── 4. Native System Clipboard Copy (CF_DIB / NSPasteboard)
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

- **Zero Cloud Uploads**: All media processing, neural upscaling, and watermark removal occurs 100% locally on your machine.
- **Zero Telemetry**: No user analytics, tracking cookies, or external phone-home requests.
- **User-Mode Only**: Requires no Administrator or `sudo` rights (`HKCU` registry on Windows; user Chrome `NativeMessagingHosts` on macOS).

---

## 📄 License

Distributed under the [MIT License](LICENSE).
Created and maintained by [darshanrathod27](https://github.com/darshanrathod27).

<div align="center">

# FlowStudio

### Ultra-Clean Watermark Remover & Neural AI Upscaler for Google Flow Media

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/Python-3.12%20(64--bit)-brightgreen.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![CUDA](https://img.shields.io/badge/CUDA-12.8%20Ready-76B900.svg)](https://developer.nvidia.com/cuda-zone)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D6.svg)](https://microsoft.com)

**100% Offline • Zero Inpainting Blur • Exact Mathematical Reverse-Alpha • Auto-Scaling Hardware Engine**

</div>

---

## Highlights

- **Exact Reverse-Alpha Reconstruction**: Unlike typical AI inpainters that blur and hallucinate background pixels, FlowStudio mathematically inverts the semi-transparent alpha overlay, restoring pristine underlying pixels with zero blur and zero outward bleed.
- **Hidden System Tray & Desktop Icon**: Runs completely windowless in the background (`pythonw.exe tray_app.py`) with zero black command prompt windows cluttering your desktop. 1-click launch from the Desktop icon anytime.
- **Neural AI 1080p / 2K / 4K Upscaler**: Integrated Real-ESRGAN CUDA FP16 pipeline for razor-sharp upscaling of both Anime/Illustration and Photorealistic/Cinematic content.
- **Always-Alive Extension Bridge**: Chrome Extension communicates via Windows Native Messaging stdio to auto-boot the local engine on port `8765`, featuring zero-bypass download interception, 60-minute self-heal, and 1-click in-popup updater.
- **Silent Windows Clipboard Copy**: Automatically places cleaned full-resolution images into your Windows clipboard (`CF_DIB`) in under 15ms so you can paste (`Ctrl+V`) directly into Discord, Photoshop, or Slack.
- **Hardware Auto-Scaler**: Automatically detects NVIDIA NVENC (RTX 5050 / 40 / 30 series with PyTorch CUDA 12.8), Intel QSV, AMD AMF, or multi-core CPU fallback.

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

Then simply:
1. Navigate to `chrome://extensions` and turn on **Developer mode**.
2. Click **Load unpacked**, press `Ctrl+V`, and hit Enter.
3. Pin **FlowStudio** to your Chrome toolbar!

---

## 🚀 Fast Re-Install & Updates (~10 Seconds)

If you already have FlowStudio installed, re-running `install.ps1` or `setup_portable.bat` automatically detects your existing healthy Python 3.12 and PyTorch environment, skipping 3GB downloads and finishing repairs/updates in **~10 seconds**.

---

## 🛠️ Manual Installation

> **Requirement:** [Python 3.12 (64-bit)](https://www.python.org/downloads/release/python-3120/) is required on Windows for native C machine-code binary acceleration (`.pyd`).

If you prefer setting up manually:

```cmd
git clone https://github.com/darshanrathod27/flowstudio-gemini-watermark-remover.git
cd flowstudio-gemini-watermark-remover
setup_portable.bat
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
         ├── Server Offline? ──► [Native Host Bridge] ──► Auto-Spawns Tray App (Port 8765)
         │
         ▼
[Localhost FastAPI Engine]
         │
         ├── 1. Mathematical Reverse-Alpha Watermark Removal (0 ms blur)
         ├── 2. Optional Neural Upscaling (1080p / 2K / 4K)
         ├── 3. Direct Save to Downloads / Subfolder
         └── 4. Native Windows Clipboard Copy (CF_DIB)
```

---

## 🖥️ Hardware Tiers & Performance

| GPU / Hardware | VRAM | Tile Size | Worker Threads | Precision |
| :--- | :--- | :--- | :--- | :--- |
| **RTX 4090 / 5090 / 5080** | 16 GB+ | 640 px | 4 Parallel Workers | CUDA FP16 |
| **RTX 5050 / 4060 / 3060** | 8 GB | 512 px | 3 Parallel Workers | CUDA FP16 |
| **RTX 3050 Laptop / 2060** | 6 GB | 320 px | 2 Parallel Workers | CUDA FP16 |
| **GTX 1650 / 4GB GPUs** | 4 GB | 192 px | 2 Parallel Workers | CUDA FP16 |
| **Universal CPU** | System RAM | 192 px | N/2 CPU Threads | FP32 |

---

## 🔒 Privacy & Offline Guarantee

- **Zero Cloud Uploads**: All media processing, neural upscaling, and watermark removal occurs 100% locally on your machine.
- **Zero Telemetry**: No user analytics, tracking cookies, or external phone-home requests.
- **User-Mode Only**: Requires no Windows Administrator rights (`HKCU` user-level registry for Chrome Native Messaging).

---

## 📄 License

Distributed under the [MIT License](LICENSE).
Created and maintained by [darshanrathod27](https://github.com/darshanrathod27).

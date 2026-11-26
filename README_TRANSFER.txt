================================================================================
                    FLOWSTUDIO PRO - PORTABLE TRANSFER GUIDE
================================================================================

FlowStudio is 100% portable and self-contained. It runs at full hardware power
on your NVIDIA RTX 3050 laptop, RTX 5050 8GB desktop, or any friend's PC.

--------------------------------------------------------------------------------
STEP 1: TRANSFER FOLDER
--------------------------------------------------------------------------------
Copy the entire "FlowStudio" directory (via USB drive, LAN share, or ZIP archive)
to any drive on your target PC (e.g. C:\FlowStudio or D:\FlowStudio).

--------------------------------------------------------------------------------
STEP 2: RUN 1-CLICK SETUP
--------------------------------------------------------------------------------
Double-click:
    setup_portable.bat

What it does automatically:
- Creates an isolated .venv environment in the folder.
- Detects your graphics card (NVIDIA RTX -> installs CUDA PyTorch; CPU -> Universal CPU PyTorch).
- Installs all dependencies and the Spandrel neural upscaling engine.
- Verifies the bundled FFmpeg binary in ./bin/.

--------------------------------------------------------------------------------
STEP 3: CHOOSE YOUR LAUNCH MODE
--------------------------------------------------------------------------------

MODE A: DAILY SILENT GOOGLE FLOW MODE (RECOMMENDED FOR WORKFLOW)
Double-click:
    start_background.vbs

What happens:
- Silently launches the local FlowStudio GPU engine in the background.
- Zero black console windows and zero browser tabs opened.
- You work directly in Google Chrome / Google Flow: every image or video you
  download is automatically cleaned directly inside your Downloads folder,
  and cleaned images are copied to Windows clipboard ready for instant Ctrl+V!

MODE B: BATCH STUDIO MODE (FOR 50+ BULK DRAG-AND-DROP & ZIP)
Double-click:
    start.bat

What happens:
- Starts the server (or uses the already running background server).
- Automatically opens the Pro Studio Web UI (http://127.0.0.1:8765) in your browser.
- Drag & drop 50+ images/videos at once, inspect with 4x before/after split slider,
  and download organized batch ZIP archives.

TO STOP THE SERVER:
Double-click:
    stop_server.bat

--------------------------------------------------------------------------------
STEP 4: LOAD CHROME EXTENSION (ONE-TIME SETUP)
--------------------------------------------------------------------------------
1. Open Google Chrome and navigate to:
       chrome://extensions/
2. Enable "Developer mode" toggle in the top-right corner.
3. Click the "Load unpacked" button in the top-left.
4. Select the "FlowStudio\extension" folder inside this directory.
5. The FlowStudio icon will appear in your Chrome toolbar.
   - Shows active GPU status (RTX 3050, RTX 5050, etc.).
   - Configure extension options: Extension Active, Add _clean suffix, AI Upscale.
   - Monitor real-time cleaning progress in the extension popup with zero web tabs!
================================================================================

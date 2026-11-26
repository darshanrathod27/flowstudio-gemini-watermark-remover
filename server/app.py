import os
import sys
import json
import time
import uuid
import shutil
import zipfile
import subprocess
import asyncio
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import threading

try:
    from engine.hardware import get_hardware_profile, get_config
    from engine.project_processor import scan_project_folder
    from server.job_manager import JobManager
except ImportError:
    from ..engine.hardware import get_hardware_profile, get_config
    from ..engine.project_processor import scan_project_folder
    from .job_manager import JobManager

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _load_server_version() -> str:
    try:
        vpath = os.path.join(base_dir, "version.json")
        if os.path.exists(vpath):
            with open(vpath, "r", encoding="utf-8") as f:
                data = json.load(f)
                return str(data.get("version", "3.9.0")).strip().lstrip("v")
    except Exception:
        pass
    return "3.9.0"

SERVER_VERSION = _load_server_version()
app = FastAPI(title="FlowStudio Pro Core", version=SERVER_VERSION)

@app.on_event("startup")
def startup_warmup():
    def _warm():
        time.sleep(3.5)
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.init()
        except Exception:
            pass
    threading.Thread(target=_warm, daemon=True).start()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

manager = JobManager()

ui_dir = os.path.join(base_dir, "ui")
os.makedirs(ui_dir, exist_ok=True)
if os.path.isdir(ui_dir):
    app.mount("/ui", StaticFiles(directory=ui_dir), name="ui")

class ConfigUpdateRequest(BaseModel):
    perf_mode: Optional[str] = None
    port: Optional[int] = None
    default_upscale: Optional[str] = None
    remove_watermark_default: Optional[bool] = None

class ExtensionIngestRequest(BaseModel):
    file_path: str
    upscale_mode: str = "off"
    remove_logo: bool = True
    add_clean_suffix: bool = False
    copy_image_to_clipboard: bool = True
    replace_original: bool = False

class ExtensionFetchAndCleanRequest(BaseModel):
    url: str
    filename: Optional[str] = None
    upscale_mode: str = "off"
    remove_logo: bool = True
    add_clean_suffix: bool = False
    save_dir: Optional[str] = None

class ZipDownloadRequest(BaseModel):
    job_ids: Optional[List[str]] = None
    organize_folders: Optional[bool] = False

class ProjectScanRequest(BaseModel):
    folder_path: str

class ProjectRunRequest(BaseModel):
    folder_path: str
    mode: str = "in_place"
    output_name: Optional[str] = None
    upscale_mode: str = "off"
    upscale_clean_files: bool = False

class ExtensionIngestZipRequest(BaseModel):
    file_path: str
    output_name: Optional[str] = None
    upscale_mode: str = "off"
    upscale_clean_files: Optional[bool] = None
    delete_source_zip: bool = True

class OpenFolderRequest(BaseModel):
    folder_path: str

class UninstallRequest(BaseModel):
    clean_caches: bool = True
    confirm: str = ""

@app.get("/")
def serve_index():
    index_file = os.path.join(ui_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file, media_type="text/html")
    return JSONResponse({"status": "FlowStudio Backend Running", "ui": "Place index.html in ./FlowStudio/ui/"})

@app.get("/api/health")
def get_health():
    profile = get_hardware_profile()
    pools = manager.get_pool_status()
    return {
        "status": "ONLINE",
        "version": SERVER_VERSION,
        "tier": profile["tier"],
        "device": profile["device"],
        "cuda_available": profile["cuda_available"],
        "gpu_name": profile["gpu_name"],
        "vram_gb": profile["vram_gb"],
        "cpu_cores": profile["cpu_cores"],
        "encoder_vendor": profile["encoder_vendor"],
        "video_encoder": profile["video_encoder"],
        "hevc_encoder": profile["hevc_encoder"],
        "perf_mode": profile["perf_mode"],
        "masks_loaded": len(manager.remover.master_masks),
        "tile_size": profile["tile_size"],
        "logo_workers": profile["logo_workers"],
        "upscale_workers": profile["upscale_workers"],
        "has_ai_upscaler": profile["has_ai_upscaler"],
        "pools": pools,
        "ffmpeg_path": "./FlowStudio/bin/ffmpeg.exe"
    }

@app.get("/api/config")
def read_configuration():
    return get_config()

@app.post("/api/config")
def update_configuration(req: ConfigUpdateRequest):
    config_path = os.path.join(base_dir, "config.json")
    current = get_config()
    if req.perf_mode is not None:
        current["perf_mode"] = req.perf_mode
    if req.port is not None:
        current["port"] = req.port
    if req.default_upscale is not None:
        current["default_upscale"] = req.default_upscale
    if req.remove_watermark_default is not None:
        current["remove_watermark_default"] = req.remove_watermark_default

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save config: {e}")

    if req.perf_mode:
        get_hardware_profile(perf_mode=req.perf_mode)

    return {"status": "UPDATED", "config": current}

@app.post("/api/jobs/upload")
@app.post("/api/upload")
@app.post("/api/process")
async def upload_jobs(
    files: List[UploadFile] = File(...),
    upscale_mode: str = Form("off"),
    remove_logo: str = Form("true"),
    output_format: str = Form("original")
):
    import uuid
    batch_id = str(uuid.uuid4())
    created_jobs = []
    should_remove_logo = str(remove_logo).strip().lower() in ("true", "1", "yes", "on")

    for file in files:
        safe_name = os.path.basename(file.filename)
        save_path = os.path.join(manager.uploads_dir, f"{str(uuid.uuid4())[:8]}_{safe_name}")
        content = await file.read()
        with open(save_path, "wb") as f:
            f.write(content)

        job = manager.create_job(
            filename=safe_name,
            input_path=save_path,
            upscale_mode=upscale_mode,
            remove_logo=should_remove_logo,
            batch_id=batch_id,
            source="web"
        )
        created_jobs.append(job)

    return {"batch_id": batch_id, "jobs": created_jobs}

@app.post("/api/extension/fetch-and-clean")
async def extension_fetch_and_clean(req: ExtensionFetchAndCleanRequest):
    import urllib.request
    import uuid
    import shutil
    import cv2
    try:
        from engine.clipboard_win import copy_image_to_windows_clipboard
    except ImportError:
        from ..engine.clipboard_win import copy_image_to_windows_clipboard

    tmp_dir = os.path.join(base_dir, "workspace", "tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    url_str = req.url
    raw_name = req.filename or os.path.basename(url_str.split("?")[0]) or f"download_{str(uuid.uuid4())[:8]}"
    if "." not in raw_name:
        raw_name += ".png"

    stem, ext = os.path.splitext(raw_name)
    ext_lower = ext.lower()
    if ext_lower not in [".mp4", ".mov", ".mkv", ".webm", ".jpg", ".jpeg", ".png", ".webp"]:
        raw_name += ".png"
        stem, ext = os.path.splitext(raw_name)
        ext_lower = ext.lower()

    temp_in = os.path.join(tmp_dir, f"fetch_{uuid.uuid4()}_{raw_name}")
    try:
        req_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) FlowStudio/2.0"}
        request_obj = urllib.request.Request(url_str, headers=req_headers)
        with urllib.request.urlopen(request_obj) as resp, open(temp_in, "wb") as out_f:
            shutil.copyfileobj(resp, out_f)
    except Exception as e:
        if os.path.exists(temp_in):
            try: os.unlink(temp_in)
            except Exception: pass
        raise HTTPException(status_code=400, detail=f"Failed to fetch media from URL: {e}")

    # Determine destination directory
    target_dir = None
    if req.save_dir and os.path.isdir(req.save_dir):
        target_dir = req.save_dir
    else:
        user_dl = os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "Downloads")
        if os.path.isdir(user_dl):
            target_dir = user_dl
        else:
            target_dir = manager.outputs_dir

    clean_filename = f"{stem}_clean{ext}" if req.add_clean_suffix else raw_name
    final_output_path = os.path.join(target_dir, clean_filename)

    is_video = ext_lower in [".mp4", ".mov", ".mkv", ".webm"]
    copied = False

    try:
        try:
            from engine.video_pipeline import process_video_stream, process_image_file
        except ImportError:
            from ..engine.video_pipeline import process_video_stream, process_image_file

        if not is_video:
            temp_out = os.path.join(tmp_dir, f"out_{uuid.uuid4()}_{clean_filename}")
            proc_res = process_image_file(
                temp_in,
                temp_out,
                upscale_mode=req.upscale_mode,
                remove_logo=req.remove_logo,
                remover=manager.remover,
                upscaler=manager.upscaler
            )
            if os.path.exists(final_output_path):
                try: os.unlink(final_output_path)
                except Exception: pass
            shutil.move(temp_out, final_output_path)
            copied = copy_image_to_windows_clipboard(final_output_path)
        else:
            temp_out = os.path.join(tmp_dir, f"out_{uuid.uuid4()}_{clean_filename}")
            proc_res = process_video_stream(
                temp_in,
                temp_out,
                upscale_mode=req.upscale_mode,
                remove_logo=req.remove_logo,
                remover=manager.remover,
                upscaler=manager.upscaler
            )
            if os.path.exists(final_output_path):
                try: os.unlink(final_output_path)
                except Exception: pass
            shutil.move(temp_out, final_output_path)

        job = manager.create_job(
            filename=clean_filename,
            input_path=temp_in,
            upscale_mode=req.upscale_mode,
            remove_logo=req.remove_logo,
            source="extension",
            add_clean_suffix=req.add_clean_suffix,
            copy_image_to_clipboard=copied,
            auto_start=False
        )
        job["status"] = "completed"
        job["detected_mask"] = proc_res.get("detected_mask", "none")
        job["output_path"] = final_output_path
        job["progress_pct"] = 100.0
        job["file_type"] = "video" if is_video else "image"
        manager.jobs[job["id"]] = job

        return {
            "status": "COMPLETED",
            "job_id": job["id"],
            "filename": clean_filename,
            "file_path": final_output_path,
            "copied_to_clipboard": copied,
            "file_type": "video" if is_video else "image",
            "size_bytes": os.path.getsize(final_output_path) if os.path.exists(final_output_path) else 0
        }
    finally:
        if os.path.exists(temp_in):
            try:
                os.unlink(temp_in)
            except Exception:
                pass

@app.post("/api/media/probe")
async def probe_media_endpoint(
    file_path: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None)
):
    try:
        from engine.video_pipeline import probe_video
    except ImportError:
        from ..engine.video_pipeline import probe_video
    import cv2
    import uuid

    target_path = None
    temp_probe = False
    if file is not None:
        temp_path = os.path.join(manager.uploads_dir, f"probe_{uuid.uuid4()}_{file.filename}")
        content = await file.read()
        with open(temp_path, "wb") as f:
            f.write(content)
        target_path = temp_path
        temp_probe = True
    elif file_path and os.path.exists(file_path):
        target_path = file_path

    if not target_path or not os.path.exists(target_path):
        raise HTTPException(status_code=400, detail="Valid file or file_path required")

    ext = os.path.splitext(target_path)[1].lower()
    is_video = ext in [".mp4", ".mov", ".mkv", ".webm"]

    try:
        if is_video:
            meta = probe_video(target_path)
            meta["file_type"] = "video"
        else:
            img = cv2.imread(target_path)
            if img is None:
                raise HTTPException(status_code=400, detail="Could not decode image")
            h, w = img.shape[:2]
            meta = {
                "width": w,
                "height": h,
                "fps": 0,
                "duration": 0,
                "nb_frames": 1,
                "has_audio": False,
                "audio_codec": None,
                "file_type": "image"
            }
        meta["filename"] = os.path.basename(target_path)
        meta["size_bytes"] = os.path.getsize(target_path)
        return meta
    finally:
        if temp_probe and os.path.exists(target_path):
            try:
                os.unlink(target_path)
            except Exception:
                pass

@app.post("/api/extension/ingest")
def extension_ingest(req: ExtensionIngestRequest):
    if not os.path.exists(req.file_path):
        raise HTTPException(status_code=404, detail="Local file not found")

    filename = os.path.basename(req.file_path)
    stem, ext = os.path.splitext(filename)
    ext_lower = ext.lower()
    valid_exts = [".mp4", ".mov", ".mkv", ".webm", ".jpg", ".jpeg", ".png", ".webp"]
    if ext_lower not in valid_exts:
        raise HTTPException(status_code=400, detail=f"Unsupported media format: {ext}")

    if stem.endswith("_clean") or filename.startswith(".flowtmp_") or ".tmp_flowstudio" in filename:
        return {"status": "SKIPPED", "detail": "File already cleaned or temporary", "file_path": req.file_path}

    job = manager.create_job(
        filename=filename,
        input_path=req.file_path,
        upscale_mode=req.upscale_mode,
        remove_logo=req.remove_logo,
        source="extension",
        replace_original=req.replace_original,
        add_clean_suffix=req.add_clean_suffix,
        copy_image_to_clipboard=req.copy_image_to_clipboard
    )
    return {
        "job_id": job["id"],
        "status": "queued",
        "file_path": req.file_path
    }


@app.post("/api/system/pick-folder")
def pick_project_folder():
    if os.name != "nt":
        return {"ok": False, "cancelled": True, "detail": "Folder picker requires Windows"}

    ps_script = (
        "$OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$owner = New-Object System.Windows.Forms.Form; "
        "$owner.TopMost = $true; "
        "$dlg = New-Object System.Windows.Forms.FolderBrowserDialog; "
        "$dlg.Description = 'Select FlowStudio Project Folder'; "
        "$dlg.ShowNewFolderButton = $true; "
        "$res = $dlg.ShowDialog($owner); "
        "$owner.Dispose(); "
        "if ($res -eq [System.Windows.Forms.DialogResult]::OK -and $dlg.SelectedPath) { Write-Output $dlg.SelectedPath }"
    )
    creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Sta", "-WindowStyle", "Hidden", "-Command", ps_script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            creationflags=creationflags,
        )
        selected = (proc.stdout or "").strip()
        if selected and os.path.isdir(selected):
            return {"ok": True, "path": selected}
        return {"ok": False, "cancelled": True}
    except subprocess.TimeoutExpired:
        return {"ok": False, "cancelled": True, "detail": "Picker timed out"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Folder picker failed: {e}")


@app.post("/api/project/scan")
def scan_project_endpoint(req: ProjectScanRequest):
    if not req.folder_path or not os.path.isdir(req.folder_path):
        raise HTTPException(status_code=404, detail=f"Folder not found: {req.folder_path}")
    try:
        scan = scan_project_folder(req.folder_path, remover=manager.remover)
        return {"ok": True, **scan}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Project scan failed: {e}")


@app.post("/api/project/run")
def run_project_endpoint(req: ProjectRunRequest):
    if not req.folder_path or not os.path.isdir(req.folder_path):
        raise HTTPException(status_code=404, detail=f"Folder not found: {req.folder_path}")
    mode = (req.mode or "in_place").strip().lower()
    if mode not in ("in_place", "new_folder"):
        raise HTTPException(status_code=400, detail="mode must be 'in_place' or 'new_folder'")

    job = manager.create_project_job(
        folder_path=req.folder_path,
        mode=mode,
        output_name=req.output_name,
        upscale_mode=req.upscale_mode,
        upscale_clean_files=req.upscale_clean_files,
        source="web",
    )
    return {
        "ok": True,
        "job_id": job["id"],
        "status": job["status"],
        "mode": mode,
        "folder_path": os.path.abspath(req.folder_path),
        "target_dir": job["output_path"],
    }


@app.post("/api/project/upload-zip")
async def upload_project_zip(
    file: UploadFile = File(...),
    output_name: Optional[str] = Form(None),
    upscale_mode: str = Form("off"),
    upscale_clean_files: str = Form("false"),
):
    safe_name = os.path.basename(file.filename or "FlowProject.zip")
    if not safe_name.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Uploaded archive must be a .zip file")

    save_path = os.path.join(manager.uploads_dir, f"proj_{uuid.uuid4().hex[:8]}_{safe_name}")
    try:
        with open(save_path, "wb") as out_f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                out_f.write(chunk)
        if not zipfile.is_zipfile(save_path):
            raise HTTPException(status_code=400, detail="Invalid or corrupted ZIP archive")
    except HTTPException:
        if os.path.exists(save_path):
            try: os.remove(save_path)
            except Exception: pass
        raise
    except Exception as e:
        if os.path.exists(save_path):
            try: os.remove(save_path)
            except Exception: pass
        raise HTTPException(status_code=500, detail=f"Failed to receive ZIP upload: {e}")

    up_clean = str(upscale_clean_files).strip().lower() in ("true", "1", "yes", "on")
    clean_out_name = output_name.strip() if output_name and output_name.strip() else os.path.splitext(safe_name)[0]
    job = manager.create_project_job(
        zip_path=save_path,
        output_name=clean_out_name,
        upscale_mode=upscale_mode,
        upscale_clean_files=up_clean,
        delete_source_zip=True,
        source="web",
    )
    return {
        "ok": True,
        "job_id": job["id"],
        "status": job["status"],
        "filename": safe_name,
        "target_dir": job["output_path"],
    }


@app.post("/api/extension/ingest-zip")
def extension_ingest_zip(req: ExtensionIngestZipRequest):
    if not req.file_path or not os.path.exists(req.file_path):
        raise HTTPException(status_code=404, detail="Local ZIP file not found")
    if not req.file_path.lower().endswith(".zip") or not zipfile.is_zipfile(req.file_path):
        raise HTTPException(status_code=400, detail="File is not a valid .zip archive")

    fname = os.path.basename(req.file_path)
    if fname.startswith(".flowtmp_") or ".tmp_flowstudio" in fname.lower():
        return {"status": "SKIPPED", "detail": "Temporary archive ignored", "file_path": req.file_path}

    do_upscale = (req.upscale_mode or "off").strip().lower() not in ("off", "none", "")
    upscale_clean = do_upscale if req.upscale_clean_files is None else bool(req.upscale_clean_files)

    job = manager.create_project_job(
        zip_path=req.file_path,
        output_name=req.output_name,
        upscale_mode=req.upscale_mode,
        upscale_clean_files=upscale_clean,
        delete_source_zip=req.delete_source_zip,
        source="extension",
    )
    return {
        "ok": True,
        "job_id": job["id"],
        "status": job["status"],
        "file_path": req.file_path,
        "target_dir": job["output_path"],
    }

@app.get("/api/jobs")
def list_jobs(batch_id: Optional[str] = None, source: Optional[str] = None, limit: Optional[int] = None):
    return manager.list_jobs(batch_id=batch_id, source=source, limit=limit)

@app.post("/api/system/shutdown")
def shutdown_server():
    import threading
    def _exit():
        time.sleep(0.5)
        os._exit(0)
    threading.Thread(target=_exit, daemon=True).start()
    return {"status": "SHUTTING_DOWN"}

@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.post("/api/jobs/{job_id}/pause")
def pause_single_job(job_id: str):
    ok = manager.pause_job(job_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Job cannot be paused (not active or not found)")
    return {"ok": True, "status": "paused", "job_id": job_id}

@app.post("/api/jobs/{job_id}/resume")
def resume_single_job(job_id: str):
    ok = manager.resume_job(job_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Job cannot be resumed (not paused or not found)")
    job = manager.get_job(job_id)
    return {"ok": True, "status": job["status"] if job else "processing", "job_id": job_id}

@app.post("/api/jobs/clear-history")
def clear_history_jobs(source: Optional[str] = Query(None)):
    removed = manager.clear_history(source=source)
    return {"ok": True, "removed": removed}

@app.post("/api/jobs/clear")
def clear_completed_jobs():
    cleared = manager.clear_jobs()
    return {"status": "CLEARED", "count": cleared}

@app.post("/api/jobs/{job_id}/cancel")
def cancel_single_job(job_id: str):
    cancelled = manager.cancel_job(job_id)
    if not cancelled:
        raise HTTPException(status_code=400, detail="Job cannot be cancelled (not active or not found)")
    return {"ok": True, "status": "CANCELLED", "job_id": job_id}

@app.post("/api/jobs/cancel-all")
def cancel_all_jobs():
    count = manager.cancel_all_jobs()
    return {"status": "CANCELLED_ALL", "count": count}

@app.get("/api/jobs/{job_id}/file-base64")
def get_job_file_base64(job_id: str):
    import base64
    job = manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("file_type") != "image":
        raise HTTPException(status_code=400, detail="Base64 push is only supported for images")
    if job.get("status") != "completed" or not os.path.exists(job.get("output_path", "")):
        raise HTTPException(status_code=400, detail="Clean image is not ready yet")

    ext = os.path.splitext(job["filename"])[1].lower()
    mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
    mime = mime_map.get(ext, "application/octet-stream")

    with open(job["output_path"], "rb") as f:
        data_b64 = base64.b64encode(f.read()).decode("utf-8")

    return {
        "job_id": job_id,
        "filename": job["filename"],
        "mime": mime,
        "data_base64": data_b64
    }

@app.delete("/api/jobs/{job_id}")
def delete_single_job(job_id: str):
    deleted = manager.delete_job(job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True, "status": "DELETED", "job_id": job_id}

@app.get("/api/jobs/{job_id}/preview")
def get_job_preview(job_id: str):
    job = manager.get_job(job_id)
    if not job or not os.path.exists(job.get("preview_path", "")):
        raise HTTPException(status_code=404, detail="Preview not available yet")
    return FileResponse(job["preview_path"], media_type="image/png")

@app.get("/api/jobs/{job_id}/preview/before")
def get_job_preview_before(job_id: str):
    job = manager.get_job(job_id)
    if not job or not os.path.exists(job.get("before_crop_path", "")):
        raise HTTPException(status_code=404, detail="Before preview not available yet")
    return FileResponse(job["before_crop_path"], media_type="image/png")

@app.get("/api/jobs/{job_id}/preview/after")
def get_job_preview_after(job_id: str):
    job = manager.get_job(job_id)
    if not job or not os.path.exists(job.get("after_crop_path", "")):
        raise HTTPException(status_code=404, detail="After preview not available yet")
    return FileResponse(job["after_crop_path"], media_type="image/png")

@app.get("/api/jobs/{job_id}/download")
def download_job(job_id: str):
    job = manager.get_job(job_id)
    if not job or not os.path.exists(job.get("output_path", "")):
        raise HTTPException(status_code=404, detail="Output file not ready")
    return FileResponse(job["output_path"], filename=os.path.basename(job["output_path"]))

@app.post("/api/system/open-outputs")
def open_outputs_folder():
    outputs_dir = manager.outputs_dir
    os.makedirs(outputs_dir, exist_ok=True)
    try:
        if os.name == "nt":
            os.startfile(outputs_dir)
        elif sys.platform == "darwin":
            subprocess.run(["open", outputs_dir])
        else:
            subprocess.run(["xdg-open", outputs_dir])
        return {"status": "OPENED", "path": outputs_dir}
    except Exception as e:
        return {"status": "ERROR", "detail": str(e), "path": outputs_dir}

@app.post("/api/system/open-folder")
def open_specific_folder(req: OpenFolderRequest):
    raw_path = (req.folder_path or "").strip()
    if not raw_path:
        raise HTTPException(status_code=400, detail="folder_path is required")
    abs_path = os.path.abspath(raw_path)
    if not os.path.isdir(abs_path):
        raise HTTPException(status_code=404, detail=f"Folder not found: {abs_path}")
    try:
        if os.name == "nt":
            os.startfile(abs_path)
        elif sys.platform == "darwin":
            subprocess.run(["open", abs_path], check=False)
        else:
            subprocess.run(["xdg-open", abs_path], check=False)
        return {"ok": True, "status": "OPENED", "path": abs_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open folder: {e}")


@app.post("/api/system/uninstall")
def uninstall_flowstudio(req: UninstallRequest):
    import tempfile
    if req.confirm != "UNINSTALL_FLOWSTUDIO":
        raise HTTPException(status_code=400, detail="Confirmation token 'UNINSTALL_FLOWSTUDIO' is required")

    abs_base = os.path.abspath(base_dir).rstrip("\\/")
    if (
        "PRIVATE_SOURCE" in abs_base.upper()
        or os.path.isdir(os.path.join(abs_base, "cloud_backend"))
        or os.path.isdir(os.path.join(abs_base, "assets", "masks"))
        or not os.path.isfile(os.path.join(abs_base, "tray_app.py"))
        or not os.path.isdir(os.path.join(abs_base, ".venv"))
    ):
        raise HTTPException(
            status_code=403,
            detail="Developer safety guard refused uninstall: not a standalone runtime install directory.",
        )

    ps_script_path = os.path.join(tempfile.gettempdir(), "flowstudio_self_uninstall.ps1")
    clean_flag = "$true" if req.clean_caches else "$false"
    escaped_base = abs_base.replace("'", "''")

    ps_content = f"""param()
$ErrorActionPreference = 'SilentlyContinue'
Start-Sleep -Milliseconds 1500
$targetDir = '{escaped_base}'
$cleanCaches = {clean_flag}

if ($targetDir -imatch 'PRIVATE_SOURCE' -or (Test-Path (Join-Path $targetDir 'cloud_backend')) -or (Test-Path (Join-Path $targetDir 'assets\\masks'))) {{
    Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
    exit 2
}}
if (-not ((Test-Path (Join-Path $targetDir 'tray_app.py')) -and (Test-Path (Join-Path $targetDir '.venv')))) {{
    Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
    exit 2
}}

try {{
    $null = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/system/shutdown' -Method Post -Body '{{}}' -ContentType 'application/json' -TimeoutSec 2 -ErrorAction SilentlyContinue
}} catch {{}}

$escapedRegex = [Regex]::Escape($targetDir)
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {{
    ($_.Name -match '^python.*\\.exe$') -and ($_.CommandLine -notmatch 'PRIVATE_SOURCE') -and
    (($_.CommandLine -match $escapedRegex) -or ($_.CommandLine -match 'tray_app\\.py|server\\.app:app|uvicorn'))
}} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}

Start-Sleep -Milliseconds 1500

$regPath = 'HKCU:\\Software\\Google\\Chrome\\NativeMessagingHosts\\com.flowstudio.bridge'
if (Test-Path $regPath) {{
    Remove-Item -Path $regPath -Force -ErrorAction SilentlyContinue
}}

$desktopPaths = @([Environment]::GetFolderPath('Desktop'), (Join-Path $env:USERPROFILE 'Desktop')) | Where-Object {{ $_ }} | Select-Object -Unique
foreach ($desk in $desktopPaths) {{
    $lnk = Join-Path $desk 'FlowStudio.lnk'
    if (Test-Path -LiteralPath $lnk) {{
        Remove-Item -LiteralPath $lnk -Force -ErrorAction SilentlyContinue
    }}
}}

Set-Location $env:TEMP
for ($i = 0; $i -lt 4; $i++) {{
    if (Test-Path -LiteralPath $targetDir) {{
        Remove-Item -LiteralPath $targetDir -Recurse -Force -ErrorAction SilentlyContinue
    }}
    if (-not (Test-Path -LiteralPath $targetDir)) {{ break }}
    Start-Sleep -Milliseconds 600
}}
if (Test-Path -LiteralPath $targetDir) {{
    & cmd.exe /c "rmdir /s /q `"$targetDir`"" 2>$null | Out-Null
}}

if ($cleanCaches) {{
    foreach ($cd in @((Join-Path $env:LOCALAPPDATA 'pip\\cache'), (Join-Path $env:LOCALAPPDATA 'uv\\cache'))) {{
        if (Test-Path -LiteralPath $cd) {{
            Remove-Item -LiteralPath $cd -Recurse -Force -ErrorAction SilentlyContinue
        }}
    }}
}}

Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
"""
    with open(ps_script_path, "w", encoding="utf-8") as f:
        f.write(ps_content)

    cflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    launched = False
    if os.name == "nt":
        escaped_ps = ps_script_path.replace("'", "''")
        wmi_cmd = (
            f"$cmd = 'powershell.exe -NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File \"{escaped_ps}\"'; "
            f"$res = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{{ CommandLine = $cmd; CurrentDirectory = $env:TEMP }}; "
            f"exit $res.ReturnValue"
        )
        try:
            r = subprocess.run(
                ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", wmi_cmd],
                creationflags=cflags,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
            launched = (r.returncode == 0)
        except Exception:
            launched = False

        if not launched:
            CREATE_BREAKAWAY_FROM_JOB = 0x01000000
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            for extra in (CREATE_BREAKAWAY_FROM_JOB, 0):
                try:
                    subprocess.Popen(
                        ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-File", ps_script_path],
                        cwd=tempfile.gettempdir(),
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        close_fds=True,
                        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP | extra,
                        startupinfo=startupinfo,
                    )
                    launched = True
                    break
                except Exception:
                    pass

    if not launched:
        raise HTTPException(status_code=500, detail="Failed to launch detached uninstaller process")

    return {
        "ok": True,
        "status": "UNINSTALLING",
        "install_dir": abs_base,
        "clean_caches": bool(req.clean_caches),
    }

@app.post("/api/jobs/download-zip")
def download_zip(req: ZipDownloadRequest):
    zip_path = manager.create_zip_archive(req.job_ids, organize_folders=req.organize_folders or False)
    if not os.path.exists(zip_path):
        raise HTTPException(status_code=500, detail="Failed to create zip archive")
    return FileResponse(zip_path, filename=os.path.basename(zip_path), media_type="application/zip")

@app.websocket("/ws/progress")
async def websocket_progress(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            jobs_list = manager.list_jobs()
            pools = manager.get_pool_status()
            await websocket.send_json({"jobs": jobs_list, "pools": pools})
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass

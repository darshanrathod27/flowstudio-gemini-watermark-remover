import os
import sys
import json
import time
import asyncio
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, UploadFile, File, Form, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

try:
    from engine.hardware import get_hardware_profile, get_config
    from server.job_manager import JobManager
except ImportError:
    from ..engine.hardware import get_hardware_profile, get_config
    from .job_manager import JobManager

app = FastAPI(title="FlowStudio Pro Core", version="3.4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

manager = JobManager()

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
    add_clean_suffix: bool = False
    copy_image_to_clipboard: bool = True

class ExtensionFetchAndCleanRequest(BaseModel):
    url: str
    filename: Optional[str] = None
    upscale_mode: str = "off"
    add_clean_suffix: bool = False
    save_dir: Optional[str] = None

class ZipDownloadRequest(BaseModel):
    job_ids: Optional[List[str]] = None
    organize_folders: Optional[bool] = False

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
async def upload_jobs(
    files: List[UploadFile] = File(...),
    upscale_mode: str = Form("off"),
    remove_logo: str = Form("true"),
    output_format: str = Form("original")
):
    import uuid
    batch_id = str(uuid.uuid4())
    created_jobs = []
    should_remove_logo = str(remove_logo).lower() in ("true", "1", "yes", "on")

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
        if not is_video:
            temp_out = os.path.join(tmp_dir, f"out_{uuid.uuid4()}_{clean_filename}")
            manager.remover.process_image_file(temp_in, temp_out, upscale_mode=req.upscale_mode)
            if os.path.exists(final_output_path):
                try: os.unlink(final_output_path)
                except Exception: pass
            shutil.move(temp_out, final_output_path)
            copied = copy_image_to_windows_clipboard(final_output_path)
        else:
            temp_out = os.path.join(tmp_dir, f"out_{uuid.uuid4()}_{clean_filename}")
            try:
                from engine.video_pipeline import process_video_stream
            except ImportError:
                from ..engine.video_pipeline import process_video_stream
            process_video_stream(temp_in, temp_out, upscale_mode=req.upscale_mode, remove_logo=True, remover=manager.remover, upscaler=manager.upscaler)
            if os.path.exists(final_output_path):
                try: os.unlink(final_output_path)
                except Exception: pass
            shutil.move(temp_out, final_output_path)

        return {
            "status": "COMPLETED",
            "filename": clean_filename,
            "file_path": final_output_path,
            "copied_to_clipboard": copied,
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
        remove_logo=True,
        source="extension",
        add_clean_suffix=req.add_clean_suffix,
        copy_image_to_clipboard=req.copy_image_to_clipboard
    )
    return {
        "job_id": job["id"],
        "status": "queued",
        "file_path": req.file_path
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

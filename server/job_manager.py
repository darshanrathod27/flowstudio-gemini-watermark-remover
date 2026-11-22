import os
import sys
import uuid
import time
import zipfile
import threading
import ctypes
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Dict, Any, List, Optional
import numpy as np
import cv2

try:
    from engine.hardware import get_hardware_profile
    from engine.watermark_remover import WatermarkRemover
    from engine.upscaler import Upscaler
    from engine.video_pipeline import process_video_stream
    from engine.clipboard_win import copy_image_to_windows_clipboard
except ImportError:
    from ..engine.hardware import get_hardware_profile
    from ..engine.watermark_remover import WatermarkRemover
    from ..engine.upscaler import Upscaler
    from ..engine.video_pipeline import process_video_stream
    from ..engine.clipboard_win import copy_image_to_windows_clipboard

def set_keep_awake(enable: bool):
    """Prevents Windows from sleeping or throttling GPU background execution."""
    if os.name == "nt":
        try:
            ES_CONTINUOUS = 0x80000000
            ES_SYSTEM_REQUIRED = 0x00000001
            if enable:
                ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
            else:
                ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        except Exception:
            pass

class JobManager:
    def __init__(self, workspace_dir: Optional[str] = None):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if workspace_dir is None:
            workspace_dir = os.path.join(base_dir, "workspace")
        self.workspace_dir = workspace_dir
        self.uploads_dir = os.path.join(workspace_dir, "uploads")
        self.outputs_dir = os.path.join(workspace_dir, "outputs")
        self.previews_dir = os.path.join(self.outputs_dir, "previews")

        os.makedirs(self.uploads_dir, exist_ok=True)
        os.makedirs(self.outputs_dir, exist_ok=True)
        os.makedirs(self.previews_dir, exist_ok=True)

        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.cancel_events: Dict[str, threading.Event] = {}
        self.job_futures: Dict[str, Future] = {}
        self.active_procs: Dict[str, List[subprocess.Popen]] = {}
        self.listeners: List[Any] = []
        self._lock = threading.Lock()
        self._active_count = 0

        profile = get_hardware_profile()
        logo_workers = profile.get("logo_workers", 4)
        upscale_workers = profile.get("upscale_workers", 1)

        # Thread pools
        self.fast_executor = ThreadPoolExecutor(max_workers=max(2, logo_workers))
        self.upscale_executor = ThreadPoolExecutor(max_workers=max(1, upscale_workers))

        self.remover = WatermarkRemover()
        self.upscaler = Upscaler()

    def _increment_active(self):
        with self._lock:
            self._active_count += 1
            if self._active_count == 1:
                set_keep_awake(True)

    def _decrement_active(self):
        with self._lock:
            self._active_count = max(0, self._active_count - 1)
            if self._active_count == 0:
                set_keep_awake(False)

    def get_pool_status(self) -> Dict[str, Any]:
        with self._lock:
            fast_active = sum(1 for j in self.jobs.values() if j["status"] == "processing" and j.get("upscale_mode") == "off")
            upscale_active = sum(1 for j in self.jobs.values() if j["status"] == "processing" and j.get("upscale_mode") != "off")
            fast_queued = sum(1 for j in self.jobs.values() if j["status"] == "queued" and j.get("upscale_mode") == "off")
            upscale_queued = sum(1 for j in self.jobs.values() if j["status"] == "queued" and j.get("upscale_mode") != "off")
        return {
            "fast_active": fast_active,
            "fast_queued": fast_queued,
            "upscale_active": upscale_active,
            "upscale_queued": upscale_queued
        }

    def create_job(
        self,
        filename: str,
        input_path: str,
        upscale_mode: str = "off",
        remove_logo: bool = True,
        batch_id: Optional[str] = None,
        source: str = "web",
        replace_original: bool = False,
        add_clean_suffix: bool = False,
        copy_image_to_clipboard: bool = True
    ) -> Dict[str, Any]:
        job_id = str(uuid.uuid4())
        if batch_id is None:
            batch_id = str(uuid.uuid4())

        ext = os.path.splitext(filename)[1].lower()
        is_video = ext in [".mp4", ".mov", ".mkv", ".webm"]
        file_type = "video" if is_video else "image"
        base_stem = os.path.splitext(filename)[0]

        if source == "extension":
            # Process into a dedicated local temp output path first
            output_path = os.path.join(self.outputs_dir, f"ext_temp_{job_id}{ext}")
        else:
            out_name = f"{base_stem}_clean{ext}"
            output_path = os.path.join(self.outputs_dir, out_name)

        preview_path = os.path.join(self.previews_dir, f"{job_id}_preview.png")
        before_crop_path = os.path.join(self.previews_dir, f"{job_id}_before_crop.png")
        after_crop_path = os.path.join(self.previews_dir, f"{job_id}_after_crop.png")

        cancel_ev = threading.Event()
        self.cancel_events[job_id] = cancel_ev
        self.active_procs[job_id] = []

        job = {
            "id": job_id,
            "batch_id": batch_id,
            "filename": filename,
            "file_type": file_type,
            "source": source,
            "replace_original": replace_original,
            "add_clean_suffix": add_clean_suffix,
            "copy_image_to_clipboard": copy_image_to_clipboard,
            "copied_to_clipboard": False,
            "input_path": input_path,
            "output_path": output_path,
            "final_saved_path": None,
            "preview_path": preview_path,
            "before_crop_path": before_crop_path,
            "after_crop_path": after_crop_path,
            "status": "queued",
            "progress_pct": 0.0,
            "current_frame": 0,
            "total_frames": 0,
            "elapsed_sec": 0.0,
            "eta_sec": 0.0,
            "detected_mask": "pending",
            "upscale_mode": upscale_mode,
            "remove_logo": remove_logo,
            "error": None,
            "created_at": time.time()
        }

        with self._lock:
            self.jobs[job_id] = job

        is_fast = (upscale_mode.lower() in ("off", "none", ""))
        if is_fast:
            fut = self.fast_executor.submit(self._process_job, job_id)
        else:
            fut = self.upscale_executor.submit(self._process_job, job_id)

        self.job_futures[job_id] = fut
        return job

    def cancel_job(self, job_id: str) -> bool:
        """Instant stop/cancel for both queued and processing jobs."""
        with self._lock:
            job = self.jobs.get(job_id)
            if not job or job["status"] in ("completed", "failed", "cancelled"):
                return False
            curr_status = job["status"]
            job["status"] = "cancelled"
            job["error"] = "Cancelled by user"

        cancel_ev = self.cancel_events.get(job_id)
        if cancel_ev:
            cancel_ev.set()

        if curr_status == "queued":
            fut = self.job_futures.get(job_id)
            if fut:
                fut.cancel()

        procs = self.active_procs.get(job_id, [])
        for p in list(procs):
            try:
                p.kill()
            except Exception:
                pass

        out_p = job.get("output_path")
        if out_p and os.path.exists(out_p):
            try:
                os.remove(out_p)
            except Exception:
                pass

        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

        return True

    def cancel_all_jobs(self) -> int:
        count = 0
        with self._lock:
            target_ids = [jid for jid, j in self.jobs.items() if j["status"] in ("queued", "processing")]
        for jid in target_ids:
            if self.cancel_job(jid):
                count += 1
        return count

    def delete_job(self, job_id: str) -> bool:
        """Auto-cancels if active, cleans up temp files, and removes from queue list."""
        with self._lock:
            job = self.jobs.get(job_id)
            if not job:
                return False

        if job["status"] in ("queued", "processing"):
            self.cancel_job(job_id)

        with self._lock:
            for p in [job.get("output_path"), job.get("preview_path"), job.get("before_crop_path"), job.get("after_crop_path")]:
                if p and os.path.exists(p) and "ext_temp_" in p:
                    try:
                        os.remove(p)
                    except Exception:
                        pass
            if job_id in self.jobs:
                del self.jobs[job_id]
            self.cancel_events.pop(job_id, None)
            self.job_futures.pop(job_id, None)
            self.active_procs.pop(job_id, None)
            return True

    def _process_job(self, job_id: str):
        cancel_ev = self.cancel_events.get(job_id)
        if cancel_ev and cancel_ev.is_set():
            with self._lock:
                if job_id in self.jobs:
                    self.jobs[job_id]["status"] = "cancelled"
            return

        with self._lock:
            if job_id not in self.jobs or self.jobs[job_id]["status"] == "cancelled":
                return
            self.jobs[job_id]["status"] = "processing"

        job = self.jobs[job_id]
        in_p = job["input_path"]
        out_p = job["output_path"]
        prev_p = job["preview_path"]
        before_p = job["before_crop_path"]
        after_p = job["after_crop_path"]
        is_vid = job["file_type"] == "video"
        upscale = job["upscale_mode"]
        rem_logo = job["remove_logo"]
        is_ext = job.get("source") == "extension"
        add_suffix = job.get("add_clean_suffix", False)
        copy_clip = job.get("copy_image_to_clipboard", True)

        self._increment_active()
        try:
            if cancel_ev and cancel_ev.is_set():
                with self._lock:
                    job["status"] = "cancelled"
                return

            if is_vid:
                def on_progress(done, total, elapsed, eta):
                    pct = round((done / max(1, total)) * 100.0, 1)
                    with self._lock:
                        job["current_frame"] = done
                        job["total_frames"] = total
                        job["progress_pct"] = pct
                        job["elapsed_sec"] = round(elapsed, 1)
                        job["eta_sec"] = round(eta, 1)

                procs_list = self.active_procs.setdefault(job_id, [])
                res = process_video_stream(
                    in_p, out_p,
                    upscale_mode=upscale,
                    remove_logo=rem_logo,
                    remover=self.remover,
                    upscaler=self.upscaler,
                    progress_callback=on_progress,
                    cancel_event=cancel_ev,
                    active_procs=procs_list
                )
                if res.get("status") == "CANCELLED" or (cancel_ev and cancel_ev.is_set()):
                    with self._lock:
                        job["status"] = "cancelled"
                    return

                with self._lock:
                    job["detected_mask"] = res.get("detected_mask", "none")

            else:
                if cancel_ev and cancel_ev.is_set():
                    with self._lock:
                        job["status"] = "cancelled"
                    return
                if rem_logo:
                    res = self.remover.process_image_file(in_p, out_p, upscale_mode=upscale, cancel_event=cancel_ev)
                    detected_mask = res.get("detected_mask", "none")
                else:
                    img = cv2.imread(in_p, cv2.IMREAD_COLOR)
                    final_img = self.upscaler.upscale_image(img, upscale_mode=upscale, cancel_event=cancel_ev)
                    os.makedirs(os.path.dirname(os.path.abspath(out_p)), exist_ok=True)
                    cv2.imwrite(out_p, final_img)
                    detected_mask = "disabled"
                with self._lock:
                    job["detected_mask"] = detected_mask

            if cancel_ev and cancel_ev.is_set():
                with self._lock:
                    job["status"] = "cancelled"
                return

            # Generate 4x preview crops
            self._generate_previews(in_p, out_p, prev_p, before_p, after_p, is_video=is_vid)

            # STEP 1: Rock-Solid Direct-to-Downloads Save & Windows Clipboard Copy
            if is_ext and os.path.exists(out_p) and os.path.getsize(out_p) > 0:
                src_dir = os.path.dirname(os.path.abspath(in_p))
                stem, ext = os.path.splitext(os.path.basename(in_p))
                local_tmp = os.path.join(src_dir, f".flowtmp_{job_id[:8]}{ext}")

                if add_suffix:
                    final_path = os.path.join(src_dir, f"{stem}_clean{ext}")
                    shutil.copy2(out_p, local_tmp)
                    os.replace(local_tmp, final_path)

                    if os.path.exists(final_path) and os.path.getsize(final_path) > 0:
                        # Delete original watermarked file with retry loop (Chrome/Defender lock release)
                        for _ in range(15):
                            try:
                                if os.path.exists(in_p) and in_p != final_path:
                                    os.remove(in_p)
                                break
                            except Exception:
                                time.sleep(0.3)
                else:
                    final_path = in_p
                    shutil.copy2(out_p, local_tmp)
                    replaced = False
                    for _ in range(20):
                        try:
                            os.replace(local_tmp, final_path)
                            replaced = True
                            break
                        except Exception:
                            time.sleep(0.3)
                    if not replaced and os.path.exists(local_tmp):
                        try:
                            shutil.copy2(local_tmp, final_path)
                            os.remove(local_tmp)
                        except Exception:
                            pass

                # If image and copy_image_to_clipboard is True, copy to Windows clipboard silently
                if not is_vid and copy_clip:
                    copied = copy_image_to_windows_clipboard(final_path)
                    job["copied_to_clipboard"] = copied

                # Clean up local temp file in outputs_dir
                if os.path.exists(out_p):
                    try:
                        os.remove(out_p)
                    except Exception:
                        pass

                out_p = final_path
                job["final_saved_path"] = final_path

            # Atomic replace for Web UI if requested
            elif job.get("replace_original", False) and os.path.exists(out_p) and os.path.getsize(out_p) > 0:
                replaced = False
                for _ in range(20):
                    try:
                        os.replace(out_p, in_p)
                        out_p = in_p
                        replaced = True
                        break
                    except PermissionError:
                        time.sleep(0.25)
                if not replaced:
                    shutil.copy2(out_p, in_p)
                    try:
                        os.remove(out_p)
                    except Exception:
                        pass
                    out_p = in_p

            with self._lock:
                job["output_path"] = out_p
                job["status"] = "completed"
                job["progress_pct"] = 100.0

        except Exception as e:
            if cancel_ev and cancel_ev.is_set():
                with self._lock:
                    job["status"] = "cancelled"
            else:
                with self._lock:
                    job["status"] = "failed"
                    job["error"] = str(e)
                print(f"[JobManager] Job {job_id} failed: {e}")
        finally:
            self._decrement_active()

    def _generate_previews(self, in_p: str, out_p: str, prev_p: str, before_p: str, after_p: str, is_video: bool = False):
        """Generates before crop, after crop, and side-by-side comparison zoomed 4x into the bottom-right corner."""
        try:
            if is_video:
                cap_in = cv2.VideoCapture(in_p)
                ret1, orig = cap_in.read()
                cap_in.release()

                cap_out = cv2.VideoCapture(out_p)
                ret2, clean = cap_out.read()
                cap_out.release()

                if not ret1 or not ret2 or orig is None or clean is None:
                    return
            else:
                orig = cv2.imread(in_p)
                clean = cv2.imread(out_p)
                if orig is None or clean is None:
                    return

            h, w = orig.shape[:2]
            pw = max(64, int(min(w, h) * 0.25))

            orig_corner = orig[h-pw:h, w-pw:w]

            ch, cw = clean.shape[:2]
            cpw_h = max(64, int(ch * (pw / float(h))))
            cpw_w = max(64, int(cw * (pw / float(w))))
            clean_corner = clean[ch-cpw_h:ch, cw-cpw_w:cw]

            if clean_corner.shape[:2] != orig_corner.shape[:2]:
                clean_corner = cv2.resize(clean_corner, (orig_corner.shape[1], orig_corner.shape[0]), interpolation=cv2.INTER_LANCZOS4)

            before_4x = cv2.resize(orig_corner, (orig_corner.shape[1] * 2, orig_corner.shape[0] * 2), interpolation=cv2.INTER_LANCZOS4)
            after_4x = cv2.resize(clean_corner, (clean_corner.shape[1] * 2, clean_corner.shape[0] * 2), interpolation=cv2.INTER_LANCZOS4)

            cv2.imwrite(before_p, before_4x)
            cv2.imwrite(after_p, after_4x)

            strip = np.hstack([orig_corner, clean_corner])
            cv2.imwrite(prev_p, strip)

        except Exception as e:
            print(f"[JobManager] Failed to generate corner previews: {e}")

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self.jobs.get(job_id)

    def list_jobs(self, batch_id: Optional[str] = None, source: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        with self._lock:
            jobs_list = list(self.jobs.values())
            if batch_id:
                jobs_list = [j for j in jobs_list if j.get("batch_id") == batch_id]
            if source:
                jobs_list = [j for j in jobs_list if j.get("source") == source]
            # Newest first
            jobs_list.sort(key=lambda j: j.get("created_at", 0), reverse=True)
            if limit and limit > 0:
                jobs_list = jobs_list[:limit]
            return jobs_list

    def clear_jobs(self) -> int:
        with self._lock:
            to_remove = [jid for jid, j in self.jobs.items() if j["status"] in ("completed", "failed", "cancelled")]
            for jid in to_remove:
                del self.jobs[jid]
                self.cancel_events.pop(jid, None)
                self.job_futures.pop(jid, None)
                self.active_procs.pop(jid, None)
            return len(to_remove)

    def create_zip_archive(self, job_ids: Optional[List[str]] = None, organize_folders: bool = False) -> str:
        zip_id = str(uuid.uuid4())[:8]
        zip_path = os.path.join(self.outputs_dir, f"FlowStudio_Batch_{zip_id}.zip")

        with self._lock:
            if job_ids is None or len(job_ids) == 0:
                targets = [j for j in self.jobs.values() if j["status"] == "completed"]
            else:
                targets = [self.jobs[jid] for jid in job_ids if jid in self.jobs and self.jobs[jid]["status"] == "completed"]

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for job in targets:
                out_p = job["output_path"]
                if os.path.exists(out_p):
                    fname = os.path.basename(out_p)
                    if organize_folders:
                        subdir = "videos" if job.get("file_type") == "video" else "images"
                        arcname = f"{subdir}/{fname}"
                    else:
                        arcname = fname
                    zf.write(out_p, arcname=arcname)

        return zip_path

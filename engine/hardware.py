import os
import sys
import glob
import json
import shutil
import subprocess
from functools import lru_cache

_CACHED_PROFILE = None

def get_config():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def get_tool(tool_name: str) -> str:
    """
    True Global & Portable Tool Discovery Order:
    1. ./FlowStudio/bin/<tool>.exe (bundled locally)
    2. config.json custom override
    3. System PATH (shutil.which)
    4. Dynamic %LOCALAPPDATA% / %USERPROFILE% wildcards (CapCut, WinGet, Gyan, Program Files)
    Zero hardcoded usernames.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    local_bin = os.path.join(base_dir, "bin", f"{tool_name}.exe")
    if os.path.isfile(local_bin):
        return local_bin

    config = get_config()
    cfg_key = f"{tool_name}_path"
    if config.get(cfg_key) and os.path.isfile(config[cfg_key]):
        return config[cfg_key]

    which_path = shutil.which(tool_name)
    if which_path:
        return which_path

    # Dynamic search in Windows standard user and program directories
    candidates = []
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    
    if local_app_data:
        candidates.extend(glob.glob(os.path.join(local_app_data, "CapCut", "Apps", "*", f"{tool_name}.exe")))
        candidates.extend(glob.glob(os.path.join(local_app_data, "Microsoft", "WinGet", "Packages", "*FFmpeg*", "*", "bin", f"{tool_name}.exe")))
        candidates.extend(glob.glob(os.path.join(local_app_data, "Programs", "*", f"{tool_name}.exe")))
        candidates.extend(glob.glob(os.path.join(local_app_data, "Programs", "*", "bin", f"{tool_name}.exe")))

    candidates.append(os.path.join(r"C:\ffmpeg", "bin", f"{tool_name}.exe"))
    candidates.append(os.path.join(program_files, "ffmpeg", "bin", f"{tool_name}.exe"))

    for path in candidates:
        if os.path.isfile(path):
            return path

    return tool_name

@lru_cache(maxsize=1)
def detect_hardware_encoders(ffmpeg_bin: str):
    """Probes FFmpeg encoders and validates runtime operational capability."""
    encoders_text = ""
    try:
        res = subprocess.run([ffmpeg_bin, "-hide_banner", "-encoders"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        encoders_text = res.stdout
    except Exception:
        pass

    def _test(enc: str) -> bool:
        if enc not in encoders_text:
            return False
        try:
            cmd = [ffmpeg_bin, "-y", "-v", "error", "-f", "lavfi", "-i", "nullsrc=s=64x64:d=0.04", "-c:v", enc, "-f", "null", "-"]
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2)
            return r.returncode == 0
        except Exception:
            return False

    has_nvenc = _test("h264_nvenc")
    has_hevc_nvenc = _test("hevc_nvenc") if has_nvenc else False
    has_amf = _test("h264_amf")
    has_hevc_amf = _test("hevc_amf") if has_amf else False
    has_qsv = _test("h264_qsv")
    has_hevc_qsv = _test("hevc_qsv") if has_qsv else False

    return {
        "nvenc": has_nvenc,
        "hevc_nvenc": has_hevc_nvenc,
        "amf": has_amf,
        "hevc_amf": has_hevc_amf,
        "qsv": has_qsv,
        "hevc_qsv": has_hevc_qsv
    }

def detect_gpu():
    """Detects GPU brand, name, VRAM (GB), and CUDA status."""
    gpu_name = "CPU Only"
    vram_gb = 0.0
    cuda_available = False
    vendor = "cpu"

    # 1. Check PyTorch CUDA if installed
    try:
        import torch
        if torch.cuda.is_available():
            cuda_available = True
            vendor = "nvidia"
            gpu_name = torch.cuda.get_device_name(0)
            vram_bytes = torch.cuda.get_device_properties(0).total_memory
            vram_gb = round(vram_bytes / (1024 ** 3), 1)
            return cuda_available, gpu_name, vram_gb, vendor
    except Exception:
        pass

    # 2. Check nvidia-smi fallback
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True
        )
        line = res.stdout.strip().split("\n")[0]
        if line and "," in line:
            parts = line.split(",")
            gpu_name = parts[0].strip()
            mem_mib = float(parts[1].strip())
            vram_gb = round(mem_mib / 1024.0, 1)
            cuda_available = True
            vendor = "nvidia"
            return cuda_available, gpu_name, vram_gb, vendor
    except Exception:
        pass

    return cuda_available, gpu_name, vram_gb, vendor

def check_ai_upscaler():
    """Checks if torch and spandrel are available for neural upscaling without heavy import overhead."""
    import importlib.util
    return importlib.util.find_spec("spandrel") is not None and importlib.util.find_spec("torch") is not None

def get_hardware_profile(perf_mode: str = "auto"):
    """
    Computes global multi-vendor hardware tiering and full-power auto-scaling.
    Supports auto, full, balanced, and eco performance modes.
    """
    global _CACHED_PROFILE
    config = get_config()
    if perf_mode == "auto":
        perf_mode = config.get("perf_mode", "full")

    if _CACHED_PROFILE is not None and _CACHED_PROFILE.get("perf_mode") == perf_mode:
        return _CACHED_PROFILE

    ffmpeg_bin = get_tool("ffmpeg")
    ffprobe_bin = get_tool("ffprobe")
    enc_support = detect_hardware_encoders(ffmpeg_bin)
    cuda_available, gpu_name, vram_gb, vendor = detect_gpu()
    cpu_cores = os.cpu_count() or 4
    has_ai = check_ai_upscaler()

    # Determine best encoder vendor and codec names
    if cuda_available and enc_support["nvenc"]:
        encoder_vendor = "nvidia"
        video_encoder = "h264_nvenc"
        hevc_encoder = "hevc_nvenc" if enc_support["hevc_nvenc"] else "h264_nvenc"
    elif enc_support["amf"]:
        encoder_vendor = "amd"
        video_encoder = "h264_amf"
        hevc_encoder = "hevc_amf" if enc_support["hevc_amf"] else "h264_amf"
    elif enc_support["qsv"]:
        encoder_vendor = "intel"
        video_encoder = "h264_qsv"
        hevc_encoder = "hevc_qsv" if enc_support["hevc_qsv"] else "h264_qsv"
    else:
        encoder_vendor = "cpu"
        video_encoder = "libx264"
        hevc_encoder = "libx265"

    # Full-Power VRAM Tiering
    if cuda_available:
        if vram_gb >= 11.5:
            tier = "ULTRA"
            tile_size = 640
            base_logo_workers = 4
            base_upscale_workers = 2
            use_fp16 = True
        elif vram_gb >= 7.5:
            tier = "PRO_8GB"
            tile_size = 512
            base_logo_workers = 3
            base_upscale_workers = 1
            use_fp16 = True
        elif vram_gb >= 5.5:
            tier = "GPU_6GB"
            tile_size = 320
            base_logo_workers = 2
            base_upscale_workers = 1
            use_fp16 = True
        else:
            tier = "GPU_4GB"
            tile_size = 192
            base_logo_workers = 2
            base_upscale_workers = 1
            use_fp16 = True
    else:
        tier = "CPU_UNIVERSAL"
        tile_size = 192
        base_logo_workers = max(1, cpu_cores // 2)
        base_upscale_workers = 1
        use_fp16 = False

    # Apply Performance Mode Modifiers
    if perf_mode == "eco":
        logo_workers = 1
        upscale_workers = 1
    elif perf_mode == "balanced":
        logo_workers = max(1, base_logo_workers - 1)
        upscale_workers = base_upscale_workers
    else:  # full
        logo_workers = base_logo_workers
        upscale_workers = base_upscale_workers

    profile = {
        "tier": tier,
        "device": "cuda" if cuda_available else "cpu",
        "cuda_available": cuda_available,
        "gpu_name": gpu_name,
        "vram_gb": vram_gb,
        "cpu_cores": cpu_cores,
        "encoder_vendor": encoder_vendor,
        "video_encoder": video_encoder,
        "hevc_encoder": hevc_encoder,
        "tile_size": tile_size,
        "logo_workers": logo_workers,
        "upscale_workers": upscale_workers,
        "use_fp16": use_fp16,
        "perf_mode": perf_mode,
        "has_ai_upscaler": has_ai,
        "ffmpeg_path": ffmpeg_bin,
        "ffprobe_path": ffprobe_bin
    }
    _CACHED_PROFILE = profile
    return profile

if __name__ == "__main__":
    prof = get_hardware_profile()
    print(json.dumps(prof, indent=2))

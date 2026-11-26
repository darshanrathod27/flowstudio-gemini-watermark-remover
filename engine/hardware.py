import os
import sys
import glob
import json
import shutil
import platform
import subprocess
from functools import lru_cache

_CACHED_PROFILE = None
_CACHED_PLATFORM = None


def get_subprocess_kwargs(extra_flags: int = 0, hide_window: bool = False) -> dict:
    """
    Returns OS-safe subprocess keyword arguments.
    Windows (sys.platform == "win32"): sets CREATE_NO_WINDOW (plus any extra_flags and optional hidden STARTUPINFO).
    macOS / Linux: returns {} so CREATE_NO_WINDOW is never accessed on POSIX.
    """
    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) | int(extra_flags or 0)
        kw = {"creationflags": flags}
        if hide_window:
            startupinfo_cls = getattr(subprocess, "STARTUPINFO", None)
            if startupinfo_cls is not None:
                startupinfo = startupinfo_cls()
                startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0x00000001)
                startupinfo.wShowWindow = 0
                kw["startupinfo"] = startupinfo
        return kw
    return {}


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
    Cross-Platform Global & Portable Tool Discovery Order:
    Windows:
      1. ./FlowStudio/bin/<tool>.exe (bundled locally)
      2. config.json custom override
      3. System PATH (shutil.which)
      4. Dynamic %LOCALAPPDATA% / %USERPROFILE% wildcards (CapCut, WinGet, Gyan, Program Files)
    macOS (darwin):
      1. ./FlowStudio/bin/<tool> (bundled locally, no .exe)
      2. config.json custom override
      3. /opt/homebrew/bin/<tool> (Apple Silicon Homebrew)
      4. /usr/local/bin/<tool> (Intel Homebrew)
      5. System PATH (shutil.which)
    Zero hardcoded usernames.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    is_windows = (sys.platform == "win32")
    exe_name = f"{tool_name}.exe" if is_windows else tool_name

    local_bin = os.path.join(base_dir, "bin", exe_name)
    if os.path.isfile(local_bin):
        return local_bin

    config = get_config()
    cfg_key = f"{tool_name}_path"
    if config.get(cfg_key) and os.path.isfile(config[cfg_key]):
        return config[cfg_key]

    if sys.platform == "darwin":
        for path in (f"/opt/homebrew/bin/{tool_name}", f"/usr/local/bin/{tool_name}"):
            if os.path.isfile(path):
                return path
        which_path = shutil.which(tool_name)
        if which_path:
            return which_path
        return tool_name

    which_path = shutil.which(tool_name)
    if which_path:
        return which_path

    if not is_windows:
        return tool_name

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


@lru_cache(maxsize=4)
def _detect_hardware_encoders_cached(ffmpeg_bin: str, platform_name: str):
    """Probes FFmpeg encoders and validates runtime operational capability (cached in workspace/hw_encoders.json)."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cache_path = os.path.join(base_dir, "workspace", "hw_encoders.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if isinstance(cached, dict):
                cached_plat = cached.get("platform")
                if platform_name == "darwin":
                    if cached_plat == "darwin" and "videotoolbox" in cached:
                        return cached
                elif cached_plat in (None, platform_name):
                    return cached
        except Exception:
            pass

    sub_kwargs = get_subprocess_kwargs()
    encoders_text = ""
    try:
        res = subprocess.run(
            [ffmpeg_bin, "-hide_banner", "-encoders"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True,
            **sub_kwargs
        )
        encoders_text = res.stdout
    except Exception:
        pass

    def _test(enc: str, extra_args=None, size: str = "64x64") -> bool:
        if enc not in encoders_text:
            return False
        try:
            cmd = [
                ffmpeg_bin, "-y", "-v", "error", "-f", "lavfi",
                "-i", f"nullsrc=s={size}:d=0.04", "-c:v", enc
            ]
            if extra_args:
                cmd.extend(extra_args)
            cmd.extend(["-f", "null", "-"])
            r = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=3 if platform_name == "darwin" else 2,
                **sub_kwargs
            )
            return r.returncode == 0
        except Exception:
            return False

    if platform_name == "darwin":
        has_vt = _test(
            "h264_videotoolbox",
            extra_args=["-q:v", "65", "-pix_fmt", "yuv420p"],
            size="256x256"
        )
        has_hevc_vt = _test(
            "hevc_videotoolbox",
            extra_args=["-q:v", "65", "-pix_fmt", "yuv420p"],
            size="256x256"
        ) if has_vt else False
        result = {
            "platform": "darwin",
            "nvenc": False,
            "hevc_nvenc": False,
            "amf": False,
            "hevc_amf": False,
            "qsv": False,
            "hevc_qsv": False,
            "videotoolbox": has_vt,
            "hevc_videotoolbox": has_hevc_vt,
        }
    else:
        has_nvenc = _test("h264_nvenc")
        has_hevc_nvenc = _test("hevc_nvenc") if has_nvenc else False
        has_qsv = _test("h264_qsv")
        has_hevc_qsv = _test("hevc_qsv") if has_qsv else False
        has_amf = _test("h264_amf") if (not has_nvenc and not has_qsv) else False
        has_hevc_amf = _test("hevc_amf") if has_amf else False
        result = {
            "platform": platform_name,
            "nvenc": has_nvenc,
            "hevc_nvenc": has_hevc_nvenc,
            "amf": has_amf,
            "hevc_amf": has_hevc_amf,
            "qsv": has_qsv,
            "hevc_qsv": has_hevc_qsv,
            "videotoolbox": False,
            "hevc_videotoolbox": False,
        }

    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(result, f)
    except Exception:
        pass
    return result


def detect_hardware_encoders(ffmpeg_bin: str):
    """Probes FFmpeg encoders and validates runtime operational capability (cached in workspace/hw_encoders.json)."""
    return _detect_hardware_encoders_cached(ffmpeg_bin, sys.platform)


detect_hardware_encoders.cache_clear = _detect_hardware_encoders_cached.cache_clear


def _detect_darwin_hardware():
    """Fast (<50ms) Apple Silicon / Intel Mac detection via sysctl without importing torch."""
    arch = (platform.machine() or "").lower()
    sub_kwargs = get_subprocess_kwargs()
    chip_name = ""
    mem_gb = 0.0

    try:
        res = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True,
            timeout=1.5, **sub_kwargs
        )
        chip_name = res.stdout.strip()
    except Exception:
        pass

    try:
        res = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True,
            timeout=1.5, **sub_kwargs
        )
        mem_bytes = int(res.stdout.strip())
        mem_gb = round(mem_bytes / (1024.0 ** 3), 1)
    except Exception:
        if hasattr(os, "sysconf"):
            try:
                mem_bytes = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
                mem_gb = round(mem_bytes / (1024.0 ** 3), 1)
            except Exception:
                pass

    if arch in ("arm64", "aarch64"):
        return {
            "arch": arch,
            "mps_available": True,
            "gpu_name": chip_name or "Apple Silicon",
            "vram_gb": mem_gb,
            "vendor": "apple",
        }
    return {
        "arch": arch,
        "mps_available": False,
        "gpu_name": chip_name or "CPU Only",
        "vram_gb": 0.0,
        "vendor": "cpu",
    }


def detect_gpu():
    """
    Rapidly detects GPU brand, name, VRAM/Unified Memory (GB), and CUDA/Apple status in < 100ms.
    Uses nvidia-smi on Windows or sysctl on macOS to avoid slow top-level torch imports.
    """
    if sys.platform == "darwin":
        mac_info = _detect_darwin_hardware()
        return False, mac_info["gpu_name"], mac_info["vram_gb"], mac_info["vendor"]

    gpu_name = "CPU Only"
    vram_gb = 0.0
    cuda_available = False
    vendor = "cpu"
    sub_kwargs = get_subprocess_kwargs()

    # 1. Fast path (<100ms): Check via nvidia-smi without importing torch
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True,
            timeout=1.5, **sub_kwargs
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

    # 2. Check if torch is already imported in sys.modules
    if "torch" in sys.modules:
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

    return cuda_available, gpu_name, vram_gb, vendor


def check_ai_upscaler():
    """Checks if torch and spandrel are available for neural upscaling without heavy import overhead."""
    import importlib.util
    return importlib.util.find_spec("spandrel") is not None and importlib.util.find_spec("torch") is not None


def get_hardware_profile(perf_mode: str = "auto"):
    """
    Computes global multi-vendor hardware tiering and full-power auto-scaling.
    Supports Windows CUDA/AMF/QSV, macOS Apple Silicon MPS/VideoToolbox, and CPU fallback.
    Supports auto, full, balanced, and eco performance modes.
    """
    global _CACHED_PROFILE, _CACHED_PLATFORM
    config = get_config()
    if perf_mode == "auto":
        perf_mode = config.get("perf_mode", "full")

    if (
        _CACHED_PROFILE is not None
        and _CACHED_PROFILE.get("perf_mode") == perf_mode
        and _CACHED_PLATFORM == sys.platform
    ):
        return _CACHED_PROFILE

    ffmpeg_bin = get_tool("ffmpeg")
    ffprobe_bin = get_tool("ffprobe")
    enc_support = detect_hardware_encoders(ffmpeg_bin)
    cuda_available, gpu_name, vram_gb, vendor = detect_gpu()
    cpu_cores = os.cpu_count() or 4
    has_ai = check_ai_upscaler()

    # Determine best encoder vendor and codec names
    if sys.platform == "darwin":
        if enc_support.get("videotoolbox"):
            encoder_vendor = "apple"
            video_encoder = "h264_videotoolbox"
            hevc_encoder = "hevc_videotoolbox" if enc_support.get("hevc_videotoolbox") else "h264_videotoolbox"
        else:
            encoder_vendor = "cpu"
            video_encoder = "libx264"
            hevc_encoder = "libx265"
    elif cuda_available and enc_support.get("nvenc"):
        encoder_vendor = "nvidia"
        video_encoder = "h264_nvenc"
        hevc_encoder = "hevc_nvenc" if enc_support.get("hevc_nvenc") else "h264_nvenc"
    elif enc_support.get("amf"):
        encoder_vendor = "amd"
        video_encoder = "h264_amf"
        hevc_encoder = "hevc_amf" if enc_support.get("hevc_amf") else "h264_amf"
    elif enc_support.get("qsv"):
        encoder_vendor = "intel"
        video_encoder = "h264_qsv"
        hevc_encoder = "hevc_qsv" if enc_support.get("hevc_qsv") else "h264_qsv"
    else:
        encoder_vendor = "cpu"
        video_encoder = "libx264"
        hevc_encoder = "libx265"

    mps_available = False
    if sys.platform == "darwin":
        if vendor == "apple":
            mps_available = True
            device = "mps"
            if vram_gb >= 24.0:
                tier = "APPLE_PRO"
                tile_size = 512
                base_logo_workers = 4
                base_upscale_workers = 1
                use_fp16 = True
            else:
                tier = "APPLE_SILICON"
                tile_size = 384
                base_logo_workers = 2
                base_upscale_workers = 1
                use_fp16 = True
        else:
            device = "cpu"
            tier = "CPU_FALLBACK"
            tile_size = 192
            base_logo_workers = max(1, cpu_cores // 2)
            base_upscale_workers = 1
            use_fp16 = False
    elif cuda_available:
        device = "cuda"
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
        elif vram_gb >= 5.0:
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
        device = "cpu"
        tier = "CPU_FALLBACK"
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
        "device": device,
        "device_hint": device,
        "cuda_available": cuda_available,
        "mps_available": mps_available,
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
        "ffprobe_path": ffprobe_bin,
    }
    _CACHED_PROFILE = profile
    _CACHED_PLATFORM = sys.platform
    return profile


if __name__ == "__main__":
    prof = get_hardware_profile()
    print(json.dumps(prof, indent=2))

import os
import sys
import shutil
import zipfile
import urllib.request

def ensure_ffmpeg():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bin_dir = os.path.join(base_dir, "bin")
    os.makedirs(bin_dir, exist_ok=True)

    ffmpeg_dst = os.path.join(bin_dir, "ffmpeg.exe")
    ffprobe_dst = os.path.join(bin_dir, "ffprobe.exe")

    if os.path.isfile(ffmpeg_dst) and os.path.isfile(ffprobe_dst):
        print("[FFmpeg] Already present in bin/ - skipping download.")
        return True

    # Check system PATH
    sys_ffmpeg = shutil.which("ffmpeg")
    sys_ffprobe = shutil.which("ffprobe")
    if sys_ffmpeg and sys_ffprobe:
        print(f"[FFmpeg] Copying from system PATH: {sys_ffmpeg}")
        shutil.copy2(sys_ffmpeg, ffmpeg_dst)
        shutil.copy2(sys_ffprobe, ffprobe_dst)
        return True

    # Download official essentials build
    url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    zip_temp = os.path.join(bin_dir, "ffmpeg_download.zip")
    print(f"[FFmpeg] Downloading official FFmpeg build from {url}...")

    try:
        def reporthook(blocknum, blocksize, totalsize):
            if totalsize > 0:
                percent = min(100.0, blocknum * blocksize * 100.0 / totalsize)
                sys.stdout.write(f"\r[FFmpeg] Download: {percent:.1f}% ({blocknum*blocksize/(1024*1024):.1f}/{totalsize/(1024*1024):.1f} MB)")
                sys.stdout.flush()

        urllib.request.urlretrieve(url, zip_temp, reporthook)
        print("\n[FFmpeg] Extracting ffmpeg.exe and ffprobe.exe...")

        with zipfile.ZipFile(zip_temp, "r") as z:
            for member in z.namelist():
                base_name = os.path.basename(member).lower()
                if base_name in ("ffmpeg.exe", "ffprobe.exe"):
                    target_file = os.path.join(bin_dir, base_name)
                    with z.open(member) as source, open(target_file, "wb") as target:
                        shutil.copyfileobj(source, target)
                    print(f"[FFmpeg] Extracted {base_name}")

        if os.path.isfile(zip_temp):
            os.remove(zip_temp)

        print("[FFmpeg] Successfully bundled into bin/")
        return True
    except Exception as e:
        print(f"[FFmpeg] Failed to download/extract: {e}")
        if os.path.isfile(zip_temp):
            try:
                os.remove(zip_temp)
            except Exception:
                pass
        return False

if __name__ == "__main__":
    ok = ensure_ffmpeg()
    sys.exit(0 if ok else 1)

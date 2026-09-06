import ipaddress
import json
import os
import shutil
import socket
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp

from ..config import settings


ALLOWED_HOST_SUFFIXES = (
    "bilibili.com", "b23.tv", "douyin.com", "iesdouyin.com", "youtube.com",
    "youtu.be", "xiaohongshu.com", "xhslink.com", "weibo.com", "weibo.cn",
    "tiktok.com", "instagram.com", "twitter.com", "x.com",
)


def validate_public_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("仅支持 HTTPS 视频链接")
    host = parsed.hostname.lower().rstrip(".")
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("无法解析视频地址") from exc
    for item in addresses:
        ip = ipaddress.ip_address(item[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError("不允许访问内网或本机地址")
    supported_host = any(host == suffix or host.endswith(f".{suffix}") for suffix in ALLOWED_HOST_SUFFIXES)
    if not supported_host and not parsed.path.lower().endswith((".mp4", ".mov", ".mkv", ".webm")):
        raise ValueError("暂不支持这个视频平台")
    return url.strip()


def download_video(url: str, task_dir: Path) -> tuple[Path, str]:
    output = str(task_dir / "source.%(ext)s")
    opts = {
        "outtmpl": output,
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "max_filesize": settings.max_upload_mb * 1024 * 1024,
        "socket_timeout": 30,
        "retries": 3,
        "quiet": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(validate_public_url(url), download=True)
        title = info.get("title") or "网络视频"
        requested = info.get("requested_downloads") or []
        candidate = requested[0].get("filepath") if requested else None
    if candidate and Path(candidate).exists():
        return Path(candidate), title
    matches = sorted(task_dir.glob("source.*"))
    if not matches:
        raise RuntimeError("视频下载完成后未找到文件")
    return matches[0], title


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, timeout=60, check=True,
    )
    return float(result.stdout.strip())


def ensure_browser_preview(media_path: Path, task_dir: Path) -> Path:
    """Return an H.264/AAC MP4 for consistent playback in Chromium browsers."""
    preview = task_dir / "preview.mp4"
    if preview.exists() and preview.stat().st_size > 0:
        return preview
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,pix_fmt", "-of", "json", str(media_path)],
        capture_output=True, text=True, timeout=60, check=True,
    )
    streams = json.loads(result.stdout).get("streams") or [{}]
    video = streams[0]
    if media_path.suffix.lower() == ".mp4" and video.get("codec_name") == "h264" and video.get("pix_fmt") == "yuv420p":
        return media_path
    subprocess.run([
        "ffmpeg", "-y", "-i", str(media_path),
        "-vf", "scale=1280:1280:force_original_aspect_ratio=decrease",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(preview),
    ], capture_output=True, timeout=7200, check=True)
    return preview


def split_audio(media_path: Path, task_dir: Path, chunk_seconds: int) -> list[Path]:
    chunk_dir = task_dir / "audio"
    shutil.rmtree(chunk_dir, ignore_errors=True)
    chunk_dir.mkdir(parents=True, exist_ok=True)
    pattern = chunk_dir / "chunk-%05d.mp3"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(media_path), "-vn", "-ac", "1", "-ar", "16000",
        "-b:a", "48k", "-f", "segment", "-segment_time", str(chunk_seconds),
        "-reset_timestamps", "1", str(pattern),
    ], capture_output=True, timeout=7200, check=True)
    chunks = sorted(chunk_dir.glob("chunk-*.mp3"))
    if not chunks:
        raise RuntimeError("未能从视频中提取音频")
    return chunks


def delete_source(path: str | None) -> None:
    if path:
        try:
            source = Path(path)
            source.unlink(missing_ok=True)
            (source.parent / "preview.mp4").unlink(missing_ok=True)
            shutil.rmtree(source.parent / "audio", ignore_errors=True)
        except OSError:
            pass

import html
import ipaddress
import json
import os
import re
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
AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
DIRECT_MEDIA_HOST_SUFFIXES = (
    "qq.com", "qpic.cn", "qlogo.cn", "weixin.qq.com", "wechat.com",
)
MARKDOWN_URL_RE = re.compile(r"\]\((https?://[^)\s]+)\)", re.IGNORECASE)
URL_CANDIDATE_RE = re.compile(r"https?://[^\s<>\"'`\[\]()]+", re.IGNORECASE)


def extract_video_url(value: str) -> str:
    """Extract the first supported video URL from a pasted share message."""
    text = html.unescape(value or "")
    candidates = MARKDOWN_URL_RE.findall(text) + URL_CANDIDATE_RE.findall(text)
    for raw in candidates:
        # Shared Markdown copied from chat apps often escapes &, _, or other
        # URL characters with a backslash. Those escapes are not part of URL.
        candidate = raw.replace("\\", "")
        candidate = candidate.rstrip(".,!?;:，。！？；：)]}》」』")
        try:
            return validate_public_url(candidate)
        except ValueError:
            continue
    raise ValueError("未找到可用的视频链接，请粘贴视频链接或包含视频链接的分享文案")


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
    direct_media_host = any(host == suffix or host.endswith(f".{suffix}") for suffix in DIRECT_MEDIA_HOST_SUFFIXES)
    if not supported_host and not direct_media_host and not parsed.path.lower().endswith((".mp4", ".mov", ".mkv", ".webm")):
        raise ValueError("暂不支持这个视频平台")
    return url.strip()


def media_kind(path: str | Path | None) -> str:
    return "audio" if path and Path(path).suffix.lower() in AUDIO_SUFFIXES else "video"


def source_platform_label(url: str | None) -> str:
    host = (urlparse(url or "").hostname or "").lower().rstrip(".")
    groups = (
        (("douyin.com", "iesdouyin.com"), "抖音"),
        (("xiaohongshu.com", "xhslink.com"), "小红书"),
        (("bilibili.com", "b23.tv"), "哔哩哔哩"),
        (("youtube.com", "youtu.be"), "YouTube"),
        (("tiktok.com",), "TikTok"),
        (("weibo.com", "weibo.cn"), "微博"),
        (("instagram.com",), "Instagram"),
        (("twitter.com", "x.com"), "X / Twitter"),
        (("qq.com", "qpic.cn", "qlogo.cn", "weixin.qq.com", "wechat.com"), "腾讯/微信"),
    )
    for suffixes, label in groups:
        if any(host == suffix or host.endswith(f".{suffix}") for suffix in suffixes):
            return label
    if url and urlparse(url).path.lower().endswith(tuple(VIDEO_SUFFIXES)):
        return "视频直链"
    return "视频链接"


def download_video(url: str, task_dir: Path) -> tuple[Path, str, bool]:
    normalized_url = validate_public_url(url)
    audio_only = False
    try:
        with yt_dlp.YoutubeDL({"noplaylist": True, "quiet": True, "socket_timeout": 30}) as ydl:
            info = ydl.extract_info(normalized_url, download=False)
            duration = float(info.get("duration") or 0)
            audio_only = duration >= settings.url_audio_only_minutes * 60
    except Exception:
        # The download pass below provides the real error message. Metadata
        # lookup is only a hint used to avoid downloading a huge video.
        pass
    output = str(task_dir / "source.%(ext)s")
    opts = {
        "outtmpl": output,
        "format": "bestaudio/best" if audio_only else "bv*+ba/b",
        "noplaylist": True,
        "max_filesize": settings.max_upload_mb * 1024 * 1024,
        "socket_timeout": 30,
        "retries": 3,
        "quiet": True,
    }
    if not audio_only:
        opts["merge_output_format"] = "mp4"
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(normalized_url, download=True)
        title = info.get("title") or "网络视频"
        requested = info.get("requested_downloads") or []
        candidate = requested[0].get("filepath") if requested else None
    if candidate and Path(candidate).exists():
        return Path(candidate), title, audio_only
    matches = sorted(task_dir.glob("source.*"))
    if not matches:
        raise RuntimeError("视频下载完成后未找到文件")
    return matches[0], title, audio_only


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
            shutil.rmtree(source.parent / "visual", ignore_errors=True)
        except OSError:
            pass

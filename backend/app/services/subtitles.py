"""Fetch bounded, public subtitle tracks; callers fall back to audio ASR."""
import html
import ipaddress
import json
import math
import re
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests
import yt_dlp

from .media import _yt_dlp_options, validate_public_url

PAGE_HOSTS = ("youtube.com", "youtu.be", "bilibili.com", "b23.tv")
TRACK_HOSTS = ("youtube.com", "googlevideo.com", "bilibili.com", "hdslb.com", "biliapi.net", "biliapi.com")
MAX_BYTES = 4 * 1024 * 1024


@dataclass
class SubtitleResult:
    title: str
    duration: float
    segments: list[dict]
    source: str
    language: str


class QuietLogger:
    # yt-dlp errors may contain signed URLs. Never log them.
    def debug(self, _): pass
    def info(self, _): pass
    def warning(self, _): pass
    def error(self, _): pass


def _clock(seconds):
    total = int(seconds)
    return f"{total // 3600:02}:{total % 3600 // 60:02}:{total % 60:02}"


def _seconds(value):
    parts = value.replace(",", ".").split(":")
    return sum(float(v) * 60 ** i for i, v in enumerate(reversed(parts)))


def parse_subtitles(text: str, extension: str) -> list[dict]:
    rows = []
    if extension in {"json", "json3"}:
        data = json.loads(text)
        if "body" in data:
            rows = [(s["from"], s["to"], s["content"]) for s in data["body"]]
        else:
            rows = [(s["tStartMs"] / 1000, (s["tStartMs"] + s.get("dDurationMs", 0)) / 1000,
                     "".join(x.get("utf8", "") for x in s.get("segs", [])))
                    for s in data.get("events", []) if "tStartMs" in s]
    else:
        blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").lstrip("\ufeff"))
        for block in blocks:
            lines = block.splitlines()
            for index, line in enumerate(lines):
                match = re.match(r"\s*([\d:.,]+)\s*-->\s*([\d:.,]+)", line)
                if match:
                    rows.append((_seconds(match[1]), _seconds(match[2]), " ".join(lines[index + 1:])))
                    break
    segments = []
    for start, end, value in rows:
        start, end = float(start), float(end)
        value = html.unescape(re.sub(r"<[^>]*>", "", str(value)))
        value = re.sub(r"\s+", " ", value).strip()
        if not value or not all(math.isfinite(x) for x in (start, end)) or start < 0 or end <= start:
            continue
        if len(value) > 20000 or end > 7 * 24 * 3600:
            raise ValueError("字幕内容超出处理范围")
        # Rolling captions sometimes repeat an identical cue.
        if segments and segments[-1]["text"] == value and start <= segments[-1]["end_seconds"]:
            segments[-1]["end_seconds"] = max(end, segments[-1]["end_seconds"])
            segments[-1]["end"] = _clock(segments[-1]["end_seconds"])
            continue
        segments.append({"start": _clock(start), "end": _clock(end),
                         "start_seconds": start, "end_seconds": end, "text": value})
        if len(segments) > 50000:
            raise ValueError("字幕段落过多")
    return segments


def _track_text(session, url):
    for _ in range(6):
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443)
            or not any(host == s or host.endswith("." + s) for s in TRACK_HOSTS)):
            raise ValueError("字幕地址不受支持")
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError("不允许访问内网字幕地址")
        with session.get(url, stream=True, allow_redirects=False, timeout=(10, 20)) as response:
            if response.status_code in {301, 302, 303, 307, 308}:
                url = urljoin(url, response.headers.get("Location", ""))
                continue
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_content(65536):
                body.extend(chunk)
                if len(body) > MAX_BYTES:
                    raise ValueError("字幕文件过大")
            return body.decode("utf-8-sig")
    raise ValueError("字幕重定向次数过多")


def fetch_subtitles(url: str) -> SubtitleResult | None:
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    if not any(host == s or host.endswith("." + s) for s in PAGE_HOSTS):
        return None
    validate_public_url(url)
    options = _yt_dlp_options(url, skip_download=True, socket_timeout=15, retries=0,
        extractor_retries=0, logger=QuietLogger())
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
    if not isinstance(info, dict) or info.get("_type") in {"playlist", "multi_video"}:
        return None
    with requests.Session() as session:
        for key, source in (("subtitles", "author_subtitles"), ("automatic_captions", "automatic_subtitles")):
            tracks = info.get(key) or {}
            languages = sorted(tracks, key=lambda lang: (not lang.startswith("zh"), not lang.startswith("en"), lang))
            if source == "automatic_subtitles":
                # Avoid silently importing platform machine translations.
                original = [lang for lang in languages if lang.endswith("-orig")]
                languages = original or [lang for lang in languages if lang == info.get("language")]
            for language in languages[:5]:
                formats = sorted(tracks[language], key=lambda f: {"json3": 0, "json": 1, "vtt": 2, "srt": 3}.get(f.get("ext"), 99))
                for track in formats:
                    if track.get("ext") not in {"json3", "json", "vtt", "srt"} or not track.get("url"):
                        continue
                    try:
                        segments = parse_subtitles(_track_text(session, track["url"]), track["ext"])
                    except (ValueError, KeyError, TypeError, requests.RequestException, OSError):
                        continue
                    if segments:
                        raw_duration = float(info.get("duration") or 0)
                        duration = max(raw_duration if math.isfinite(raw_duration) else 0, max(s["end_seconds"] for s in segments))
                        return SubtitleResult(str(info.get("title") or "视频字幕")[:300], duration,
                                              segments, source, language.removesuffix("-orig"))
    return None

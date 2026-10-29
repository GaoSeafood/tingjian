import html
from http.cookiejar import MozillaCookieJar
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
import yt_dlp

from ..config import settings
from .kuaishou import download_kuaishou_video, is_kuaishou_url


ALLOWED_HOST_SUFFIXES = (
    "bilibili.com", "b23.tv", "douyin.com", "iesdouyin.com", "youtube.com",
    "youtu.be", "xiaohongshu.com", "xhslink.com", "weibo.com", "weibo.cn",
    "tiktok.com", "instagram.com", "twitter.com", "x.com",
    "kuaishou.com", "kuaishou.cn", "gifshow.com",
    "vimeo.com", "dailymotion.com", "dai.ly", "reddit.com", "redd.it", "twitch.tv",
)
AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
DIRECT_MEDIA_HOST_SUFFIXES = (
    "qq.com", "qpic.cn", "qlogo.cn", "weixin.qq.com", "wechat.com",
    "oceanengine.com",
)
DOUYIN_MEDIA_HOST_SUFFIXES = (
    "douyinvod.com", "douyinstatic.com", "douyincdn.com", "bytecdn.cn",
    "pstatp.com", "snssdk.com",
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
    if parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("不支持含登录信息或自定义端口的视频链接")
    host = parsed.hostname.lower().rstrip(".")
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("无法解析视频地址") from exc
    for item in addresses:
        ip = ipaddress.ip_address(item[4][0])
        if not ip.is_global:
            raise ValueError("不允许访问内网或本机地址")
    supported_host = any(host == suffix or host.endswith(f".{suffix}") for suffix in ALLOWED_HOST_SUFFIXES)
    direct_media_host = any(host == suffix or host.endswith(f".{suffix}") for suffix in DIRECT_MEDIA_HOST_SUFFIXES)
    if not supported_host and not direct_media_host and not _direct_media_suffix(url):
        raise ValueError("暂不支持这个视频平台")
    return url.strip()


def media_kind(path: str | Path | None) -> str:
    if not path:
        return "video"
    suffix = Path(path).suffix.lower()
    if suffix in AUDIO_SUFFIXES:
        return "audio"
    if suffix == ".webm" and Path(path).is_file():
        try:
            return "video" if _has_video_stream(Path(path)) else "audio"
        except (OSError, subprocess.SubprocessError):
            pass
    return "video"


def source_platform_label(url: str | None) -> str:
    host = (urlparse(url or "").hostname or "").lower().rstrip(".")
    groups = (
        (("douyin.com", "iesdouyin.com"), "抖音"),
        (("kuaishou.com", "kuaishou.cn", "gifshow.com"), "快手"),
        (("xiaohongshu.com", "xhslink.com"), "小红书"),
        (("bilibili.com", "b23.tv"), "哔哩哔哩"),
        (("youtube.com", "youtu.be"), "YouTube"),
        (("tiktok.com",), "TikTok"),
        (("weibo.com", "weibo.cn"), "微博"),
        (("instagram.com",), "Instagram"),
        (("twitter.com", "x.com"), "X / Twitter"),
        (("vimeo.com",), "Vimeo"),
        (("dailymotion.com", "dai.ly"), "Dailymotion"),
        (("reddit.com", "redd.it"), "Reddit"),
        (("twitch.tv",), "Twitch"),
        (("oceanengine.com",), "抖音"),
        (("qq.com", "qpic.cn", "qlogo.cn", "weixin.qq.com", "wechat.com"), "腾讯/微信"),
    )
    for suffixes, label in groups:
        if any(host == suffix or host.endswith(f".{suffix}") for suffix in suffixes):
            return label
    if url and urlparse(url).path.lower().endswith(tuple(VIDEO_SUFFIXES)):
        return "视频直链"
    return "视频链接"


def _cookie_file_for_url(url: str) -> str | None:
    """Return the persisted Douyin cookie file only for Douyin requests."""
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    is_douyin = host == "douyin.com" or host.endswith(".douyin.com") or host == "iesdouyin.com" or host.endswith(".iesdouyin.com")
    if is_douyin and settings.douyin_cookie_file.is_file() and settings.douyin_cookie_file.stat().st_size > 0:
        return str(settings.douyin_cookie_file)
    return None


def _douyin_browser_user_agent(url: str) -> str | None:
    """Return the Chrome UA synced with the Douyin cookie session."""
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    is_douyin = host == "douyin.com" or host.endswith(".douyin.com") or host == "iesdouyin.com" or host.endswith(".iesdouyin.com")
    path = settings.douyin_user_agent_file
    if not is_douyin or not path.is_file():
        return None
    try:
        user_agent = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if len(user_agent) > 512 or not all(marker in user_agent for marker in ("Mozilla/5.0", "AppleWebKit/", "Chrome/", "Safari/")):
        return None
    return user_agent


class _YtDlpDiagnosticLogger:
    """Capture yt-dlp warnings so platform HTTP failures survive error mapping."""

    def __init__(self):
        self.messages: list[str] = []

    def debug(self, message: str) -> None:
        pass

    def info(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        self.messages.append(str(message))

    def error(self, message: str) -> None:
        self.messages.append(str(message))


def _is_safe_douyin_media_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower().rstrip(".")
    if not any(host == suffix or host.endswith(f".{suffix}") for suffix in DOUYIN_MEDIA_HOST_SUFFIXES):
        return False
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False
    for item in addresses:
        address = ipaddress.ip_address(item[4][0])
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
            return False
    return True


def _has_audio_stream(media_path: Path) -> bool:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(media_path)],
        capture_output=True, text=True, timeout=30,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def _has_video_stream(media_path: Path) -> bool:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(media_path)],
        capture_output=True, text=True, timeout=30,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def _download_douyin_audio_track(audio_urls: list[str], task_dir: Path, session: requests.Session, max_bytes: int) -> tuple[Path, str]:
    output = task_dir / "source-audio.mp3"
    temporary = task_dir / "source-audio.part"
    for audio_url in dict.fromkeys(audio_urls):
        if not _is_safe_douyin_media_url(audio_url) or Path(urlparse(audio_url).path).suffix.lower() != ".mp3":
            continue
        temporary.unlink(missing_ok=True)
        try:
            with session.get(audio_url, stream=True, allow_redirects=True, timeout=(20, 90)) as response:
                if response.status_code != 200:
                    continue
                content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                if not content_type.startswith("audio/"):
                    continue
                expected_size = int(response.headers.get("content-length") or 0)
                if expected_size > max_bytes:
                    continue
                written = 0
                with temporary.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        written += len(chunk)
                        if written > max_bytes:
                            break
                        handle.write(chunk)
                if written > max_bytes or (expected_size and written != expected_size) or written < 16:
                    continue
                probe = subprocess.run(
                    ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(temporary)],
                    capture_output=True, text=True, timeout=30,
                )
                if probe.returncode != 0 or not probe.stdout.strip():
                    continue
                temporary.replace(output)
                return output, audio_url
        except (requests.RequestException, OSError, subprocess.SubprocessError):
            continue
    temporary.unlink(missing_ok=True)
    raise RuntimeError("抖音播放器没有提供可用的配套音轨")


def _douyin_aweme_id(url: str) -> str | None:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in ("aweme_id", "modal_id", "item_id", "video_id"):
        for candidate in query.get(key) or []:
            if candidate.isdigit() and len(candidate) >= 10:
                return candidate
    match = re.search(r"/(?:video|note)/(\d{10,})(?:/|$)", parsed.path)
    if match:
        return match.group(1)
    return None


def _download_douyin_with_browser(
    url: str,
    task_dir: Path,
    progress_callback=None,
    *,
    source_video_path: Path | None = None,
    audio_only: bool = False,
    resolve_only: bool = False,
):
    """Use the synced browser session to capture and stream Douyin's MP4 URL."""
    from playwright.sync_api import sync_playwright

    cookie_path = _cookie_file_for_url(url)
    user_agent = _douyin_browser_user_agent(url)
    if not cookie_path or not user_agent:
        raise RuntimeError("抖音 Cookie 或 Chrome 标识未同步")

    cookie_jar = MozillaCookieJar(cookie_path)
    try:
        cookie_jar.load(ignore_discard=True, ignore_expires=True)
    except Exception as exc:
        raise RuntimeError("无法读取抖音登录 Cookie") from exc

    browser_cookies = []
    for cookie in cookie_jar:
        if cookie.is_expired():
            continue
        domain = cookie.domain.lstrip(".").lower()
        if not any(domain == suffix or domain.endswith(f".{suffix}") for suffix in ("douyin.com", "iesdouyin.com")):
            continue
        item = {
            "name": cookie.name,
            "value": cookie.value,
            "path": cookie.path or "/",
            "secure": bool(cookie.secure),
        }
        if cookie.domain_specified:
            item["domain"] = cookie.domain if cookie.domain.startswith(".") else f".{domain}"
        else:
            item["url"] = f"https://{domain}{cookie.path or '/'}"
        if cookie.expires and cookie.expires > 0:
            item["expires"] = int(cookie.expires)
        if "HttpOnly" in cookie._rest:
            item["httpOnly"] = True
        browser_cookies.append(item)
    if not browser_cookies:
        raise RuntimeError("抖音 Cookie 已过期，请重新同步")

    session = requests.Session()
    session.cookies.update(cookie_jar)
    session.headers.update({
        "User-Agent": user_agent,
        "Referer": url,
        "Origin": "https://www.douyin.com",
        "Accept": "*/*",
        "Accept-Encoding": "identity",
    })
    candidates: dict[str, dict] = {}
    detail_responses = []
    audio_urls = []
    preferred_video_urls = []
    title = "抖音视频"
    expected_duration = 0.0

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            context = browser.new_context(user_agent=user_agent, viewport={"width": 1365, "height": 900})
            for cookie in browser_cookies:
                try:
                    context.add_cookies([cookie])
                except Exception:
                    # A malformed or obsolete individual cookie must not keep
                    # the rest of the browser session from being used.
                    continue
            if audio_only or resolve_only:
                def block_platform_media(route):
                    media_host = (urlparse(route.request.url).hostname or "").lower().rstrip(".")
                    if any(media_host == suffix or media_host.endswith(f".{suffix}") for suffix in DOUYIN_MEDIA_HOST_SUFFIXES):
                        route.abort()
                    else:
                        route.continue_()
                context.route("**/*", block_platform_media)
            page = context.new_page()

            def capture_media_response(response):
                try:
                    response_url = urlparse(response.url)
                    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                    if (
                        response.status == 200
                        and "aweme" in response_url.path.lower()
                        and "json" in content_type
                        and len(detail_responses) < 32
                    ):
                        detail_responses.append(response)
                    if response.status not in (200, 206) or not content_type.startswith("video/"):
                        return
                    media_url = response.url
                    if not _is_safe_douyin_media_url(media_url):
                        return
                    content_range = response.headers.get("content-range", "")
                    match = re.search(r"/(\d+)$", content_range)
                    size = int(match.group(1)) if match else int(response.headers.get("content-length") or 0)
                    previous = candidates.get(media_url)
                    if not previous or size > previous["size"]:
                        candidates[media_url] = {"size": size, "content_type": content_type}
                except Exception:
                    return

            page.on("response", capture_media_response)
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(5000)
            if not audio_only and not resolve_only:
                page.evaluate("""async () => {
                    for (const video of document.querySelectorAll('video')) {
                        video.muted = true;
                        try { await video.play(); } catch {}
                    }
                }""")
                page.wait_for_timeout(4000)
            try:
                title = (page.title() or title).removesuffix(" - 抖音").removesuffix(" | 抖音").strip() or title
            except Exception:
                pass
            try:
                expected_duration = float(page.evaluate("""() => Math.max(0, ...Array.from(document.querySelectorAll('video'))
                    .map(video => Number.isFinite(video.duration) ? video.duration : 0))"""))
            except Exception:
                pass
            for detail_response in detail_responses:
                try:
                    detail = (detail_response.json().get("aweme_detail") or {})
                    play_url = ((detail.get("music") or {}).get("play_url") or {})
                    for audio_url in play_url.get("url_list") or []:
                        if audio_url not in audio_urls and _is_safe_douyin_media_url(audio_url):
                            audio_urls.append(audio_url)
                    video = detail.get("video") or {}
                    media_duration = float(video.get("duration") or 0)
                    if media_duration > 0:
                        expected_duration = max(expected_duration, media_duration / 1000 if media_duration > 1000 else media_duration)
                    video_addresses = [video.get("play_addr"), video.get("download_addr")]
                    video_addresses.extend(item.get("play_addr") for item in video.get("bit_rate") or [])
                    for address in video_addresses:
                        for video_url in (address or {}).get("url_list") or []:
                            if video_url not in preferred_video_urls and _is_safe_douyin_media_url(video_url):
                                preferred_video_urls.append(video_url)
                except Exception:
                    continue
            if not audio_urls or not preferred_video_urls:
                aweme_id = _douyin_aweme_id(page.url) or _douyin_aweme_id(url)
                if aweme_id:
                    try:
                        media_urls = page.evaluate("""async (awemeId) => {
                            const query = new URLSearchParams({
                                aweme_id: awemeId,
                                aid: "6383",
                                channel: "channel_pc_web",
                            });
                            const response = await fetch(
                                `/aweme/v1/web/aweme/detail/?${query.toString()}`,
                                { credentials: "include", headers: { Accept: "application/json" } },
                            );
                            if (!response.ok) return { audio: [], video: [] };
                            const detail = (await response.json()).aweme_detail || {};
                            const video = detail.video || {};
                            const videoUrls = [];
                            for (const address of [
                                video.play_addr,
                                video.download_addr,
                                ...(video.bit_rate || []).map(item => item.play_addr),
                            ]) {
                                if (address && Array.isArray(address.url_list)) videoUrls.push(...address.url_list);
                            }
                            return {
                                audio: (((detail.music || {}).play_url || {}).url_list || []),
                                video: videoUrls,
                                duration: video.duration || 0,
                            };
                        }""", aweme_id)
                        for audio_url in (media_urls or {}).get("audio") or []:
                            if audio_url not in audio_urls and _is_safe_douyin_media_url(audio_url):
                                audio_urls.append(audio_url)
                        for video_url in (media_urls or {}).get("video") or []:
                            if video_url not in preferred_video_urls and _is_safe_douyin_media_url(video_url):
                                preferred_video_urls.append(video_url)
                        media_duration = float((media_urls or {}).get("duration") or 0)
                        if media_duration > 0:
                            expected_duration = max(expected_duration, media_duration / 1000 if media_duration > 1000 else media_duration)
                    except Exception:
                        pass
        finally:
            browser.close()

    task_dir.mkdir(parents=True, exist_ok=True)
    if audio_only or resolve_only:
        playback_url = next(iter(dict.fromkeys(preferred_video_urls)), None)
        if not playback_url and candidates:
            playback_url = max(candidates.items(), key=lambda item: item[1]["size"])[0]
        if not playback_url or not _is_safe_douyin_media_url(playback_url):
            raise RuntimeError("抖音没有提供可用于网页播放的视频直链")
        playback_audio_url = next((item for item in audio_urls if _is_safe_douyin_media_url(item)), None)
        if resolve_only:
            return None, title[:300], playback_url, playback_audio_url
        audio_path, playback_audio_url = _download_douyin_audio_track(
            audio_urls, task_dir, session, settings.max_upload_mb * 1024 * 1024,
        )
        if expected_duration > 0:
            audio_duration = probe_duration(audio_path)
            if abs(audio_duration - expected_duration) > max(5.0, expected_duration * 0.03):
                audio_path.unlink(missing_ok=True)
                raise RuntimeError("抖音配套音轨时长与视频不匹配")
        return audio_path, title[:300], playback_url, playback_audio_url

    existing_video = Path(source_video_path) if source_video_path else None
    use_existing_video = bool(
        existing_video
        and existing_video.is_file()
        and existing_video.suffix.lower() == ".mp4"
        and existing_video.stat().st_size > 0
    )
    if use_existing_video and expected_duration > 0:
        try:
            duration = probe_duration(existing_video)
            if abs(duration - expected_duration) > max(5.0, expected_duration * 0.03):
                use_existing_video = False
        except Exception:
            use_existing_video = False

    max_bytes = settings.max_upload_mb * 1024 * 1024
    preferred = [] if use_existing_video else [
        (0, media_url, "video/mp4")
        for media_url in dict.fromkeys(preferred_video_urls)
        if _is_safe_douyin_media_url(media_url)
    ]
    ranked = [] if use_existing_video else preferred + [
        (metadata["size"], media_url, metadata["content_type"])
        for media_url, metadata in sorted(candidates.items(), key=lambda item: item[1]["size"], reverse=True)
        if media_url not in preferred_video_urls
    ][:24]
    measured = []
    oversized = False
    for size, media_url, content_type in ranked:
        if size > max_bytes:
            oversized = True
            continue
        if not size:
            try:
                with session.get(media_url, headers={"Range": "bytes=0-1023"}, stream=True, timeout=(15, 25)) as probe:
                    content_range = probe.headers.get("content-range", "")
                    match = re.search(r"/(\d+)$", content_range)
                    size = int(match.group(1)) if match else int(probe.headers.get("content-length") or 0)
            except requests.RequestException:
                continue
        if size > max_bytes:
            oversized = True
            continue
        measured.append((size, media_url, content_type))

    if not measured and not use_existing_video:
        if oversized:
            raise RuntimeError(f"视频文件超过 {settings.max_upload_mb} MB 限制")
        raise RuntimeError("抖音播放器没有提供可下载的视频流")

    output = existing_video if use_existing_video else task_dir / "source.mp4"
    temporary = task_dir / "source.browser.part"
    video_downloaded = use_existing_video
    for total_size, media_url, expected_type in ([] if use_existing_video else sorted(measured, reverse=True)):
        if not _is_safe_douyin_media_url(media_url):
            continue
        temporary.unlink(missing_ok=True)
        try:
            with session.get(media_url, stream=True, allow_redirects=True, timeout=(20, 120)) as response:
                if response.status_code not in (200, 206):
                    continue
                content_type = response.headers.get("content-type", "").split(";", 1)[0].lower() or expected_type
                if not content_type.startswith("video/"):
                    continue
                content_range = response.headers.get("content-range", "")
                match = re.search(r"/(\d+)$", content_range)
                expected_size = int(match.group(1)) if match else int(response.headers.get("content-length") or total_size)
                if expected_size > max_bytes:
                    oversized = True
                    continue
                written = 0
                last_progress = 0
                with temporary.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        written += len(chunk)
                        if written > max_bytes:
                            oversized = True
                            break
                        handle.write(chunk)
                        if progress_callback and expected_size:
                            progress = min(94, int(5 + written / expected_size * 89))
                            if progress >= last_progress + 5:
                                last_progress = progress
                                progress_callback(progress)
                if written > max_bytes:
                    continue
                if expected_size and written != expected_size:
                    continue
                if written < 16:
                    continue
                try:
                    duration = probe_duration(temporary)
                except Exception:
                    continue
                if expected_duration > 0 and abs(duration - expected_duration) > max(5.0, expected_duration * 0.03):
                    continue
                temporary.replace(output)
                video_downloaded = True
                break
        except (requests.RequestException, OSError, subprocess.SubprocessError):
            continue
    temporary.unlink(missing_ok=True)
    if not video_downloaded and oversized:
        raise RuntimeError(f"视频文件超过 {settings.max_upload_mb} MB 限制")
    if not video_downloaded:
        raise RuntimeError("抖音浏览器流无法完整下载")

    if not _has_audio_stream(output):
        audio_path, _ = _download_douyin_audio_track(audio_urls, task_dir, session, max_bytes)
        merged = task_dir / "source.with-audio.mp4"
        merged.unlink(missing_ok=True)
        result = subprocess.run([
            "ffmpeg", "-hide_banner", "-y", "-i", str(output), "-i", str(audio_path),
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
            "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(merged),
        ], capture_output=True, text=True, timeout=7200)
        if result.returncode != 0 or not merged.is_file() or not _has_audio_stream(merged):
            merged.unlink(missing_ok=True)
            audio_path.unlink(missing_ok=True)
            raise RuntimeError("抖音配套音轨无法与视频合并")
        if merged.stat().st_size > max_bytes:
            merged.unlink(missing_ok=True)
            audio_path.unlink(missing_ok=True)
            raise RuntimeError(f"视频文件超过 {settings.max_upload_mb} MB 限制")
        merged.replace(output)
        audio_path.unlink(missing_ok=True)

    return output, title[:300]


def refresh_douyin_playback(url: str, task_dir: Path) -> tuple[str, str | None]:
    """Resolve fresh browser-playable Douyin URLs without downloading the video."""
    normalized_url = validate_public_url(url)
    host = (urlparse(normalized_url).hostname or "").lower().rstrip(".")
    if not (host == "douyin.com" or host.endswith(".douyin.com") or host == "iesdouyin.com" or host.endswith(".iesdouyin.com")):
        raise RuntimeError("当前只支持刷新抖音播放地址")
    _, _, playback_url, playback_audio_url = _download_douyin_with_browser(
        normalized_url, task_dir, resolve_only=True,
    )
    return playback_url, playback_audio_url


def _yt_dlp_options(url: str, *, use_douyin_cookies: bool = True, **overrides) -> dict:
    options = {
        "noplaylist": True,
        "js_runtimes": {"node": {}},
        "quiet": True,
        # Some CDN edges take longer than the default probe timeout to return
        # headers.  Direct media URLs use the streaming downloader below, but
        # keep a more forgiving timeout for platform pages.
        "socket_timeout": 60,
        "retries": 5,
        "fragment_retries": 5,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131 Safari/537.36",
            "Accept": "*/*",
        },
    }
    cookie_file = _cookie_file_for_url(url) if use_douyin_cookies else None
    if cookie_file:
        options["cookiefile"] = cookie_file
        options["http_headers"]["User-Agent"] = _douyin_browser_user_agent(url) or options["http_headers"]["User-Agent"]
    options.update(overrides)
    return options


def is_direct_media_url(url: str) -> bool:
    """Return True for a URL that points straight at a media file.

    CDN links (for example, ByteDance TOS signed .mp4 URLs) are not platform
    pages. Running yt-dlp's generic webpage extractor against them adds an
    unnecessary probe which can hang on an otherwise healthy CDN response.
    """
    path = urlparse(url).path.lower()
    return path.endswith(tuple(AUDIO_SUFFIXES | VIDEO_SUFFIXES)) or _direct_media_suffix(url) is not None


def _direct_media_suffix(url: str) -> str | None:
    """Infer media type from signed CDN query metadata when the path is opaque."""
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix.lower()
    if suffix in AUDIO_SUFFIXES | VIDEO_SUFFIXES:
        return suffix
    mime_type = (parse_qs(parsed.query).get("mime_type") or [""])[0].lower().replace("/", "_")
    return {
        "video_mp4": ".mp4", "application_mp4": ".mp4", "video_x_mp4": ".mp4",
        "video_webm": ".webm", "video_quicktime": ".mov", "video_x_matroska": ".mkv",
        "audio_mp4": ".m4a", "audio_x_m4a": ".m4a", "audio_mpeg": ".mp3",
        "audio_wav": ".wav", "audio_x_wav": ".wav", "audio_aac": ".aac",
        "audio_ogg": ".ogg", "audio_flac": ".flac",
    }.get(mime_type)


def is_direct_video_url(url: str | None) -> bool:
    return bool(url and is_direct_media_url(url) and _direct_media_suffix(url) in VIDEO_SUFFIXES)


def _download_direct_media(url: str, task_dir: Path, progress_callback=None) -> tuple[Path, str, bool, str]:
    """Stream a direct media URL to disk with CDN-friendly retries."""
    parsed = urlparse(url)
    suffix = _direct_media_suffix(url) or ".mp4"
    output = task_dir / f"source{suffix}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131 Safari/537.36",
        "Accept": "*/*",
        "Accept-Encoding": "identity",
    }
    host = (parsed.hostname or "").lower().rstrip(".")
    if any(host == suffix or host.endswith(f".{suffix}") for suffix in DOUYIN_MEDIA_HOST_SUFFIXES):
        headers["Referer"] = "https://www.douyin.com/"
    max_bytes = settings.max_upload_mb * 1024 * 1024
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            with requests.get(
                url,
                headers=headers,
                stream=True,
                allow_redirects=True,
                timeout=(20, 120),
            ) as response:
                if response.status_code not in (200, 206):
                    raise RuntimeError(f"直链服务器返回 HTTP {response.status_code}")
                content_length = int(response.headers.get("content-length") or 0)
                if content_length > max_bytes:
                    raise RuntimeError(f"视频文件超过 {settings.max_upload_mb} MB 限制")
                written = 0
                last_progress = 0
                with output.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        written += len(chunk)
                        if written > max_bytes:
                            raise RuntimeError(f"视频文件超过 {settings.max_upload_mb} MB 限制")
                        handle.write(chunk)
                        if progress_callback and content_length:
                            progress = min(94, int(5 + written / content_length * 89))
                            if progress >= last_progress + 5:
                                last_progress = progress
                                progress_callback(progress)
            if written <= 0:
                raise RuntimeError("直链响应为空")
            final_path = Path(urlparse(response.url).path)
            title = final_path.stem or "网络视频"
            return output, title, suffix in AUDIO_SUFFIXES, url
        except (requests.RequestException, OSError, RuntimeError) as exc:
            last_error = exc
            output.unlink(missing_ok=True)
            if attempt < 3:
                time.sleep(min(2 ** attempt, 8))
    raise RuntimeError(f"直链下载失败：{last_error}") from last_error


def _extract_source_audio(source: str | Path, task_dir: Path) -> Path:
    """Demux audio into a small local ASR file without keeping the video stream."""
    task_dir.mkdir(parents=True, exist_ok=True)
    output = task_dir / "source-audio.mp3"
    output.unlink(missing_ok=True)
    result = subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
        "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k",
        "-fs", str(settings.max_upload_mb * 1024 * 1024), str(output),
    ], capture_output=True, text=True, timeout=7200)
    if result.returncode != 0 or not output.is_file() or not _has_audio_stream(output):
        output.unlink(missing_ok=True)
        detail = (result.stderr or "").strip().splitlines()
        reason = detail[-1] if detail else "没有可用音轨"
        raise RuntimeError(f"视频无法提取音频：{reason}")
    return output


def _select_playback_urls(info: dict | None) -> tuple[str | None, str | None]:
    """Select remote video and optional separate audio streams from yt-dlp metadata."""
    if not isinstance(info, dict):
        return None, None
    formats = info.get("formats") or []

    def safe_url(item):
        media_url = item.get("url") or ""
        return media_url if urlparse(media_url).scheme == "https" else None

    def rank(item):
        return (
            int(item.get("height") or 0),
            float(item.get("tbr") or item.get("abr") or 0),
            int(item.get("filesize") or item.get("filesize_approx") or 0),
        )

    def has_codec(item, field):
        return item.get(field) not in (None, "", "none")

    video_formats = [item for item in formats if safe_url(item) and has_codec(item, "vcodec")]
    combined = [item for item in video_formats if has_codec(item, "acodec")]
    if combined:
        return safe_url(max(combined, key=rank)), None
    audio_formats = [item for item in formats if safe_url(item) and has_codec(item, "acodec") and not has_codec(item, "vcodec")]
    video = max(video_formats, key=rank) if video_formats else None
    audio = max(audio_formats, key=rank) if audio_formats else None
    if video:
        return safe_url(video), safe_url(audio) if audio else None
    if has_codec(info, "vcodec") and safe_url(info):
        return safe_url(info), None
    return None, None


def download_video(url: str, task_dir: Path) -> tuple[Path, str, bool, str | None, str | None]:
    normalized_url = validate_public_url(url)
    if is_kuaishou_url(normalized_url):
        media_path, title = download_kuaishou_video(
            normalized_url, task_dir, settings.max_upload_mb * 1024 * 1024,
        )
        if not _has_audio_stream(media_path):
            raise RuntimeError("这个快手视频没有可用音轨，无法听写")
        if probe_duration(media_path) >= settings.url_audio_only_minutes * 60:
            audio_path = _extract_source_audio(media_path, task_dir)
            media_path.unlink(missing_ok=True)
            return audio_path, title, True, None, None
        return media_path, title, False, None, None
    if is_direct_media_url(normalized_url):
        suffix = _direct_media_suffix(normalized_url)
        if suffix in VIDEO_SUFFIXES:
            audio_path = _extract_source_audio(normalized_url, task_dir)
            title = Path(urlparse(normalized_url).path).stem or "网络视频"
            return audio_path, title, True, normalized_url, None
        path, title, audio_only, playback_url = _download_direct_media(normalized_url, task_dir)
        return path, title, audio_only, playback_url, None
    host = (urlparse(normalized_url).hostname or "").lower().rstrip(".")
    is_douyin = host == "douyin.com" or host.endswith(".douyin.com") or host == "iesdouyin.com" or host.endswith(".iesdouyin.com")
    cached_video = task_dir / "source.mp4"

    if is_douyin and _cookie_file_for_url(normalized_url) and _douyin_browser_user_agent(normalized_url):
        try:
            media_path, title, playback_url, playback_audio_url = _download_douyin_with_browser(
                normalized_url, task_dir, audio_only=True,
            )
            for stale_video in task_dir.glob("source.*"):
                if stale_video != media_path and stale_video.suffix.lower() in VIDEO_SUFFIXES:
                    stale_video.unlink(missing_ok=True)
            (task_dir / "preview.mp4").unlink(missing_ok=True)
            return media_path, title, True, playback_url, playback_audio_url
        except Exception:
            # Keep the existing yt-dlp and full-video fallbacks for posts whose
            # separate music track cannot be fetched as an ASR source.
            pass

    if is_douyin and cached_video.is_file() and cached_video.stat().st_size > 0:
        try:
            if probe_duration(cached_video) > 1 and not _has_audio_stream(cached_video):
                media_path, title = _download_douyin_with_browser(
                    normalized_url, task_dir, source_video_path=cached_video,
                )
                return media_path, title, False, None, None
        except Exception as exc:
            raise RuntimeError("已下载的视频没有音轨，暂时未能补齐抖音配套音频，请稍后重试") from exc
    audio_only = False
    playback_url = None
    playback_audio_url = None
    diagnostic_logger = _YtDlpDiagnosticLogger()
    try:
        with yt_dlp.YoutubeDL(_yt_dlp_options(normalized_url, logger=diagnostic_logger)) as ydl:
            info = ydl.extract_info(normalized_url, download=False)
            duration = float(info.get("duration") or 0)
            playback_url, playback_audio_url = _select_playback_urls(info)
            audio_only = duration >= settings.url_audio_only_minutes * 60 or bool(playback_url)
    except Exception:
        # The download pass below provides the real error message. Metadata
        # lookup is only a hint used to avoid downloading a huge video.
        pass
    output = str(task_dir / "source.%(ext)s")
    opts = _yt_dlp_options(normalized_url, **{
        "outtmpl": output,
        "format": "bestaudio/best" if audio_only else "bv*+ba/b",
        "max_filesize": settings.max_upload_mb * 1024 * 1024,
        "retries": 3,
        "logger": diagnostic_logger,
    })
    if not audio_only:
        opts["merge_output_format"] = "mp4"
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(normalized_url, download=True)
    except Exception as exc:
        detail = "\n".join([str(exc), *diagnostic_logger.messages])
        needs_browser_fallback = "HTTP Error 403" in detail or "403 Forbidden" in detail or "Fresh cookies" in detail
        if is_douyin and needs_browser_fallback:
            try:
                browser_path, browser_title = _download_douyin_with_browser(normalized_url, task_dir)
                return browser_path, browser_title, False, None, None
            except Exception as fallback_exc:
                if str(fallback_exc).startswith("视频文件超过"):
                    raise fallback_exc from exc
                raise RuntimeError(
                    "抖音拒绝了 yt-dlp 的详情请求，Chrome 浏览器取流回退也未能取得完整视频。请确认视频在 Chrome 可播放，或先保存到本机再上传听写。"
                ) from exc
        raise
    title = info.get("title") or "网络视频"
    requested = info.get("requested_downloads") or []
    candidate = requested[0].get("filepath") if requested else None
    if not playback_url:
        playback_url, playback_audio_url = _select_playback_urls(info)
    if not playback_url and not audio_only and isinstance(info, dict):
        playback_url = info.get("url")
    if candidate and Path(candidate).exists():
        media_path = Path(candidate)
        if is_douyin and not _has_audio_stream(media_path):
            try:
                browser_path, browser_title = _download_douyin_with_browser(
                    normalized_url, task_dir,
                    source_video_path=media_path if media_path.suffix.lower() == ".mp4" else None,
                )
                return browser_path, browser_title, audio_only, None, None
            except Exception as exc:
                raise RuntimeError("抖音下载到的视频没有音频轨，且未能获取配套音轨，请重试或上传本机视频") from exc
        if audio_only and _has_video_stream(media_path):
            audio_path = _extract_source_audio(media_path, task_dir)
            media_path.unlink(missing_ok=True)
            media_path = audio_path
        return media_path, title, audio_only, playback_url, playback_audio_url
    matches = sorted(task_dir.glob("source.*"))
    if not matches:
        raise RuntimeError("视频下载完成后未找到文件")
    if is_douyin and not _has_audio_stream(matches[0]):
        try:
            browser_path, browser_title = _download_douyin_with_browser(
                normalized_url, task_dir,
                source_video_path=matches[0] if matches[0].suffix.lower() == ".mp4" else None,
            )
            return browser_path, browser_title, audio_only, None, None
        except Exception as exc:
            raise RuntimeError("抖音下载到的视频没有音频轨，且未能获取配套音轨，请重试或上传本机视频") from exc
    media_path = matches[0]
    if audio_only and _has_video_stream(media_path):
        audio_path = _extract_source_audio(media_path, task_dir)
        media_path.unlink(missing_ok=True)
        media_path = audio_path
    return media_path, title, audio_only, playback_url, playback_audio_url


def download_original_video(url: str, task_dir: Path, progress_callback=None, *, use_douyin_cookies: bool = False) -> tuple[Path, str]:
    """Download a user-requested video artifact (never switch to audio-only)."""
    normalized_url = validate_public_url(url)
    if is_kuaishou_url(normalized_url):
        path, title = download_kuaishou_video(
            normalized_url, task_dir, settings.max_upload_mb * 1024 * 1024, progress_callback,
        )
        if not _has_video_stream(path):
            path.unlink(missing_ok=True)
            raise RuntimeError("这个快手作品没有可用的视频画面")
        return path, title
    if is_direct_media_url(normalized_url):
        if Path(urlparse(normalized_url).path).suffix.lower() in AUDIO_SUFFIXES:
            raise RuntimeError("这个链接是音频文件；下载视频请粘贴视频链接")
        path, title, is_audio, _ = _download_direct_media(normalized_url, task_dir, progress_callback)
        if is_audio:
            raise RuntimeError("这个链接没有视频画面，无法作为视频下载")
        if progress_callback:
            progress_callback(96)
        return path, title

    def report_progress(status):
        if not progress_callback or status.get("status") != "downloading":
            return
        total = status.get("total_bytes") or status.get("total_bytes_estimate")
        downloaded = status.get("downloaded_bytes") or 0
        if total:
            progress_callback(min(94, max(5, int(5 + downloaded / total * 89))))

    options = _yt_dlp_options(normalized_url, use_douyin_cookies=use_douyin_cookies, **{
        "outtmpl": str(task_dir / "source.%(ext)s"),
        "format": "bv*+ba/b",
        "max_filesize": settings.max_upload_mb * 1024 * 1024,
        "retries": 3,
        "merge_output_format": "mp4",
        "progress_hooks": [report_progress],
        "logger": _YtDlpDiagnosticLogger(),
    })
    diagnostic_logger = options["logger"]
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(normalized_url, download=True)
    except Exception as exc:
        detail = "\n".join([str(exc), *diagnostic_logger.messages])
        host = (urlparse(normalized_url).hostname or "").lower().rstrip(".")
        is_douyin = host == "douyin.com" or host.endswith(".douyin.com") or host == "iesdouyin.com" or host.endswith(".iesdouyin.com")
        needs_browser_fallback = "HTTP Error 403" in detail or "403 Forbidden" in detail or "Fresh cookies" in detail
        if is_douyin and use_douyin_cookies and needs_browser_fallback:
            try:
                return _download_douyin_with_browser(normalized_url, task_dir, progress_callback)
            except Exception as fallback_exc:
                if str(fallback_exc).startswith("视频文件超过"):
                    raise fallback_exc from exc
                raise RuntimeError(
                    "抖音拒绝了 yt-dlp 的详情请求，Chrome 浏览器取流回退也未能取得完整视频。请确认视频在 Chrome 可播放，或先保存到本机再上传。"
                ) from exc
        raise

    candidates = [
        path for path in task_dir.glob("source.*")
        if path.is_file() and not path.name.endswith((".part", ".ytdl"))
        and path.suffix.lower() in VIDEO_SUFFIXES
    ]
    if not candidates:
        raise RuntimeError("下载完成后没有找到可用的视频文件")
    path = max(candidates, key=lambda item: item.stat().st_mtime)
    if path.stat().st_size > settings.max_upload_mb * 1024 * 1024:
        path.unlink(missing_ok=True)
        raise RuntimeError(f"视频文件超过 {settings.max_upload_mb} MB 限制")
    host = (urlparse(normalized_url).hostname or "").lower().rstrip(".")
    is_douyin = host == "douyin.com" or host.endswith(".douyin.com") or host == "iesdouyin.com" or host.endswith(".iesdouyin.com")
    if is_douyin and use_douyin_cookies and not _has_audio_stream(path):
        try:
            return _download_douyin_with_browser(
                normalized_url, task_dir, progress_callback,
                source_video_path=path if path.suffix.lower() == ".mp4" else None,
            )
        except Exception as exc:
            raise RuntimeError("抖音下载到的视频没有音频轨，且未能获取配套音轨，请重试或上传本机视频") from exc
    title = str((info or {}).get("title") or "网络视频")[:300]
    return path, title


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


def ensure_cover_image(media_path: Path, task_dir: Path) -> Path:
    """Create one downloadable cover frame for the temporary task result."""
    cover = task_dir / "cover.jpg"
    if cover.exists() and cover.stat().st_size > 0:
        return cover
    temporary = task_dir / "cover.partial.jpg"
    try:
        subprocess.run([
            "ffmpeg", "-y", "-ss", "1", "-i", str(media_path), "-frames:v", "1",
            "-vf", "scale=960:960:force_original_aspect_ratio=decrease", "-q:v", "3", str(temporary),
        ], capture_output=True, timeout=120, check=True)
    except Exception:
        temporary.unlink(missing_ok=True)
        subprocess.run([
            "ffmpeg", "-y", "-i", str(media_path), "-frames:v", "1",
            "-vf", "scale=960:960:force_original_aspect_ratio=decrease", "-q:v", "3", str(temporary),
        ], capture_output=True, timeout=120, check=True)
    if not temporary.exists() or temporary.stat().st_size == 0:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("未能生成视频封面")
    temporary.replace(cover)
    return cover


def ensure_remote_cover_image(media_url: str, task_dir: Path) -> Path:
    """Extract and cache one frame from a safe, direct video URL."""
    normalized_url = validate_public_url(media_url)
    if not is_direct_video_url(normalized_url):
        raise RuntimeError("没有可用于生成封面的直链视频")

    cover = task_dir / "cover.jpg"
    if cover.is_file() and cover.stat().st_size > 0:
        return cover
    task_dir.mkdir(parents=True, exist_ok=True)

    parsed = urlparse(normalized_url)
    host = (parsed.hostname or "").lower().rstrip(".")
    headers = [
        "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131 Safari/537.36",
        "Accept: */*",
    ]
    if any(host == suffix or host.endswith(f".{suffix}") for suffix in DOUYIN_MEDIA_HOST_SUFFIXES):
        headers.append("Referer: https://www.douyin.com/")
    header_value = "".join(f"{header}\r\n" for header in headers)

    temporary = task_dir / f"cover.partial-{os.getpid()}-{time.time_ns()}.jpg"
    for seek in ("1", None):
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-headers", header_value]
        if seek:
            command.extend(["-ss", seek])
        command.extend([
            "-i", normalized_url,
            "-frames:v", "1",
            "-vf", "scale=960:960:force_original_aspect_ratio=decrease",
            "-q:v", "3", str(temporary),
        ])
        try:
            result = subprocess.run(command, capture_output=True, timeout=120)
        except (OSError, subprocess.SubprocessError):
            temporary.unlink(missing_ok=True)
            continue
        if result.returncode == 0 and temporary.is_file() and temporary.stat().st_size > 0:
            temporary.replace(cover)
            return cover
        temporary.unlink(missing_ok=True)
    raise RuntimeError("视频直链暂时无法生成封面")


def ensure_download_audio(media_path: Path, task_dir: Path) -> Path:
    """Create a user-friendly MP3 download without changing ASR audio chunks."""
    audio_dir = task_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    output = audio_dir / "download.mp3"
    if output.exists() and output.stat().st_size > 0:
        return output
    temporary = audio_dir / "download.partial.mp3"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(media_path), "-vn", "-codec:a", "libmp3lame",
        "-b:a", "128k", "-ar", "44100", str(temporary),
    ], capture_output=True, timeout=7200, check=True)
    if not temporary.exists() or temporary.stat().st_size == 0:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("未能生成可播放的音频文件")
    temporary.replace(output)
    return output


def split_audio(media_path: Path, task_dir: Path, chunk_seconds: int) -> list[Path]:
    if not _has_audio_stream(media_path):
        raise RuntimeError("这个视频没有可用的音频轨，无法进行听写")
    chunk_dir = task_dir / "audio" / "chunks"
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


def extract_audio(media_path: Path, task_dir: Path) -> Path:
    """Create one normalized audio file for full-file ASR providers."""
    if not _has_audio_stream(media_path):
        raise RuntimeError("这个视频没有可用的音频轨，无法进行听写")
    audio_dir = task_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    output = audio_dir / "full.mp3"
    if output.exists() and output.stat().st_size > 0:
        return output
    subprocess.run([
        "ffmpeg", "-y", "-i", str(media_path), "-vn", "-ac", "1", "-ar", "16000",
        "-b:a", "48k", str(output),
    ], capture_output=True, timeout=7200, check=True)
    if not output.exists() or output.stat().st_size == 0:
        raise RuntimeError("未能从媒体中提取音频")
    return output


def delete_source(path: str | None) -> None:
    if path:
        try:
            source = Path(path)
            source.unlink(missing_ok=True)
            (source.parent / "preview.mp4").unlink(missing_ok=True)
            (source.parent / "cover.jpg").unlink(missing_ok=True)
            (source.parent / "cover.partial.jpg").unlink(missing_ok=True)
            shutil.rmtree(source.parent / "audio", ignore_errors=True)
            shutil.rmtree(source.parent / "visual", ignore_errors=True)
        except OSError:
            pass

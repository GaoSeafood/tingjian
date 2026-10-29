"""Resolve public Kuaishou share pages without a third-party parsing service."""

import ipaddress
import json
import re
import socket
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import requests

PAGE_HOSTS = ("kuaishou.com", "kuaishou.cn", "gifshow.com")
MEDIA_HOSTS = ("kwaicdn.com", "kwai.net", "ksapisrv.com", "gifshow.com")
USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1"
)
STATE_RE = re.compile(r"window\.(?:INIT_STATE|__APOLLO_STATE__)\s*=\s*")


def is_kuaishou_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in PAGE_HOSTS)


def _validate_url(url: str, hosts: tuple[str, ...]) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme != "https" or parsed.username or parsed.password
        or parsed.port not in (None, 443)
        or not any(host == suffix or host.endswith(f".{suffix}") for suffix in hosts)
    ):
        raise ValueError("快手返回了不受支持的地址")
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("无法解析快手服务器地址") from exc
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("不允许访问内网或本机地址")
    return url


def _get(session: requests.Session, url: str, hosts: tuple[str, ...]):
    # Validate every redirect before sending a request, including CDN redirects.
    for _ in range(6):
        _validate_url(url, hosts)
        response = session.get(url, allow_redirects=False, stream=True, timeout=(20, 90))
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise RuntimeError("快手重定向缺少目标地址")
            url = urljoin(url, location)
            continue
        if response.status_code != 200:
            status = response.status_code
            response.close()
            raise requests.HTTPError(f"快手服务器返回 HTTP {status}")
        return response
    raise RuntimeError("快手链接重定向次数过多")


def _parse_page(page: str, expected_id: str | None = None) -> tuple[list[str], str]:
    decoder = json.JSONDecoder()
    photos = []
    for match in STATE_RE.finditer(page):
        try:
            state, _ = decoder.raw_decode(page[match.end():])
        except ValueError:
            continue
        if not isinstance(state, dict):
            continue
        # Mobile share pages use opaque cache keys; desktop pages use Apollo.
        entries = state.get("defaultClient", state)
        if not isinstance(entries, dict):
            continue
        for key, entry in entries.items():
            if not isinstance(entry, dict):
                continue
            photo = entry.get("photo")
            if not isinstance(photo, dict) and key.startswith("VisionVideoDetailPhoto:"):
                photo = {**entry, "photoId": key.split(":", 1)[1]}
            if isinstance(photo, dict):
                photos.append(photo)
    for photo in photos:
        photo_ids = {str(photo.get("photoId") or ""), str(photo.get("id") or "")}
        photo_ids.update(parse_qs(str(photo.get("share_info") or "")).get("photoId", []))
        if expected_id and expected_id not in photo_ids:
            continue
        if photo.get("photoType") not in (None, "VIDEO"):
            continue
        urls = []
        for item in photo.get("mainMvUrls") or []:
            if isinstance(item, dict):
                urls.append(item.get("url"))
        manifest = photo.get("manifest") or {}
        if isinstance(manifest, str):
            try:
                manifest = json.loads(manifest)
            except ValueError:
                manifest = {}
        if isinstance(manifest, dict):
            for group in manifest.get("adaptationSet") or []:
                if not isinstance(group, dict):
                    continue
                for representation in group.get("representation") or []:
                    if not isinstance(representation, dict) or representation.get("mute"):
                        continue
                    urls.append(representation.get("url"))
                    urls.extend(representation.get("backupUrl") or [])
        urls.extend([photo.get("photoUrl"), photo.get("srcNoMark")])
        candidates = []
        for url in urls:
            if not isinstance(url, str) or not url:
                continue
            # Older pages still advertise HTTP CDN addresses that support TLS.
            if url.startswith("//"):
                url = "https:" + url
            if url.startswith("http://"):
                url = "https://" + url[len("http://"):]
            if url not in candidates:
                candidates.append(url)
        if candidates:
            title = str(photo.get("caption") or "").strip()
            if not title or title in {"...", "…"}:
                title = "快手视频"
            return candidates, title[:300]
    raise RuntimeError("未能取得快手视频，请确认链接为公开的视频作品，未失效且无需登录或验证")


def download_kuaishou_video(
    url: str, task_dir: Path, max_bytes: int, progress_callback=None,
) -> tuple[Path, str]:
    task_dir.mkdir(parents=True, exist_ok=True)
    output = task_dir / "source.mp4"
    temporary = task_dir / "source.mp4.part"
    path_match = re.search(r"/(?:short-video|photo)/([\w-]+)", urlparse(url).path)
    expected_id = path_match.group(1) if path_match else None
    try:
        with requests.Session() as session:
            session.headers.update({
                "User-Agent": USER_AGENT,
                "Referer": "https://www.kuaishou.com/",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Accept-Encoding": "identity",
            })
            with _get(session, url, PAGE_HOSTS) as response:
                resolved_id = re.search(r"/(?:short-video|photo)/([\w-]+)", urlparse(response.url).path)
                if resolved_id:
                    expected_id = expected_id or resolved_id.group(1)
                chunks = []
                size = 0
                for chunk in response.iter_content(64 * 1024):
                    size += len(chunk)
                    if size > 4 * 1024 * 1024:
                        raise RuntimeError("快手分享页响应过大")
                    chunks.append(chunk)
                page = b"".join(chunks).decode("utf-8", errors="replace")
            candidates, title = _parse_page(page, expected_id)
            for candidate in candidates:
                temporary.unlink(missing_ok=True)
                try:
                    with _get(session, candidate, MEDIA_HOSTS) as response:
                        length = int(response.headers.get("Content-Length") or 0)
                        if length > max_bytes:
                            raise RuntimeError("快手视频超过文件大小限制")
                        written = 0
                        with temporary.open("wb") as handle:
                            for chunk in response.iter_content(1024 * 1024):
                                written += len(chunk)
                                if written > max_bytes:
                                    raise RuntimeError("快手视频超过文件大小限制")
                                handle.write(chunk)
                                if progress_callback and length:
                                    progress_callback(min(94, 5 + int(written / length * 89)))
                        if written < 16 or (length and written != length):
                            continue
                        with temporary.open("rb") as handle:
                            if handle.read(12)[4:8] != b"ftyp":
                                continue
                    temporary.replace(output)
                    return output, title
                except (requests.RequestException, ValueError):
                    # Try another CDN without exposing signed URLs in task errors.
                    continue
            raise RuntimeError("快手视频下载失败，请稍后重试或上传本机视频")
    except requests.RequestException as exc:
        raise RuntimeError("快手连接失败，请稍后重试") from exc
    finally:
        temporary.unlink(missing_ok=True)

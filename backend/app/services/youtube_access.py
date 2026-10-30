"""Private, administrator-managed YouTube session files. Never return their contents."""
import io
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from http.cookiejar import LoadError, MozillaCookieJar
from pathlib import Path

import requests

from ..config import settings


def normalize_cookies(raw: bytes) -> str:
    if len(raw) > 1024 * 1024:
        raise ValueError("Cookie 文件不能超过 1MB")
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("Cookie 文件必须是 UTF-8 文本") from None
    rows = []
    for line in content.splitlines():
        if not line or (line.startswith("#") and not line.startswith("#HttpOnly_")):
            continue
        fields = line.removeprefix("#HttpOnly_").split("\t")
        if (len(fields) != 7 or fields[1] not in {"TRUE", "FALSE"}
            or fields[3] not in {"TRUE", "FALSE"} or not re.fullmatch(r"[0-9]{1,12}", fields[4])
            or not fields[2].startswith("/") or not fields[5]
            or any(ord(c) < 32 or ord(c) == 127 for field in fields for c in field)):
            raise ValueError("请上传有效的 Netscape 格式 YouTube Cookie 文件")
        domain = fields[0].lower()
        if not re.fullmatch(r"\.?([a-z0-9-]+\.)*youtube\.com", domain):
            continue
        if domain.startswith(".") != (fields[1] == "TRUE"):
            raise ValueError("Cookie 域名格式不正确")
        if fields[4] != "0" and int(fields[4]) <= time.time():
            continue
        fields[0] = domain
        rows.append(("#HttpOnly_" if line.startswith("#HttpOnly_") else "") + "\t".join(fields))
    if not rows:
        raise ValueError("文件中没有未过期的 YouTube Cookie；请仅导出 YouTube 网站的 Cookie")
    result = "# Netscape HTTP Cookie File\n" + "\n".join(rows) + "\n"
    # Validate against the same Netscape parser used by download clients.
    jar = MozillaCookieJar()
    try:
        jar._really_load(io.StringIO(result), "<upload>", True, True)
    except (LoadError, ValueError, OverflowError):
        raise ValueError("Cookie 文件格式不正确") from None
    return result


def validate_user_agent(value: str) -> str:
    if value and (len(value) > 512 or any(ord(c) < 32 or ord(c) == 127 for c in value)
                  or not all(marker in value for marker in ("Mozilla/5.0", "AppleWebKit/", "Chrome/", "Safari/"))):
        raise ValueError("浏览器标识格式不正确")
    return value.strip()


def _write_private(path: Path, value: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(value)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def save_cookies(raw: bytes, user_agent: str):
    content = normalize_cookies(raw)
    user_agent = validate_user_agent(user_agent)
    _write_private(settings.youtube_cookie_file, content)
    if user_agent:
        _write_private(settings.youtube_user_agent_file, user_agent + "\n")
    else:
        settings.youtube_user_agent_file.unlink(missing_ok=True)


def delete_cookies():
    settings.youtube_cookie_file.unlink(missing_ok=True)
    settings.youtube_user_agent_file.unlink(missing_ok=True)


def access_status() -> dict:
    path = settings.youtube_cookie_file
    stat = path.stat() if path.is_file() else None
    provider = "not_configured"
    if settings.youtube_pot_provider_url:
        provider = "unreachable"
        try:
            with requests.Session() as session:
                session.trust_env = False
                response = session.get(settings.youtube_pot_provider_url.rstrip("/") + "/ping", timeout=2, allow_redirects=False)
                if response.status_code == 200 and response.json().get("version") == "2.0.2":
                    provider = "ready"
        except (requests.RequestException, ValueError, AttributeError):
            pass
    return {"configured": bool(stat and stat.st_size),
            "updated_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat() if stat else None,
            "user_agent_configured": settings.youtube_user_agent_file.is_file(),
            "provider_status": provider, "cookie_scope": "admin_only"}

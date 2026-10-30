"""YouTube credential isolation and failures, using synthetic sessions only."""
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("DATA_DIR", str(Path(tempfile.gettempdir()) / "tingjian-test-data"))
from fastapi.testclient import TestClient
from app import main
from app.auth import current_user
from app.config import settings
from app.models import User
from app.services import media, subtitles, youtube_access

URL = "https://www.youtube.com/watch?v=synthetic"
COOKIE = b"# Netscape HTTP Cookie File\n#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tsynthetic-session\n"


class YouTubeAccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        config = replace(settings, youtube_cookie_file=root / "youtube.txt",
                         youtube_user_agent_file=root / "ua.txt", douyin_cookie_file=root / "douyin.txt",
                         youtube_pot_provider_url="")
        self.patches = [patch.object(youtube_access, "settings", config), patch.object(media, "settings", config)]
        for item in self.patches:
            item.start()
        self.config = config
        self.role = "admin"
        main.app.dependency_overrides[current_user] = lambda: User(id=1, username="synthetic", role=self.role)
        self.client = TestClient(main.app)

    def tearDown(self):
        self.client.close()
        main.app.dependency_overrides.clear()
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def upload(self, raw=COOKIE, **data):
        return self.client.post("/api/settings/youtube-cookies", files={"cookies": ("cookies.txt", raw)}, data=data)

    def test_upload_filters_other_sites_and_never_returns_cookie_values(self):
        raw = COOKIE + b".google.com\tTRUE\t/\tTRUE\t0\tSID\tsynthetic-other-site\n"
        response = self.upload(raw)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["configured"])
        content = self.config.youtube_cookie_file.read_text()
        self.assertIn("synthetic-session", content)
        self.assertNotIn("google.com", content)
        self.assertEqual(self.config.youtube_cookie_file.stat().st_mode & 0o777, 0o600)
        status = self.client.get("/api/settings/youtube-cookies")
        self.assertNotIn("synthetic-session", response.text + status.text)
        self.assertNotIn(str(self.config.youtube_cookie_file), status.text)
        self.assertTrue(status.json()["updated_at"].endswith("+00:00"))

    def test_ordinary_users_cannot_read_upload_or_delete(self):
        self.role = "user"
        self.assertEqual(self.upload().status_code, 403)
        self.assertEqual(self.client.get("/api/settings/youtube-cookies").status_code, 403)
        self.assertEqual(self.client.delete("/api/settings/youtube-cookies").status_code, 403)
        self.assertFalse(self.config.youtube_cookie_file.exists())

    def test_malformed_expired_and_unrelated_uploads_preserve_session(self):
        self.assertEqual(self.upload().status_code, 200)
        for raw in (b"not-a-cookie", COOKIE.replace(b"\t0\t", b"\t1\t"),
                    COOKIE.replace(b".youtube.com", b".example.com"),
                    COOKIE.replace(b"\tTRUE\t/", b"\tFALSE\t/"),
                    COOKIE.replace(b"synthetic-session", b"bad\x00value")):
            with self.subTest(raw=raw):
                self.assertEqual(self.upload(raw).status_code, 400)
                self.assertIn("synthetic-session", self.config.youtube_cookie_file.read_text())
        self.assertEqual(self.upload(b"a" * (1024 * 1024 + 1)).status_code, 413)
        self.assertEqual(list(Path(self.tmp.name).glob(".*")), [])

    def test_user_agent_validation_and_session_removal(self):
        ua = "Mozilla/5.0 AppleWebKit/537.36 Chrome/131 Safari/537.36"
        self.assertEqual(self.upload(user_agent=ua + "\r\nInjected: bad").status_code, 400)
        self.assertEqual(self.upload(user_agent=ua).status_code, 200)
        self.assertEqual(self.config.youtube_user_agent_file.stat().st_mode & 0o777, 0o600)
        self.assertTrue(self.upload().json()["configured"])
        self.assertFalse(self.config.youtube_user_agent_file.exists())
        self.assertFalse(self.client.delete("/api/settings/youtube-cookies").json()["configured"])
        self.assertFalse(self.config.youtube_cookie_file.exists())

    def test_sessions_and_provider_are_scoped_to_youtube_and_admin_opt_in(self):
        self.upload()
        config = replace(self.config, youtube_pot_provider_url="http://bgutil-provider:4416")
        with patch.object(media, "settings", config):
            self.assertNotIn("cookiefile", media._yt_dlp_options(URL))
            admin = media._yt_dlp_options(URL, use_youtube_cookies=True, use_douyin_cookies=False)
            self.assertEqual(admin["cookiefile"], str(config.youtube_cookie_file))
            self.assertEqual(admin["extractor_args"]["youtube"]["player_client"], ["mweb", "tv", "web_safari"])
            for url in ("https://www.bilibili.com/video/synthetic", "https://youtube.com.example.com/video"):
                other = media._yt_dlp_options(url, use_youtube_cookies=True)
                self.assertNotIn("cookiefile", other)
                self.assertNotIn("extractor_args", other)

    def test_provider_status_checks_availability_and_version(self):
        config = replace(self.config, youtube_pot_provider_url="http://bgutil-provider:4416")
        with patch.object(youtube_access, "settings", config), patch.object(youtube_access.requests, "Session") as factory:
            session = factory.return_value.__enter__.return_value
            session.get.return_value = Mock(status_code=200, json=lambda: {"version": "2.0.2"})
            self.assertEqual(youtube_access.access_status()["provider_status"], "ready")
            session.get.return_value = Mock(status_code=200, json=lambda: {"version": "old"})
            self.assertEqual(youtube_access.access_status()["provider_status"], "unreachable")
            session.get.side_effect = youtube_access.requests.ConnectionError()
            self.assertEqual(youtube_access.access_status()["provider_status"], "unreachable")

    def test_subtitle_request_preserves_extraction_session(self):
        jar = youtube_access.MozillaCookieJar()
        jar._really_load(youtube_access.io.StringIO(COOKIE.decode()), "<synthetic>", True, True)
        with patch.object(subtitles, "validate_public_url"), patch.object(subtitles.yt_dlp, "YoutubeDL") as factory, \
             patch.object(subtitles, "_track_text") as read_track:
            client = factory.return_value.__enter__.return_value
            client.cookiejar = jar
            client.extract_info.return_value = {"subtitles": {"en": [{"ext": "vtt", "url": URL}]}}
            def track(session, url):
                self.assertEqual(session.cookies.get("SID", domain=".youtube.com"), "synthetic-session")
                self.assertIn("Mozilla/5.0", session.headers["User-Agent"])
                return "00:00:00.000 --> 00:00:02.000\nhello"
            read_track.side_effect = track
            self.assertEqual(subtitles.fetch_subtitles(URL, use_youtube_cookies=True).segments[0]["text"], "hello")

    def test_youtube_errors_have_actionable_messages_without_upstream_urls(self):
        failure = RuntimeError("Sign in to confirm you're not a bot https://signed.invalid/?token=synthetic")
        with patch.object(media, "validate_public_url", return_value=URL), patch.object(media.yt_dlp, "YoutubeDL") as factory:
            factory.return_value.__enter__.return_value.extract_info.side_effect = failure
            for download in (media.download_video, media.download_original_video):
                with self.assertRaises(RuntimeError) as result:
                    download(URL, Path(self.tmp.name))
                self.assertIn("登录验证", str(result.exception))
                self.assertNotIn("synthetic", str(result.exception))
                self.assertNotIn("signed.invalid", str(result.exception))

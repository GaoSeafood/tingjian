"""Offline regression checks; all media and responses below are synthetic.

Run: PYTHONPATH=backend python -m unittest discover -s backend/tests -v
"""

import json
import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

os.environ.setdefault("DATA_DIR", str(Path(tempfile.gettempdir()) / "tingjian-test-data"))

from app.services import kuaishou, media


URL = "https://www.kuaishou.com/f/example"
CDN = "https://v1.kwaicdn.com/example.mp4"
MP4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 20
PUBLIC_DNS = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]


def page(photo):
    return 'window.INIT_STATE = ' + json.dumps({"opaque-cache-key": {"photo": photo}}) + ";"


def response(body=b"", *, status=200, headers=None, url=URL):
    result = Mock(status_code=status, headers=headers or {}, url=url)
    result.iter_content.return_value = [body]
    result.__enter__ = Mock(return_value=result)
    result.__exit__ = Mock(return_value=False)
    return result


class KuaishouParserTests(unittest.TestCase):
    def test_mobile_share_uses_video_not_cover_or_music(self):
        urls, title = kuaishou._parse_page(page({
            "caption": "测试标题", "photoType": "VIDEO",
            "photoId": 12345, "share_info": "photoId=public-id",
            "mainMvUrls": [{"url": CDN}],
            "coverUrls": [{"url": "https://example.com/cover.jpg"}],
            "music": {"url": "https://example.com/music.mp3"},
        }), "public-id")
        self.assertEqual(urls, [CDN])
        self.assertEqual(title, "测试标题")

    def test_manifest_string_and_backup_urls(self):
        urls, title = kuaishou._parse_page(page({
            "caption": "...",
            "manifest": json.dumps({"adaptationSet": [{"representation": [
                {"url": "https://v1.kwaicdn.com/muted.mp4", "mute": True},
                {"url": CDN, "backupUrl": [CDN.replace("v1.", "v2.")]},
            ]}]}),
        }))
        self.assertEqual(urls, [CDN, CDN.replace("v1.", "v2.")])
        self.assertEqual(title, "快手视频")

    def test_desktop_apollo_state(self):
        state = {"defaultClient": {"VisionVideoDetailPhoto:public-id": {"photoUrl": CDN}}}
        urls, _ = kuaishou._parse_page("window.__APOLLO_STATE__=" + json.dumps(state), "public-id")
        self.assertEqual(urls, [CDN])

    def test_never_use_a_different_video_or_image_post(self):
        for source, expected_id in [
            (page({"photoId": "other", "mainMvUrls": [{"url": CDN}]}), "wanted"),
            (page({"photoType": "VERTICAL_ATLAS", "photoUrl": CDN}), None),
            ("<html>请登录后观看</html>", None),
            ("window.INIT_STATE = invalid;", None),
        ]:
            with self.subTest(source=source), self.assertRaisesRegex(RuntimeError, "公开的视频作品"):
                kuaishou._parse_page(source, expected_id)

    def test_legacy_cdn_addresses_use_https(self):
        urls, _ = kuaishou._parse_page(page({"mainMvUrls": [{"url": CDN.replace("https:", "http:")}]}))
        self.assertEqual(urls, [CDN])


class KuaishouDownloadTests(unittest.TestCase):
    @patch("socket.getaddrinfo", return_value=PUBLIC_DNS)
    def test_block_untrusted_hosts_and_private_addresses(self, resolve):
        for url in ["http://v1.kwaicdn.com/a.mp4", "https://kwaicdn.com.evil.test/a.mp4",
                    "https://user:password@v1.kwaicdn.com/a.mp4", "https://v1.kwaicdn.com:8443/a.mp4"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                kuaishou._validate_url(url, kuaishou.MEDIA_HOSTS)
        resolve.return_value = PUBLIC_DNS + [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
        with self.assertRaisesRegex(ValueError, "内网"):
            kuaishou._validate_url(CDN, kuaishou.MEDIA_HOSTS)

    @patch("socket.getaddrinfo", return_value=PUBLIC_DNS)
    def test_redirect_is_checked_before_requesting_destination(self, _):
        session = Mock()
        redirect = response(status=302, headers={"Location": "https://127.0.0.1/private"})
        session.get.return_value = redirect
        with self.assertRaises(ValueError):
            kuaishou._get(session, URL, kuaishou.PAGE_HOSTS)
        session.get.assert_called_once()
        redirect.close.assert_called_once()

    @patch("socket.getaddrinfo", return_value=PUBLIC_DNS)
    def test_share_text_recognition_and_platform_label(self, _):
        for url in [URL, "https://v.kuaishou.com/example", "https://www.kuaishou.com/short-video/example"]:
            self.assertEqual(media.extract_video_url("分享视频 [点这里](" + url + ")。"), url)
            self.assertEqual(media.source_platform_label(url), "快手")

    @patch("app.services.kuaishou._get")
    def test_stream_download_and_progress(self, get):
        get.side_effect = [response(page({"mainMvUrls": [{"url": CDN}]}).encode()),
                           response(MP4, headers={"Content-Length": str(len(MP4))})]
        progress = Mock()
        with tempfile.TemporaryDirectory() as directory:
            path, _ = kuaishou.download_kuaishou_video(URL, Path(directory), 1024, progress)
            self.assertEqual(path.read_bytes(), MP4)
            self.assertFalse(path.with_suffix(".mp4.part").exists())
        progress.assert_called_once_with(94)

    @patch("app.services.kuaishou._get")
    def test_failed_cdn_uses_backup(self, get):
        get.side_effect = [response(page({"mainMvUrls": [{"url": CDN}, {"url": CDN.replace("v1.", "v2.")}]}).encode()),
                           requests.HTTPError("快手服务器返回 HTTP 403"), response(MP4)]
        with tempfile.TemporaryDirectory() as directory:
            path, _ = kuaishou.download_kuaishou_video(URL, Path(directory), 1024)
            self.assertEqual(path.read_bytes(), MP4)
        self.assertEqual(get.call_count, 3)

    @patch("app.services.kuaishou._get")
    def test_size_limit_and_truncated_or_html_responses_leave_no_file(self, get):
        for body, headers, limit in [
            (MP4, {"Content-Length": "100"}, 40),
            (MP4 * 2, {}, 40),
            (MP4, {"Content-Length": "100"}, 1024),
            (b"<html>login required</html>", {}, 1024),
        ]:
            get.side_effect = [response(page({"photoUrl": CDN}).encode()), response(body, headers=headers)]
            with self.subTest(headers=headers, limit=limit), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(RuntimeError):
                    kuaishou.download_kuaishou_video(URL, Path(directory), limit)
                self.assertEqual(list(Path(directory).iterdir()), [])

    @patch("socket.getaddrinfo", return_value=PUBLIC_DNS)
    @patch("app.services.media.download_kuaishou_video")
    def test_transcription_and_download_dispatch_without_yt_dlp(self, download, _):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.mp4"
            download.return_value = (path, "快手视频")
            with patch.object(media, "_has_audio_stream", return_value=True), \
                    patch.object(media, "probe_duration", return_value=21), \
                    patch.object(media.yt_dlp, "YoutubeDL") as yt_dlp:
                self.assertEqual(media.download_video(URL, Path(directory)), (path, "快手视频", False, None, None))
                yt_dlp.assert_not_called()
            with patch.object(media, "_has_video_stream", return_value=True):
                self.assertEqual(media.download_original_video(URL, Path(directory)), (path, "快手视频"))
            with patch.object(media, "_has_audio_stream", return_value=False), self.assertRaisesRegex(RuntimeError, "没有可用音轨"):
                media.download_video(URL, Path(directory))

    @patch("socket.getaddrinfo", return_value=PUBLIC_DNS)
    @patch("app.services.media.download_kuaishou_video")
    def test_long_video_keeps_audio_only_policy(self, download, _):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.mp4"
            path.write_bytes(MP4)
            audio = Path(directory) / "source-audio.mp3"
            download.return_value = (path, "快手视频")
            with patch.object(media, "_has_audio_stream", return_value=True), \
                    patch.object(media, "probe_duration", return_value=media.settings.url_audio_only_minutes * 60), \
                    patch.object(media, "_extract_source_audio", return_value=audio):
                self.assertEqual(media.download_video(URL, Path(directory)), (audio, "快手视频", True, None, None))
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()

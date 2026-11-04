import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("DATA_DIR", str(Path(tempfile.gettempdir()) / "tingjian-test-data"))
from app.services import media


class DouyinDownloadOrderTests(unittest.TestCase):
    def test_ytdlp_is_tried_before_browser_and_returns_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.m4a"
            source.write_bytes(b"synthetic")
            info = {"title": "test", "duration": 54, "requested_downloads": [{"filepath": str(source)}]}
            with patch.object(media, "validate_public_url", side_effect=lambda value: value), \
                 patch.object(media.yt_dlp, "YoutubeDL") as downloader, \
                 patch.object(media, "_download_douyin_with_browser") as browser, \
                 patch.object(media, "_select_playback_urls", return_value=(None, None)), \
                 patch.object(media, "_has_audio_stream", return_value=True):
                downloader.return_value.__enter__.return_value.extract_info.return_value = info
                result = media.download_video("https://www.douyin.com/video/123", Path(directory))
            self.assertEqual(result[0], source)
            browser.assert_not_called()

    def test_browser_is_used_when_ytdlp_reports_fresh_cookies(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.mp4"
            with patch.object(media, "validate_public_url", side_effect=lambda value: value), \
                 patch.object(media.yt_dlp, "YoutubeDL") as downloader, \
                 patch.object(media, "_download_douyin_with_browser", return_value=(source, "test")) as browser:
                downloader.return_value.__enter__.return_value.extract_info.side_effect = RuntimeError("Fresh cookies")
                result = media.download_video("https://www.douyin.com/video/123", Path(directory))
            self.assertEqual(result[0], source)
            browser.assert_called_once()

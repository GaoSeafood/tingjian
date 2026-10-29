"""Workspace persistence, authorization, quota recovery and subtitle fallback."""
import json
import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("DATA_DIR", str(Path(tempfile.gettempdir()) / "tingjian-test-data"))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main, jobs, worker
from app.auth import current_user
from app.database import Base, get_db
from app.models import AIFeatureUsage, Plan, Task, User, UserEntitlement, WorkspaceVersion, utcnow
from app.services import llm, subtitles

SEGMENTS = [{"start": "00:00:00", "end": "00:00:10", "start_seconds": 0,
             "end_seconds": 10, "text": "先转写视频，再核对字幕。"}]


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.Session = sessionmaker(self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        self.user_id = 1
        with self.Session() as db:
            db.add_all([User(id=1, username="test-owner", password_hash="unused", role="user"),
                        User(id=2, username="test-other", password_hash="unused", role="user")])
            db.add(Plan(code="free", name="test", monthly_minutes=100, max_video_minutes=120,
                concurrency_limit=10, ai_summary_limit=5, ai_rewrite_limit=5, ai_highlights_limit=5,
                ai_visual_limit=5, ai_translate_limit=5))
            db.flush()
            db.add(UserEntitlement(user_id=1, plan_code="free", period_start=utcnow() - timedelta(days=1), period_end=utcnow() + timedelta(days=30)))
            db.add(Task(id="test-task", user_id=1, source_type="url", source_url="https://www.youtube.com/watch?v=synthetic",
                status="completed", segments=SEGMENTS, transcript_text=SEGMENTS[0]["text"], rewrite_text="旧改写稿"))
            db.commit()

        def database():
            with self.Session() as db:
                yield db

        def user():
            with self.Session() as db:
                return db.get(User, self.user_id)

        main.app.dependency_overrides[get_db] = database
        main.app.dependency_overrides[current_user] = user
        self.client = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()
        self.client.close()
        self.engine.dispose()

    def test_rewrite_persists_and_rejects_stale_tabs(self):
        response = self.client.patch("/api/tasks/test-task/rewrite", json={"text": "编辑后保存的稿件", "base_version": None})
        self.assertEqual(response.status_code, 200)
        current = self.client.get("/api/tasks/test-task").json()
        self.assertEqual(current["rewrite_text"], "编辑后保存的稿件")
        self.assertEqual(current["rewrite_version"], response.json()["rewrite_version"])
        stale = self.client.patch("/api/tasks/test-task/rewrite", json={"text": "旧页面修改", "base_version": None})
        self.assertEqual(stale.status_code, 409)
        versions = self.client.get("/api/tasks/test-task/versions").json()
        self.assertEqual(len(versions), 2)
        legacy = next(v for v in versions if v["origin"] == "legacy")
        self.assertEqual(self.client.post(f"/api/tasks/test-task/versions/{legacy['id']}/restore").status_code, 200)
        self.assertEqual(self.client.get("/api/tasks/test-task").json()["rewrite_text"], "旧改写稿")
        self.assertEqual(len(self.client.get("/api/tasks/test-task/versions").json()), 3)

    def test_versions_and_ai_actions_stay_with_owner(self):
        self.client.patch("/api/tasks/test-task/rewrite", json={"text": "新稿"})
        version = self.client.get("/api/tasks/test-task/versions").json()[0]["id"]
        self.user_id = 2
        for method, url, body in [
            ("get", "/api/tasks/test-task/versions", None),
            ("get", f"/api/tasks/test-task/versions/{version}", None),
            ("post", f"/api/tasks/test-task/versions/{version}/restore", {}),
            ("patch", "/api/tasks/test-task/rewrite", {"text": "not owned"}),
            ("post", "/api/tasks/test-task/questions", {"question": "内容是什么？"}),
            ("post", "/api/tasks/test-task/retranscribe", {}),
        ]:
            options = {"json": body} if body is not None else {}
            self.assertEqual(getattr(self.client, method)(url, **options).status_code, 404, url)

    def test_transcript_revision_and_stale_results(self):
        segments = [{**SEGMENTS[0], "text": "先核对人名，再保存。"}]
        result = self.client.patch("/api/tasks/test-task/transcript", json={"segments": segments, "revision": 1})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["transcript_revision"], 2)
        self.assertIn("rewrite", result.json()["stale_results"])
        self.assertEqual(self.client.patch("/api/tasks/test-task/transcript", json={"segments": SEGMENTS, "revision": 1}).status_code, 409)
        with patch("app.main.enqueue"):
            self.assertEqual(self.client.post("/api/tasks/test-task/summary").status_code, 200)
        self.assertEqual(self.client.patch("/api/tasks/test-task/transcript", json={"segments": SEGMENTS, "revision": 2}).status_code, 409)

    def test_queue_failure_returns_reserved_quota(self):
        with patch("app.main.enqueue", side_effect=RuntimeError("offline")):
            response = self.client.post("/api/tasks/test-task/questions", json={"question": "怎样整理字幕？"})
        self.assertEqual(response.status_code, 503)
        with self.Session() as db:
            usage = db.scalar(select(AIFeatureUsage))
            self.assertEqual(usage.status, "released")
            self.assertEqual(db.get(Task, "test-task").ai_status, "failed")

    def test_timeout_recovery_preserves_transcript(self):
        with patch("app.main.enqueue"):
            self.client.post("/api/tasks/test-task/summary")
        job = SimpleNamespace(args=["test-task"], func_name="app.jobs.summarize_task")
        with patch("app.database.SessionLocal", self.Session):
            worker.ai_failure(job, None, TimeoutError, TimeoutError(), None)
        with self.Session() as db:
            task = db.get(Task, "test-task")
            self.assertEqual(task.ai_status, "failed")
            self.assertEqual(task.status, "completed")
            self.assertEqual(task.transcript_text, SEGMENTS[0]["text"])
            self.assertEqual(db.scalar(select(AIFeatureUsage)).status, "released")

    def test_successful_question_persists_grounded_citations(self):
        with patch("app.main.enqueue"):
            self.client.post("/api/tasks/test-task/questions", json={"question": "先做什么？"})
        result = {"value": "先转写视频。", "citations": [{"segment_id": 0, **SEGMENTS[0]}]}
        with patch("app.jobs.SessionLocal", self.Session), patch("app.jobs.answer_question", return_value=result):
            jobs.question_task("test-task", "先做什么？")
        data = self.client.get("/api/tasks/test-task").json()
        self.assertEqual(data["latest_answer"]["citations"][0]["text"], SEGMENTS[0]["text"])
        with self.Session() as db:
            self.assertEqual(db.scalar(select(AIFeatureUsage)).status, "used")

    def test_subtitles_skip_download_and_asr(self):
        with self.Session() as db:
            task = db.get(Task, "test-task"); task.status = "queued"; db.commit()
        result = subtitles.SubtitleResult("字幕标题", 10, SEGMENTS, "author_subtitles", "zh")
        with patch("app.jobs.SessionLocal", self.Session), patch("app.jobs.fetch_subtitles", return_value=result), \
             patch("app.jobs.download_video") as download, patch("app.jobs.ASRClient") as asr, patch("app.jobs._schedule_cleanup"):
            jobs.transcribe_task("test-task")
        download.assert_not_called(); asr.assert_not_called()
        with self.Session() as db:
            task = db.get(Task, "test-task")
            self.assertEqual(task.status, "completed")
            self.assertEqual(task.transcript_source, "author_subtitles")
            self.assertEqual(task.segments, SEGMENTS)

    def test_subtitle_failure_falls_back_to_asr(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "source.mp3"; audio.write_bytes(b"synthetic")
            asr = Mock(); asr.config = {"asr_provider": "custom"}; asr.transcribe.return_value = {"text": "语音识别结果", "segments": []}
            with patch("app.jobs.SessionLocal", self.Session), patch("app.jobs.fetch_subtitles", side_effect=RuntimeError("private")), \
                 patch("app.jobs.download_video", return_value=(audio, "测试音频", True, None, None)), \
                 patch("app.jobs.probe_duration", return_value=10), patch("app.jobs.split_audio", return_value=[audio]), \
                 patch("app.jobs.ASRClient", return_value=asr), patch("app.jobs._schedule_cleanup"):
                jobs.transcribe_task("test-task")
            with self.Session() as db:
                task = db.get(Task, "test-task")
                self.assertEqual(task.status, "completed")
                self.assertEqual(task.transcript_source, "asr")
                self.assertEqual(task.transcript_text, "语音识别结果")

    def test_additive_upgrade_is_repeatable(self):
        columns = ["extraction_mode", "transcript_source", "transcript_language", "transcript_revision", "result_revisions"]
        with self.engine.begin() as conn:
            for column in columns:
                conn.execute(text(f"ALTER TABLE tasks DROP COLUMN {column}"))
        with patch("app.main.engine", self.engine):
            main._ensure_schema(); main._ensure_schema()
        with self.Session() as db:
            task = db.get(Task, "test-task")
            self.assertEqual(task.transcript_text, SEGMENTS[0]["text"])
            self.assertEqual(task.transcript_revision, 1)


class SubtitleParsingTests(unittest.TestCase):
    def test_vtt_srt_and_platform_json(self):
        vtt = "WEBVTT\n\n00:00:01.200 --> 00:00:03.400 align:start\n<c>你好 &amp; 世界</c>\n"
        result = subtitles.parse_subtitles(vtt, "vtt")
        self.assertEqual(result[0]["text"], "你好 & 世界")
        self.assertEqual(result[0]["start_seconds"], 1.2)
        self.assertEqual(subtitles.parse_subtitles("1\n00:00:01,000 --> 00:00:02,000\n字幕\n", "srt")[0]["end_seconds"], 2)
        self.assertEqual(subtitles.parse_subtitles(json.dumps({"body": [{"from": 0, "to": 2, "content": "B站字幕"}]}), "json")[0]["text"], "B站字幕")
        self.assertEqual(subtitles.parse_subtitles(json.dumps({"events": [{"tStartMs": 0, "dDurationMs": 1000, "segs": [{"utf8": "自动字幕"}]}]}), "json3")[0]["text"], "自动字幕")

    def test_author_track_precedes_automatic_track(self):
        info = {"title": "test", "duration": 2, "subtitles": {"en": [{"ext": "vtt", "url": "https://www.youtube.com/manual"}]},
                "automatic_captions": {"zh-orig": [{"ext": "vtt", "url": "https://www.youtube.com/auto"}]}}
        with patch("app.services.subtitles.validate_public_url"), patch.object(subtitles.yt_dlp, "YoutubeDL") as ydl, \
             patch("app.services.subtitles._track_text", return_value="00:00:00.000 --> 00:00:02.000\nhello"):
            ydl.return_value.__enter__.return_value.extract_info.return_value = info
            self.assertEqual(subtitles.fetch_subtitles("https://www.youtube.com/watch?v=synthetic").source, "author_subtitles")

    def test_redirect_to_private_address_is_never_requested(self):
        response = Mock(status_code=302, headers={"Location": "https://127.0.0.1/subtitles"})
        response.__enter__ = Mock(return_value=response); response.__exit__ = Mock(return_value=False)
        session = Mock(); session.get.return_value = response
        with patch("app.services.subtitles.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("8.8.8.8", 443))]):
            with self.assertRaises(ValueError):
                subtitles._track_text(session, "https://www.youtube.com/subtitles")
        self.assertEqual(session.get.call_count, 1)


class ModelReliabilityTests(unittest.TestCase):
    CONFIG = {"sub2api_base_url": "https://synthetic.invalid/v1", "sub2api_api_key": "synthetic-key",
              "llm_primary_model": "primary", "sub2api_fallback_api_key": "synthetic-backup", "llm_fallback_model": "backup"}

    def response(self, content, status=200):
        return Mock(status_code=status, json=Mock(return_value={"choices": [{"message": {"content": content}}]}))

    def test_malformed_json_tries_configured_fallback(self):
        with patch("app.services.llm.provider_config", return_value=self.CONFIG), \
             patch("app.services.llm.requests.post", side_effect=[self.response("invalid json"), self.response("invalid again"), self.response('{"ok":true}')]) as request:
            self.assertEqual(llm._call([], expect_json=True), '{"ok":true}')
            self.assertEqual(request.call_count, 3)
            self.assertEqual(request.call_args.kwargs["json"]["model"], "backup")

    def test_errors_never_echo_upstream_credentials(self):
        with patch("app.services.llm.provider_config", return_value={**self.CONFIG, "sub2api_fallback_api_key": ""}), \
             patch("app.services.llm.requests.post", return_value=Mock(status_code=401, text="synthetic-key")):
            with self.assertRaises(RuntimeError) as error:
                llm._call([])
            self.assertNotIn("synthetic-key", str(error.exception))
            self.assertIn("401", str(error.exception))

    def test_highlights_resolve_quotes_from_source(self):
        data = [{"start": "00:00:00", "end": "00:00:10", "original_text": "模型编造的原话", "score": 9}]
        with patch("app.services.llm._call", return_value=json.dumps(data)):
            result = llm.find_highlights("test", SEGMENTS)
        self.assertEqual(result[0]["original_text"], SEGMENTS[0]["text"])
        with patch("app.services.llm._call", return_value='[{"start":"99:00:00","end":"99:00:10"}]'):
            with self.assertRaises(RuntimeError): llm.find_highlights("test", SEGMENTS)

    def test_question_citations_cannot_escape_selected_source(self):
        with patch("app.services.llm._call", return_value='{"answer":"依据原文", "segment_ids":[0,999]}'):
            result = llm.answer_question("test", SEGMENTS, "字幕怎么核对？")
        self.assertEqual(len(result["citations"]), 1)
        self.assertEqual(result["citations"][0]["text"], SEGMENTS[0]["text"])


if __name__ == "__main__":
    unittest.main()

from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse
import re
import shutil

from sqlalchemy import and_, or_, select

from .config import settings
from .database import SessionLocal
from .models import Task, User, utcnow
from .services.asr import ASRClient
from .services.llm import find_highlights, rewrite_script, summarize_transcript, translate_transcript
from .services.media import AUDIO_SUFFIXES, _direct_media_suffix, download_original_video, download_video, ensure_browser_preview, ensure_cover_image, ensure_download_audio, extract_audio, media_kind, probe_duration, split_audio
from .services.vision import analyze_visuals


def _update(db, task: Task, **values):
    # UI status fields are intentionally short; never let a provider's verbose
    # error response prevent the worker from recording the failed state.
    for key in ("message", "ai_message"):
        if key in values and values[key] is not None:
            values[key] = str(values[key])[:300]
    for key, value in values.items():
        setattr(task, key, value)
    task.updated_at = utcnow()
    db.commit()


def _schedule_cleanup(task_id: str, delay: timedelta):
    from .worker import queue
    queue.enqueue_in(
        delay, cleanup_source_task, task_id,
        job_timeout=300, result_ttl=3600,
    )


def _needs_title_repair(title: str | None) -> bool:
    value = str(title or '').strip()
    if not value or value in {'网络视频', '快手视频', '未命名视频', 'video', 'audio'}:
        return True
    if '\ufffd' in value or re.search(r'[ÃÂÐÑ][\x80-\xff]', value):
        return True
    compact = re.sub(r'[^0-9a-f]', '', value.lower())
    return len(value) >= 16 and len(compact) == len(value)


def _title_from_transcript(text: str) -> str:
    compact = re.sub(r'\s+', ' ', str(text or '')).strip()
    if not compact:
        return '未命名视频'
    first = re.split(r'[。！？!?；;]', compact, maxsplit=1)[0].strip(' ,，、:：')
    candidate = first if len(first) >= 4 else compact
    return candidate[:36].rstrip('，。！？!?；;') or '未命名视频'


def transcribe_task(task_id: str):
    from .billing import reserve_minutes, settle_minutes
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        if not task:
            return
        task_dir = settings.data_dir / "tasks" / task.id
        duration = 0.0
        try:
            _update(db, task, status="preparing", progress=5, message="正在准备视频", error=None)
            audio_only = False
            if task.source_type == "url":
                _update(db, task, status="downloading", progress=8, message="正在准备听写音频和播放地址")
                media_path, title, audio_only, playback_url, playback_audio_url = download_video(task.source_url or "", task_dir)
                task.media_path, task.title = str(media_path), title
                task.source_playback_url = playback_url
                task.source_playback_audio_url = playback_audio_url
                if playback_url:
                    playback_suffix = _direct_media_suffix(playback_url) or Path(urlparse(playback_url).path).suffix.lower()
                    task.source_playback_kind = "audio" if playback_suffix in AUDIO_SUFFIXES else "video"
                else:
                    task.source_playback_kind = None
                db.commit()
            else:
                media_path = Path(task.media_path or "")
            duration = probe_duration(media_path)
            reserve_minutes(db, task, duration)
            long_media = duration >= settings.url_audio_only_minutes * 60
            if media_kind(media_path) == "video":
                _update(db, task, progress=9, message="正在整理视频素材")
                try:
                    ensure_cover_image(media_path, task_dir)
                except Exception:
                    # A missing cover must not block transcription.
                    pass
                try:
                    ensure_download_audio(media_path, task_dir)
                except Exception:
                    # Audio export is an optional convenience, not an ASR dependency.
                    pass
            if audio_only or media_kind(media_path) == "audio":
                _update(db, task, progress=10, message="长视频已切换为音频听写模式")
            elif long_media:
                _update(db, task, progress=10, message="长视频跳过预览，直接提取音频")
            else:
                _update(db, task, progress=10, message="正在生成浏览器预览")
                try:
                    ensure_browser_preview(media_path, task_dir)
                except Exception:
                    # Preview compatibility must not prevent transcription.
                    pass
            extraction_message = "正在提取音频（长视频模式）" if audio_only or long_media or media_kind(media_path) == "audio" else "正在提取音频"
            _update(db, task, duration=duration, progress=14, message=extraction_message)
            client = ASRClient()
            task.asr_provider = client.config["asr_provider"]
            db.commit()
            # AssemblyAI performs diarization over the complete recording. Do
            # not split it into independent jobs, otherwise speaker labels can
            # restart in every chunk (Speaker A in one chunk may be Speaker B
            # in the next). Other providers keep the existing chunk strategy.
            diarization_provider = client.config["asr_provider"] in {"assemblyai", "tencent"}
            if diarization_provider and duration <= 2 * 60 * 60:
                chunks = [extract_audio(media_path, task_dir)]
            else:
                chunks = split_audio(media_path, task_dir, settings.asr_chunk_seconds)
            segments = []
            text_parts = []
            for index, chunk in enumerate(chunks):
                whole_recording = diarization_provider and duration <= 2 * 60 * 60
                start_s = 0 if whole_recording else index * settings.asr_chunk_seconds
                end_s = duration if whole_recording else min(duration, (index + 1) * settings.asr_chunk_seconds)
                pct = 18 + int((index / len(chunks)) * 76)
                _update(db, task, status="transcribing", progress=pct, message=f"正在听写第 {index + 1}/{len(chunks)} 段")
                result = client.transcribe(chunk)
                text = result["text"]
                if text:
                    detailed = result.get("segments") or []
                    if detailed:
                        for item in detailed:
                            item_start = min(duration, start_s + max(0.0, item["start_seconds"]))
                            item_end = min(duration, start_s + max(item["start_seconds"], item["end_seconds"]))
                            if item_end > item_start:
                                segment = {
                                    "start": _clock(item_start), "end": _clock(item_end),
                                    "start_seconds": item_start, "end_seconds": item_end,
                                    "text": item["text"],
                                }
                                if item.get("speaker"):
                                    segment["speaker"] = item["speaker"]
                                segments.append(segment)
                    else:
                        segments.append({"start": _clock(start_s), "end": _clock(end_s), "start_seconds": start_s, "end_seconds": end_s, "text": text})
                    text_parts.append(text)
            if not text_parts:
                raise RuntimeError("没有识别到可用的语音内容")
            if _needs_title_repair(task.title):
                task.title = _title_from_transcript(" ".join(text_parts))
            _update(
                db, task, status="completed", progress=100, message="听写完成",
                transcript_text="\n".join(text_parts), segments=segments,
                source_delete_at=utcnow() + timedelta(hours=settings.source_retention_hours),
            )
            settle_minutes(db, task.id, duration, success=True)
            _schedule_cleanup(task.id, timedelta(hours=settings.source_retention_hours))
        except Exception as exc:
            settle_minutes(db, task.id, duration, success=False)
            deadline = utcnow() + timedelta(hours=settings.source_retention_hours)
            _update(db, task, status="failed", message="听写失败", error=str(exc), source_delete_at=deadline)
            try:
                _schedule_cleanup(task.id, timedelta(hours=settings.source_retention_hours))
            except Exception:
                # The failed task remains visible for manual cleanup if the
                # scheduler is temporarily unavailable.
                pass


def download_source_task(task_id: str):
    """Download the original video as a separate user-visible artifact."""
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        if not task or task.task_kind != "download":
            return
        task_dir = settings.data_dir / "tasks" / task.id
        last_reported = 0
        try:
            _update(db, task, status="preparing", progress=3, message="正在解析视频链接", error=None)
            _update(db, task, status="downloading", progress=5, message="正在下载原视频")

            def report_progress(value: int):
                nonlocal last_reported
                value = max(5, min(95, int(value)))
                if value >= last_reported + 5:
                    last_reported = value
                    _update(db, task, status="downloading", progress=value, message=f"正在下载原视频 {value}%")

            account = db.get(User, task.user_id)
            media_path, title = download_original_video(
                task.source_url or "", task_dir, report_progress,
                use_douyin_cookies=bool(account and account.role == "admin"),
            )
            try:
                duration = probe_duration(media_path)
            except Exception:
                duration = 0
            deadline = utcnow() + timedelta(hours=settings.source_retention_hours)
            _update(
                db, task, status="completed", progress=100, message="视频已准备好下载",
                title=title, duration=duration, media_path=str(media_path), source_delete_at=deadline,
            )
            _schedule_cleanup(task.id, timedelta(hours=settings.source_retention_hours))
        except Exception as exc:
            # A failed download has no user value; remove partial media now,
            # while retaining the failure record in history for diagnosis.
            shutil.rmtree(task_dir, ignore_errors=True)
            _update(
                db, task, status="failed", progress=0, message="下载失败",
                error=str(exc), media_path=None, source_delete_at=None,
            )


def highlight_task(task_id: str):
    from .billing import settle_ai_use
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        if not task:
            return
        try:
            _update(db, task, ai_status="highlighting", ai_message="Gemini 正在寻找亮点")
            highlights = find_highlights(task.title, task.segments or [], task.visual_analysis or [])
            _update(db, task, highlights=highlights, ai_status="idle", ai_message="亮点分析完成")
            settle_ai_use(db, task.id, "highlights", True)
        except Exception as exc:
            db.rollback()
            _update(db, task, ai_status="failed", ai_message=str(exc))
            settle_ai_use(db, task.id, "highlights", False)


def analyze_visual_task(task_id: str):
    from .billing import settle_ai_use
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        if not task:
            return
        temporary_dir = None
        try:
            _update(db, task, visual_status="analyzing", visual_message="正在抽取关键帧并分析画面")
            media_path = Path(task.media_path or "")
            if (not media_path.is_file() or media_kind(media_path) == "audio") and task.source_type == "url" and task.source_url:
                temporary_dir = settings.data_dir / "tasks" / task.id / "visual-source"
                media_path, _ = download_original_video(task.source_url, temporary_dir, use_douyin_cookies=True)
            if not media_path.is_file() or media_kind(media_path) == "audio":
                raise RuntimeError("没有可用的视频画面，无法分析")
            result = analyze_visuals(task.title, task.transcript_text or "", task.segments or [], media_path, settings.data_dir / "tasks" / task.id)
            _update(db, task, visual_analysis=result, visual_status="completed", visual_message="画面分析完成")
            settle_ai_use(db, task.id, "visual", True)
        except Exception as exc:
            db.rollback()
            _update(db, task, visual_status="failed", visual_message=str(exc)[:300])
            settle_ai_use(db, task.id, "visual", False)
        finally:
            if temporary_dir:
                shutil.rmtree(temporary_dir, ignore_errors=True)


def rewrite_task(task_id: str, direction: str):
    from .billing import settle_ai_use
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        if not task:
            return
        try:
            _update(db, task, ai_status="rewriting", ai_message="Gemini 正在改编文案")
            result = rewrite_script(task.title, task.transcript_text or "", direction)
            _update(db, task, rewrite_text=result, ai_status="idle", ai_message="改编完成")
            settle_ai_use(db, task.id, "rewrite", True)
        except Exception as exc:
            db.rollback()
            _update(db, task, ai_status="failed", ai_message=str(exc))
            settle_ai_use(db, task.id, "rewrite", False)


def summarize_task(task_id: str):
    from .billing import settle_ai_use
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        if not task:
            return
        try:
            _update(db, task, ai_status="summarizing", ai_message="正在总结视频文案")
            result = summarize_transcript(task.title, task.transcript_text or "")
            _update(db, task, summary_text=result, ai_status="idle", ai_message="文案总结完成")
            settle_ai_use(db, task.id, "summary", True)
        except Exception as exc:
            db.rollback()
            _update(db, task, ai_status="failed", ai_message=str(exc))
            settle_ai_use(db, task.id, "summary", False)


def translate_task(task_id: str, language: str):
    from .billing import settle_ai_use
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        if not task:
            return
        try:
            _update(db, task, ai_status="translating", ai_message=f"正在翻译为{language}")
            result = translate_transcript(task.title, task.transcript_text or "", language)
            _update(db, task, translated_text=result, translation_language=language, ai_status="idle", ai_message="文案翻译完成")
            settle_ai_use(db, task.id, "translate", True)
        except Exception as exc:
            db.rollback()
            _update(db, task, ai_status="failed", ai_message=str(exc))
            settle_ai_use(db, task.id, "translate", False)


def cleanup_expired_sources():
    with SessionLocal() as db:
        now = utcnow()
        legacy_cutoff = now - timedelta(hours=settings.source_retention_hours)
        expired = or_(
            Task.source_delete_at <= now,
            and_(
                Task.source_delete_at.is_(None),
                Task.status.in_(["completed", "failed"]),
                Task.created_at <= legacy_cutoff,
            ),
        )
        tasks = db.scalars(select(Task).where(expired, Task.media_path.is_not(None))).all()
        for task in tasks:
            from .services.media import delete_source
            delete_source(task.media_path)
            shutil.rmtree(settings.data_dir / "tasks" / task.id, ignore_errors=True)
            task.media_path = None
            task.source_playback_url = None
            task.source_playback_audio_url = None
            task.source_playback_kind = None
            task.updated_at = now
        db.commit()


def cleanup_source_task(task_id: str):
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        if not task or not task.source_delete_at or task.source_delete_at > utcnow():
            return
        from .services.media import delete_source
        delete_source(task.media_path)
        shutil.rmtree(settings.data_dir / "tasks" / task.id, ignore_errors=True)
        task.media_path = None
        task.source_playback_url = None
        task.source_playback_audio_url = None
        task.source_playback_kind = None
        task.source_delete_at = None
        db.commit()


def _clock(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"

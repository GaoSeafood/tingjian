from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from .config import settings
from .database import SessionLocal
from .models import Task, utcnow
from .services.asr import ASRClient
from .services.llm import find_highlights, rewrite_script
from .services.media import download_video, ensure_browser_preview, probe_duration, split_audio


def _update(db, task: Task, **values):
    for key, value in values.items():
        setattr(task, key, value)
    task.updated_at = utcnow()
    db.commit()


def transcribe_task(task_id: str):
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        if not task:
            return
        task_dir = settings.data_dir / "tasks" / task.id
        try:
            _update(db, task, status="preparing", progress=5, message="正在准备视频", error=None)
            if task.source_type == "url":
                _update(db, task, status="downloading", progress=8, message="正在下载视频")
                media_path, title = download_video(task.source_url or "", task_dir)
                task.media_path, task.title = str(media_path), title
                db.commit()
            else:
                media_path = Path(task.media_path or "")
            duration = probe_duration(media_path)
            _update(db, task, progress=10, message="正在生成浏览器预览")
            try:
                ensure_browser_preview(media_path, task_dir)
            except Exception:
                # Preview compatibility must not prevent transcription.
                pass
            _update(db, task, duration=duration, progress=14, message="正在提取音频")
            chunks = split_audio(media_path, task_dir, settings.asr_chunk_seconds)
            client = ASRClient()
            task.asr_provider = client.config["asr_provider"]
            db.commit()
            segments = []
            text_parts = []
            for index, chunk in enumerate(chunks):
                start_s = index * settings.asr_chunk_seconds
                end_s = min(duration, (index + 1) * settings.asr_chunk_seconds)
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
                                segments.append({
                                    "start": _clock(item_start), "end": _clock(item_end),
                                    "start_seconds": item_start, "end_seconds": item_end,
                                    "text": item["text"],
                                })
                    else:
                        segments.append({"start": _clock(start_s), "end": _clock(end_s), "start_seconds": start_s, "end_seconds": end_s, "text": text})
                    text_parts.append(text)
            if not text_parts:
                raise RuntimeError("没有识别到可用的语音内容")
            _update(
                db, task, status="completed", progress=100, message="听写完成",
                transcript_text="\n".join(text_parts), segments=segments,
                source_delete_at=utcnow() + timedelta(hours=settings.source_retention_hours),
            )
            from .worker import queue
            queue.enqueue_in(
                timedelta(hours=settings.source_retention_hours), cleanup_source_task, task.id,
                job_timeout=300, result_ttl=3600,
            )
        except Exception as exc:
            _update(db, task, status="failed", message="听写失败", error=str(exc))


def highlight_task(task_id: str):
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        if not task:
            return
        try:
            _update(db, task, ai_status="highlighting", ai_message="Gemini 正在寻找亮点")
            highlights = find_highlights(task.title, task.segments or [])
            _update(db, task, highlights=highlights, ai_status="idle", ai_message="亮点分析完成")
        except Exception as exc:
            _update(db, task, ai_status="failed", ai_message=str(exc))


def rewrite_task(task_id: str, direction: str):
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        if not task:
            return
        try:
            _update(db, task, ai_status="rewriting", ai_message="Gemini 正在改编文案")
            result = rewrite_script(task.title, task.transcript_text or "", direction)
            _update(db, task, rewrite_text=result, ai_status="idle", ai_message="改编完成")
        except Exception as exc:
            _update(db, task, ai_status="failed", ai_message=str(exc))


def cleanup_expired_sources():
    with SessionLocal() as db:
        tasks = db.scalars(select(Task).where(Task.source_delete_at <= utcnow(), Task.media_path.is_not(None))).all()
        for task in tasks:
            from .services.media import delete_source
            delete_source(task.media_path)
            task.media_path = None
        db.commit()


def cleanup_source_task(task_id: str):
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        if not task or not task.source_delete_at or task.source_delete_at > utcnow():
            return
        from .services.media import delete_source
        delete_source(task.media_path)
        task.media_path = None
        task.source_delete_at = None
        db.commit()


def _clock(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"

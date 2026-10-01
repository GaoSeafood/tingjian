from datetime import timedelta

from redis import Redis
from rq import Queue

from .config import settings


redis = Redis.from_url(settings.redis_url)
queue = Queue("tingjian", connection=redis, default_timeout=settings.job_timeout_seconds)
# AI actions live on their own queue so a slow URL download or long ASR job
# cannot leave a user-facing rewrite/highlight request waiting indefinitely.
ai_queue = Queue("tingjian-ai", connection=redis, default_timeout=settings.job_timeout_seconds)


def transcription_failure(job, connection, exc_type, exc_value, traceback):
    """Persist timeout/worker-kill failures and schedule source cleanup."""
    if not job.args:
        return
    task_id = str(job.args[0])
    from .database import SessionLocal
    from .jobs import cleanup_source_task
    from .models import Task, utcnow

    with SessionLocal() as db:
        task = db.get(Task, task_id)
        if not task:
            return
        deadline = utcnow() + timedelta(hours=settings.source_retention_hours)
        task.status = "failed"
        task.message = "下载失败" if task.task_kind == "download" else "听写失败"
        task.error = str(exc_value or exc_type or "后台任务异常")[:1000]
        task.source_delete_at = deadline
        task.updated_at = utcnow()
        db.commit()
        try:
            queue.enqueue_in(
                timedelta(hours=settings.source_retention_hours), cleanup_source_task, task.id,
                job_timeout=300, result_ttl=3600,
            )
        except Exception:
            pass


def enqueue(func, *args):
    options = {"job_timeout": settings.job_timeout_seconds, "result_ttl": 86400, "failure_ttl": 604800}
    if getattr(func, "__name__", "") in {"transcribe_task", "download_source_task"}:
        options["on_failure"] = transcription_failure
    target = ai_queue if getattr(func, "__name__", "") in {"highlight_task", "analyze_visual_task", "rewrite_task"} else queue
    return target.enqueue(func, *args, **options)

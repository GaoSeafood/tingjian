from datetime import timedelta

from redis import Redis
from rq import Queue

from .config import settings


redis = Redis.from_url(settings.redis_url)
queue = Queue("tingjian", connection=redis, default_timeout=settings.job_timeout_seconds)
pro_queue = Queue("tingjian-pro", connection=redis, default_timeout=settings.job_timeout_seconds)
ultra_queue = Queue("tingjian-ultra", connection=redis, default_timeout=settings.job_timeout_seconds)
# AI actions live on their own queue so a slow URL download or long ASR job
# cannot leave a user-facing rewrite/highlight request waiting indefinitely.
ai_queue = Queue("tingjian-ai", connection=redis, default_timeout=settings.job_timeout_seconds)
pro_ai_queue = Queue("tingjian-pro-ai", connection=redis, default_timeout=settings.job_timeout_seconds)
ultra_ai_queue = Queue("tingjian-ultra-ai", connection=redis, default_timeout=settings.job_timeout_seconds)


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
    if getattr(func, "__name__", "") in AI_FEATURES:
        options["on_failure"] = ai_failure
    priority = "normal"
    if args and isinstance(args[0], str):
        from .billing import get_entitlement
        from .database import SessionLocal
        from .models import Task, User

        with SessionLocal() as db:
            task = db.get(Task, args[0])
            if task:
                owner = db.get(User, task.user_id)
                if owner:
                    _, plan = get_entitlement(db, owner)
                    if owner.role == "admin" or plan.code.startswith("ultra_"):
                        priority = "ultra"
                    elif plan.code.startswith("pro_"):
                        priority = "pro"
    is_ai = getattr(func, "__name__", "") in AI_FEATURES
    target = (ultra_ai_queue if priority == "ultra" else pro_ai_queue if priority == "pro" else ai_queue) if is_ai else (ultra_queue if priority == "ultra" else pro_queue if priority == "pro" else queue)
    return target.enqueue(func, *args, **options)


AI_FEATURES = {"highlight_task": "highlights", "analyze_visual_task": "visual", "rewrite_task": "rewrite",
               "summarize_task": "summary", "translate_task": "translate", "question_task": "summary"}


def ai_failure(job, connection, exc_type, exc_value, traceback):
    """RQ timeouts must release quota and unlock the UI."""
    from .database import SessionLocal
    from .models import Task, utcnow
    from .billing import settle_ai_use
    feature = AI_FEATURES.get(job.func_name.rsplit(".", 1)[-1])
    if not feature or not job.args:
        return
    with SessionLocal() as db:
        task = db.get(Task, str(job.args[0]))
        if task:
            if feature == "visual":
                if task.visual_status in {"completed", "failed"}:
                    return
                task.visual_status, task.visual_message = "failed", "画面分析中断，请重试；本次额度已退回"
            else:
                if task.ai_status in {"idle", "failed"}:
                    return
                task.ai_status, task.ai_message = "failed", "AI 处理中断，请重试；本次额度已退回"
            task.updated_at = utcnow()
            db.commit()
            settle_ai_use(db, task.id, feature, False)

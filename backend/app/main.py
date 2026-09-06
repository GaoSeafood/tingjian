import json
import re
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .auth import create_session, current_user, hash_password, seed_admin, verify_password
from .config import settings
from .database import Base, engine, get_db
from .jobs import highlight_task, rewrite_task, transcribe_task
from .models import Task, User
from .provider_config import provider_config, public_provider_config, update_provider_config
from .services.media import AUDIO_SUFFIXES, VIDEO_SUFFIXES, delete_source, extract_video_url, media_kind
from .worker import enqueue


class LoginBody(BaseModel):
    username: str
    password: str


class UrlBody(BaseModel):
    url: str


class TranscriptBody(BaseModel):
    segments: list[dict]


class RewriteBody(BaseModel):
    direction: str = ""


class ProviderSettingsBody(BaseModel):
    asr_provider: str | None = None
    mimo_api_key: str | None = None
    mimo_base_url: str | None = None
    mimo_model: str | None = None
    asr_language: str | None = None
    custom_asr_base_url: str | None = None
    custom_asr_api_key: str | None = None
    custom_asr_model: str | None = None
    sub2api_base_url: str | None = None
    sub2api_api_key: str | None = None
    sub2api_fallback_api_key: str | None = None
    llm_primary_model: str | None = None
    llm_fallback_model: str | None = None


class PasswordBody(BaseModel):
    current_password: str
    new_password: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    seed_admin()
    yield


app = FastAPI(title="听见", lifespan=lifespan)


def task_dict(task: Task, detail: bool = False):
    data = {
        "id": task.id, "title": task.title, "source_type": task.source_type,
        "duration": task.duration, "language": task.language, "status": task.status,
        "progress": task.progress, "message": task.message, "error": task.error,
        "asr_provider": task.asr_provider, "ai_status": task.ai_status,
        "ai_message": task.ai_message, "source_available": bool(task.media_path),
        "media_kind": media_kind(task.media_path),
        "source_delete_at": task.source_delete_at.isoformat() if task.source_delete_at else None,
        "created_at": task.created_at.isoformat(), "updated_at": task.updated_at.isoformat(),
    }
    if detail:
        data.update({
            "transcript_text": task.transcript_text, "segments": task.segments or [],
            "highlights": task.highlights, "rewrite_text": task.rewrite_text,
        })
    return data


def owned_task(task_id: str, user: User, db: Session) -> Task:
    task = db.scalar(select(Task).where(Task.id == task_id, Task.user_id == user.id))
    if not task:
        raise HTTPException(404, "任务不存在")
    return task


@app.get("/api/health")
def health():
    cfg = provider_config()
    return {"ok": True, "asr": cfg["asr_provider"], "mimo_configured": bool(cfg["mimo_api_key"]), "llm_configured": bool(cfg["sub2api_api_key"])}


@app.post("/api/auth/login")
def login(body: LoginBody, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    response.set_cookie(
        "tingjian_session", create_session(user.id), httponly=True,
        secure=settings.secure_cookie, samesite="lax", max_age=settings.session_max_age,
    )
    return {"username": user.username}


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie("tingjian_session")
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: User = Depends(current_user)):
    return {"username": user.username, "role": user.role}


@app.post("/api/auth/change-password")
def change_password(body: PasswordBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "当前密码不正确")
    if len(body.new_password) < 12:
        raise HTTPException(400, "新密码至少需要 12 个字符")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True}


@app.get("/api/settings/providers")
def get_provider_settings(user: User = Depends(current_user)):
    if user.role != "admin":
        raise HTTPException(403, "仅管理员可以查看接口设置")
    return public_provider_config()


@app.put("/api/settings/providers")
def put_provider_settings(body: ProviderSettingsBody, user: User = Depends(current_user)):
    if user.role != "admin":
        raise HTTPException(403, "仅管理员可以修改接口设置")
    try:
        return update_provider_config(body.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/tasks")
def list_tasks(user: User = Depends(current_user), db: Session = Depends(get_db)):
    items = db.scalars(select(Task).where(Task.user_id == user.id).order_by(desc(Task.created_at)).limit(50)).all()
    return [task_dict(item) for item in items]


@app.post("/api/tasks/upload")
async def upload_task(
    video: UploadFile = File(...), language: str = Form("auto"),
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    task_id = str(uuid.uuid4())
    task_dir = settings.data_dir / "tasks" / task_id
    task_dir.mkdir(parents=True, exist_ok=False)
    suffix = Path(video.filename or "video.mp4").suffix.lower() or ".mp4"
    content_type = (video.content_type or "").lower()
    if suffix not in VIDEO_SUFFIXES | AUDIO_SUFFIXES:
        if content_type.startswith("audio/"):
            suffix = ".mp3"
        elif content_type.startswith("video/"):
            suffix = ".mp4"
        else:
            shutil.rmtree(task_dir, ignore_errors=True)
            raise HTTPException(400, "不支持这种视频或音频格式")
    if suffix not in VIDEO_SUFFIXES | AUDIO_SUFFIXES:
        shutil.rmtree(task_dir, ignore_errors=True)
        raise HTTPException(400, "不支持这种视频或音频格式")
    media_path = task_dir / f"source{suffix}"
    max_bytes = settings.max_upload_mb * 1024 * 1024
    written = 0
    try:
        with media_path.open("wb") as target:
            while chunk := await video.read(1024 * 1024):
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(413, f"文件不能超过 {settings.max_upload_mb}MB")
                target.write(chunk)
    except Exception:
        shutil.rmtree(task_dir, ignore_errors=True)
        raise
    title = re.sub(r"\.[^.]+$", "", video.filename or "本地视频")[:300]
    task = Task(id=task_id, user_id=user.id, title=title, source_type="file", media_path=str(media_path), language=language, asr_provider=provider_config()["asr_provider"])
    db.add(task)
    db.commit()
    enqueue(transcribe_task, task.id)
    return task_dict(task)


@app.post("/api/tasks/url")
def url_task(body: UrlBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        url = extract_video_url(body.url)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    task_id = str(uuid.uuid4())
    (settings.data_dir / "tasks" / task_id).mkdir(parents=True, exist_ok=False)
    task = Task(id=task_id, user_id=user.id, title="网络视频", source_type="url", source_url=url, language="auto", asr_provider=provider_config()["asr_provider"])
    db.add(task)
    db.commit()
    enqueue(transcribe_task, task.id)
    return task_dict(task)


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return task_dict(owned_task(task_id, user, db), detail=True)


@app.patch("/api/tasks/{task_id}/transcript")
def save_transcript(task_id: str, body: TranscriptBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = owned_task(task_id, user, db)
    task.segments = body.segments
    task.transcript_text = "\n".join(str(item.get("text", "")).strip() for item in body.segments if item.get("text"))
    db.commit()
    return task_dict(task, detail=True)


@app.post("/api/tasks/{task_id}/highlights")
def start_highlights(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = owned_task(task_id, user, db)
    if task.status != "completed":
        raise HTTPException(409, "请先完成听写")
    if task.ai_status not in {"idle", "failed"}:
        raise HTTPException(409, "已有 AI 任务正在进行")
    task.ai_status, task.ai_message = "queued", "亮点分析已排队"
    db.commit()
    enqueue(highlight_task, task.id)
    return {"ok": True}


@app.post("/api/tasks/{task_id}/rewrite")
def start_rewrite(task_id: str, body: RewriteBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = owned_task(task_id, user, db)
    if task.status != "completed":
        raise HTTPException(409, "请先完成听写")
    if task.ai_status not in {"idle", "failed"}:
        raise HTTPException(409, "已有 AI 任务正在进行")
    task.ai_status, task.ai_message = "queued", "复刻改编已排队"
    db.commit()
    enqueue(rewrite_task, task.id, body.direction)
    return {"ok": True}


@app.delete("/api/tasks/{task_id}/source")
def remove_source(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = owned_task(task_id, user, db)
    delete_source(task.media_path)
    task.media_path = None
    task.source_delete_at = None
    db.commit()
    return {"ok": True}


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = owned_task(task_id, user, db)
    # Remove the complete task directory, including a partially downloaded
    # URL task that may not have media_path populated yet.
    task_dir = settings.data_dir / "tasks" / task.id
    delete_source(task.media_path)
    shutil.rmtree(task_dir, ignore_errors=True)
    db.delete(task)
    db.commit()
    return {"ok": True}


@app.get("/api/tasks/{task_id}/media")
def media(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = owned_task(task_id, user, db)
    if not task.media_path or not Path(task.media_path).exists():
        raise HTTPException(404, "原视频已删除")
    source = Path(task.media_path)
    preview = source.parent / "preview.mp4"
    return FileResponse(preview if preview.exists() else source)


@app.get("/api/tasks/{task_id}/export/{kind}")
def export(task_id: str, kind: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = owned_task(task_id, user, db)
    if kind == "txt":
        return PlainTextResponse(task.transcript_text or "", headers={"Content-Disposition": f'attachment; filename="{task.id[:8]}.txt"'})
    if kind == "srt":
        blocks = []
        for index, item in enumerate(task.segments or [], 1):
            blocks.append(f"{index}\n{_srt(item['start_seconds'])} --> {_srt(item['end_seconds'])}\n{item['text']}\n")
        return PlainTextResponse("\n".join(blocks), headers={"Content-Disposition": f'attachment; filename="{task.id[:8]}.srt"'})
    raise HTTPException(404, "不支持的导出格式")


def _srt(seconds: float) -> str:
    ms = int(seconds * 1000)
    return f"{ms // 3600000:02d}:{(ms % 3600000) // 60000:02d}:{(ms % 60000) // 1000:02d},{ms % 1000:03d}"


static_dir = Path(__file__).resolve().parents[2] / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")

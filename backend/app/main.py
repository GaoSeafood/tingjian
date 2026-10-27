import json
import hashlib
import hmac
import re
import secrets
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import delete, desc, func, inspect, select, text
from sqlalchemy.orm import Session

from .auth import create_session, current_user, hash_password, seed_admin, verify_password
from .billing import check_can_submit, ensure_entitlements, entitlement_dict, get_entitlement, month_bounds, reserve_ai_use, settle_ai_use
from .config import settings
from .database import Base, SessionLocal, engine, get_db
from .jobs import analyze_visual_task, cleanup_expired_sources, download_source_task, highlight_task, rewrite_task, summarize_task, translate_task, transcribe_task
from .models import AIFeatureUsage, BillingOrder, Plan, Task, UsageLedger, User, UserAPIKey, UserEntitlement, utcnow
from .provider_config import provider_config, public_provider_config, update_provider_config
from .services.media import AUDIO_SUFFIXES, VIDEO_SUFFIXES, _direct_media_suffix, delete_source, ensure_cover_image, ensure_remote_cover_image, extract_video_url, is_direct_media_url, is_direct_video_url, media_kind, source_platform_label
from .worker import enqueue


class LoginBody(BaseModel):
    username: str
    password: str


class UrlBody(BaseModel):
    url: str


class BatchUrlsBody(BaseModel):
    urls: list[str]


class TranscriptBody(BaseModel):
    segments: list[dict]


class RewriteBody(BaseModel):
    direction: str = ""


class TranslateBody(BaseModel):
    language: str


class APIKeyCreateBody(BaseModel):
    name: str = ""


class ProviderSettingsBody(BaseModel):
    asr_provider: str | None = None
    mimo_api_key: str | None = None
    mimo_base_url: str | None = None
    mimo_model: str | None = None
    siliconflow_base_url: str | None = None
    siliconflow_api_key: str | None = None
    siliconflow_model: str | None = None
    asr_language: str | None = None
    custom_asr_base_url: str | None = None
    custom_asr_api_key: str | None = None
    custom_asr_model: str | None = None
    assemblyai_base_url: str | None = None
    assemblyai_api_key: str | None = None
    assemblyai_model: str | None = None
    tencent_app_id: str | None = None
    tencent_secret_id: str | None = None
    tencent_secret_key: str | None = None
    tencent_engine_type: str | None = None
    sub2api_base_url: str | None = None
    sub2api_api_key: str | None = None
    sub2api_fallback_api_key: str | None = None
    llm_primary_model: str | None = None
    llm_fallback_model: str | None = None


class PasswordBody(BaseModel):
    current_password: str
    new_password: str


class UserCreateBody(BaseModel):
    username: str
    password: str


class PlanUpdateBody(BaseModel):
    name: str | None = None
    tier: str | None = None
    term_days: int | None = None
    price_fen: int | None = None
    monthly_minutes: int | None = None
    max_video_minutes: int | None = None
    concurrency_limit: int | None = None
    ai_summary_limit: int | None = None
    ai_highlights_limit: int | None = None
    ai_visual_limit: int | None = None
    ai_rewrite_limit: int | None = None
    ai_translate_limit: int | None = None
    is_active: bool | None = None


class AssignPlanBody(BaseModel):
    plan_code: str
    days: int = 30


class APITranscribeBody(BaseModel):
    url: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    _ensure_schema()
    seed_admin()
    with SessionLocal() as db:
        ensure_entitlements(db)
    cleanup_expired_sources()
    yield


app = FastAPI(title="听见", lifespan=lifespan)


def _ensure_schema():
    """Add fields introduced after the initial deployment without losing data."""
    additions = {
        "tasks": {
            "source_playback_url": "TEXT",
            "source_playback_audio_url": "TEXT",
            "source_playback_kind": "VARCHAR(20)",
            "task_kind": "VARCHAR(20) NOT NULL DEFAULT 'transcription'",
            "visual_analysis": "JSON",
            "visual_status": "VARCHAR(30) DEFAULT 'idle'",
            "visual_message": "VARCHAR(300) DEFAULT ''",
            "summary_text": "TEXT",
            "translated_text": "TEXT",
            "translation_language": "VARCHAR(40)",
        },
        "plans": {"tier": "VARCHAR(20) NOT NULL DEFAULT 'standard'", "term_days": "INTEGER NOT NULL DEFAULT 30",
                  "ai_summary_limit": "INTEGER NOT NULL DEFAULT 0", "ai_highlights_limit": "INTEGER NOT NULL DEFAULT 0",
                  "ai_visual_limit": "INTEGER NOT NULL DEFAULT 0", "ai_rewrite_limit": "INTEGER NOT NULL DEFAULT 0",
                  "ai_translate_limit": "INTEGER NOT NULL DEFAULT 0", "feature_version": "INTEGER NOT NULL DEFAULT 0"},
    }
    missing = []
    for table, columns in additions.items():
        existing = {item["name"] for item in inspect(engine).get_columns(table)}
        missing.extend((table, name, definition) for name, definition in columns.items() if name not in existing)
    if not missing: return
    with engine.begin() as connection:
        for table, name, definition in missing:
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))


def _playback_fallback_video(task_id: str) -> Path | None:
    folder = settings.data_dir / "tasks" / task_id / "playback-fallback"
    if not folder.is_dir():
        return None
    return next((path for path in folder.rglob("*") if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES), None)


def _source_is_retained(task: Task) -> bool:
    deadline = task.source_delete_at
    if not deadline:
        return True
    now = utcnow()
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=now.tzinfo)
    return deadline > now


def task_dict(task: Task, detail: bool = False):
    playback_url = task.source_playback_url
    source_path = Path(task.media_path) if task.media_path else None
    source_exists = bool(source_path and source_path.is_file())
    if task.task_kind != "download" and not playback_url and source_exists and task.source_type == "url" and task.source_url and is_direct_media_url(task.source_url):
        # Backfill direct-link playback for tasks created before this column
        # was introduced.
        playback_url = task.source_url
    task_dir = settings.data_dir / "tasks" / task.id
    fallback_video = _playback_fallback_video(task.id)
    current_media_kind = media_kind(task.media_path)
    playback_kind = task.source_playback_kind
    if not playback_kind:
        playback_suffix = _direct_media_suffix(playback_url or "") or Path(urlparse(playback_url or "").path).suffix.lower()
        if playback_suffix in AUDIO_SUFFIXES:
            playback_kind = "audio"
        elif playback_suffix in VIDEO_SUFFIXES:
            playback_kind = "video"
        else:
            playback_kind = current_media_kind
    cover_path = task_dir / "cover.jpg"
    can_generate_cover = _source_is_retained(task) and (
        bool(source_exists and current_media_kind == "video")
        or bool(fallback_video)
        or is_direct_video_url(playback_url)
    )
    data = {
        "id": task.id, "title": task.title, "source_type": task.source_type,
        "task_kind": task.task_kind,
        "duration": task.duration, "language": task.language, "status": task.status,
        "progress": task.progress, "message": task.message, "error": task.error,
        "asr_provider": task.asr_provider, "ai_status": task.ai_status,
        "ai_message": task.ai_message,
        "source_available": bool(task.media_path) if task.task_kind == "download" else bool(
            source_exists or playback_url or fallback_video
        ),
        "playback_url": playback_url if task.source_type == "url" else None,
        "playback_kind": playback_kind,
        "playback_audio_available": bool(task.source_playback_audio_url),
        "playback_fallback_available": bool(fallback_video),
        "local_playback_kind": "video" if fallback_video else current_media_kind,
        "local_media_kind": current_media_kind,
        "visual_status": task.visual_status, "visual_message": task.visual_message,
        "media_kind": current_media_kind,
        "cover_available": bool((cover_path.is_file() and cover_path.stat().st_size > 0) or can_generate_cover),
        "audio_available": bool((current_media_kind == "audio" and source_exists) or (task_dir / "audio" / "download.mp3").is_file()),
        "source_delete_at": task.source_delete_at.isoformat() if task.source_delete_at else None,
        "source_platform": source_platform_label(task.source_url) if task.source_type == "url" else "本地文件",
        "created_at": task.created_at.isoformat(), "updated_at": task.updated_at.isoformat(),
    }
    if detail:
        data.update({
            "transcript_text": task.transcript_text, "segments": task.segments or [],
            "highlights": task.highlights, "rewrite_text": task.rewrite_text,
            "summary_text": task.summary_text, "translated_text": task.translated_text,
            "translation_language": task.translation_language,
            "visual_analysis": task.visual_analysis,
            "source_url": task.source_url if task.source_type == "url" else None,
        })
    return data


def owned_task(task_id: str, user: User, db: Session) -> Task:
    task = db.scalar(select(Task).where(Task.id == task_id, Task.user_id == user.id))
    if not task:
        raise HTTPException(404, "任务不存在")
    return task


def owned_transcription_task(task_id: str, user: User, db: Session) -> Task:
    task = owned_task(task_id, user, db)
    if task.task_kind != "transcription":
        raise HTTPException(409, "此操作只适用于听写任务")
    return task


def admin_only(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "仅管理员可以执行此操作")
    return user


@app.get("/api/health")
def health():
    cfg = provider_config()
    return {
        "ok": True,
        "asr": cfg["asr_provider"],
        "mimo_configured": bool(cfg["mimo_api_key"]),
        "tencent_configured": bool(cfg["tencent_app_id"] and cfg["tencent_secret_id"] and cfg["tencent_secret_key"]),
        "llm_configured": bool(cfg["sub2api_api_key"]),
    }


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


@app.get("/api/admin/users")
def list_users(user: User = Depends(admin_only), db: Session = Depends(get_db)):
    users = db.scalars(select(User).order_by(User.created_at)).all()
    return [{"id": item.id, "username": item.username, "role": item.role, "created_at": item.created_at.isoformat(),
             "plan_code": (db.get(UserEntitlement, item.id).plan_code if db.get(UserEntitlement, item.id) else "free")}
            for item in users]


@app.post("/api/admin/users")
def create_user(body: UserCreateBody, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    username = body.username.strip()
    if len(username) < 3 or len(username) > 80:
        raise HTTPException(400, "用户名需要 3～80 个字符")
    if len(body.password) < 12:
        raise HTTPException(400, "初始密码至少需要 12 个字符")
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(409, "用户名已存在")
    account = User(username=username, password_hash=hash_password(body.password), role="user")
    db.add(account)
    db.commit()
    db.refresh(account)
    return {"id": account.id, "username": account.username, "role": account.role, "created_at": account.created_at.isoformat()}


@app.delete("/api/admin/users/{user_id}")
def delete_user(user_id: int, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    account = db.get(User, user_id)
    if not account:
        raise HTTPException(404, "用户不存在")
    if account.role == "admin" or account.id == user.id:
        raise HTTPException(403, "管理员账号不可删除")
    if db.scalar(select(BillingOrder.id).where(BillingOrder.user_id == account.id).limit(1)):
        raise HTTPException(409, "该账号存在账单记录，为保留财务审计记录暂不能删除")

    tasks = db.scalars(select(Task).where(Task.user_id == account.id)).all()
    has_active_task = any(
        task.status not in {"completed", "failed"}
        or task.ai_status not in {"idle", "completed", "failed"}
        or task.visual_status not in {"idle", "completed", "failed"}
        for task in tasks
    )
    if has_active_task:
        raise HTTPException(409, "该账号仍有任务运行，请任务完成或失败后再删除")

    task_paths = [(task.id, task.media_path) for task in tasks]
    db.execute(delete(AIFeatureUsage).where(AIFeatureUsage.user_id == account.id))
    db.execute(delete(UsageLedger).where(UsageLedger.user_id == account.id))
    db.execute(delete(UserAPIKey).where(UserAPIKey.user_id == account.id))
    db.execute(delete(UserEntitlement).where(UserEntitlement.user_id == account.id))
    for task in tasks:
        db.delete(task)
    db.delete(account)
    db.commit()

    for task_id, media_path in task_paths:
        delete_source(media_path)
        shutil.rmtree(settings.data_dir / "tasks" / task_id, ignore_errors=True)
    return {"ok": True}


@app.get("/api/billing/me")
def billing_me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return entitlement_dict(db, user)


def _require_ultra_api(user: User, db: Session) -> Plan:
    _, plan = get_entitlement(db, user)
    if not plan.code.startswith("ultra_") or not plan.is_active:
        raise HTTPException(403, "API 接入仅包含在有效的 Ultra 专业版套餐中")
    return plan


@app.get("/api/account/api-keys")
def list_api_keys(user: User = Depends(current_user), db: Session = Depends(get_db)):
    _require_ultra_api(user, db)
    rows = db.scalars(select(UserAPIKey).where(UserAPIKey.user_id == user.id).order_by(desc(UserAPIKey.created_at))).all()
    return [{"id": row.id, "name": row.name, "prefix": row.key_prefix,
             "created_at": row.created_at.isoformat(),
             "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
             "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None} for row in rows]


@app.post("/api/account/api-keys")
def create_api_key(body: APIKeyCreateBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _require_ultra_api(user, db)
    active_count = db.scalar(select(func.count()).select_from(UserAPIKey).where(UserAPIKey.user_id == user.id, UserAPIKey.revoked_at.is_(None))) or 0
    if active_count >= 5:
        raise HTTPException(409, "最多可同时保留 5 个有效 API Key")
    name = body.name.strip()[:80] or "API Key"
    secret = f"tj_live_{secrets.token_urlsafe(32)}"
    prefix = secret[:15]
    row = UserAPIKey(user_id=user.id, name=name, key_prefix=prefix, key_hash=hashlib.sha256(secret.encode()).hexdigest())
    db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "name": row.name, "prefix": row.key_prefix, "key": secret,
            "created_at": row.created_at.isoformat()}


@app.delete("/api/account/api-keys/{key_id}")
def revoke_api_key(key_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _require_ultra_api(user, db)
    row = db.scalar(select(UserAPIKey).where(UserAPIKey.id == key_id, UserAPIKey.user_id == user.id, UserAPIKey.revoked_at.is_(None)))
    if not row: raise HTTPException(404, "有效的 API Key 不存在")
    row.revoked_at = utcnow(); db.commit()
    return {"id": row.id, "revoked": True}


def api_key_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "请在 Authorization 请求头中提供 Bearer API Key")
    secret = authorization[7:].strip()
    if not secret.startswith("tj_live_"):
        raise HTTPException(401, "API Key 无效")
    digest = hashlib.sha256(secret.encode()).hexdigest()
    row = db.scalar(select(UserAPIKey).where(UserAPIKey.key_hash == digest, UserAPIKey.revoked_at.is_(None)))
    if not row or not hmac.compare_digest(row.key_hash, digest):
        raise HTTPException(401, "API Key 无效或已撤销")
    user = db.get(User, row.user_id)
    if not user: raise HTTPException(401, "API Key 所属账号不存在")
    _require_ultra_api(user, db)
    row.last_used_at = utcnow()
    db.commit()
    return user


@app.post("/api/v1/tasks")
def api_create_task(body: APITranscribeBody, user: User = Depends(api_key_user), db: Session = Depends(get_db)):
    try: url = extract_video_url(body.url)
    except ValueError as exc: raise HTTPException(400, str(exc))
    check_can_submit(db, user, lock=True)
    task_id = str(uuid.uuid4())
    (settings.data_dir / "tasks" / task_id).mkdir(parents=True, exist_ok=False)
    task = Task(id=task_id, user_id=user.id, title="网络视频", source_type="url", source_url=url,
                source_playback_url=url if is_direct_media_url(url) else None,
                language="auto", asr_provider=provider_config()["asr_provider"])
    db.add(task); db.commit()
    try: enqueue(transcribe_task, task.id)
    except Exception as exc:
        task.status, task.message, task.error = "failed", "任务排队失败", str(exc)[:300]
        db.commit()
    return task_dict(task)


@app.get("/api/v1/tasks/{task_id}")
def api_get_task(task_id: str, user: User = Depends(api_key_user), db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task or task.user_id != user.id or task.task_kind != "transcription":
        raise HTTPException(404, "听写任务不存在")
    return task_dict(task, detail=True)


@app.get("/api/billing/plans")
def billing_plans(user: User = Depends(current_user), db: Session = Depends(get_db)):
    plans = db.scalars(select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.sort_order)).all()
    return [{"code": plan.code, "name": plan.name, "tier": plan.tier, "term_days": plan.term_days, "price_fen": plan.price_fen,
             "monthly_minutes": plan.monthly_minutes, "max_video_minutes": plan.max_video_minutes,
             "concurrency_limit": plan.concurrency_limit,
             "ai_limits": {key: getattr(plan, f"ai_{key}_limit") for key in ("summary", "highlights", "visual", "rewrite", "translate")}}
            for plan in plans]


@app.post("/api/billing/orders")
def request_plan(body: AssignPlanBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    plan = db.get(Plan, body.plan_code)
    if not plan or not plan.is_active or plan.code in {"free", "legacy", "admin"} or not plan.price_fen:
        raise HTTPException(404, "套餐暂不可申请")
    current, _ = get_entitlement(db, user)
    if current.plan_code == plan.code:
        raise HTTPException(409, "你已在使用该套餐")
    pending = db.scalar(select(BillingOrder).where(
        BillingOrder.user_id == user.id, BillingOrder.status == "requested"
    ))
    if pending:
        raise HTTPException(409, "你已有待处理的开通申请，请等待管理员处理")
    order = BillingOrder(id=str(uuid.uuid4()), user_id=user.id, plan_code=plan.code,
                         amount_fen=plan.price_fen, status="requested")
    db.add(order); db.commit()
    return {"id": order.id, "plan_code": plan.code, "status": order.status}


@app.get("/api/billing/orders")
def billing_orders(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(BillingOrder).where(BillingOrder.user_id == user.id).order_by(desc(BillingOrder.created_at))).all()
    return [{"id": row.id, "plan_code": row.plan_code, "amount_fen": row.amount_fen,
             "status": row.status, "created_at": row.created_at.isoformat(),
             "paid_at": row.paid_at.isoformat() if row.paid_at else None} for row in rows]


@app.delete("/api/billing/orders/{order_id}")
def cancel_billing_order(order_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    order = db.scalar(select(BillingOrder).where(
        BillingOrder.id == order_id, BillingOrder.user_id == user.id, BillingOrder.status == "requested"
    ))
    if not order:
        raise HTTPException(404, "待处理申请不存在")
    order.status = "cancelled"
    db.commit()
    return {"id": order.id, "status": order.status}


@app.get("/api/admin/billing/orders")
def admin_billing_orders(user: User = Depends(admin_only), db: Session = Depends(get_db)):
    rows = db.scalars(select(BillingOrder).where(BillingOrder.status == "requested").order_by(BillingOrder.created_at)).all()
    return [{"id": row.id, "username": db.get(User, row.user_id).username if db.get(User, row.user_id) else "(deleted)",
             "plan_code": row.plan_code, "plan_name": db.get(Plan, row.plan_code).name if db.get(Plan, row.plan_code) else row.plan_code,
             "amount_fen": row.amount_fen, "created_at": row.created_at.isoformat()} for row in rows]


@app.post("/api/admin/billing/orders/{order_id}/fulfill")
def fulfill_billing_order(order_id: str, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    order = db.get(BillingOrder, order_id)
    if not order or order.status != "requested":
        raise HTTPException(404, "待处理申请不存在")
    target = db.get(User, order.user_id)
    plan = db.get(Plan, order.plan_code)
    if not target or not plan or not plan.is_active:
        raise HTTPException(409, "账号或套餐已不可用")
    now = utcnow()
    entitlement = db.get(UserEntitlement, target.id)
    if entitlement is None:
        start, end = month_bounds(now)
        entitlement = UserEntitlement(user_id=target.id, plan_code=plan.code, period_start=start, period_end=end)
        db.add(entitlement)
    entitlement.plan_code = plan.code
    entitlement.period_start = now
    entitlement.period_end = now + timedelta(days=30)
    entitlement.expires_at = None if plan.term_days == 0 else now + timedelta(days=plan.term_days)
    entitlement.used_minutes = 0
    order.status = "fulfilled"
    order.paid_at = now
    db.commit()
    return {"username": target.username, "plan": plan.name, "status": order.status}


@app.get("/api/admin/plans")
def admin_plans(user: User = Depends(admin_only), db: Session = Depends(get_db)):
    return [{"code": plan.code, "name": plan.name, "tier": plan.tier, "term_days": plan.term_days, "price_fen": plan.price_fen,
             "monthly_minutes": plan.monthly_minutes, "max_video_minutes": plan.max_video_minutes,
             "concurrency_limit": plan.concurrency_limit,
             **{f"ai_{key}_limit": getattr(plan, f"ai_{key}_limit") for key in ("summary", "highlights", "visual", "rewrite", "translate")},
             "is_active": plan.is_active, "sort_order": plan.sort_order}
            for plan in db.scalars(select(Plan).order_by(Plan.sort_order))]


@app.put("/api/admin/plans/{plan_code}")
def update_plan(plan_code: str, body: PlanUpdateBody, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    plan = db.get(Plan, plan_code)
    if not plan:
        raise HTTPException(404, "套餐不存在")
    values = body.model_dump(exclude_unset=True)
    if any(value is None for key, value in values.items() if key != "price_fen"):
        raise HTTPException(400, "除价格外，套餐字段不能留空")
    for key in ("price_fen", "monthly_minutes", "max_video_minutes", "concurrency_limit"):
        if key in values and values[key] is not None and values[key] < 0 and not (key == "monthly_minutes" and values[key] == -1):
            raise HTTPException(400, f"{key} 参数无效")
    for key in ("ai_summary_limit", "ai_highlights_limit", "ai_visual_limit", "ai_rewrite_limit", "ai_translate_limit"):
        if key in values and values[key] is not None and values[key] < -1:
            raise HTTPException(400, f"{key} 参数无效；-1 表示不限次数")
    if "term_days" in values and values["term_days"] is not None and values["term_days"] < 0:
        raise HTTPException(400, "套餐期限不能小于 0；0 表示永久")
    if "tier" in values and values["tier"] not in {"standard", "professional"}:
        raise HTTPException(400, "套餐等级无效")
    concurrency = values.get("concurrency_limit", plan.concurrency_limit)
    if concurrency is not None and concurrency < 1:
        raise HTTPException(400, "并发数必须至少为 1")
    if values.get("is_active") is True and plan.code not in {"free", "legacy", "admin"}:
        price = values.get("price_fen", plan.price_fen)
        minutes = values.get("monthly_minutes", plan.monthly_minutes)
        if price is None or price <= 0 or minutes <= 0:
            raise HTTPException(400, "启用付费套餐前请配置正数价格和月度时长")
    for key, value in values.items():
        setattr(plan, key, value)
    db.commit(); db.refresh(plan)
    return {"code": plan.code, "name": plan.name, "tier": plan.tier, "term_days": plan.term_days, "price_fen": plan.price_fen,
            "monthly_minutes": plan.monthly_minutes, "max_video_minutes": plan.max_video_minutes,
            "concurrency_limit": plan.concurrency_limit,
            **{f"ai_{key}_limit": getattr(plan, f"ai_{key}_limit") for key in ("summary", "highlights", "visual", "rewrite", "translate")},
            "is_active": plan.is_active}


@app.post("/api/admin/users/{user_id}/plan")
def assign_user_plan(user_id: int, body: AssignPlanBody, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    plan = db.get(Plan, body.plan_code)
    if not target or not plan:
        raise HTTPException(404, "账号或套餐不存在")
    if not plan.is_active:
        raise HTTPException(400, "此套餐尚未开放")
    if target.role == "admin":
        raise HTTPException(400, "管理员账号不需要分配套餐")
    if plan.term_days != 0 and (body.days < 1 or body.days > 3650):
        raise HTTPException(400, "套餐期限需在 1 至 3650 天之间")
    now = utcnow()
    paid_until = now + timedelta(days=body.days) if plan.term_days != 0 else None
    cycle_start, cycle_end = (month_bounds(now) if plan.code == "free" else (now, now + timedelta(days=30)))
    entitlement = db.get(UserEntitlement, target.id)
    if entitlement is None:
        entitlement = UserEntitlement(user_id=target.id, plan_code=plan.code, period_start=cycle_start, period_end=cycle_end)
        db.add(entitlement)
    entitlement.plan_code = plan.code
    entitlement.period_start = cycle_start
    entitlement.period_end = cycle_end
    entitlement.expires_at = None if plan.code == "free" or plan.term_days == 0 else paid_until
    entitlement.used_minutes = 0
    db.commit()
    return {"username": target.username, "plan": plan.name, "expires_at": entitlement.expires_at.isoformat() if entitlement.expires_at else None}


@app.get("/api/settings/providers")
def get_provider_settings(user: User = Depends(admin_only)):
    return public_provider_config()


@app.put("/api/settings/providers")
def put_provider_settings(body: ProviderSettingsBody, user: User = Depends(admin_only)):
    try:
        return update_provider_config(body.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/settings/douyin-cookies")
def get_douyin_cookie_status(user: User = Depends(admin_only)):
    path = settings.douyin_cookie_file
    user_agent_configured = settings.douyin_user_agent_file.is_file()
    if not path.is_file() or path.stat().st_size == 0:
        return {"configured": False, "updated_at": None, "user_agent_configured": user_agent_configured}
    return {
        "configured": True,
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
        "user_agent_configured": user_agent_configured,
    }


@app.post("/api/settings/douyin-cookies")
async def upload_douyin_cookies(
    cookies: UploadFile = File(...), user_agent: str = Form(""),
    user: User = Depends(admin_only),
):
    """Store an exported Netscape cookie file and matching browser UA."""
    raw = await cookies.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise HTTPException(413, "Cookie 文件不能超过 1MB")
    try:
        text_content = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(400, "Cookie 文件必须是 UTF-8 文本") from exc
    lines = [
        line.strip() for line in text_content.splitlines()
        if line.strip() and (not line.lstrip().startswith("#") or line.lstrip().startswith("#HttpOnly_"))
    ]
    if not lines or not any(line.removeprefix("#HttpOnly_").count("\t") >= 6 for line in lines):
        raise HTTPException(400, "请上传浏览器导出的 Netscape 格式 Cookie 文件（通常是 cookies.txt）")
    user_agent = user_agent.strip()
    if user_agent and (
        len(user_agent) > 512
        or any(ord(char) < 32 or ord(char) == 127 for char in user_agent)
        or not all(marker in user_agent for marker in ("Mozilla/5.0", "AppleWebKit/", "Chrome/", "Safari/"))
    ):
        raise HTTPException(400, "浏览器标识格式不正确，请重新从 Chrome 同步")
    path = settings.douyin_cookie_file
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp_path.write_text(text_content, encoding="utf-8")
        temp_path.chmod(0o600)
        temp_path.replace(path)
        path.chmod(0o600)
        if user_agent:
            user_agent_path = settings.douyin_user_agent_file
            user_agent_path.parent.mkdir(parents=True, exist_ok=True)
            user_agent_temp = user_agent_path.with_name(f".{user_agent_path.name}.{uuid.uuid4().hex}.tmp")
            try:
                user_agent_temp.write_text(user_agent, encoding="utf-8")
                user_agent_temp.chmod(0o600)
                user_agent_temp.replace(user_agent_path)
                user_agent_path.chmod(0o600)
            finally:
                if user_agent_temp.exists():
                    user_agent_temp.unlink()
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return {
        "configured": True,
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
        "user_agent_configured": settings.douyin_user_agent_file.is_file(),
    }


@app.get("/api/tasks")
def list_tasks(user: User = Depends(current_user), db: Session = Depends(get_db)):
    # Repair legacy tasks and missed delayed jobs whenever history is opened.
    cleanup_expired_sources()
    items = db.scalars(select(Task).where(Task.user_id == user.id).order_by(desc(Task.created_at)).limit(50)).all()
    return [task_dict(item) for item in items]


@app.post("/api/tasks/upload")
async def upload_task(
    video: UploadFile = File(...), language: str = Form("auto"),
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    check_can_submit(db, user, lock=False)
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
    try:
        check_can_submit(db, user, lock=True)
    except Exception:
        shutil.rmtree(task_dir, ignore_errors=True)
        raise
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
    check_can_submit(db, user)
    task_id = str(uuid.uuid4())
    (settings.data_dir / "tasks" / task_id).mkdir(parents=True, exist_ok=False)
    task = Task(
        id=task_id, user_id=user.id, title="网络视频", source_type="url", source_url=url,
        source_playback_url=url if is_direct_media_url(url) else None,
        language="auto", asr_provider=provider_config()["asr_provider"],
    )
    db.add(task)
    db.commit()
    enqueue(transcribe_task, task.id)
    return task_dict(task)


@app.post("/api/tasks/batch")
def batch_url_tasks(body: BatchUrlsBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not body.urls or len(body.urls) > 20:
        raise HTTPException(400, "每批请提交 1 至 20 条视频链接")
    urls = []
    for raw in body.urls:
        try:
            url = extract_video_url(raw)
        except ValueError as exc:
            raise HTTPException(400, f"链接无法解析：{str(exc)}")
        if url not in urls:
            urls.append(url)
    if not urls:
        raise HTTPException(400, "没有可处理的视频链接")
    tasks = []
    task_dirs = []
    try:
        for url in urls:
            check_can_submit(db, user, lock=True)
            task_id = str(uuid.uuid4())
            task_dir = settings.data_dir / "tasks" / task_id
            task_dir.mkdir(parents=True, exist_ok=False)
            task_dirs.append(task_dir)
            task = Task(id=task_id, user_id=user.id, title="网络视频", source_type="url", source_url=url,
                        source_playback_url=url if is_direct_media_url(url) else None,
                        language="auto", asr_provider=provider_config()["asr_provider"])
            db.add(task)
            db.flush()
            tasks.append(task)
        db.commit()
    except Exception:
        db.rollback()
        for task_dir in task_dirs: shutil.rmtree(task_dir, ignore_errors=True)
        raise
    for task in tasks:
        try:
            enqueue(transcribe_task, task.id)
        except Exception as exc:
            task.status, task.message, task.error = "failed", "任务排队失败", str(exc)[:300]
            db.add(task)
    db.commit()
    return {"tasks": [task_dict(task) for task in tasks]}


@app.post("/api/tasks/download")
def create_download_task(body: UrlBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Create a separate, time-limited original-video download task."""
    try:
        url = extract_video_url(body.url)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if urlparse(url).path.lower().endswith(tuple(AUDIO_SUFFIXES)):
        raise HTTPException(400, "这个链接是音频文件；下载视频请粘贴视频链接")
    task_id = str(uuid.uuid4())
    (settings.data_dir / "tasks" / task_id).mkdir(parents=True, exist_ok=False)
    task = Task(
        id=task_id, user_id=user.id, title="网络视频", task_kind="download",
        source_type="url", source_url=url, language="auto",
        asr_provider="none", status="queued", message="等待下载",
    )
    db.add(task)
    db.commit()
    enqueue(download_source_task, task.id)
    return task_dict(task)


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return task_dict(owned_task(task_id, user, db), detail=True)


@app.post("/api/tasks/{task_id}/retry")
def retry_task(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = db.scalar(select(Task).where(Task.id == task_id, Task.user_id == user.id).with_for_update())
    if not task:
        raise HTTPException(404, "任务不存在")
    if task.status != "failed":
        raise HTTPException(409, "只有失败的任务可以重试")

    if task.task_kind == "download":
        if not task.source_url:
            raise HTTPException(409, "缺少原视频链接，无法重试下载")
        job = download_source_task
        task.message = "等待重新下载"
    else:
        if task.source_type == "file" and (not task.media_path or not Path(task.media_path).is_file()):
            raise HTTPException(410, "本地素材已清理，请重新上传后提交听写")
        if task.source_type == "url" and not task.source_url:
            raise HTTPException(409, "缺少原视频链接，无法重试听写")
        check_can_submit(db, user)
        job = transcribe_task
        task.message = "等待重新听写"

    task_dir = settings.data_dir / "tasks" / task.id
    task_dir.mkdir(parents=True, exist_ok=True)
    previous_delete_at = task.source_delete_at
    task.status = "queued"
    task.progress = 0
    task.error = None
    task.source_delete_at = None
    db.commit()
    try:
        enqueue(job, task.id)
    except Exception as exc:
        task.status = "failed"
        task.message = "任务重新排队失败"
        task.error = str(exc)[:300]
        task.source_delete_at = previous_delete_at
        db.commit()
        raise HTTPException(503, "任务暂时无法排队，请稍后重试")
    return task_dict(task, detail=True)


@app.patch("/api/tasks/{task_id}/transcript")
def save_transcript(task_id: str, body: TranscriptBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = owned_transcription_task(task_id, user, db)
    task.segments = body.segments
    task.transcript_text = "\n".join(str(item.get("text", "")).strip() for item in body.segments if item.get("text"))
    db.commit()
    return task_dict(task, detail=True)


@app.post("/api/tasks/{task_id}/highlights")
def start_highlights(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = owned_transcription_task(task_id, user, db)
    if task.status != "completed":
        raise HTTPException(409, "请先完成听写")
    if task.ai_status not in {"idle", "failed"}:
        raise HTTPException(409, "已有 AI 任务正在进行")
    reserve_ai_use(db, user, task.id, "highlights")
    task.ai_status, task.ai_message = "queued", "亮点分析已排队"
    db.commit()
    try: enqueue(highlight_task, task.id)
    except Exception:
        settle_ai_use(db, task.id, "highlights", False)
        task.ai_status, task.ai_message = "failed", "AI 任务暂时无法排队，请稍后重试"
        db.commit()
        raise HTTPException(503, task.ai_message)
    return {"ok": True}


@app.post("/api/tasks/{task_id}/summary")
def start_summary(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = owned_transcription_task(task_id, user, db)
    if task.status != "completed": raise HTTPException(409, "请先完成听写")
    if task.ai_status not in {"idle", "failed"}: raise HTTPException(409, "已有 AI 任务正在进行")
    reserve_ai_use(db, user, task.id, "summary")
    task.ai_status, task.ai_message = "queued", "文案总结已排队"
    db.commit()
    try: enqueue(summarize_task, task.id)
    except Exception:
        settle_ai_use(db, task.id, "summary", False)
        task.ai_status, task.ai_message = "failed", "AI 任务暂时无法排队，请稍后重试"
        db.commit()
        raise HTTPException(503, task.ai_message)
    return {"ok": True}


@app.post("/api/tasks/{task_id}/translate")
def start_translation(task_id: str, body: TranslateBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = owned_transcription_task(task_id, user, db)
    language = body.language.strip()
    if language not in {"英语", "简体中文", "繁體中文", "日语", "韩语", "西班牙语", "法语"}:
        raise HTTPException(400, "请选择受支持的目标语言")
    if task.status != "completed": raise HTTPException(409, "请先完成听写")
    if task.ai_status not in {"idle", "failed"}: raise HTTPException(409, "已有 AI 任务正在进行")
    reserve_ai_use(db, user, task.id, "translate")
    task.ai_status, task.ai_message = "queued", f"文案翻译为{language}已排队"
    db.commit()
    try: enqueue(translate_task, task.id, language)
    except Exception:
        settle_ai_use(db, task.id, "translate", False)
        task.ai_status, task.ai_message = "failed", "AI 任务暂时无法排队，请稍后重试"
        db.commit()
        raise HTTPException(503, task.ai_message)
    return {"ok": True}


@app.post("/api/tasks/{task_id}/visual-analysis")
def start_visual_analysis(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = owned_transcription_task(task_id, user, db)
    if task.status != "completed":
        raise HTTPException(409, "请先完成听写")
    has_remote_video = task.source_type == "url" and bool(task.source_url) and bool(task.media_path or task.source_playback_url) and (
        task.source_playback_kind == "video"
        or Path(urlparse(task.source_url).path).suffix.lower() in VIDEO_SUFFIXES
    )
    if media_kind(task.media_path) == "audio" and not has_remote_video:
        raise HTTPException(409, "画面分析仅支持视频文件")
    if (not task.media_path or not Path(task.media_path).exists()) and not has_remote_video:
        raise HTTPException(409, "原视频已删除，无法分析画面")
    # A completed analysis can be explicitly rerun when the analysis schema
    # evolves (for example, to add the style profile). Switching tabs never
    # calls this endpoint; the UI only uses it for an explicit rerun button.
    if task.visual_status not in {"idle", "failed", "completed"}:
        raise HTTPException(409, "已有画面分析任务正在进行")
    reserve_ai_use(db, user, task.id, "visual")
    task.visual_status, task.visual_message = "queued", "画面分析已排队"
    db.commit()
    try: enqueue(analyze_visual_task, task.id)
    except Exception:
        settle_ai_use(db, task.id, "visual", False)
        task.visual_status, task.visual_message = "failed", "AI 任务暂时无法排队，请稍后重试"
        db.commit()
        raise HTTPException(503, task.visual_message)
    return {"ok": True}


@app.post("/api/tasks/{task_id}/rewrite")
def start_rewrite(task_id: str, body: RewriteBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = owned_transcription_task(task_id, user, db)
    if task.status != "completed":
        raise HTTPException(409, "请先完成听写")
    if task.ai_status not in {"idle", "failed"}:
        raise HTTPException(409, "已有 AI 任务正在进行")
    reserve_ai_use(db, user, task.id, "rewrite")
    task.ai_status, task.ai_message = "queued", "复刻改编已排队"
    db.commit()
    try: enqueue(rewrite_task, task.id, body.direction)
    except Exception:
        settle_ai_use(db, task.id, "rewrite", False)
        task.ai_status, task.ai_message = "failed", "AI 任务暂时无法排队，请稍后重试"
        db.commit()
        raise HTTPException(503, task.ai_message)
    return {"ok": True}


@app.delete("/api/tasks/{task_id}/source")
def remove_source(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = owned_task(task_id, user, db)
    delete_source(task.media_path)
    task.media_path = None
    task.source_playback_url = None
    task.source_playback_audio_url = None
    task.source_playback_kind = None
    shutil.rmtree(settings.data_dir / "tasks" / task.id / "playback-fallback", ignore_errors=True)
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
def media(task_id: str, local: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = owned_task(task_id, user, db)
    playback_url = task.source_playback_url
    if not playback_url and task.media_path and task.source_type == "url" and task.source_url and is_direct_media_url(task.source_url):
        playback_url = task.source_url
    if playback_url and not local:
        return RedirectResponse(playback_url, status_code=307)
    fallback_video = _playback_fallback_video(task.id) if local else None
    if fallback_video:
        return FileResponse(fallback_video, headers={"Cache-Control": "private, no-store"})
    source = Path(task.media_path) if task.media_path else None
    if source and source.is_file():
        preview = source.parent / "preview.mp4"
        return FileResponse(preview if preview.exists() else source)
    raise HTTPException(404, "原视频已删除")


@app.get("/api/tasks/{task_id}/playback-audio")
def playback_audio(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = owned_task(task_id, user, db)
    if not task.source_playback_audio_url:
        raise HTTPException(404, "没有独立的远端音轨")
    return RedirectResponse(task.source_playback_audio_url, status_code=307)


@app.post("/api/tasks/{task_id}/refresh-playback")
def refresh_playback(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = owned_task(task_id, user, db)
    if task.source_type != "url" or not task.source_url:
        raise HTTPException(409, "这个任务没有可刷新的网络视频地址")
    if not task.media_path and not task.source_playback_url:
        raise HTTPException(409, "原媒体已删除，无法刷新播放地址")
    try:
        from .services.media import refresh_douyin_playback
        playback_url, audio_url = refresh_douyin_playback(
            task.source_url, settings.data_dir / "tasks" / task.id,
        )
    except Exception as exc:
        raise HTTPException(502, f"无法刷新远端播放地址：{exc}") from exc
    task.source_playback_url = playback_url
    task.source_playback_audio_url = audio_url
    task.source_playback_kind = "video"
    db.commit()
    return {"ok": True}


@app.post("/api/tasks/{task_id}/prepare-playback-video")
def prepare_playback_video(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = owned_transcription_task(task_id, user, db)
    if task.source_type != "url" or not task.source_url:
        raise HTTPException(409, "没有可准备的视频来源")
    deadline = task.source_delete_at
    now = utcnow()
    if deadline and deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=now.tzinfo)
    if not deadline or deadline <= now:
        raise HTTPException(410, "视频保存时间已过，请重新提交任务")
    if _playback_fallback_video(task.id):
        return {"ok": True}
    from .services.media import _has_video_stream, download_original_video
    fallback_root = settings.data_dir / "tasks" / task.id / "playback-fallback"
    candidates = []
    direct_suffix = _direct_media_suffix(task.source_playback_url or "") if task.source_playback_url else None
    if task.source_playback_url and direct_suffix in VIDEO_SUFFIXES and is_direct_media_url(task.source_playback_url):
        candidates.append(("direct", task.source_playback_url))
    if task.source_url and all(url != task.source_url for _, url in candidates):
        candidates.append(("source", task.source_url))
    for name, url in candidates:
        target_dir = fallback_root / name
        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            media_path, _ = download_original_video(url, target_dir, use_douyin_cookies=True)
            if _has_video_stream(media_path):
                return {"ok": True}
            delete_source(media_path)
        except Exception:
            continue
    raise HTTPException(502, "视频暂时无法准备，请稍后重试")


@app.get("/api/tasks/{task_id}/cover")
def task_cover(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = owned_transcription_task(task_id, user, db)
    task_dir = settings.data_dir / "tasks" / task.id
    cover = task_dir / "cover.jpg"
    if cover.is_file() and cover.stat().st_size > 0:
        return FileResponse(
            cover, filename=f"{task.id[:8]}-cover.jpg", media_type="image/jpeg",
            headers={"Cache-Control": "private, no-store"},
        )
    if not _source_is_retained(task):
        raise HTTPException(410, "视频封面已过期")

    source_path = Path(task.media_path) if task.media_path else None
    fallback_video = _playback_fallback_video(task.id)
    playback_url = task.source_playback_url
    if not playback_url and task.source_type == "url" and task.source_url and is_direct_video_url(task.source_url):
        playback_url = task.source_url
    try:
        if source_path and source_path.is_file() and media_kind(source_path) == "video":
            ensure_cover_image(source_path, task_dir)
        elif fallback_video:
            ensure_cover_image(fallback_video, task_dir)
        elif is_direct_video_url(playback_url):
            ensure_remote_cover_image(playback_url, task_dir)
        else:
            raise HTTPException(404, "这条任务没有可用的视频封面")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, "封面暂时无法生成，请稍后重试") from exc
    return FileResponse(
        cover, filename=f"{task.id[:8]}-cover.jpg", media_type="image/jpeg",
        headers={"Cache-Control": "private, no-store"},
    )


@app.get("/api/tasks/{task_id}/audio")
def task_audio(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = owned_transcription_task(task_id, user, db)
    if task.task_kind != "transcription" or not task.media_path:
        raise HTTPException(404, "這條任務沒有可用的音頻")
    source = Path(task.media_path)
    if not source.is_file():
        raise HTTPException(410, "原媒體已過期")
    audio = source if media_kind(source) == "audio" else settings.data_dir / "tasks" / task.id / "audio" / "download.mp3"
    if not audio.is_file():
        raise HTTPException(404, "音頻正在準備中")
    extension = audio.suffix.lower() or ".mp3"
    safe_title = re.sub(r'[\\/:*?"<>|\r\n]+', "_", task.title).strip(" .")[:120] or "音頻"
    return FileResponse(
        audio, filename=f"{safe_title}{extension}",
        headers={"Cache-Control": "private, no-store"},
    )


@app.get("/api/tasks/{task_id}/download")
def download_task_file(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = owned_task(task_id, user, db)
    if task.task_kind != "download":
        raise HTTPException(409, "这条记录不是独立下载任务")
    if task.status != "completed" or not task.media_path or not Path(task.media_path).is_file():
        raise HTTPException(410, "下载文件不存在或已过期，请重新创建下载任务")
    path = Path(task.media_path)
    safe_title = re.sub(r'[\\/:*?"<>|\r\n]+', "_", task.title).strip(" .")[:140] or "视频"
    filename = f"{safe_title}{path.suffix.lower()}"
    return FileResponse(
        path, filename=filename, media_type="application/octet-stream",
        headers={"Cache-Control": "private, no-store"},
    )


@app.get("/api/tasks/{task_id}/export/{kind}")
def export(task_id: str, kind: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = owned_transcription_task(task_id, user, db)
    if kind == "txt":
        return PlainTextResponse(task.transcript_text or "", headers={"Content-Disposition": f'attachment; filename="{task.id[:8]}.txt"'})
    if kind == "srt":
        blocks = []
        for index, item in enumerate(task.segments or [], 1):
            speaker = f"[{item['speaker']}] " if item.get("speaker") else ""
            blocks.append(f"{index}\n{_srt(item['start_seconds'])} --> {_srt(item['end_seconds'])}\n{speaker}{item['text']}\n")
        return PlainTextResponse("\n".join(blocks), headers={"Content-Disposition": f'attachment; filename="{task.id[:8]}.srt"'})
    raise HTTPException(404, "不支持的导出格式")


def _srt(seconds: float) -> str:
    ms = int(seconds * 1000)
    return f"{ms // 3600000:02d}:{(ms % 3600000) // 60000:02d}:{(ms % 60000) // 1000:02d},{ms % 1000:03d}"


static_dir = Path(__file__).resolve().parents[2] / "static"
if static_dir.exists():
    @app.get("/admin")
    def admin_frontend():
        return FileResponse(static_dir / "index.html")

    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")

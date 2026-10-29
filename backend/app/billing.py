"""Provider-neutral subscription quotas and idempotent usage metering."""

from calendar import monthrange
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import (
    AIFeatureUsage,
    Plan,
    Task,
    UsageLedger,
    User,
    UserEntitlement,
    utcnow,
)


DEFAULT_PLANS = (
    {"code": "free", "name": "免费体验", "tier": "standard", "term_days": 30, "price_fen": 0, "monthly_minutes": 10, "max_video_minutes": 30, "concurrency_limit": 1, "is_active": True, "sort_order": 0},
    {"code": "pro_monthly", "name": "PRO月卡", "tier": "standard", "term_days": 30, "price_fen": 1490, "monthly_minutes": 480, "max_video_minutes": 240, "concurrency_limit": 2, "is_active": True, "sort_order": 1},
    {"code": "pro_yearly", "name": "PRO年卡", "tier": "standard", "term_days": 365, "price_fen": 5900, "monthly_minutes": 1200, "max_video_minutes": 240, "concurrency_limit": 5, "is_active": True, "sort_order": 2},
    {"code": "pro_lifetime", "name": "PRO永久卡", "tier": "standard", "term_days": 0, "price_fen": 15900, "monthly_minutes": 1800, "max_video_minutes": 240, "concurrency_limit": 5, "is_active": True, "sort_order": 3},
    {"code": "ultra_monthly", "name": "Ultra月卡", "tier": "professional", "term_days": 30, "price_fen": 12900, "monthly_minutes": 6000, "max_video_minutes": 0, "concurrency_limit": 20, "is_active": True, "sort_order": 4},
    {"code": "ultra_quarterly", "name": "Ultra季卡", "tier": "professional", "term_days": 90, "price_fen": 22900, "monthly_minutes": 15000, "max_video_minutes": 0, "concurrency_limit": 30, "is_active": True, "sort_order": 5},
    {"code": "ultra_yearly", "name": "Ultra年卡", "tier": "professional", "term_days": 365, "price_fen": 69900, "monthly_minutes": 30000, "max_video_minutes": 0, "concurrency_limit": 50, "is_active": True, "sort_order": 6},
    {"code": "creator", "name": "旧创作者套餐", "tier": "standard", "term_days": 30, "price_fen": 1794, "monthly_minutes": 480, "max_video_minutes": 240, "concurrency_limit": 2, "is_active": False, "sort_order": 97},
    {"code": "studio", "name": "旧团队套餐", "tier": "professional", "term_days": 30, "price_fen": 8940, "monthly_minutes": 6000, "max_video_minutes": 0, "concurrency_limit": 20, "is_active": False, "sort_order": 98},
    {"code": "legacy", "name": "原有账号", "tier": "standard", "term_days": 0, "price_fen": 0, "monthly_minutes": -1, "max_video_minutes": 0, "concurrency_limit": 20, "is_active": False, "sort_order": 99},
    {"code": "admin", "name": "管理员", "tier": "professional", "term_days": 0, "price_fen": 0, "monthly_minutes": -1, "max_video_minutes": 0, "concurrency_limit": 1000, "is_active": False, "sort_order": 100},
)

AI_FEATURE_NAMES = {
    "summary": "文案总结",
    "highlights": "找亮点",
    "visual": "画面分析",
    "rewrite": "复刻改编",
    "translate": "翻译",
}


def month_bounds(value: datetime) -> tuple[datetime, datetime]:
    value = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    start = value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def ensure_catalog(db: Session) -> None:
    for values in DEFAULT_PLANS:
        plan = db.get(Plan, values["code"])
        if plan is None:
            db.add(Plan(**values))
        elif values["code"] in {"pro_monthly", "pro_yearly", "pro_lifetime", "ultra_monthly", "ultra_quarterly", "ultra_yearly"} and plan.price_fen is None:
            # Seed an untouched catalog row once; preserve administrator edits.
            for key, value in values.items():
                setattr(plan, key, value)
        elif values["code"] in {"creator", "studio"} and plan.is_active:
            plan.is_active = False
    db.commit()


def ensure_entitlements(db: Session) -> None:
    ensure_catalog(db)
    start, end = month_bounds(utcnow())
    for user in db.scalars(select(User)).all():
        if db.get(UserEntitlement, user.id) is None:
            # Keep existing accounts' access intact while billing is initialized.
            db.add(UserEntitlement(
                user_id=user.id,
                plan_code="admin" if user.role == "admin" else "legacy",
                period_start=start,
                period_end=end,
            ))
    db.commit()


def get_entitlement(db: Session, user: User, *, lock: bool = False) -> tuple[UserEntitlement, Plan]:
    statement = select(UserEntitlement).where(UserEntitlement.user_id == user.id)
    if lock:
        statement = statement.with_for_update()
    entitlement = db.scalar(statement)
    if entitlement is None:
        start, end = month_bounds(utcnow())
        entitlement = UserEntitlement(
            user_id=user.id,
            plan_code="admin" if user.role == "admin" else "free",
            period_start=start,
            period_end=end,
        )
        db.add(entitlement)
        db.flush()

    plan = db.get(Plan, entitlement.plan_code)
    if plan is None:
        plan = db.get(Plan, "free")
        entitlement.plan_code = "free"
        entitlement.used_minutes = 0
        entitlement.period_start, entitlement.period_end = month_bounds(utcnow())
        db.flush()

    now = utcnow()
    period_end = entitlement.period_end
    if period_end.tzinfo is None:
        period_end = period_end.replace(tzinfo=timezone.utc)
    if entitlement.expires_at:
        expires_at = entitlement.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if now >= expires_at and entitlement.plan_code not in {"free", "admin", "legacy"}:
            entitlement.plan_code = "free"
            entitlement.expires_at = None
            entitlement.period_start, entitlement.period_end = month_bounds(now)
            entitlement.used_minutes = 0
            plan = db.get(Plan, "free")
            db.flush()
            period_end = entitlement.period_end
            if period_end.tzinfo is None:
                period_end = period_end.replace(tzinfo=timezone.utc)

    if now >= period_end:
        if plan.code == "free":
            entitlement.period_start, entitlement.period_end = month_bounds(now)
        else:
            period_start = entitlement.period_end
            if period_start.tzinfo is None:
                period_start = period_start.replace(tzinfo=timezone.utc)
            while period_start + timedelta(days=30) <= now:
                period_start += timedelta(days=30)
            entitlement.period_start = period_start
            entitlement.period_end = period_start + timedelta(days=30)
        entitlement.used_minutes = 0
        db.flush()
    return entitlement, plan


def entitlement_dict(db: Session, user: User) -> dict:
    entitlement, plan = get_entitlement(db, user)
    db.commit()
    unlimited = plan.monthly_minutes < 0 or user.role == "admin"
    remaining = -1 if unlimited else max(0, plan.monthly_minutes - entitlement.used_minutes - entitlement.reserved_minutes)
    return {
        "plan": {
            "code": plan.code,
            "name": plan.name,
            "tier": plan.tier,
            "term_days": plan.term_days,
            "price_fen": plan.price_fen,
            "monthly_minutes": plan.monthly_minutes,
            "max_video_minutes": plan.max_video_minutes,
            "concurrency_limit": plan.concurrency_limit,
        },
        "used_minutes": entitlement.used_minutes,
        "reserved_minutes": entitlement.reserved_minutes,
        "remaining_minutes": remaining,
        "unlimited": unlimited,
        "period_end": entitlement.period_end.isoformat(),
        "expires_at": entitlement.expires_at.isoformat() if entitlement.expires_at else None,
    }


def check_can_submit(db: Session, user: User, *, lock: bool = True) -> None:
    if user.role == "admin":
        return
    entitlement, plan = get_entitlement(db, user, lock=lock)
    available = plan.monthly_minutes - entitlement.used_minutes - entitlement.reserved_minutes
    if plan.monthly_minutes >= 0 and available <= 0:
        raise HTTPException(402, "本周期的听写额度已用完，请升级套餐或等待额度重置。")
    active_count = db.scalar(select(func.count()).select_from(Task).where(
        Task.user_id == user.id,
        Task.task_kind == "transcription",
        Task.status.in_(["queued", "preparing", "downloading", "transcribing"]),
    )) or 0
    if active_count >= plan.concurrency_limit:
        raise HTTPException(429, "当前套餐的并发任务已满，请等待现有任务完成。")


def reserve_minutes(db: Session, task: Task, duration_seconds: float) -> int:
    if not task.user_id:
        return 0
    user = db.get(User, task.user_id)
    if not user or user.role == "admin":
        return 0
    entitlement, plan = get_entitlement(db, user, lock=True)
    minutes = max(1, int((max(0.0, duration_seconds) + 59) // 60))
    if plan.max_video_minutes > 0 and minutes > plan.max_video_minutes:
        raise RuntimeError(f"单条视频最长支持 {plan.max_video_minutes} 分钟，请升级套餐。")
    current = db.scalar(select(UsageLedger).where(UsageLedger.task_id == task.id).with_for_update())
    if current:
        return current.reserved_minutes
    available = plan.monthly_minutes - entitlement.used_minutes - entitlement.reserved_minutes
    if plan.monthly_minutes >= 0 and available < minutes:
        raise RuntimeError(f"本周期剩余 {max(0, available)} 分钟，本条视频需要 {minutes} 分钟。请升级套餐或等待额度重置。")
    entitlement.reserved_minutes += minutes
    db.add(UsageLedger(user_id=user.id, task_id=task.id, reserved_minutes=minutes, status="reserved"))
    db.commit()
    return minutes


def settle_minutes(db: Session, task_id: str, duration_seconds: float, success: bool) -> None:
    ledger = db.scalar(select(UsageLedger).where(UsageLedger.task_id == task_id).with_for_update())
    if not ledger or ledger.status != "reserved":
        return
    entitlement = db.scalar(select(UserEntitlement).where(UserEntitlement.user_id == ledger.user_id).with_for_update())
    if entitlement:
        entitlement.reserved_minutes = max(0, entitlement.reserved_minutes - ledger.reserved_minutes)
        if success:
            charged = max(1, int((max(0.0, duration_seconds) + 59) // 60))
            entitlement.used_minutes += charged
            ledger.charged_minutes = charged
            ledger.status = "charged"
        else:
            ledger.status = "released"
        ledger.settled_at = utcnow()
        db.commit()


def reserve_ai_use(db: Session, user: User, task_id: str, feature: str) -> None:
    if feature not in AI_FEATURE_NAMES:
        raise ValueError(f"unsupported AI feature: {feature}")
    if user.role == "admin":
        return
    entitlement, plan = get_entitlement(db, user, lock=True)
    limit = getattr(plan, f"ai_{feature}_limit")
    if limit == 0:
        raise HTTPException(403, f"当前套餐未开放{AI_FEATURE_NAMES[feature]}功能，请升级套餐。")
    if limit > 0:
        used = db.scalar(select(func.count()).select_from(AIFeatureUsage).where(
            AIFeatureUsage.user_id == user.id,
            AIFeatureUsage.feature == feature,
            AIFeatureUsage.created_at >= entitlement.period_start,
            AIFeatureUsage.created_at < entitlement.period_end,
            AIFeatureUsage.status.in_(["reserved", "used"]),
        )) or 0
        if used >= limit:
            raise HTTPException(402, f"本周期的{AI_FEATURE_NAMES[feature]}次数已用完，请升级套餐或等待额度重置。")
    db.add(AIFeatureUsage(user_id=user.id, task_id=task_id, feature=feature, status="reserved"))
    # Commit with queued state while the caller still holds the task row lock.
    db.flush()


def settle_ai_use(db: Session, task_id: str, feature: str, success: bool) -> None:
    usage = db.scalar(
        select(AIFeatureUsage)
        .where(
            AIFeatureUsage.task_id == task_id,
            AIFeatureUsage.feature == feature,
            AIFeatureUsage.status == "reserved",
        )
        .order_by(AIFeatureUsage.created_at.desc(), AIFeatureUsage.id.desc())
        .with_for_update()
    )
    if not usage:
        return
    usage.status = "used" if success else "released"
    usage.settled_at = utcnow()
    db.commit()

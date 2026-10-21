import bcrypt
from fastapi import Cookie, Depends, HTTPException
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal, get_db
from .models import User


serializer = URLSafeTimedSerializer(settings.session_secret, salt="tingjian-session")


def hash_password(password: str) -> str:
    if len(password.encode()) > 72:
        raise HTTPException(400, "密码的 UTF-8 编码不能超过 72 字节")
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash or len(password.encode()) > 72:
        return False
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_session(user_id: int, session_version: int = 0) -> str:
    return serializer.dumps({"user_id": user_id, "session_version": session_version})


def seed_admin() -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == settings.admin_username))
        if not user:
            db.add(User(
                username=settings.admin_username,
                password_hash=hash_password(settings.admin_password),
                role="admin",
            ))
            db.commit()


def current_user(
    session: str | None = Cookie(default=None, alias="tingjian_session"),
    db: Session = Depends(get_db),
) -> User:
    if not session:
        raise HTTPException(401, "请先登录")
    try:
        payload = serializer.loads(session, max_age=settings.session_max_age)
    except (BadSignature, SignatureExpired):
        raise HTTPException(401, "登录已过期")
    user = db.get(User, payload.get("user_id"))
    if not user or (user.email and not user.email_verified_at):
        raise HTTPException(401, "用户不存在")
    if payload.get("session_version", 0) != user.session_version:
        raise HTTPException(401, "登录已失效，请重新登录")
    return user

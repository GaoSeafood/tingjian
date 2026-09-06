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
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_session(user_id: int) -> str:
    return serializer.dumps({"user_id": user_id})


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
    if not user:
        raise HTTPException(401, "用户不存在")
    return user


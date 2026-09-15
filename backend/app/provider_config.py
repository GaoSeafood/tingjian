import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select

from .config import settings
from .database import SessionLocal
from .models import AppSetting


SECRET_KEYS = {"mimo_api_key", "custom_asr_api_key", "assemblyai_api_key", "tencent_secret_id", "tencent_secret_key", "sub2api_api_key", "sub2api_fallback_api_key"}


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.session_secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def _decrypt(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError):
        return ""


def provider_config() -> dict:
    data = {
        "asr_provider": settings.asr_provider,
        "mimo_api_key": settings.mimo_api_key,
        "mimo_base_url": settings.mimo_base_url,
        "mimo_model": settings.mimo_model,
        "asr_language": settings.asr_language,
        "custom_asr_base_url": settings.custom_asr_base_url,
        "custom_asr_api_key": settings.custom_asr_api_key,
        "custom_asr_model": settings.custom_asr_model,
        "assemblyai_base_url": settings.assemblyai_base_url,
        "assemblyai_api_key": settings.assemblyai_api_key,
        "assemblyai_model": settings.assemblyai_model,
        "tencent_app_id": settings.tencent_app_id,
        "tencent_secret_id": settings.tencent_secret_id,
        "tencent_secret_key": settings.tencent_secret_key,
        "tencent_engine_type": settings.tencent_engine_type,
        "sub2api_base_url": settings.sub2api_base_url,
        "sub2api_api_key": settings.sub2api_api_key,
        "sub2api_fallback_api_key": settings.sub2api_fallback_api_key,
        "llm_primary_model": settings.llm_primary_model,
        "llm_fallback_model": settings.llm_fallback_model,
    }
    with SessionLocal() as db:
        rows = db.scalars(select(AppSetting)).all()
    for row in rows:
        data[row.key] = _decrypt(row.value) if row.key in SECRET_KEYS else row.value
    return data


def update_provider_config(values: dict) -> dict:
    allowed = {
        "asr_provider", "mimo_api_key", "mimo_base_url", "mimo_model", "asr_language",
        "custom_asr_base_url", "custom_asr_api_key", "custom_asr_model",
        "assemblyai_base_url", "assemblyai_api_key", "assemblyai_model",
        "tencent_app_id", "tencent_secret_id", "tencent_secret_key", "tencent_engine_type",
        "sub2api_base_url", "sub2api_api_key", "sub2api_fallback_api_key", "llm_primary_model", "llm_fallback_model",
    }
    with SessionLocal() as db:
        for key, raw_value in values.items():
            if key not in allowed or raw_value is None:
                continue
            value = str(raw_value).strip()
            if key in SECRET_KEYS and not value:
                continue
            if key.endswith("base_url") and value and not value.startswith(("https://", "http://")):
                raise ValueError(f"{key} 必须是完整的 HTTP(S) 地址")
            stored = _encrypt(value) if key in SECRET_KEYS else value
            row = db.get(AppSetting, key)
            if row:
                row.value = stored
            else:
                db.add(AppSetting(key=key, value=stored))
        db.commit()
    return public_provider_config()


def public_provider_config() -> dict:
    cfg = provider_config()
    return {
        "asr_provider": cfg["asr_provider"],
        "mimo_base_url": cfg["mimo_base_url"],
        "mimo_model": cfg["mimo_model"],
        "asr_language": cfg["asr_language"],
        "mimo_api_key_configured": bool(cfg["mimo_api_key"]),
        "custom_asr_base_url": cfg["custom_asr_base_url"],
        "custom_asr_model": cfg["custom_asr_model"],
        "custom_asr_api_key_configured": bool(cfg["custom_asr_api_key"]),
        "assemblyai_base_url": cfg["assemblyai_base_url"],
        "assemblyai_model": cfg["assemblyai_model"],
        "assemblyai_api_key_configured": bool(cfg["assemblyai_api_key"]),
        "tencent_app_id": cfg["tencent_app_id"],
        "tencent_engine_type": cfg["tencent_engine_type"],
        "tencent_secret_id_configured": bool(cfg["tencent_secret_id"]),
        "tencent_secret_key_configured": bool(cfg["tencent_secret_key"]),
        "sub2api_base_url": cfg["sub2api_base_url"],
        "sub2api_api_key_configured": bool(cfg["sub2api_api_key"]),
        "sub2api_fallback_api_key_configured": bool(cfg["sub2api_fallback_api_key"]),
        "llm_primary_model": cfg["llm_primary_model"],
        "llm_fallback_model": cfg["llm_fallback_model"],
    }

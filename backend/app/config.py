import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path(os.getenv("DATA_DIR", "/data"))
    database_url: str = os.getenv("DATABASE_URL", "sqlite:////data/app.db")
    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    session_secret: str = os.getenv("SESSION_SECRET", "dev-only-change-me")
    session_max_age: int = int(os.getenv("SESSION_MAX_AGE", str(30 * 24 * 3600)))
    resend_api_key: str = os.getenv("RESEND_API_KEY", "")
    mail_from: str = os.getenv("MAIL_FROM", "听见 <onboarding@resend.dev>")
    app_public_url: str = os.getenv("APP_PUBLIC_URL", "http://localhost:18092").rstrip("/")
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    secure_cookie: bool = _bool("SECURE_COOKIE", False)
    admin_username: str = os.getenv("ADMIN_USERNAME", "admin")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "change-me")
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "2048"))
    source_retention_hours: int = int(os.getenv("SOURCE_RETENTION_HOURS", "24"))
    job_timeout_seconds: int = int(os.getenv("JOB_TIMEOUT_SECONDS", str(6 * 3600)))
    asr_provider: str = os.getenv("ASR_PROVIDER", "mimo")
    mimo_api_key: str = os.getenv("MIMO_API_KEY", "")
    mimo_base_url: str = os.getenv("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1")
    mimo_model: str = os.getenv("MIMO_MODEL", "mimo-v2.5-asr")
    siliconflow_base_url: str = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
    siliconflow_api_key: str = os.getenv("SILICONFLOW_API_KEY", "")
    siliconflow_model: str = os.getenv("SILICONFLOW_MODEL", "FunAudioLLM/SenseVoiceSmall")
    asr_language: str = os.getenv("ASR_LANGUAGE", "auto")
    # Three-minute chunks are a better default for OpenAI-compatible ASR
    # providers while remaining comfortably below MiMo's payload limit.
    asr_chunk_seconds: int = int(os.getenv("ASR_CHUNK_SECONDS", "180"))
    url_audio_only_minutes: int = int(os.getenv("URL_AUDIO_ONLY_MINUTES", "45"))
    # Netscape-format cookies exported from a dedicated Douyin account. The
    # file lives in the persistent app-data volume and is never exposed via
    # the API.
    douyin_cookie_file: Path = Path(os.getenv("DOUYIN_COOKIE_FILE", str(Path(os.getenv("DATA_DIR", "/data")) / "secrets" / "douyin-cookies.txt")))
    douyin_user_agent_file: Path = Path(os.getenv("DOUYIN_USER_AGENT_FILE", str(Path(os.getenv("DATA_DIR", "/data")) / "secrets" / "douyin-user-agent.txt")))
    youtube_cookie_file: Path = Path(os.getenv("YOUTUBE_COOKIE_FILE", str(Path(os.getenv("DATA_DIR", "/data")) / "secrets" / "youtube-cookies.txt")))
    youtube_user_agent_file: Path = Path(os.getenv("YOUTUBE_USER_AGENT_FILE", str(Path(os.getenv("DATA_DIR", "/data")) / "secrets" / "youtube-user-agent.txt")))
    youtube_pot_provider_url: str = os.getenv("YOUTUBE_POT_PROVIDER_URL", "")
    visual_max_frames: int = int(os.getenv("VISUAL_MAX_FRAMES", "48"))
    visual_min_interval_seconds: int = int(os.getenv("VISUAL_MIN_INTERVAL_SECONDS", "4"))
    custom_asr_base_url: str = os.getenv("CUSTOM_ASR_BASE_URL", "")
    custom_asr_api_key: str = os.getenv("CUSTOM_ASR_API_KEY", "")
    custom_asr_model: str = os.getenv("CUSTOM_ASR_MODEL", "whisper-1")
    assemblyai_base_url: str = os.getenv("ASSEMBLYAI_BASE_URL", "https://api.assemblyai.com")
    assemblyai_api_key: str = os.getenv("ASSEMBLYAI_API_KEY", "")
    assemblyai_model: str = os.getenv("ASSEMBLYAI_MODEL", "universal-2")
    tencent_app_id: str = os.getenv("TENCENT_APP_ID", "")
    tencent_secret_id: str = os.getenv("TENCENT_SECRET_ID", "")
    tencent_secret_key: str = os.getenv("TENCENT_SECRET_KEY", "")
    tencent_engine_type: str = os.getenv("TENCENT_ENGINE_TYPE", "16k_zh")
    sub2api_base_url: str = os.getenv("SUB2API_BASE_URL", "")
    sub2api_api_key: str = os.getenv("SUB2API_API_KEY", "")
    sub2api_fallback_api_key: str = os.getenv("SUB2API_FALLBACK_API_KEY", "")
    llm_primary_model: str = os.getenv("LLM_PRIMARY_MODEL", "gemini-2.5-pro")
    llm_fallback_model: str = os.getenv("LLM_FALLBACK_MODEL", "gpt-5.4")


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
(settings.data_dir / "tasks").mkdir(parents=True, exist_ok=True)
settings.douyin_cookie_file.parent.mkdir(parents=True, exist_ok=True)
settings.douyin_user_agent_file.parent.mkdir(parents=True, exist_ok=True)
settings.youtube_cookie_file.parent.mkdir(parents=True, exist_ok=True)
settings.youtube_user_agent_file.parent.mkdir(parents=True, exist_ok=True)

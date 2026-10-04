"""Application configuration, loaded from environment variables (see .env.example)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    APP_NAME: str = "Suraksha AI"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"  # development | staging | production
    DEBUG: bool = False
    API_PREFIX: str = ""
    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = True

    # --- Security ---
    SECRET_KEY: str = "change-me-in-production-use-openssl-rand-hex-32"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    PASSWORD_MIN_LENGTH: int = 8
    GOOGLE_CLIENT_ID: str = ""
    PASSWORD_RESET_EXPIRE_MINUTES: int = 60
    EMAIL_VERIFY_EXPIRE_HOURS: int = 48
    REQUIRE_EMAIL_VERIFICATION: bool = False  # block password logins until the email is verified
    BOOTSTRAP_ADMIN_EMAIL: str = ""
    BOOTSTRAP_ADMIN_PASSWORD: str = ""

    # --- Email (any SMTP server; docker compose ships Mailpit for local testing) ---
    EMAIL_ENABLED: bool = True
    SMTP_HOST: str = "mailpit"
    SMTP_PORT: int = 1025
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_STARTTLS: bool = False
    SMTP_SSL: bool = False
    SMTP_TIMEOUT_SECONDS: float = 15.0
    EMAIL_FROM: str = "Suraksha AI <no-reply@suraksha.example>"
    FRONTEND_URL: str = "http://localhost:3000"  # links in emails: {FRONTEND_URL}/reset-password?token=...

    # --- Monitoring ---
    METRICS_ENABLED: bool = True
    METRICS_TOKEN: str = ""  # if set, GET /metrics requires "Authorization: Bearer <token>"

    # --- SMS / phone OTP ---
    # console: log only | email_bridge: deliver SMS text to Mailpit (dev) | webhook: POST JSON to any gateway
    # (e.g. a self-hosted Android SMS gateway) | twilio | msg91 | fast2sms
    SMS_PROVIDER: str = "console"
    SMS_EMAIL_BRIDGE_DOMAIN: str = "sms.suraksha.local"
    SMS_WEBHOOK_URL: str = ""
    SMS_WEBHOOK_TOKEN: str = ""
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""
    MSG91_AUTH_KEY: str = ""
    MSG91_OTP_TEMPLATE_ID: str = ""  # DLT-approved template ids (required for Indian SMS)
    MSG91_ALERT_TEMPLATE_ID: str = ""
    FAST2SMS_API_KEY: str = ""
    SMS_SENDER_NAME: str = "Suraksha AI"
    OTP_LENGTH: int = 6
    OTP_TTL_SECONDS: int = 300
    OTP_MAX_ATTEMPTS: int = 5
    OTP_RESEND_COOLDOWN_SECONDS: int = 60
    OTP_MAX_PER_HOUR: int = 5
    DEFAULT_COUNTRY_CODE: str = "91"

    # --- Rate limiting ---
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_DEFAULT: str = "120/minute"
    RATE_LIMIT_AUTH: str = "10/minute"
    RATE_LIMIT_AI: str = "20/minute"
    RATE_LIMIT_UPLOAD: str = "10/minute"

    # --- Database ---
    DATABASE_URL: str = "postgresql+psycopg://suraksha:suraksha@postgres:5432/suraksha"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # --- Redis / Celery ---
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"
    CACHE_TTL_SECONDS: int = 3600

    # --- Storage ---
    UPLOAD_DIR: Path = Path("/data/uploads")
    # Privacy: uploads are deleted right after text extraction; leftovers after 24 h. Analyses
    # (which only keep a redacted 500-character excerpt) are deleted after this many days (0 = keep).
    ANALYSIS_RETENTION_DAYS: int = 180
    # Users must accept the current privacy notice (GET /privacy) before scans, chat, voice or family
    # features process their data. Bump the version when the notice changes to ask again.
    REQUIRE_CONSENT: bool = True
    CONSENT_VERSION: str = "2026-10"
    MAX_UPLOAD_MB: int = 10
    MAX_AUDIO_MB: int = 15
    MAX_PDF_PAGES: int = 10

    # --- Ollama ---
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_PRIMARY_MODEL: str = "llama3.1:8b"
    OLLAMA_SECONDARY_MODEL: str = "gemma2:9b"  # lessons, quizzes, translations, nudges
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    OLLAMA_TIMEOUT_SECONDS: float = 180.0
    OLLAMA_KEEP_ALIVE: str = "10m"
    OLLAMA_NUM_CTX: int = 8192  # context window; Indic scripts need more tokens per character
    LLM_ENABLED: bool = True
    # Optional per-language model override, e.g. {"ta": "<model you pulled>"} (JSON)
    OLLAMA_LANGUAGE_MODELS: dict[str, str] = Field(default_factory=dict)

    # --- Risk scoring (calibrate with scripts/evaluate_risk.py) ---
    RISK_MEDIUM_THRESHOLD: int = 25
    RISK_HIGH_THRESHOLD: int = 50
    RISK_CRITICAL_THRESHOLD: int = 75
    SCAN_MAX_TOKENS: int = 600  # cap on the AI's answer per scan; shorter = faster (the prompt asks for ~250)
    RISK_LLM_WEIGHT: float = 0.6  # blended = (1-w)*rules + w*llm; final = max(rules, blended)

    # --- ChromaDB / RAG ---
    CHROMA_HOST: str = "chromadb"
    CHROMA_PORT: int = 8000
    CHROMA_COLLECTION: str = "suraksha_knowledge"
    RAG_TOP_K: int = 4
    RAG_CHUNK_SIZE: int = 900
    RAG_CHUNK_OVERLAP: int = 150
    RAG_MIN_RELEVANCE: float = 0.35
    KNOWLEDGE_DIR: Path = Path(__file__).resolve().parent / "rag" / "knowledge"
    RAG_AUTO_INGEST: bool = True
    KNOWLEDGE_UPLOAD_DIR: Path = Path("/data/knowledge")  # admin uploads + fetched official documents
    KNOWLEDGE_MAX_MB: int = 25
    KNOWLEDGE_SOURCES_FILE: Path = Path(__file__).resolve().parent / "rag" / "sources.json"

    # --- OCR ---
    TESSERACT_CMD: str = "tesseract"
    OCR_LANGUAGES: str = "eng+hin"  # always loaded; the user's script is added per request

    # --- Voice ---
    VOICE_ENABLED: bool = True
    WHISPER_MODEL: str = "base"
    WHISPER_DEVICE: str = "cpu"
    TTS_ENABLED: bool = True
    TTS_MODEL_EN: str = "tts_models/en/ljspeech/vits"
    TTS_MODEL_MULTILINGUAL: str = "tts_models/multilingual/multi-dataset/xtts_v2"
    TTS_HINDI_SPEAKER: str = "Ana Florence"
    # Extra Coqui-compatible voices per language (e.g. AI4Bharat Indic-TTS checkpoints), JSON:
    # {"ta": {"model_path": "/models/indic/ta/fastpitch/best_model.pth", "config_path": ".../config.json",
    #         "vocoder_path": ".../hifigan/best_model.pth", "vocoder_config_path": ".../config.json", "speaker": "female"}}
    TTS_CUSTOM_MODELS: dict[str, dict[str, str]] = Field(default_factory=dict)

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                import json

                return json.loads(v)
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

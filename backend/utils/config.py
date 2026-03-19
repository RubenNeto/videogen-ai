"""
Configuração — suporta providers gratuitos e pagos.

OPÇÕES GRATUITAS (recomendadas para começar):
  - Groq (Llama 3.3-70B): https://console.groq.com  → grátis, muito rápido
  - Google Gemini Flash:   https://aistudio.google.com → grátis, generoso
  - Pexels:                https://www.pexels.com/api  → fotos reais, grátis
  - gTTS:                  sem chave, funciona logo    → voz Google

OPÇÕES PAGAS (opcionais):
  - OpenAI GPT-4o  → melhor qualidade de script
  - ElevenLabs     → voz mais natural
"""
import os
from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    APP_ENV: str = "development"
    SECRET_KEY: str = "dev-secret"
    DATABASE_URL: str = "sqlite+aiosqlite:///./videogen.db"

    # ── AI PROVIDERS (usa pelo menos 1) ──────────────────
    # Groq: grátis em console.groq.com
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # Gemini: grátis em aistudio.google.com
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-flash"

    # OpenAI: pago mas opcional
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    # ── IMAGENS ──────────────────────────────────────────
    PEXELS_API_KEY: str = ""      # grátis em pexels.com/api
    STABILITY_API_KEY: str = ""   # pago, opcional

    # ── VOZ ──────────────────────────────────────────────
    ELEVENLABS_API_KEY: str = ""  # pago, opcional (usa gTTS se vazio)
    ELEVENLABS_VOICE_ID: str = "21m00Tcm4TlvDq8ikWAM"

    # ── OUTPUT ───────────────────────────────────────────
    OUTPUT_DIR: str = "./output/videos"
    TEMP_DIR: str = "./output/temp"
    VIDEO_QUALITY: str = "medium"
    VIDEOS_PER_RUN: int = 1

    # ── STORAGE (opcional) ───────────────────────────────
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_S3_BUCKET: str = ""
    AWS_REGION: str = "us-east-1"

    MAX_RETRIES: int = 3
    RETRY_DELAY_SECONDS: int = 30
    LOG_LEVEL: str = "INFO"
    SENTRY_DSN: str = ""

    @field_validator("OUTPUT_DIR", "TEMP_DIR", mode="after")
    @classmethod
    def create_dirs(cls, v):
        os.makedirs(v, exist_ok=True)
        return v

    @property
    def ai_provider(self) -> str:
        """Retorna o provider disponível com maior prioridade."""
        if self.GROQ_API_KEY:
            return "groq"
        if self.GEMINI_API_KEY:
            return "gemini"
        if self.OPENAI_API_KEY:
            return "openai"
        return "none"

    @property
    def has_any_ai(self) -> bool:
        return self.ai_provider != "none"

    @property
    def has_pexels(self) -> bool:
        return bool(self.PEXELS_API_KEY)

    @property
    def has_elevenlabs(self) -> bool:
        return bool(self.ELEVENLABS_API_KEY)

    @property
    def has_stability(self) -> bool:
        return bool(self.STABILITY_API_KEY)

    @property
    def has_s3(self) -> bool:
        return bool(self.AWS_ACCESS_KEY_ID and self.AWS_S3_BUCKET)

    @property
    def ffmpeg_preset(self) -> str:
        # ultrafast em todos os casos para Railway 512MB
        return "ultrafast"

    @property
    def ffmpeg_crf(self) -> int:
        return {"low": 30, "medium": 28, "high": 26}.get(self.VIDEO_QUALITY, 28)

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

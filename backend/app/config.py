from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    MONGODB_URI: str = "mongodb://localhost:27017/creatorai"
    GEMINI_API_KEY: str = ""
    GEMINI_TEXT_MODEL: str = "gemini-3.5-flash"  # Google retires names often; 2.5-flash is closed to new keys
    # Free-tier quotas are per model (3.5-flash: 20 requests/day), so on a 429 we fall through these in order.
    GEMINI_FALLBACK_MODELS: str = "gemini-3-flash-preview,gemini-3.5-flash-lite,gemini-flash-lite-latest"
    GEMINI_EMBED_MODEL: str = "gemini-embedding-001"
    GROQ_API_KEY: str = ""
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""
    STORAGE_BACKEND: Literal["local", "cloudinary"] = "local"
    PEXELS_API_KEY: str = ""
    WHISPER_LOCAL_MODEL: str = "base"  # faster-whisper fallback: tiny | base | small | medium
    JWT_SECRET: str  # required, no default
    CORS_ORIGINS: str = "http://localhost:5173"  # comma-separated
    ENABLE_DEV_ENDPOINTS: bool = True  # /dev/* (mock analytics seeding, reindex); set false in production


settings = Settings()

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Supabase
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    supabase_jwt_secret: str

    # Google OAuth
    google_client_id: str
    google_client_secret: str
    oauth_redirect_url: str = "http://localhost:8000/gmail/callback"

    # Encryption — 32-byte base64-encoded key, e.g. `python -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"`
    encryption_secret: str  # base64-encoded 32-byte key
    # Optional: comma-separated list for key rotation "id:key,id:key"
    encryption_keys: str = ""

    # DB (optional direct asyncpg; falls back to Supabase REST)
    database_url: str = ""

    # Redis (optional, for Celery)
    redis_url: str = "redis://localhost:6379/0"

    # App
    environment: str = "development"
    backend_cors_origins: list[str] = ["http://localhost:8501", "https://localhost:8501"]

    # OpenAI (for anonymizer)
    openai_api_key: str = ""

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()

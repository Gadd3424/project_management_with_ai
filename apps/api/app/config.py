from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_name: str = "Evolutionary Project AI"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite+aiosqlite:///./project_ai.db"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    jwt_secret: str = Field(default="development-only-secret-change-me-32", min_length=32)
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    cookie_secure: bool = False
    cors_origins: str = "http://localhost:3000"
    inference_url: str = "http://localhost:8001"
    ai_provider: str = "mock"
    ai_min_evidence_count: int = 1
    mlflow_tracking_uri: str = "http://localhost:5000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

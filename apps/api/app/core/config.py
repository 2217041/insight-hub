"""应用配置：从环境变量/.env 读取，带默认值。"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Insight Hub API"
    app_version: str = "0.3.0"

    database_url: str = "postgresql+psycopg://insight:insight@127.0.0.1:5432/insight"
    redis_url: str = "redis://127.0.0.1:6379/0"

    jwt_secret: str = "dev-only-change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 7

    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./data/hacker_news.db"
    HACKERNEWS_BASE_URL: str = "https://hacker-news.firebaseio.com/v0"
    HACKERNEWS_TIMEOUT_SECONDS: int = 20
    SERVICE_NAME: str = "hackernews-api"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

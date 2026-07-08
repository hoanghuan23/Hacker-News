from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./data/hacker_news.db"
    HACKERNEWS_BASE_URL: str = "https://hacker-news.firebaseio.com/v0"
    HACKERNEWS_TIMEOUT_SECONDS: int = 20
    SCHEDULER_ENABLED: bool = True
    SCHEDULER_INTERVAL_SECONDS: int = 120
    SOURCE_CRAWL_INTERVAL_MINUTES: dict[str, int] = {
        "news": 15,
        "newest": 25,
        "best": 30,
        "ask": 45,
        "show": 50,
        "jobs": 60,
    }
    METRICS_UPDATE_LIMIT: int = 100
    SOURCE_SCRAPE_LIMIT: int = 10
    SERVICE_NAME: str = "hackernews-api"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

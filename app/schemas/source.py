from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


SOURCE_API_PATH_MAP: dict[str, str] = {
    "news": "topstories.json",
    "newest": "newstories.json",
    "best": "beststories.json",
    "ask": "askstories.json",
    "show": "showstories.json",
    "jobs": "jobstories.json",
}

SourceType = Literal["news", "newest", "best", "ask", "show", "jobs"]


class SourceCreate(BaseModel):
    source_type: SourceType
    include_comments: bool = False
    comment_max_depth: int = Field(default=2, ge=0)
    max_days_old: int = Field(default=1, ge=1)


class SourceUpdate(BaseModel):
    is_active: bool | None = None
    include_comments: bool | None = None
    comment_max_depth: int | None = Field(default=None, ge=0)
    max_days_old: int | None = Field(default=None, ge=1)
    schedule_override_minutes: int | None = Field(default=None, ge=1)

    def update_data(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


class SourceRead(BaseModel):
    id: int
    source_type: str
    api_path: str
    is_active: bool
    is_accessible: bool
    include_comments: bool
    comment_max_depth: int
    max_days_old: int
    created_at: datetime | None
    last_scraped: datetime | None
    next_scrape: datetime | None
    schedule_tier: int | None
    schedule_override_minutes: int | None

    model_config = ConfigDict(from_attributes=True)

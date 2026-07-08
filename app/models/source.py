from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('news', 'newest', 'best', 'ask', 'show', 'jobs')",
            name="ck_hn_source_type",
        ),
        CheckConstraint(
            "api_path IN ('topstories.json', 'newstories.json', 'beststories.json', "
            "'askstories.json', 'showstories.json', 'jobstories.json')",
            name="ck_hn_api_path",
        ),
        Index("idx_sources_active", "is_active"),
        Index("idx_sources_accessible", "is_accessible"),
        Index("idx_sources_next_scrape", "next_scrape"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    api_path: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_accessible: Mapped[bool] = mapped_column(Boolean, default=True)
    include_comments: Mapped[bool] = mapped_column(Boolean, default=False)
    comment_max_depth: Mapped[int] = mapped_column(Integer, default=2)
    max_days_old: Mapped[int] = mapped_column(Integer, default=3)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.current_timestamp())
    last_scraped: Mapped[datetime | None] = mapped_column(DateTime)
    next_scrape: Mapped[datetime | None] = mapped_column(DateTime)
    schedule_tier: Mapped[int | None] = mapped_column(Integer)
    schedule_override_minutes: Mapped[int | None] = mapped_column(Integer)

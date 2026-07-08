from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        CheckConstraint("post_type IN ('story', 'job', 'poll')", name="ck_posts_post_type"),
        Index("ix_posts_hn_post_id", "hn_post_id", unique=True),
        Index("idx_posts_posted_at", "posted_at"),
        Index("idx_posts_author", "author"),
        Index("idx_posts_metric_due", "is_tracked", "next_metric_update"),
        Index("idx_posts_last_metric_update", "last_metric_update"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hn_post_id: Mapped[int] = mapped_column(Integer, nullable=False)
    post_type: Mapped[str] = mapped_column(String(20), nullable=False, default="story")
    title: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(100))
    score: Mapped[int] = mapped_column(Integer, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    kids_json: Mapped[str | None] = mapped_column(Text)
    posted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    is_tracked: Mapped[bool] = mapped_column(Boolean, default=True)
    tracking_until: Mapped[datetime | None] = mapped_column(DateTime)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    is_dead: Mapped[bool] = mapped_column(Boolean, default=False)
    last_metric_update: Mapped[datetime | None] = mapped_column(DateTime)
    next_metric_update: Mapped[datetime | None] = mapped_column(DateTime)
    metric_tier: Mapped[str] = mapped_column(String(20), nullable=False, default="bootstrap")
    last_engagement_velocity: Mapped[float | None] = mapped_column(Float)
    cold_check_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metric_scan_miss_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    raw_json: Mapped[str | None] = mapped_column(Text)


class PostSource(Base):
    __tablename__ = "post_sources"
    __table_args__ = (
        Index("idx_post_sources_source", "source_id", "last_seen_at"),
    )

    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.current_timestamp())
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.current_timestamp())

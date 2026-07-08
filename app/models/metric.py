from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class PostMetric(Base):
    __tablename__ = "post_metrics"
    __table_args__ = (
        Index("idx_post_metrics_post_time", "post_id", "recorded_at"),
        Index("idx_post_metrics_recorded_at", "recorded_at"),
        Index("idx_post_metrics_job_time", "job_id", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.current_timestamp())
    job_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("pipeline_jobs.id", ondelete="SET NULL"))


class AnalyticsCache(Base):
    __tablename__ = "analytics_cache"
    __table_args__ = (
        UniqueConstraint("source_id", "date", name="uq_hn_analytics_cache"),
        Index("idx_analytics_source_date", "source_id", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    total_posts: Mapped[int] = mapped_column(Integer, default=0)
    total_score: Mapped[int] = mapped_column(Integer, default=0)
    total_comments: Mapped[int] = mapped_column(Integer, default=0)
    avg_score_per_post: Mapped[float | None] = mapped_column(Float)
    avg_comments_per_post: Mapped[float | None] = mapped_column(Float)
    top_post_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("posts.id", ondelete="SET NULL"))
    growth_rate: Mapped[float | None] = mapped_column(Float)
    cached_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.current_timestamp())

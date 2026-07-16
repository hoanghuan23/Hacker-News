from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class PipelineJob(Base):
    __tablename__ = "pipeline_jobs"
    __table_args__ = (
        CheckConstraint(
            "job_type IN ('scrape_posts', 'scrape_new_posts', 'update_metrics', 'scrape_comments', 'analytics')",
            name="ck_pipeline_jobs_job_type",
        ),
        CheckConstraint("status IN ('pending', 'running', 'done', 'failed')", name="ck_pipeline_jobs_status"),
        Index("idx_pipeline_jobs_source_time", "source_id", "started_at"),
        Index("idx_pipeline_jobs_type_status", "job_type", "status", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_type: Mapped[str] = mapped_column(String(30), nullable=False, default="scrape_posts")
    source_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("sources.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="pending")
    posts_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    posts_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comments_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comments_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class PipelineLog(Base):
    __tablename__ = "pipeline_logs"
    __table_args__ = (
        CheckConstraint("log_level IN ('ERROR', 'WARNING')", name="ck_pipeline_logs_log_level"),
        Index("idx_pipeline_logs_job", "job_id", "created_at"),
        Index("idx_pipeline_logs_source", "source_id", "created_at"),
        Index("idx_pipeline_logs_level", "log_level", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("pipeline_jobs.id", ondelete="SET NULL"))
    source_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("sources.id", ondelete="SET NULL"))
    log_level: Mapped[str] = mapped_column(String(20), nullable=False, default="ERROR")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    error_type: Mapped[str | None] = mapped_column(String(100))
    error_details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.current_timestamp())

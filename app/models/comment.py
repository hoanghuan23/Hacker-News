from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (
        Index("ix_comments_hn_comment_id", "hn_comment_id", unique=True),
        Index("idx_comments_post", "post_id"),
        Index("idx_comments_parent_hn_item", "parent_hn_item_id"),
        Index("idx_comments_author", "author"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    parent_comment_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("comments.id", ondelete="SET NULL"),
    )
    hn_comment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_hn_item_id: Mapped[int | None] = mapped_column(Integer)
    author: Mapped[str | None] = mapped_column(String(100))
    comment_text: Mapped[str | None] = mapped_column(Text)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    is_dead: Mapped[bool] = mapped_column(Boolean, default=False)
    kids_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.current_timestamp())
    last_updated: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.current_timestamp())
    raw_json: Mapped[str | None] = mapped_column(Text)

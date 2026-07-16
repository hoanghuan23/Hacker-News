from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.metric import PostMetric
from app.models.post import Post
from app.services.pipeline_service import add_pipeline_log, finish_pipeline_job, start_pipeline_job
from app.services.hackernews_client import HackerNewsClient
from app.utils.datetime_utils import utc_now


POST_METRIC_INTERVAL_MINUTES = {
    "viral": 10,
    "high": 15,
    "medium": 30,
    "low": 60,
    "very_low": 120,
}
POST_METRIC_TRACKING_WINDOW_HOURS = 24


def _as_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def calculate_metric_tier(score: int, comment_count: int) -> str:
    post_score = score * 10 + comment_count * 6
    if post_score >= 3000:
        return "viral"
    if post_score >= 1200:
        return "high"
    if post_score >= 400:
        return "medium"
    if post_score >= 80:
        return "low"
    return "very_low"


def calculate_next_metric_update(now: datetime, tier: str) -> datetime:
    interval_minutes = POST_METRIC_INTERVAL_MINUTES[tier]
    return now + timedelta(minutes=interval_minutes)


def calculate_metric_tracking_until(posted_at: datetime) -> datetime:
    return _as_utc_naive(posted_at) + timedelta(hours=POST_METRIC_TRACKING_WINDOW_HOURS)


def apply_metric_schedule(post: Post, score: int, comment_count: int, recorded_at: datetime) -> None:
    recorded_at = _as_utc_naive(recorded_at)
    tier = calculate_metric_tier(score, comment_count)
    tracking_until = calculate_metric_tracking_until(post.posted_at)
    next_metric_update = calculate_next_metric_update(recorded_at, tier)

    post.metric_tier = tier
    post.last_metric_update = recorded_at
    post.tracking_until = tracking_until
    post.is_tracked = recorded_at <= tracking_until
    post.next_metric_update = min(next_metric_update, tracking_until) if post.is_tracked else None


def update_due_post_metrics(
    db: Session,
    client: HackerNewsClient | None = None,
    limit: int = 100,
    now: datetime | None = None,
) -> dict[str, int]:
    now = _as_utc_naive(now or utc_now())
    tracking_cutoff = now - timedelta(hours=POST_METRIC_TRACKING_WINDOW_HOURS)
    job = start_pipeline_job(db, "update_metrics", started_at=now)
    hn_client = client or HackerNewsClient()
    statement = (
        select(Post)
        .where(
            Post.is_tracked.is_(True),
            Post.next_metric_update <= now,
            Post.posted_at >= tracking_cutoff,
            or_(Post.tracking_until.is_(None), Post.tracking_until >= now),
        )
        .order_by(Post.next_metric_update, Post.id)
        .limit(limit)
    )
    posts = list(db.scalars(statement).all())
    result = {"items_total": len(posts), "items_updated": 0, "items_failed": 0}

    try:
        for post in posts:
            try:
                item = hn_client.get_item(post.hn_post_id)
            except requests.RequestException as exc:
                result["items_failed"] += 1
                add_pipeline_log(
                    db,
                    job_id=job.id,
                    message=f"Metric update request failed for post_id={post.id}",
                    error_type=type(exc).__name__,
                    error_details=str(exc),
                )
                continue
            if not _is_valid_metric_item(item):
                result["items_failed"] += 1
                add_pipeline_log(
                    db,
                    job_id=job.id,
                    message=f"Metric update returned invalid item for post_id={post.id}",
                    log_level="WARNING",
                    error_details=repr(item),
                )
                continue

            post.is_deleted = bool(item.get("deleted", False))
            post.is_dead = bool(item.get("dead", False))
            if post.is_deleted or post.is_dead:
                result["items_failed"] += 1
                db.add(post)
                add_pipeline_log(
                    db,
                    job_id=job.id,
                    message=f"Metric update skipped deleted/dead post_id={post.id}",
                    log_level="WARNING",
                    error_details=repr(item),
                )
                continue

            score = item.get("score") or 0
            comment_count = item.get("descendants") or 0
            apply_metric_schedule(post, score, comment_count, now)
            db.add(
                PostMetric(
                    post_id=post.id,
                    score=score,
                    comment_count=comment_count,
                    recorded_at=now,
                    job_id=job.id,
                )
            )
            db.add(post)
            result["items_updated"] += 1

        finish_pipeline_job(job, "done", **result)
        db.commit()
        return result
    except Exception as exc:
        db.rollback()
        job = db.get(type(job), job.id)
        if job is not None:
            add_pipeline_log(
                db,
                job_id=job.id,
                message="Metric update job failed",
                error_type=type(exc).__name__,
                error_details=str(exc),
            )
            finish_pipeline_job(job, "failed", error_message=str(exc), **result)
            db.commit()
        raise


def _is_valid_metric_item(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    if item.get("deleted") or item.get("dead"):
        return True
    return isinstance(item.get("id"), int)

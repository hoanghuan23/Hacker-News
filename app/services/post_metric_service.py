from datetime import datetime, timedelta
from typing import Any

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.metric import PostMetric
from app.models.post import Post
from app.services.hackernews_client import HackerNewsClient
from app.utils.datetime_utils import utc_now


POST_METRIC_INTERVAL_MINUTES = {
    "viral": 10,
    "high": 15,
    "medium": 30,
    "low": 60,
    "very_low": 120,
}


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


def apply_metric_schedule(post: Post, score: int, comment_count: int, recorded_at: datetime) -> None:
    tier = calculate_metric_tier(score, comment_count)
    post.metric_tier = tier
    post.last_metric_update = recorded_at
    post.next_metric_update = calculate_next_metric_update(recorded_at, tier)


def update_due_post_metrics(
    db: Session,
    client: HackerNewsClient | None = None,
    limit: int = 100,
) -> dict[str, int]:
    now = utc_now()
    hn_client = client or HackerNewsClient()
    statement = (
        select(Post)
        .where(Post.is_tracked.is_(True), Post.next_metric_update <= now)
        .order_by(Post.next_metric_update, Post.id)
        .limit(limit)
    )
    posts = list(db.scalars(statement).all())
    result = {"items_total": len(posts), "items_updated": 0, "items_failed": 0}

    for post in posts:
        try:
            item = hn_client.get_item(post.hn_post_id)
        except requests.RequestException:
            result["items_failed"] += 1
            continue
        if not _is_valid_metric_item(item):
            result["items_failed"] += 1
            continue

        post.is_deleted = bool(item.get("deleted", False))
        post.is_dead = bool(item.get("dead", False))
        if post.is_deleted or post.is_dead:
            result["items_failed"] += 1
            db.add(post)
            continue

        score = item.get("score") or 0
        comment_count = item.get("descendants") or 0
        apply_metric_schedule(post, score, comment_count, now)
        db.add(PostMetric(post_id=post.id, score=score, comment_count=comment_count, recorded_at=now))
        db.add(post)
        result["items_updated"] += 1

    db.commit()
    return result


def _is_valid_metric_item(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    if item.get("deleted") or item.get("dead"):
        return True
    return isinstance(item.get("id"), int)

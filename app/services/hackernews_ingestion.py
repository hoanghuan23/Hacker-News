from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.metric import PostMetric
from app.models.post import Post, PostSource
from app.models.source import Source
from app.services.hackernews_client import HackerNewsClient
from app.utils.datetime_utils import from_unix_timestamp, utc_now


SUPPORTED_POST_TYPES = {"story", "job", "poll"}
HN_ITEM_BASE_URL = "https://news.ycombinator.com/item?id="


def fetch_recent_source_items(
    client: HackerNewsClient,
    api_path: str,
    max_days_old: int,
) -> list[dict[str, Any]]:
    story_ids = client.get_story_ids(api_path)
    earliest_time = utc_now() - timedelta(days=max_days_old)
    items: list[dict[str, Any]] = []

    for story_id in story_ids:
        item = client.get_item(story_id)
        if not item:
            continue
        if item.get("deleted") or item.get("dead"):
            continue
        if item.get("type") not in SUPPORTED_POST_TYPES:
            continue

        posted_at = from_unix_timestamp(item.get("time"))
        if posted_at is None or posted_at < earliest_time:
            continue

        items.append(item)

    return items


def upsert_source_posts(db: Session, source: Source, items: list[dict[str, Any]]) -> int:
    now = utc_now()
    updated_count = 0

    for item in items:
        hn_post_id = item["id"]
        posted_at = from_unix_timestamp(item.get("time"))
        if posted_at is None:
            continue

        post = db.scalars(select(Post).where(Post.hn_post_id == hn_post_id)).first()
        if post is None:
            post = Post(hn_post_id=hn_post_id, posted_at=posted_at)
            db.add(post)

        post.post_type = item.get("type", "story")
        post.title = item.get("title")
        post.url = item.get("url")
        post.hn_item_url = f"{HN_ITEM_BASE_URL}{hn_post_id}"
        post.author = item.get("by")
        post.posted_at = posted_at
        post.updated_at = now
        post.is_deleted = bool(item.get("deleted", False))
        post.is_dead = bool(item.get("dead", False))
        post.last_metric_update = now

        db.flush()

        post_source = db.get(PostSource, {"post_id": post.id, "source_id": source.id})
        if post_source is None:
            post_source = PostSource(post_id=post.id, source_id=source.id, first_seen_at=now)
            db.add(post_source)
        post_source.last_seen_at = now

        db.add(
            PostMetric(
                post_id=post.id,
                score=item.get("score") or 0,
                comment_count=item.get("descendants") or 0,
                recorded_at=now,
            )
        )
        updated_count += 1

    source.last_scraped = now
    db.add(source)
    db.commit()
    db.refresh(source)
    return updated_count

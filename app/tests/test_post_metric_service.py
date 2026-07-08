from datetime import datetime, timedelta, timezone

import requests
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401
from app.database import Base
from app.models.metric import PostMetric
from app.models.post import Post
from app.models.source import Source
from app.services.hackernews_ingestion import upsert_source_posts
from app.services.post_metric_service import (
    POST_METRIC_INTERVAL_MINUTES,
    calculate_metric_tier,
    update_due_post_metrics,
)


class FakeHackerNewsClient:
    def __init__(self, items):
        self.items = items

    def get_item(self, item_id):
        item = self.items.get(item_id)
        if isinstance(item, Exception):
            raise item
        return item


def make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return testing_session()


def test_calculate_metric_tier_boundaries():
    assert calculate_metric_tier(300, 0) == "viral"
    assert calculate_metric_tier(299, 1) == "high"
    assert calculate_metric_tier(120, 0) == "high"
    assert calculate_metric_tier(119, 1) == "medium"
    assert calculate_metric_tier(40, 0) == "medium"
    assert calculate_metric_tier(39, 1) == "low"
    assert calculate_metric_tier(8, 0) == "low"
    assert calculate_metric_tier(7, 1) == "very_low"


def test_upsert_source_posts_sets_metric_tier_and_next_update():
    db = make_session()
    source = Source(source_type="news", api_path="topstories.json")
    db.add(source)
    db.commit()
    db.refresh(source)

    count = upsert_source_posts(
        db,
        source,
        [
            {
                "id": 123,
                "type": "story",
                "title": "Example",
                "time": 1_700_000_000,
                "score": 120,
                "descendants": 0,
            }
        ],
    )

    assert count == 1
    post = db.scalars(select(Post).where(Post.hn_post_id == 123)).one()
    metric = db.scalars(select(PostMetric).where(PostMetric.post_id == post.id)).one()
    assert metric.score == 120
    assert metric.comment_count == 0
    assert post.metric_tier == "high"
    assert post.last_metric_update is not None
    assert post.next_metric_update == post.last_metric_update + timedelta(
        minutes=POST_METRIC_INTERVAL_MINUTES["high"]
    )


def test_update_due_post_metrics_updates_only_due_posts_and_recomputes_tier():
    db = make_session()
    now = datetime.now(timezone.utc)
    due_post = Post(
        hn_post_id=1,
        posted_at=now - timedelta(days=1),
        is_tracked=True,
        next_metric_update=now - timedelta(minutes=1),
        metric_tier="very_low",
    )
    future_post = Post(
        hn_post_id=2,
        posted_at=now - timedelta(days=1),
        is_tracked=True,
        next_metric_update=now + timedelta(hours=1),
        metric_tier="very_low",
    )
    missing_post = Post(
        hn_post_id=3,
        posted_at=now - timedelta(days=1),
        is_tracked=True,
        next_metric_update=now - timedelta(minutes=1),
        metric_tier="very_low",
    )
    db.add_all([due_post, future_post, missing_post])
    db.commit()

    result = update_due_post_metrics(
        db,
        client=FakeHackerNewsClient(
            {
                1: {"id": 1, "type": "story", "score": 300, "descendants": 0},
                3: requests.RequestException("temporary failure"),
            }
        ),
    )

    assert result == {"items_total": 2, "items_updated": 1, "items_failed": 1}
    db.refresh(due_post)
    db.refresh(future_post)
    db.refresh(missing_post)
    assert due_post.metric_tier == "viral"
    assert due_post.next_metric_update == due_post.last_metric_update + timedelta(
        minutes=POST_METRIC_INTERVAL_MINUTES["viral"]
    )
    assert future_post.last_metric_update is None
    assert future_post.metric_tier == "very_low"
    assert missing_post.last_metric_update is None
    assert db.scalars(select(PostMetric).where(PostMetric.post_id == due_post.id)).one().score == 300

from datetime import datetime, timedelta, timezone

import requests
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401
from app.database import Base
from app.models.metric import PostMetric
from app.models.pipeline import PipelineJob, PipelineLog
from app.models.post import Post, PostSource
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
    now = datetime.now(timezone.utc)
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
                "time": int((now - timedelta(hours=1)).timestamp()),
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
    assert post.tracking_until == post.posted_at + timedelta(hours=24)
    assert post.next_metric_update == post.last_metric_update + timedelta(
        minutes=POST_METRIC_INTERVAL_MINUTES["high"]
    )


def test_update_due_post_metrics_updates_only_due_posts_and_recomputes_tier():
    db = make_session()
    now = datetime.now(timezone.utc)
    due_post = Post(
        hn_post_id=1,
        posted_at=now - timedelta(hours=23),
        is_tracked=True,
        next_metric_update=now - timedelta(minutes=1),
        metric_tier="very_low",
    )
    future_post = Post(
        hn_post_id=2,
        posted_at=now - timedelta(hours=23),
        is_tracked=True,
        next_metric_update=now + timedelta(hours=1),
        metric_tier="very_low",
    )
    missing_post = Post(
        hn_post_id=3,
        posted_at=now - timedelta(hours=23),
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
        now=now,
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
    metric = db.scalars(select(PostMetric).where(PostMetric.post_id == due_post.id)).one()
    job = db.scalars(select(PipelineJob).where(PipelineJob.job_type == "update_metrics")).one()
    log = db.scalars(select(PipelineLog).where(PipelineLog.job_id == job.id)).one()
    assert metric.score == 300
    assert metric.job_id == job.id
    assert job.status == "done"
    assert job.items_total == 2
    assert job.items_updated == 1
    assert job.items_failed == 1
    assert log.log_level == "ERROR"
    assert log.error_type == "RequestException"


def test_update_due_post_metrics_can_run_for_one_source():
    db = make_session()
    now = datetime.now(timezone.utc)
    source = Source(source_type="news", api_path="topstories.json")
    other_source = Source(source_type="best", api_path="beststories.json")
    source_post = Post(
        hn_post_id=10,
        posted_at=now - timedelta(hours=1),
        is_tracked=True,
        next_metric_update=now - timedelta(minutes=1),
        metric_tier="very_low",
    )
    other_post = Post(
        hn_post_id=11,
        posted_at=now - timedelta(hours=1),
        is_tracked=True,
        next_metric_update=now - timedelta(minutes=1),
        metric_tier="very_low",
    )
    db.add_all([source, other_source, source_post, other_post])
    db.commit()
    db.add_all(
        [
            PostSource(post_id=source_post.id, source_id=source.id),
            PostSource(post_id=other_post.id, source_id=other_source.id),
        ]
    )
    db.commit()

    result = update_due_post_metrics(
        db,
        client=FakeHackerNewsClient(
            {
                10: {"id": 10, "type": "story", "score": 300, "descendants": 0},
                11: {"id": 11, "type": "story", "score": 300, "descendants": 0},
            }
        ),
        now=now,
        source_id=source.id,
    )

    db.refresh(source_post)
    db.refresh(other_post)
    job = db.scalars(select(PipelineJob).where(PipelineJob.job_type == "update_metrics")).one()
    assert result == {"items_total": 1, "items_updated": 1, "items_failed": 0}
    assert source_post.metric_tier == "viral"
    assert other_post.metric_tier == "very_low"
    assert job.source_id == source.id


def test_update_due_post_metrics_skips_posts_older_than_24_hours():
    db = make_session()
    now = datetime.now(timezone.utc)
    old_post = Post(
        hn_post_id=4,
        posted_at=now - timedelta(hours=24, minutes=1),
        is_tracked=True,
        tracking_until=now - timedelta(minutes=1),
        next_metric_update=now - timedelta(minutes=1),
        metric_tier="very_low",
    )
    db.add(old_post)
    db.commit()

    result = update_due_post_metrics(
        db,
        client=FakeHackerNewsClient({4: {"id": 4, "type": "story", "score": 300, "descendants": 0}}),
        now=now,
    )

    db.refresh(old_post)
    assert result == {"items_total": 0, "items_updated": 0, "items_failed": 0}
    assert old_post.last_metric_update is None
    assert db.scalars(select(PostMetric).where(PostMetric.post_id == old_post.id)).first() is None
    assert db.scalars(select(PipelineJob).where(PipelineJob.job_type == "update_metrics")).first() is None


def test_update_due_post_metrics_does_not_create_job_without_due_posts():
    db = make_session()
    now = datetime.now(timezone.utc)
    future_post = Post(
        hn_post_id=5,
        posted_at=now - timedelta(hours=1),
        is_tracked=True,
        next_metric_update=now + timedelta(minutes=30),
        metric_tier="very_low",
    )
    db.add(future_post)
    db.commit()

    result = update_due_post_metrics(
        db,
        client=FakeHackerNewsClient({5: {"id": 5, "type": "story", "score": 300, "descendants": 0}}),
        now=now,
    )

    assert result == {"items_total": 0, "items_updated": 0, "items_failed": 0}
    assert db.scalars(select(PipelineJob).where(PipelineJob.job_type == "update_metrics")).first() is None

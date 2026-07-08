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
from app.workers.scheduler import run_scheduler_tick


class FakeHackerNewsClient:
    def __init__(self, items=None, story_ids=None, story_id_error=None):
        self.items = items or {}
        self.story_ids = story_ids or {}
        self.story_id_error = story_id_error

    def get_story_ids(self, api_path):
        if self.story_id_error is not None:
            raise self.story_id_error
        return self.story_ids.get(api_path, [])

    def get_item(self, item_id):
        item = self.items.get(item_id)
        if isinstance(item, Exception):
            raise item
        return item


class RecordingHackerNewsClient(FakeHackerNewsClient):
    def __init__(self, items=None, story_ids=None, story_id_error=None):
        super().__init__(items=items, story_ids=story_ids, story_id_error=story_id_error)
        self.requested_item_ids = []

    def get_item(self, item_id):
        self.requested_item_ids.append(item_id)
        return super().get_item(item_id)


def make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return testing_session()


def test_scheduler_tick_updates_due_post_metrics_and_skips_future_posts():
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
    db.add_all([due_post, future_post])
    db.commit()

    result = run_scheduler_tick(
        db,
        client=FakeHackerNewsClient(items={1: {"id": 1, "type": "story", "score": 300, "descendants": 0}}),
        now=now,
    )

    db.refresh(due_post)
    db.refresh(future_post)
    assert result["metrics"] == {"items_total": 1, "items_updated": 1, "items_failed": 0}
    assert due_post.metric_tier == "viral"
    assert future_post.last_metric_update is None
    metric = db.scalars(select(PostMetric).where(PostMetric.post_id == due_post.id)).one()
    metric_job = db.scalars(select(PipelineJob).where(PipelineJob.job_type == "update_metrics")).one()
    assert metric.score == 300
    assert metric.job_id == metric_job.id
    assert metric_job.status == "done"
    assert metric_job.items_total == 1
    assert metric_job.items_updated == 1


def test_scheduler_tick_scrapes_due_sources_and_skips_null_next_scrape():
    db = make_session()
    now = datetime.now(timezone.utc)
    due_source = Source(
        source_type="newest",
        api_path="newstories.json",
        is_active=True,
        is_accessible=True,
        max_days_old=1,
        next_scrape=now - timedelta(seconds=1),
    )
    null_source = Source(
        source_type="news",
        api_path="topstories.json",
        is_active=True,
        is_accessible=True,
        max_days_old=1,
        next_scrape=None,
    )
    db.add_all([due_source, null_source])
    db.commit()

    result = run_scheduler_tick(
        db,
        client=FakeHackerNewsClient(
            story_ids={"newstories.json": [10], "topstories.json": [20]},
            items={
                10: {
                    "id": 10,
                    "type": "story",
                    "title": "Due source story",
                    "time": int(now.timestamp()),
                    "score": 5,
                    "descendants": 2,
                },
                20: {
                    "id": 20,
                    "type": "story",
                    "title": "Null source story",
                    "time": int(now.timestamp()),
                    "score": 5,
                    "descendants": 2,
                },
            },
        ),
        now=now,
        interval_seconds=120,
    )

    db.refresh(due_source)
    db.refresh(null_source)
    assert result["sources"]["sources_scraped"] == 1
    assert due_source.next_scrape == (now + timedelta(minutes=25)).replace(tzinfo=None)
    assert null_source.next_scrape is None
    post = db.scalars(select(Post).where(Post.hn_post_id == 10)).one()
    source_job = db.scalars(select(PipelineJob).where(PipelineJob.job_type == "scrape_posts")).one()
    metric = db.scalars(select(PostMetric).where(PostMetric.post_id == post.id)).one()
    assert post.title == "Due source story"
    assert source_job.source_id == due_source.id
    assert source_job.status == "done"
    assert source_job.posts_found == 1
    assert source_job.posts_new == 1
    assert metric.job_id == source_job.id
    assert db.scalars(select(Post).where(Post.hn_post_id == 20)).first() is None


def test_scheduler_tick_stops_newstories_crawl_at_latest_posted_at():
    db = make_session()
    now = datetime.now(timezone.utc)
    source = Source(
        source_type="newest",
        api_path="newstories.json",
        is_active=True,
        is_accessible=True,
        max_days_old=1,
        next_scrape=now - timedelta(seconds=1),
    )
    latest_post = Post(
        hn_post_id=100,
        posted_at=now - timedelta(minutes=5),
        title="Already crawled",
    )
    db.add_all([source, latest_post])
    db.commit()
    db.add(PostSource(post_id=latest_post.id, source_id=source.id))
    db.commit()

    client = RecordingHackerNewsClient(
        story_ids={"newstories.json": [101, 100, 99]},
        items={
            101: {
                "id": 101,
                "type": "story",
                "title": "Fresh story",
                "time": int((now - timedelta(minutes=1)).timestamp()),
                "score": 10,
                "descendants": 1,
            },
            100: {
                "id": 100,
                "type": "story",
                "title": "Already crawled",
                "time": int((now - timedelta(minutes=5)).timestamp()),
                "score": 5,
                "descendants": 0,
            },
            99: {
                "id": 99,
                "type": "story",
                "title": "Should not be fetched",
                "time": int((now - timedelta(minutes=10)).timestamp()),
                "score": 1,
                "descendants": 0,
            },
        },
    )

    result = run_scheduler_tick(db, client=client, now=now, interval_seconds=120)

    assert client.requested_item_ids == [101, 100]
    assert result["sources"]["posts_found"] == 1
    assert db.scalars(select(Post).where(Post.hn_post_id == 101)).one()
    assert db.scalars(select(Post).where(Post.hn_post_id == 99)).first() is None


def test_scheduler_tick_uses_source_schedule_override_minutes():
    db = make_session()
    now = datetime.now(timezone.utc)
    source = Source(
        source_type="best",
        api_path="beststories.json",
        is_active=True,
        is_accessible=True,
        max_days_old=1,
        next_scrape=now - timedelta(seconds=1),
        schedule_override_minutes=5,
    )
    db.add(source)
    db.commit()

    run_scheduler_tick(
        db,
        client=FakeHackerNewsClient(story_ids={"beststories.json": []}),
        now=now,
        interval_seconds=120,
    )

    db.refresh(source)
    assert source.next_scrape == (now + timedelta(minutes=5)).replace(tzinfo=None)


def test_scheduler_tick_retries_source_after_hackernews_failure():
    db = make_session()
    now = datetime.now(timezone.utc)
    source = Source(
        source_type="show",
        api_path="showstories.json",
        is_active=True,
        is_accessible=True,
        max_days_old=1,
        next_scrape=now - timedelta(seconds=1),
    )
    db.add(source)
    db.commit()

    result = run_scheduler_tick(
        db,
        client=FakeHackerNewsClient(story_id_error=requests.RequestException("temporary failure")),
        now=now,
        interval_seconds=120,
    )

    db.refresh(source)
    source_job = db.scalars(select(PipelineJob).where(PipelineJob.job_type == "scrape_posts")).one()
    log = db.scalars(select(PipelineLog).where(PipelineLog.job_id == source_job.id)).one()
    assert result["sources"]["sources_failed"] == 1
    assert source.next_scrape == (now + timedelta(minutes=50)).replace(tzinfo=None)
    assert source_job.source_id == source.id
    assert source_job.status == "failed"
    assert source_job.error_message == "temporary failure"
    assert log.source_id == source.id
    assert log.error_type == "RequestException"

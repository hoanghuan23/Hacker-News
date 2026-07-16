from datetime import datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401
from app.database import Base
from app.models.metric import PostMetric
from app.models.pipeline import PipelineJob
from app.models.source import Source
from app.schemas.source import SourceCreate, SourceUpdate
from app.services.source_service import create_source, update_source


class FakeHackerNewsClient:
    def __init__(self, items=None, story_ids=None):
        self.items = items or {}
        self.story_ids = story_ids or {}

    def get_story_ids(self, api_path):
        return self.story_ids.get(api_path, [])

    def get_item(self, item_id):
        return self.items.get(item_id)


def make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return testing_session()


def test_update_source_schedule_override_recomputes_next_scrape_from_last_scraped():
    db = make_session()
    last_scraped = datetime(2026, 7, 8, 9, 48, 20)
    source = Source(
        source_type="newest",
        api_path="newstories.json",
        is_active=True,
        is_accessible=True,
        max_days_old=1,
        last_scraped=last_scraped,
        next_scrape=None,
    )
    db.add(source)
    db.commit()

    updated = update_source(db, source.id, SourceUpdate(schedule_override_minutes=40))

    assert updated.schedule_override_minutes == 40
    assert updated.next_scrape == last_scraped + timedelta(minutes=40)


def test_update_source_clearing_schedule_override_recomputes_next_scrape_from_config():
    db = make_session()
    last_scraped = datetime(2026, 7, 8, 9, 48, 20)
    source = Source(
        source_type="newest",
        api_path="newstories.json",
        is_active=True,
        is_accessible=True,
        max_days_old=1,
        last_scraped=last_scraped,
        next_scrape=last_scraped + timedelta(minutes=40),
        schedule_override_minutes=40,
    )
    db.add(source)
    db.commit()

    updated = update_source(db, source.id, SourceUpdate(schedule_override_minutes=None))

    assert updated.schedule_override_minutes is None
    assert updated.next_scrape == last_scraped + timedelta(minutes=25)


def test_create_source_sets_next_scrape_from_config_after_initial_scrape():
    db = make_session()
    item_time = int(datetime.now().timestamp())

    source = create_source(
        db,
        SourceCreate(source_type="news", max_days_old=1),
        client=FakeHackerNewsClient(
            story_ids={"topstories.json": [1]},
            items={
                1: {
                    "id": 1,
                    "type": "story",
                    "title": "Fresh story",
                    "time": item_time,
                    "score": 10,
                    "descendants": 1,
                }
            },
        ),
    )

    assert source.last_scraped is not None
    assert source.next_scrape == source.last_scraped + timedelta(minutes=15)
    job = db.scalars(select(PipelineJob).where(PipelineJob.source_id == source.id)).one()
    metric = db.scalars(select(PostMetric).where(PostMetric.job_id == job.id)).one()
    assert job.job_type == "scrape_posts"
    assert job.status == "done"
    assert job.posts_found == 1
    assert job.posts_new == 1
    assert metric.score == 10

from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.source import Source
from app.schemas.source import SOURCE_API_PATH_MAP, SourceCreate, SourceUpdate


def refresh_next_scrape_from_last_scraped(db: Session, source: Source) -> Source:
    if source.last_scraped is None:
        return source
    interval_minutes = source.schedule_override_minutes
    if interval_minutes is None:
        interval_minutes = settings.SOURCE_CRAWL_INTERVAL_MINUTES.get(source.source_type)
    if interval_minutes is None:
        source.next_scrape = source.last_scraped + timedelta(seconds=settings.SCHEDULER_INTERVAL_SECONDS)
    else:
        source.next_scrape = source.last_scraped + timedelta(minutes=interval_minutes)
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def get_source(db: Session, source_id: int) -> Source | None:
    return db.get(Source, source_id)


def get_source_by_type_or_path(db: Session, source_type: str, api_path: str) -> Source | None:
    statement = select(Source).where(or_(Source.source_type == source_type, Source.api_path == api_path))
    return db.scalars(statement).first()


def list_sources(db: Session, active_only: bool = False) -> list[Source]:
    statement = select(Source).order_by(Source.id)
    if active_only:
        statement = statement.where(Source.is_active.is_(True))
    return list(db.scalars(statement).all())


def create_source(db: Session, source_in: SourceCreate) -> Source:
    source = Source(**source_in.model_dump(), api_path=SOURCE_API_PATH_MAP[source_in.source_type])
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def update_source(db: Session, source: Source, source_in: SourceUpdate) -> Source:
    update_data = source_in.update_data()
    for field, value in update_data.items():
        setattr(source, field, value)
    if "schedule_override_minutes" in update_data and source.last_scraped is not None:
        return refresh_next_scrape_from_last_scraped(db, source)
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def set_source_active(db: Session, source: Source, is_active: bool) -> Source:
    source.is_active = is_active
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def set_source_accessible(db: Session, source: Source, is_accessible: bool) -> Source:
    source.is_accessible = is_accessible
    db.add(source)
    db.commit()
    db.refresh(source)
    return source

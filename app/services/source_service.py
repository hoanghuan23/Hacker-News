import logging
from typing import Any

import requests
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crud import source as source_crud
from app.models.source import Source
from app.schemas.source import SOURCE_API_PATH_MAP, SourceCreate, SourceUpdate
from app.services.hackernews_ingestion import fetch_recent_source_items, upsert_source_posts
from app.services.hackernews_client import HackerNewsClient
from app.services.pipeline_service import finish_pipeline_job, start_pipeline_job

logger = logging.getLogger(__name__)


def create_source(
    db: Session,
    source_in: SourceCreate,
    client: HackerNewsClient | None = None,
) -> Source:
    api_path = SOURCE_API_PATH_MAP[source_in.source_type]
    existing = source_crud.get_source_by_type_or_path(db, source_in.source_type, api_path)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Source already exists")
    hn_client = client or HackerNewsClient()
    try:
        items = fetch_recent_source_items(hn_client, api_path, source_in.max_days_old)
    except requests.RequestException as exc:
        logger.warning("Hacker News source crawl failed for api_path=%s: %s", api_path, exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Hacker News API request failed") from exc

    try:
        source = source_crud.create_source(db, source_in)
    except IntegrityError as exc:
        db.rollback()
        logger.info("Duplicate source rejected by database: %s", exc)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Source already exists") from exc
    job = start_pipeline_job(db, "scrape_posts", source_id=source.id)
    posts_updated = upsert_source_posts(db, source, items, job_id=job.id)
    finish_pipeline_job(
        job,
        "done",
        posts_found=len(items),
        posts_new=posts_updated,
        items_total=len(items),
        items_updated=posts_updated,
    )
    db.commit()
    return source_crud.refresh_next_scrape_from_last_scraped(db, source)


def list_sources(db: Session, active_only: bool = False) -> list[Source]:
    return source_crud.list_sources(db, active_only=active_only)


def get_source_or_404(db: Session, source_id: int) -> Source:
    source = source_crud.get_source(db, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return source


def update_source(db: Session, source_id: int, source_in: SourceUpdate) -> Source:
    source = get_source_or_404(db, source_id)
    return source_crud.update_source(db, source, source_in)


def enable_source(db: Session, source_id: int) -> Source:
    source = get_source_or_404(db, source_id)
    return source_crud.set_source_active(db, source, True)


def disable_source(db: Session, source_id: int) -> Source:
    source = get_source_or_404(db, source_id)
    return source_crud.set_source_active(db, source, False)


def test_source(db: Session, source_id: int, client: HackerNewsClient | None = None) -> dict[str, Any]:
    source = get_source_or_404(db, source_id)
    hn_client = client or HackerNewsClient()
    try:
        result = hn_client.test_source(source.api_path)
    except requests.RequestException as exc:
        source_crud.set_source_accessible(db, source, False)
        logger.warning("Hacker News source test failed for source_id=%s: %s", source_id, exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Hacker News API request failed") from exc

    source_crud.set_source_accessible(db, source, True)
    return {
        "source_id": source.id,
        "source_type": source.source_type,
        "api_path": source.api_path,
        "url": result["url"],
        "ok": True,
        "sample_count": result["sample_count"],
        "sample_ids": result["sample_ids"],
    }

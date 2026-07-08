import asyncio
import contextlib
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database import SessionLocal
from app.models.post import Post, PostSource
from app.models.source import Source
from app.services.hackernews_client import HackerNewsClient
from app.services.hackernews_ingestion import fetch_recent_source_items, upsert_source_posts
from app.services.pipeline_service import add_pipeline_log, finish_pipeline_job, start_pipeline_job
from app.services.post_metric_service import update_due_post_metrics
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


SessionFactory = Callable[[], Session]


def _next_source_scrape_at(source: Source, now: datetime, interval_seconds: int) -> datetime:
    if source.schedule_override_minutes is not None:
        return now + timedelta(minutes=source.schedule_override_minutes)
    interval_minutes = settings.SOURCE_CRAWL_INTERVAL_MINUTES.get(source.source_type)
    if interval_minutes is not None:
        return now + timedelta(minutes=interval_minutes)
    return now + timedelta(seconds=interval_seconds)


def _get_due_sources(db: Session, now: datetime, limit: int) -> list[Source]:
    statement = (
        select(Source)
        .where(
            Source.is_active.is_(True),
            Source.is_accessible.is_(True),
            Source.next_scrape.is_not(None),
            Source.next_scrape <= now,
        )
        .order_by(Source.next_scrape, Source.id)
        .limit(limit)
    )
    return list(db.scalars(statement).all())


def _get_latest_source_posted_at(db: Session, source_id: int) -> datetime | None:
    statement = (
        select(Post.posted_at)
        .join(PostSource, PostSource.post_id == Post.id)
        .where(PostSource.source_id == source_id)
        .order_by(Post.posted_at.desc())
        .limit(1)
    )
    return db.scalars(statement).first()


def scrape_due_sources(
    db: Session,
    client: HackerNewsClient | None = None,
    now: datetime | None = None,
    interval_seconds: int | None = None,
    limit: int | None = None,
) -> dict[str, int]:
    scan_time = now or utc_now()
    retry_interval_seconds = interval_seconds or settings.SCHEDULER_INTERVAL_SECONDS
    source_limit = limit or settings.SOURCE_SCRAPE_LIMIT
    hn_client = client or HackerNewsClient()
    sources = _get_due_sources(db, scan_time, source_limit)
    result = {"sources_total": len(sources), "sources_scraped": 0, "sources_failed": 0, "posts_found": 0}

    for source in sources:
        job = start_pipeline_job(db, "scrape_posts", source_id=source.id, started_at=scan_time)
        try:
            latest_posted_at = _get_latest_source_posted_at(db, source.id)
            items = fetch_recent_source_items(
                hn_client,
                source.api_path,
                source.max_days_old,
                latest_posted_at=latest_posted_at,
            )
            result["posts_found"] += len(items)
            posts_updated = upsert_source_posts(db, source, items, job_id=job.id)
            source.next_scrape = _next_source_scrape_at(source, scan_time, retry_interval_seconds)
            db.add(source)
            finish_pipeline_job(
                job,
                "done",
                posts_found=len(items),
                posts_new=posts_updated,
                items_total=len(items),
                items_updated=posts_updated,
            )
            db.commit()
            result["sources_scraped"] += 1
        except requests.RequestException as exc:
            db.rollback()
            source.next_scrape = _next_source_scrape_at(source, scan_time, retry_interval_seconds)
            db.add(source)
            add_pipeline_log(
                db,
                job_id=job.id,
                source_id=source.id,
                message=f"Hacker News source scrape failed for source_id={source.id}",
                error_type=type(exc).__name__,
                error_details=str(exc),
            )
            finish_pipeline_job(job, "failed", error_message=str(exc))
            db.commit()
            result["sources_failed"] += 1
            logger.exception("Hacker News source scrape failed for source_id=%s", source.id)
        except Exception as exc:
            db.rollback()
            add_pipeline_log(
                db,
                job_id=job.id,
                source_id=source.id,
                message=f"Unexpected source scrape failure for source_id={source.id}",
                error_type=type(exc).__name__,
                error_details=str(exc),
            )
            finish_pipeline_job(job, "failed", error_message=str(exc))
            db.commit()
            result["sources_failed"] += 1
            logger.exception("Unexpected source scrape failure for source_id=%s", source.id)

    return result


def run_scheduler_tick(
    db: Session,
    client: HackerNewsClient | None = None,
    now: datetime | None = None,
    interval_seconds: int | None = None,
    metrics_limit: int | None = None,
    source_limit: int | None = None,
) -> dict[str, Any]:
    scan_time = now or utc_now()
    metric_result = update_due_post_metrics(
        db,
        client=client,
        limit=metrics_limit or settings.METRICS_UPDATE_LIMIT,
    )
    source_result = scrape_due_sources(
        db,
        client=client,
        now=scan_time,
        interval_seconds=interval_seconds or settings.SCHEDULER_INTERVAL_SECONDS,
        limit=source_limit or settings.SOURCE_SCRAPE_LIMIT,
    )
    return {"metrics": metric_result, "sources": source_result}


def run_scheduler_once(
    session_factory: SessionFactory = SessionLocal,
    client: HackerNewsClient | None = None,
) -> dict[str, Any]:
    db = session_factory()
    try:
        return run_scheduler_tick(db, client=client)
    finally:
        db.close()


async def run_scheduler(
    session_factory: SessionFactory = SessionLocal,
    interval_seconds: int | None = None,
) -> None:
    sleep_seconds = interval_seconds or settings.SCHEDULER_INTERVAL_SECONDS
    logger.info("Scheduler started with interval_seconds=%s", sleep_seconds)
    while True:
        try:
            await asyncio.to_thread(run_scheduler_once, session_factory)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Scheduler tick failed")
        await asyncio.sleep(sleep_seconds)


async def stop_scheduler(task: asyncio.Task[None]) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

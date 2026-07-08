import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI

from app.api.routes import health, sources
from app.core.config import settings
from app.core.logging_config import configure_logging
from app.database import Base, engine
from app.workers.scheduler import run_scheduler, stop_scheduler
import app.models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    Base.metadata.create_all(bind=engine)
    scheduler_task: asyncio.Task[None] | None = None
    if settings.SCHEDULER_ENABLED:
        scheduler_task = asyncio.create_task(run_scheduler())
    try:
        yield
    finally:
        if scheduler_task is not None:
            await stop_scheduler(scheduler_task)


configure_logging()

app = FastAPI(title="Hacker News API", lifespan=lifespan)
app.include_router(health.router)
app.include_router(sources.router)

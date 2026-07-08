from datetime import datetime

from sqlalchemy.orm import Session

from app.models.pipeline import PipelineJob, PipelineLog
from app.utils.datetime_utils import utc_now


def start_pipeline_job(
    db: Session,
    job_type: str,
    source_id: int | None = None,
    started_at: datetime | None = None,
) -> PipelineJob:
    job = PipelineJob(
        job_type=job_type,
        source_id=source_id,
        status="running",
        started_at=started_at or utc_now(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def finish_pipeline_job(
    job: PipelineJob,
    status: str,
    finished_at: datetime | None = None,
    error_message: str | None = None,
    **counts: int,
) -> PipelineJob:
    job.status = status
    job.finished_at = finished_at or utc_now()
    job.error_message = error_message
    for field, value in counts.items():
        if value is not None and hasattr(job, field):
            setattr(job, field, value)
    return job


def add_pipeline_log(
    db: Session,
    message: str,
    job_id: int | None = None,
    source_id: int | None = None,
    log_level: str = "ERROR",
    error_type: str | None = None,
    error_details: str | None = None,
) -> PipelineLog:
    log = PipelineLog(
        job_id=job_id,
        source_id=source_id,
        log_level=log_level,
        message=message,
        error_type=error_type,
        error_details=error_details,
    )
    db.add(log)
    return log

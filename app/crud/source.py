from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.source import Source
from app.schemas.source import SourceCreate, SourceUpdate


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
    source = Source(**source_in.model_dump())
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def update_source(db: Session, source: Source, source_in: SourceUpdate) -> Source:
    for field, value in source_in.update_data().items():
        setattr(source, field, value)
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

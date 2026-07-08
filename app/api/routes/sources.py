from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.source import SourceCreate, SourceRead, SourceUpdate
from app.services import source_service

router = APIRouter(prefix="/sources", tags=["sources"])


@router.post("", response_model=SourceRead, status_code=201)
def create_source(source_in: SourceCreate, db: Session = Depends(get_db)) -> SourceRead:
    return source_service.create_source(db, source_in)


@router.get("", response_model=list[SourceRead])
def list_sources(active_only: bool = False, db: Session = Depends(get_db)) -> list[SourceRead]:
    return source_service.list_sources(db, active_only=active_only)


@router.get("/{source_id}", response_model=SourceRead)
def get_source(source_id: int, db: Session = Depends(get_db)) -> SourceRead:
    return source_service.get_source_or_404(db, source_id)


@router.patch("/{source_id}", response_model=SourceRead)
def update_source(source_id: int, source_in: SourceUpdate, db: Session = Depends(get_db)) -> SourceRead:
    return source_service.update_source(db, source_id, source_in)


@router.post("/{source_id}/disable", response_model=SourceRead)
def disable_source(source_id: int, db: Session = Depends(get_db)) -> SourceRead:
    return source_service.disable_source(db, source_id)


@router.post("/{source_id}/enable", response_model=SourceRead)
def enable_source(source_id: int, db: Session = Depends(get_db)) -> SourceRead:
    return source_service.enable_source(db, source_id)


@router.get("/{source_id}/test")
def test_source(source_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    return source_service.test_source(db, source_id)

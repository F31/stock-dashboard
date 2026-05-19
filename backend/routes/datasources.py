"""数据源 CRUD 路由。"""
import datetime
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import DataSource, User
from routes.auth import get_current_user
from schemas import DataSourceCreate, DataSourceUpdate, DataSourceResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/datasources", tags=["datasources"])


def _to_resp(s: DataSource) -> DataSourceResponse:
    return DataSourceResponse(
        id=s.id, name=s.name, url=s.url, source_type=s.source_type,
        category=s.category, notes=s.notes or "", enabled=bool(s.enabled),
        created_at=s.created_at.strftime("%Y-%m-%d %H:%M") if s.created_at else "",
    )


@router.get("", response_model=list[DataSourceResponse])
def list_sources(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return [_to_resp(s) for s in db.query(DataSource).order_by(DataSource.id).all()]


@router.post("", response_model=DataSourceResponse)
def create_source(req: DataSourceCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    s = DataSource(name=req.name, url=req.url, source_type=req.source_type,
                   category=req.category, notes=req.notes, enabled=1 if req.enabled else 0)
    db.add(s); db.commit(); db.refresh(s)
    return _to_resp(s)


@router.put("/{sid}", response_model=DataSourceResponse)
def update_source(sid: int, req: DataSourceUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    s = db.query(DataSource).filter(DataSource.id == sid).first()
    if not s:
        raise HTTPException(404, "Not found")
    if req.name is not None: s.name = req.name
    if req.url is not None: s.url = req.url
    if req.source_type is not None: s.source_type = req.source_type
    if req.category is not None: s.category = req.category
    if req.notes is not None: s.notes = req.notes
    if req.enabled is not None: s.enabled = 1 if req.enabled else 0
    db.commit(); db.refresh(s)
    return _to_resp(s)


@router.delete("/{sid}")
def delete_source(sid: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    s = db.query(DataSource).filter(DataSource.id == sid).first()
    if not s:
        raise HTTPException(404, "Not found")
    db.delete(s); db.commit()
    return {"msg": "deleted"}

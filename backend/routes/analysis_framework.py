"""产业链分析框架 CRUD API。"""
import json
import datetime
import logging
from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import get_db
from models import AnalysisFramework

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class FrameworkUpsert(BaseModel):
    name: str
    description: Optional[str] = ""
    framework_data: Optional[dict] = None            # new hierarchical WYSIWYG structure
    layer_definition: Optional[list[dict[str, Any]]] = []
    keyword_dict: Optional[dict[str, list[str]]] = {}
    entity_matrix: Optional[list[dict[str, Any]]] = []


def _resolve_flat(body: FrameworkUpsert) -> tuple[list, dict, list]:
    """Derive (layer_definition, keyword_dict, entity_matrix) from the upsert body."""
    if body.framework_data and body.framework_data.get("layers"):
        from premarket.framework import framework_data_to_flat
        layer_def, entity_matrix = framework_data_to_flat(body.framework_data)
        return layer_def, body.keyword_dict or {}, entity_matrix
    return body.layer_definition or [], body.keyword_dict or {}, body.entity_matrix or []


def _to_resp(row: AnalysisFramework) -> dict:
    return {
        "id":               row.id,
        "name":             row.name,
        "description":      row.description or "",
        "is_active":        row.is_active,
        "framework_data":   json.loads(row.framework_data or "null"),
        "layer_definition": json.loads(row.layer_definition or "[]"),
        "keyword_dict":     json.loads(row.keyword_dict or "{}"),
        "entity_matrix":    json.loads(row.entity_matrix or "[]"),
        "updated_at":       row.updated_at.isoformat() if row.updated_at else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/analysis-frameworks")
def list_frameworks(db: Session = Depends(get_db)):
    rows = db.query(AnalysisFramework).order_by(AnalysisFramework.id).all()
    return [_to_resp(r) for r in rows]


@router.get("/analysis-frameworks/{fid}")
def get_framework(fid: int, db: Session = Depends(get_db)):
    row = db.query(AnalysisFramework).filter(AnalysisFramework.id == fid).first()
    if not row:
        raise HTTPException(404, "Framework not found")
    return _to_resp(row)


@router.post("/analysis-frameworks", status_code=201)
def create_framework(body: FrameworkUpsert, db: Session = Depends(get_db)):
    layer_def, kw_dict, entity_matrix = _resolve_flat(body)
    row = AnalysisFramework(
        name             = body.name.strip(),
        description      = body.description or "",
        is_active        = 0,
        framework_data   = json.dumps(body.framework_data, ensure_ascii=False) if body.framework_data else None,
        layer_definition = json.dumps(layer_def,     ensure_ascii=False),
        keyword_dict     = json.dumps(kw_dict,        ensure_ascii=False),
        entity_matrix    = json.dumps(entity_matrix,  ensure_ascii=False),
        updated_at       = datetime.datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("Created analysis framework id=%d name=%s", row.id, row.name)
    return _to_resp(row)


@router.put("/analysis-frameworks/{fid}")
def update_framework(fid: int, body: FrameworkUpsert, db: Session = Depends(get_db)):
    row = db.query(AnalysisFramework).filter(AnalysisFramework.id == fid).first()
    if not row:
        raise HTTPException(404, "Framework not found")
    layer_def, kw_dict, entity_matrix = _resolve_flat(body)
    row.name             = body.name.strip()
    row.description      = body.description or ""
    row.framework_data   = json.dumps(body.framework_data, ensure_ascii=False) if body.framework_data else None
    row.layer_definition = json.dumps(layer_def,    ensure_ascii=False)
    row.keyword_dict     = json.dumps(kw_dict,       ensure_ascii=False)
    row.entity_matrix    = json.dumps(entity_matrix, ensure_ascii=False)
    row.updated_at       = datetime.datetime.utcnow()
    db.commit()
    logger.info("Updated analysis framework id=%d name=%s", row.id, row.name)
    return _to_resp(row)


@router.delete("/analysis-frameworks/{fid}", status_code=204)
def delete_framework(fid: int, db: Session = Depends(get_db)):
    row = db.query(AnalysisFramework).filter(AnalysisFramework.id == fid).first()
    if not row:
        raise HTTPException(404, "Framework not found")
    if row.is_active:
        raise HTTPException(400, "不能删除当前活跃框架，请先切换到其他框架")
    db.delete(row)
    db.commit()
    logger.info("Deleted analysis framework id=%d", fid)


@router.post("/analysis-frameworks/{fid}/set-active")
def set_active(fid: int, db: Session = Depends(get_db)):
    target = db.query(AnalysisFramework).filter(AnalysisFramework.id == fid).first()
    if not target:
        raise HTTPException(404, "Framework not found")
    db.query(AnalysisFramework).filter(AnalysisFramework.id != fid).update({"is_active": 0})
    target.is_active  = 1
    target.updated_at = datetime.datetime.utcnow()
    db.commit()
    logger.info("Set active framework id=%d name=%s", fid, target.name)
    return _to_resp(target)

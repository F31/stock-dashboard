"""提示词模板 CRUD 路由。"""
import datetime
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import PromptTemplate, User
from routes.auth import get_current_user
from schemas import PromptTemplateCreate, PromptTemplateUpdate, PromptTemplateResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/prompt-templates", tags=["prompt-templates"])


def _to_resp(t: PromptTemplate) -> PromptTemplateResponse:
    return PromptTemplateResponse(
        id=t.id, name=t.name, content=t.content, status=t.status,
        is_default=bool(t.is_default),
        created_at=t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else "",
        updated_at=t.updated_at.strftime("%Y-%m-%d %H:%M") if t.updated_at else "",
    )


@router.get("", response_model=list[PromptTemplateResponse])
def list_templates(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return [_to_resp(t) for t in db.query(PromptTemplate).order_by(PromptTemplate.id).all()]


@router.post("", response_model=PromptTemplateResponse)
def create_template(req: PromptTemplateCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    if req.is_default:
        db.query(PromptTemplate).update({"is_default": 0})
    t = PromptTemplate(name=req.name, content=req.content, status=req.status,
                       is_default=1 if req.is_default else 0)
    db.add(t); db.commit(); db.refresh(t)
    return _to_resp(t)


@router.put("/{tid}", response_model=PromptTemplateResponse)
def update_template(tid: int, req: PromptTemplateUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    t = db.query(PromptTemplate).filter(PromptTemplate.id == tid).first()
    if not t:
        raise HTTPException(404, "Not found")
    if req.is_default is True:
        db.query(PromptTemplate).filter(PromptTemplate.id != tid).update({"is_default": 0})
    if req.name is not None: t.name = req.name
    if req.content is not None: t.content = req.content
    if req.status is not None: t.status = req.status
    if req.is_default is not None: t.is_default = 1 if req.is_default else 0
    t.updated_at = datetime.datetime.utcnow()
    db.commit(); db.refresh(t)
    return _to_resp(t)


@router.delete("/{tid}")
def delete_template(tid: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    t = db.query(PromptTemplate).filter(PromptTemplate.id == tid).first()
    if not t:
        raise HTTPException(404, "Not found")
    db.delete(t); db.commit()
    return {"msg": "deleted"}


@router.post("/{tid}/set-default", response_model=PromptTemplateResponse)
def set_default(tid: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    t = db.query(PromptTemplate).filter(PromptTemplate.id == tid).first()
    if not t:
        raise HTTPException(404, "Not found")
    db.query(PromptTemplate).update({"is_default": 0})
    t.is_default = 1
    t.updated_at = datetime.datetime.utcnow()
    db.commit(); db.refresh(t)
    return _to_resp(t)

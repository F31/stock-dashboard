"""LLM Configuration CRUD routes."""
import logging
import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import LLMConfig
from schemas import LLMConfigCreate, LLMConfigUpdate, LLMConfigResponse
from routes.auth import get_current_user
from models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/llm-configs", tags=["llm-configs"])


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "·" * 8 + key[-4:]


def _to_response(cfg: LLMConfig, include_key: bool = False) -> LLMConfigResponse:
    return LLMConfigResponse(
        id=cfg.id,
        name=cfg.name,
        provider=cfg.provider or "custom",
        base_url=cfg.base_url,
        model_name=cfg.model_name,
        api_key_masked=_mask_key(cfg.api_key or ""),
        api_key=cfg.api_key if include_key else None,
        description=cfg.description or "",
        is_default=bool(cfg.is_default),
        created_at=cfg.created_at.strftime("%Y-%m-%d %H:%M") if cfg.created_at else "",
        updated_at=cfg.updated_at.strftime("%Y-%m-%d %H:%M") if cfg.updated_at else "",
    )


@router.get("", response_model=list[LLMConfigResponse])
def list_configs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = db.query(LLMConfig).order_by(LLMConfig.id).all()
    return [_to_response(c) for c in items]


@router.get("/{config_id}", response_model=LLMConfigResponse)
def get_config(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回完整配置（含明文 API Key），供编辑表单使用。"""
    cfg = db.query(LLMConfig).filter(LLMConfig.id == config_id).first()
    if not cfg:
        raise HTTPException(404, "Config not found")
    return _to_response(cfg, include_key=True)


@router.post("", response_model=LLMConfigResponse)
def create_config(
    req: LLMConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if req.is_default:
        db.query(LLMConfig).update({"is_default": 0})

    cfg = LLMConfig(
        name=req.name,
        provider=req.provider,
        base_url=req.base_url,
        model_name=req.model_name,
        api_key=req.api_key,
        description=req.description,
        is_default=1 if req.is_default else 0,
        created_at=datetime.datetime.utcnow(),
        updated_at=datetime.datetime.utcnow(),
    )
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    logger.info(f"LLM config created: {cfg.name} by {current_user.username}")
    return _to_response(cfg)


@router.put("/{config_id}", response_model=LLMConfigResponse)
def update_config(
    config_id: int,
    req: LLMConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cfg = db.query(LLMConfig).filter(LLMConfig.id == config_id).first()
    if not cfg:
        raise HTTPException(404, "Config not found")

    if req.is_default is True:
        db.query(LLMConfig).filter(LLMConfig.id != config_id).update({"is_default": 0})

    if req.name is not None:
        cfg.name = req.name
    if req.provider is not None:
        cfg.provider = req.provider
    if req.base_url is not None:
        cfg.base_url = req.base_url
    if req.model_name is not None:
        cfg.model_name = req.model_name
    if req.api_key is not None:
        cfg.api_key = req.api_key
    if req.description is not None:
        cfg.description = req.description
    if req.is_default is not None:
        cfg.is_default = 1 if req.is_default else 0

    cfg.updated_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(cfg)
    logger.info(f"LLM config updated: {cfg.name} by {current_user.username}")
    return _to_response(cfg)


@router.post("/{config_id}/set-default", response_model=LLMConfigResponse)
def set_default(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cfg = db.query(LLMConfig).filter(LLMConfig.id == config_id).first()
    if not cfg:
        raise HTTPException(404, "Config not found")
    db.query(LLMConfig).update({"is_default": 0})
    cfg.is_default = 1
    cfg.updated_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(cfg)
    return _to_response(cfg)


@router.delete("/{config_id}")
def delete_config(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cfg = db.query(LLMConfig).filter(LLMConfig.id == config_id).first()
    if not cfg:
        raise HTTPException(404, "Config not found")
    name = cfg.name
    db.delete(cfg)
    db.commit()
    logger.info(f"LLM config deleted: {name} by {current_user.username}")
    return {"msg": f"Config '{name}' deleted"}

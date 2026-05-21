"""行情监控标的 CRUD 路由。"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import WatchedTicker, User
from routes.auth import get_current_user
from schemas import WatchedTickerCreate, WatchedTickerUpdate, WatchedTickerResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/watched-tickers", tags=["watched-tickers"])


def _to_resp(t: WatchedTicker) -> WatchedTickerResponse:
    return WatchedTickerResponse(
        id=t.id,
        symbol=t.symbol,
        name=t.name,
        category=t.category or "",
        enabled=bool(t.enabled),
        notes=t.notes or "",
        created_at=t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else "",
    )


@router.get("", response_model=list[WatchedTickerResponse])
def list_tickers(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return [_to_resp(t) for t in db.query(WatchedTicker).order_by(WatchedTicker.id).all()]


@router.post("", response_model=WatchedTickerResponse)
def create_ticker(req: WatchedTickerCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    symbol = req.symbol.strip().upper()
    if not symbol:
        raise HTTPException(400, "symbol 不能为空")
    if db.query(WatchedTicker).filter(WatchedTicker.symbol == symbol).first():
        raise HTTPException(400, f"标的 {symbol} 已存在")
    t = WatchedTicker(
        symbol=symbol,
        name=req.name.strip() or symbol,
        category=req.category,
        enabled=1 if req.enabled else 0,
        notes=req.notes,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    logger.info(f"WatchedTicker created: {symbol}")
    return _to_resp(t)


@router.put("/{tid}", response_model=WatchedTickerResponse)
def update_ticker(tid: int, req: WatchedTickerUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    t = db.query(WatchedTicker).filter(WatchedTicker.id == tid).first()
    if not t:
        raise HTTPException(404, "Not found")
    if req.symbol is not None:
        new_sym = req.symbol.strip().upper()
        dup = db.query(WatchedTicker).filter(
            WatchedTicker.symbol == new_sym, WatchedTicker.id != tid
        ).first()
        if dup:
            raise HTTPException(400, f"标的 {new_sym} 已存在")
        t.symbol = new_sym
    if req.name is not None:
        t.name = req.name.strip() or t.symbol
    if req.category is not None:
        t.category = req.category
    if req.enabled is not None:
        t.enabled = 1 if req.enabled else 0
    if req.notes is not None:
        t.notes = req.notes
    db.commit()
    db.refresh(t)
    return _to_resp(t)


@router.delete("/{tid}")
def delete_ticker(tid: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    t = db.query(WatchedTicker).filter(WatchedTicker.id == tid).first()
    if not t:
        raise HTTPException(404, "Not found")
    db.delete(t)
    db.commit()
    logger.info(f"WatchedTicker deleted: {t.symbol}")
    return {"msg": "deleted"}

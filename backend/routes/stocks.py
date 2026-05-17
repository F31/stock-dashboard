"""Stock API routes."""
import logging
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Request
from typing import List, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)
from services.stock_service import (
    fetch_stock_realtime,
    fetch_stocks_batch,
    fetch_stock_news,
    fetch_chart_data,
    get_tech_giants_intel,
    get_stock_performance_intel,
    get_aindex_intel,
    search_stock as search_stock_service,
)
from services.sector_service import (
    is_board_code,
    fetch_sector_realtime,
    search_board,
    lookup_board_name,
)
from database import get_db
from models import WatchlistItem, StockReport
from schemas import AddStockRequest, UpdateNotesRequest, UpdateNameRequest, StockDataResponse
from routes.auth import get_current_user
from routes.admin import log_action, get_client_ip
from sqlalchemy.orm import Session
from sqlalchemy import func

router = APIRouter(tags=["stocks"])


class BatchStockItem(BaseModel):
    code: str
    market: str


class BatchRequest(BaseModel):
    stocks: List[BatchStockItem]


class BatchStockData(BaseModel):
    code: str = ""
    market: str = ""
    stock_name: str = ""
    price: Optional[float] = None
    change: Optional[float] = None
    change_pct: Optional[float] = None
    prev_close: Optional[float] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    volume: Optional[float] = None
    amount: Optional[float] = None
    turnover_rate: Optional[float] = None
    pe: Optional[float] = None
    market_cap: Optional[float] = None
    float_market_cap: Optional[float] = None
    amplitude: Optional[float] = None
    error: str = ""


@router.get("/stocks/list")
def list_stocks(db: Session = Depends(get_db), user=Depends(get_current_user)):
    stocks = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.user_id == user.id)
        .order_by(WatchlistItem.sort_order)
        .all()
    )
    return [{
        "id": s.id, "stock_code": s.stock_code, "market": s.market,
        "stock_name": s.stock_name, "notes": s.notes, "sort_order": s.sort_order,
        "item_type": s.item_type or "stock",
        "hidden": s.hidden or 0,
    } for s in stocks]


@router.get("/stocks/{stock_id}")
async def get_stock_detail(stock_id: int, db: Session = Depends(get_db),
                            user=Depends(get_current_user)):
    stock = (db.query(WatchlistItem)
             .filter(WatchlistItem.id == stock_id, WatchlistItem.user_id == user.id)
             .first())
    if not stock:
        raise HTTPException(404, "Stock not found")

    realtime = await fetch_stock_realtime(stock.stock_code, stock.market)
    news = await fetch_stock_news(stock.stock_code, stock.market)
    chart = await fetch_chart_data(stock.stock_code, stock.market)

    return StockDataResponse(
        id=stock.id, stock_code=stock.stock_code, market=stock.market,
        stock_name=stock.stock_name, notes=stock.notes,
        **realtime, news=news, chart_data=chart,
    )


@router.post("/stocks/batch", response_model=List[BatchStockData])
async def batch_stocks(req: BatchRequest, user=Depends(get_current_user)):
    """Fetch realtime data for multiple stocks in ONE request."""
    raw = await fetch_stocks_batch([s.dict() for s in req.stocks])
    return [BatchStockData(**r) for r in raw]


@router.post("/stocks/add")
async def add_stock(req: AddStockRequest, request: Request,
                    db: Session = Depends(get_db),
                    user=Depends(get_current_user)):
    existing = (db.query(WatchlistItem)
                .filter(WatchlistItem.user_id == user.id,
                        WatchlistItem.stock_code == req.stock_code,
                        WatchlistItem.market == req.market)
                .first())
    if existing:
        raise HTTPException(400, "Stock already in watchlist")

    # Detect if it's a board/sector code
    item_type = "sector" if is_board_code(req.stock_code) else "stock"
    market = req.market
    stock_name = req.stock_name or ""

    # Auto-fetch name (for sectors, always try to get real name)
    try:
        if item_type == "sector":
            market = "SECTOR"
            rt = await fetch_sector_realtime(req.stock_code)
            real_name = rt.get("stock_name", "")
            if real_name:
                stock_name = real_name
        elif not stock_name:
            rt = await fetch_stock_realtime(req.stock_code, market)
            stock_name = rt.get("stock_name", "")
    except Exception:
        pass

    min_sort = (db.query(func.min(WatchlistItem.sort_order))
                .filter(WatchlistItem.user_id == user.id)
                .scalar())

    stock = WatchlistItem(
        user_id=user.id, stock_code=req.stock_code,
        market=market, stock_name=stock_name,
        item_type=item_type,
        sort_order=(min_sort or 0) - 1,
    )
    db.add(stock)
    db.commit()
    db.refresh(stock)

    log_action(db, user.id, user.username, "add_stock",
               target=f"{req.stock_code} ({market})",
               detail=f"type={item_type}, name={stock_name}",
               ip_address=get_client_ip(request))

    return {"id": stock.id, "msg": "Stock added"}


@router.delete("/stocks/{stock_id}")
def remove_stock(stock_id: int, request: Request,
                 db: Session = Depends(get_db),
                 user=Depends(get_current_user)):
    stock = (db.query(WatchlistItem)
             .filter(WatchlistItem.id == stock_id, WatchlistItem.user_id == user.id)
             .first())
    if not stock:
        raise HTTPException(404, "Stock not found")

    # If the stock has reports, hide it instead of deleting
    has_reports = (db.query(StockReport)
                   .filter(StockReport.stock_code == stock.stock_code,
                           StockReport.market == stock.market)
                   .count()) > 0
    if has_reports:
        stock.hidden = 1
        db.commit()
        log_action(db, user.id, user.username, "hide_stock",
                   target=f"{stock.stock_code} ({stock.market})",
                   detail=f"name={stock.stock_name}, has_reports=True",
                   ip_address=get_client_ip(request))
        return {"action": "hidden", "id": stock_id}

    log_action(db, user.id, user.username, "remove_stock",
               target=f"{stock.stock_code} ({stock.market})",
               detail=f"name={stock.stock_name}",
               ip_address=get_client_ip(request))
    db.delete(stock)
    db.commit()
    return {"action": "deleted", "id": stock_id}


@router.patch("/stocks/{stock_id}/show")
def show_stock(stock_id: int, request: Request,
               db: Session = Depends(get_db),
               user=Depends(get_current_user)):
    """Unhide a previously hidden stock."""
    stock = (db.query(WatchlistItem)
             .filter(WatchlistItem.id == stock_id, WatchlistItem.user_id == user.id)
             .first())
    if not stock:
        raise HTTPException(404, "Stock not found")
    stock.hidden = 0
    db.commit()
    log_action(db, user.id, user.username, "show_stock",
               target=f"{stock.stock_code} ({stock.market})",
               ip_address=get_client_ip(request))
    return {"action": "shown", "id": stock_id}


@router.patch("/stocks/{stock_id}/notes")
def update_notes(stock_id: int, req: UpdateNotesRequest,
                 db: Session = Depends(get_db), user=Depends(get_current_user)):
    stock = (db.query(WatchlistItem)
             .filter(WatchlistItem.id == stock_id, WatchlistItem.user_id == user.id)
             .first())
    if not stock:
        raise HTTPException(404, "Stock not found")
    stock.notes = req.notes
    db.commit()
    return {"msg": "Notes updated"}


@router.patch("/stocks/{stock_id}/name")
def update_name(stock_id: int, req: UpdateNameRequest,
                db: Session = Depends(get_db), user=Depends(get_current_user)):
    stock = (db.query(WatchlistItem)
             .filter(WatchlistItem.id == stock_id, WatchlistItem.user_id == user.id)
             .first())
    if not stock:
        raise HTTPException(404, "Stock not found")
    stock.stock_name = req.stock_name.strip()
    db.commit()
    if stock.item_type == 'sector' and stock.stock_name:
        from services.sector_service import save_board_name
        save_board_name(stock.stock_code, stock.stock_name)
    return {"msg": "Name updated"}


@router.post("/stocks/reorder")
def reorder_stocks(order: List[int], request: Request, db: Session = Depends(get_db),
                   user=Depends(get_current_user)):
    for idx, stock_id in enumerate(order):
        stock = (db.query(WatchlistItem)
                 .filter(WatchlistItem.id == stock_id, WatchlistItem.user_id == user.id)
                 .first())
        if stock:
            stock.sort_order = idx
    db.commit()

    log_action(db, user.id, user.username, "reorder",
               target=f"{len(order)} stocks",
               ip_address=get_client_ip(request))

    return {"msg": "Reordered"}


@router.get("/stocks/search/{keyword}")
async def search_stocks(keyword: str):
    kw = keyword.strip()
    if not kw:
        return []

    # ── Board code (BK+4 digits): return immediately, try akshare for real name ──
    import re
    if re.match(r'^BK\d{4}$', kw, re.IGNORECASE):
        code = kw.upper()
        name = await lookup_board_name(code)
        if not name:
            name = f"板块{code}"
        return [{"code": code, "market": "SECTOR", "name": name, "item_type": "sector"}]

    # ── Stock search ──
    results = await search_stock_service(kw)
    board_results = await search_board(kw) if not results else []
    seen = set()
    combined = []
    for r in results:
        seen.add(r.get("code", ""))
        combined.append(r)
    for r in board_results:
        if r.get("code") not in seen:
            seen.add(r.get("code", ""))
            combined.append(r)
    return combined


@router.post("/stocks/refresh")
async def refresh_stocks(db: Session = Depends(get_db),
                         user=Depends(get_current_user)):
    stocks = (db.query(WatchlistItem)
              .filter(WatchlistItem.user_id == user.id)
              .order_by(WatchlistItem.sort_order)
              .all())
    if not stocks:
        return []

    # Separate stock vs sector items
    stock_items = [s for s in stocks if (s.item_type or "stock") != "sector"]
    sector_items = [s for s in stocks if (s.item_type or "stock") == "sector"]

    data_map = {}

    # Fetch stock data via Sina batch
    if stock_items:
        batch_items = [{"code": s.stock_code, "market": s.market} for s in stock_items]
        for r in await fetch_stocks_batch(batch_items):
            data_map[(r.get("code"), r.get("market"))] = r

    # Fetch sector data in parallel with a hard per-sector timeout
    # (akshare/eastmoney may be slow or blocked — must not stall the whole refresh)
    sector_data = {}
    if sector_items:
        async def _fetch_sector_safe(code: str) -> tuple:
            try:
                sr = await asyncio.wait_for(fetch_sector_realtime(code), timeout=6)
                return code, sr
            except Exception as e:
                logger.debug(f"sector refresh error {code}: {e}")
                return code, {}

        sector_results = await asyncio.gather(
            *[_fetch_sector_safe(s.stock_code) for s in sector_items]
        )
        for code, sr in sector_results:
            if sr:
                sector_data[code] = sr

    # Parallel fetch news + chart for stock items only (with 60s total timeout)
    news_tasks = [fetch_stock_news(s.stock_code, s.market) for s in stock_items]
    chart_tasks = [fetch_chart_data(s.stock_code, s.market) for s in stock_items]
    try:
        all_news = await asyncio.wait_for(asyncio.gather(*news_tasks), timeout=60) if news_tasks else []
    except (asyncio.TimeoutError, Exception):
        all_news = []
    try:
        all_charts = await asyncio.wait_for(asyncio.gather(*chart_tasks), timeout=60) if chart_tasks else []
    except (asyncio.TimeoutError, Exception):
        all_charts = []

    result = []
    stock_idx = 0
    for s in stocks:
        is_sector = (s.item_type or "stock") == "sector"
        if is_sector:
            sr = sector_data.get(s.stock_code, {})
            name = sr.get("stock_name") or s.stock_name or ""
            result.append(StockDataResponse(
                id=s.id, stock_code=s.stock_code, market="SECTOR",
                stock_name=name, notes=s.notes, item_type="sector",
                board_type=sr.get("board_type", ""),
                up_count=sr.get("up_count"),
                down_count=sr.get("down_count"),
                **{k: sr.get(k) for k in [
                    "price", "change", "change_pct", "prev_close",
                    "open", "high", "low", "volume", "amount",
                    "turnover_rate", "amplitude", "market_cap",
                ]},
            ))
        else:
            rt = data_map.get((s.stock_code, s.market), {})
            name = rt.get("stock_name") or s.stock_name or ""
            result.append(StockDataResponse(
                id=s.id, stock_code=s.stock_code, market=s.market,
                stock_name=name, notes=s.notes, item_type="stock",
                **{k: rt.get(k) for k in [
                    "price", "change", "change_pct", "prev_close",
                    "open", "high", "low", "volume", "amount",
                    "turnover_rate", "pe", "market_cap", "float_market_cap",
                    "amplitude",
                ]},
                news=all_news[stock_idx] if stock_idx < len(all_news) else [],
                chart_data=all_charts[stock_idx] if stock_idx < len(all_charts) else [],
            ))
            stock_idx += 1

    return result


@router.get("/market-intel")
async def get_market_intel():
    """Return market intelligence data:
    - A-share indices (Shanghai / Shenzhen / ChiNext) — real-time via Sina
    - Hyperscaler CapEx + US tech giants market cap
    - Tracked stock YTD performance
    """
    items = []

    # A-share indices first
    try:
        indices = await get_aindex_intel()
        items.extend(indices)
    except Exception as e:
        logger.warning(f"aindex intel error: {e}")

    # Tech giants market cap data
    try:
        tech = await get_tech_giants_intel()
        items.extend(tech)
    except Exception as e:
        logger.warning(f"tech giants intel error: {e}")

    # Tracked stock performance
    try:
        perf = await get_stock_performance_intel()
        items.extend(perf)
    except Exception as e:
        logger.warning(f"stock perf intel error: {e}")

    return items


@router.get("/sector-congestion")
async def get_sector_congestion():
    """Return real-time metrics for all tracked AI sectors (from bk_names.json)."""
    from services.sector_service import get_sector_congestion_data
    return await get_sector_congestion_data()
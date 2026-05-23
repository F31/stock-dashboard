"""Quantitative analysis score endpoints."""
import json
import logging
import re
import sqlite3
import time
from typing import Optional

import requests
from fastapi import APIRouter, Depends, Query

from database import DB_PATH
from routes.auth import get_current_user
from models import User

logger = logging.getLogger(__name__)
router = APIRouter(tags=["quan"])

# ── Per-code live price cache ──────────────────────────────────────────────
# Keyed by stock_code → {"price": float, "change_pct": float, "ts": float}
# Each code has its own timestamp so a partial update never evicts valid data.
_price_cache: dict[str, dict] = {}
_PRICE_TTL   = 300   # seconds — 5 min
_BATCH_SIZE  = 100
_TQ_HEADERS  = {"Referer": "https://gu.qq.com", "User-Agent": "Mozilla/5.0"}


def _fetch_tencent(codes: list[str]) -> dict[str, dict]:
    """Fetch live prices from Tencent qt.gtimg.cn in GBK-encoded batches.

    Response fields (split by '~'):
      [3]  current price   [4] yesterday close
    change_pct computed from those two to avoid field-index guessing.
    """
    result: dict[str, dict] = {}
    for i in range(0, len(codes), _BATCH_SIZE):
        batch = codes[i : i + _BATCH_SIZE]
        syms  = ",".join(("sh" if c.startswith("6") else "sz") + c for c in batch)
        try:
            r = requests.get(
                f"https://qt.gtimg.cn/q={syms}",
                headers=_TQ_HEADERS,
                timeout=8,
            )
            r.encoding = "gbk"
            for line in r.text.strip().split("\n"):
                parts = line.split("~")
                if len(parts) < 5:
                    continue
                m = re.search(r"v_[a-z]{2}(\d{6})", line)
                if not m:
                    continue
                code = m.group(1)
                try:
                    price      = float(parts[3])
                    prev_close = float(parts[4])
                    if price <= 0 or prev_close <= 0:
                        continue
                    change_pct = round((price - prev_close) / prev_close * 100, 2)
                    result[code] = {"price": round(price, 2), "change_pct": change_pct}
                except (ValueError, IndexError):
                    pass
        except Exception as e:
            logger.warning("Tencent price fetch error (batch @%s): %s", batch[0], e)
    return result


def _batch_prices(codes: list[str]) -> dict[str, dict]:
    """Return per-code price dict, refreshing only stale / missing entries.

    The cache is per-code: a watchlist request for 10 codes never blocks a
    subsequent 300-code request from fetching the remaining 290.
    """
    now   = time.time()
    stale = [c for c in codes
             if c not in _price_cache or now - _price_cache[c]["ts"] > _PRICE_TTL]

    if stale:
        fresh = _fetch_tencent(stale)
        for code, data in fresh.items():
            _price_cache[code] = {**data, "ts": now}
        # Stamp codes with no market data so we don't retry them this cycle
        for code in stale:
            if code not in _price_cache:
                _price_cache[code] = {"price": None, "change_pct": None, "ts": now}

        logger.info(
            "Price cache: requested=%d  stale=%d  fetched=%d  total_cached=%d",
            len(codes), len(stale), len(fresh), len(_price_cache),
        )

    return {c: _price_cache[c] for c in codes if c in _price_cache}


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(table: str = "quan_daily_scores") -> bool:
    try:
        with _get_conn() as conn:
            return bool(conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone())
    except Exception:
        return False


def _resolve_date(conn, trade_date, model):
    if trade_date is not None:
        return trade_date
    row = conn.execute(
        "SELECT MAX(trade_date) FROM quan_daily_scores WHERE model_name=?", (model,)
    ).fetchone()
    return row[0] if row and row[0] else None


def _enrich(scores: list[dict], price_map: dict) -> list[dict]:
    for s in scores:
        px = price_map.get(s["stock_code"], {})
        s["price"]      = px.get("price")       # None if suspended / no data
        s["change_pct"] = px.get("change_pct")
    return scores


def _fetch_scores(conn, trade_date, model, min_percentile, top_n, codes_filter) -> list[dict]:
    sql = """
        SELECT q.stock_code, q.trade_date, q.model_name,
               q.raw_score, q.percentile_score, q.label, q.rank,
               COALESCE(q.sector_warning, '')           AS sector_warning,
               COALESCE(i.stock_name, w.stock_name, '') AS stock_name,
               COALESCE(i.industry, '')                 AS industry
        FROM quan_daily_scores q
        LEFT JOIN (
            SELECT stock_code, MAX(stock_name) AS stock_name, MAX(industry) AS industry
            FROM quan_stock_info GROUP BY stock_code
        ) i ON i.stock_code = q.stock_code
        LEFT JOIN (
            SELECT stock_code, MAX(stock_name) AS stock_name
            FROM watchlist WHERE stock_name IS NOT NULL AND stock_name != ''
            GROUP BY stock_code
        ) w ON w.stock_code = q.stock_code
        WHERE q.trade_date=? AND q.model_name=? AND q.percentile_score>=?
    """
    params: list = [trade_date, model, min_percentile]

    if codes_filter:
        ph = ",".join("?" * len(codes_filter))
        sql += f" AND q.stock_code IN ({ph})"
        params.extend(codes_filter)

    sql += " ORDER BY q.percentile_score DESC"
    if top_n:
        sql += f" LIMIT {top_n}"

    return [dict(r) for r in conn.execute(sql, params).fetchall()]


@router.get("/quan/scores")
async def get_quan_scores(
    trade_date: Optional[str] = Query(None),
    model: str = Query("factor"),
    min_percentile: float = Query(0.0, ge=0, le=100),
    top_n: Optional[int] = Query(None, ge=1, le=500),
    stock_codes: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    if not _table_exists():
        return {"trade_date": None, "model": model, "scores": [], "message": "No quan data yet"}

    with _get_conn() as conn:
        td = _resolve_date(conn, trade_date, model)
        if td is None:
            return {"trade_date": None, "model": model, "scores": [], "message": "No data"}

        codes_filter = [c.strip() for c in stock_codes.split(",") if c.strip()] if stock_codes else []
        scores = _fetch_scores(conn, td, model, min_percentile, top_n, codes_filter)

    if scores:
        all_codes = [s["stock_code"] for s in scores]
        prices = _batch_prices(all_codes)
        scores = _enrich(scores, prices)

    return {"trade_date": td, "model": model, "total": len(scores), "scores": scores}


@router.get("/quan/scores/{stock_code}")
async def get_stock_quan_score(
    stock_code: str,
    model: str = Query("factor"),
    trade_date: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    if not _table_exists():
        return {"stock_code": stock_code, "score": None}

    with _get_conn() as conn:
        td = _resolve_date(conn, trade_date, model)
        if td is None:
            return {"stock_code": stock_code, "score": None}
        rows = _fetch_scores(conn, td, model, 0.0, 1, [stock_code])

    if not rows:
        return {"stock_code": stock_code, "score": None}

    scores = _enrich(rows, _batch_prices([stock_code]))
    return {"stock_code": stock_code, "score": scores[0]}


@router.get("/quan/dates")
async def get_quan_dates(
    model: str = Query("factor"),
    limit: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
):
    if not _table_exists():
        return {"dates": []}
    with _get_conn() as conn:
        rows = conn.execute(
            """SELECT trade_date, COUNT(*) as stock_count
               FROM quan_daily_scores WHERE model_name=?
               GROUP BY trade_date ORDER BY trade_date DESC LIMIT ?""",
            (model, limit),
        ).fetchall()
    return {"dates": [dict(r) for r in rows]}


@router.get("/quan/top")
async def get_quan_top(
    trade_date: Optional[str] = Query(None),
    model: str = Query("factor"),
    n: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    return await get_quan_scores(
        trade_date=trade_date, model=model, min_percentile=0.0,
        top_n=n, stock_codes=None, current_user=current_user,
    )


@router.get("/quan/watchlist-scores")
async def get_watchlist_scores(
    codes: str = Query(..., description="Comma-separated stock codes"),
    current_user: User = Depends(get_current_user),
):
    """Return latest factor scores for a list of watchlist stock codes.

    Searches 'factor' first, then falls back to 'factor_star50' for codes
    not found in CSI300.  Returns a dict keyed by stock_code.
    """
    if not _table_exists():
        return {"scores": {}}

    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    if not code_list:
        return {"scores": {}}

    result: dict[str, dict] = {}

    with _get_conn() as conn:
        for model_name in ("factor", "factor_star50"):
            remaining = [c for c in code_list if c not in result]
            if not remaining:
                break
            td = _resolve_date(conn, None, model_name)
            if not td:
                continue
            rows = _fetch_scores(conn, td, model_name, 0.0, None, remaining)
            for row in rows:
                result[row["stock_code"]] = row

    all_found = list(result.keys())
    if all_found:
        prices = _batch_prices(all_found)
        for code, row in result.items():
            px = prices.get(code, {})
            row["price"]      = px.get("price")
            row["change_pct"] = px.get("change_pct")

    return {"scores": result}


@router.get("/quan/chain-filters")
async def get_chain_filters(current_user: User = Depends(get_current_user)):
    """Return all analysis frameworks with their A-share stock codes.

    Used by the QuantAnalysisMonitor dropdown to filter scores by 产业链.
    Only A-share entities (market='A', 6-digit numeric symbol) are included.
    """
    try:
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT id, name, is_active, entity_matrix "
                "FROM analysis_framework ORDER BY is_active DESC, id"
            ).fetchall()
    except Exception as e:
        logger.warning("chain-filters DB error: %s", e)
        return {"chains": []}

    chains = []
    for r in rows:
        try:
            entities = json.loads(r["entity_matrix"] or "[]")
        except (ValueError, TypeError):
            entities = []

        # Extract 6-digit A-share codes only
        codes = [
            e["symbol"]
            for e in entities
            if e.get("market") == "A"
            and str(e.get("symbol", "")).isdigit()
            and len(str(e.get("symbol", ""))) == 6
        ]

        chains.append({
            "id":        r["id"],
            "name":      r["name"],
            "is_active": bool(r["is_active"]),
            "codes":     codes,
            "count":     len(codes),
        })

    return {"chains": chains}

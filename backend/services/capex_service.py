"""Capex (capital expenditure) fetch & storage service.

Data source: akshare latest reporting-period cash flow sheet from East Money.
Uses stock_cash_flow_sheet_by_report_em (all reporting periods, cumulative YTD)
so the value always reflects the most recently published report.

Capex is stored as a positive yuan value (absolute of the cash outflow).
report_year stores a human-readable label like "2025年报" / "2025Q3" / "2025半年报".
"""
import math
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

CAPEX_STALE_HOURS = 24


# ── Period label helper ──

def _period_label(date_str: str) -> str:
    """Convert a report-date string to a human-readable label.
    Handles both "YYYY-MM-DD" and compact "YYYYMMDD" formats.
    """
    s = str(date_str).strip()
    if not s or len(s) < 6:
        return s[:4] if len(s) >= 4 else s
    if "-" in s and len(s) >= 7:
        year, month = s[:4], s[5:7]
    elif len(s) >= 8:
        year, month = s[:4], s[4:6]
    else:
        return s[:4]
    if month == "12":
        return f"{year}年报"
    if month == "09":
        return f"{year}Q3累计"
    if month == "06":
        return f"{year}半年报"
    if month == "03":
        return f"{year}Q1"
    return f"{year}-{month}"


# ── Fetch ──

def _market_prefix(code: str) -> str:
    """Return 'SH' for Shanghai codes (6xxxxx), 'SZ' for Shenzhen."""
    return "SH" if code.startswith("6") else "SZ"


def _parse_cn_amount(s) -> Optional[float]:
    """Parse Chinese-formatted amount strings like '4.28亿', '2128.12万', '-2.19亿'."""
    if s is None or s is False:
        return None
    text = str(s).strip().replace(',', '').replace('，', '')
    if not text or text in ('--', '-', 'nan', 'None', 'False'):
        return None
    try:
        if '万亿' in text:
            return float(text.replace('万亿', '')) * 1e12
        if '亿' in text:
            return float(text.replace('亿', '')) * 1e8
        if '万' in text:
            return float(text.replace('万', '')) * 1e4
        return float(text)
    except (ValueError, TypeError):
        return None


def _fetch_capex_em(code: str) -> Optional[dict]:
    """Primary: East Money cash flow via akshare (English column names, SH/SZ prefix)."""
    import akshare as ak

    symbol = _market_prefix(code) + code
    df = None
    for fn_name in ("stock_cash_flow_sheet_by_report_em",
                    "stock_cash_flow_sheet_by_quarterly_em"):
        fn = getattr(ak, fn_name, None)
        if fn is None:
            continue
        try:
            df = fn(symbol=symbol)
            if df is not None and not df.empty:
                break
        except Exception:
            continue

    if df is None or df.empty:
        return None

    capex_col = "CONSTRUCT_LONG_ASSET"
    if capex_col not in df.columns:
        return None

    for _, row in df.iterrows():
        raw = row.get(capex_col)
        if raw is None:
            continue
        try:
            val = float(raw)
            if math.isnan(val):
                continue
        except (TypeError, ValueError):
            continue

        date_str = str(row.get("REPORT_DATE", ""))[:10]
        return {"capex": abs(val), "report_year": _period_label(date_str)}

    return None


def _fetch_capex_ths(code: str) -> Optional[dict]:
    """Fallback: Tonghuashun cash flow (Chinese column names, bare 6-digit code)."""
    import akshare as ak

    fn = getattr(ak, "stock_financial_cash_ths", None)
    if fn is None:
        return None

    df = fn(symbol=code, indicator='按报告期')
    if df is None or df.empty:
        return None

    capex_col = '购建固定资产、无形资产和其他长期资产支付的现金'
    if capex_col not in df.columns:
        # Try approximate match
        for c in df.columns:
            if '购建固定资产' in str(c) or '购置固定资产' in str(c):
                capex_col = c
                break
        else:
            return None

    # Rows are descending by date (most recent first)
    for _, row in df.iterrows():
        raw = row.get(capex_col)
        val = _parse_cn_amount(raw)
        if val is None:
            continue
        date_str = str(row.get("报告期", ""))[:10]
        return {"capex": abs(val), "report_year": _period_label(date_str)}

    return None


def _fetch_capex_akshare(code: str) -> Optional[dict]:
    """Blocking: fetch latest-period Capex. Tries East Money first, then THS."""
    try:
        import akshare as ak  # noqa: ensure installed

        result = _fetch_capex_em(code)
        if result is not None:
            return result

        logger.debug(f"EM capex failed for {code}, trying THS fallback")
        result = _fetch_capex_ths(code)
        if result is not None:
            return result

        return None
    except Exception as e:
        logger.debug(f"capex fetch error {code}: {e}")
        return None


async def fetch_capex(code: str, market: str) -> Optional[dict]:
    """Async: fetch Capex for one A-share stock. Returns None for HK/US/SECTOR."""
    if market != "A":
        return None
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_capex_akshare, code)


# ── DB helpers ──

def get_capex_record_from_db(code: str, market: str, db) -> Tuple[Optional[float], str]:
    """Read Capex value + period label from DB. Returns (capex, period_label)."""
    from models import StockCapex
    rec = db.query(StockCapex).filter(
        StockCapex.stock_code == code,
        StockCapex.market == market,
    ).first()
    if rec:
        return rec.capex, (rec.report_year or "")
    return None, ""


def _upsert_capex(code: str, market: str, capex: Optional[float],
                  report_year: str, db) -> None:
    from models import StockCapex
    rec = db.query(StockCapex).filter(
        StockCapex.stock_code == code,
        StockCapex.market == market,
    ).first()
    if rec:
        rec.capex = capex
        rec.report_year = report_year
        rec.updated_at = datetime.utcnow()
    else:
        db.add(StockCapex(
            stock_code=code, market=market,
            capex=capex, report_year=report_year,
            updated_at=datetime.utcnow(),
        ))
    db.commit()


def _is_stale(code: str, market: str, db) -> bool:
    from models import StockCapex
    rec = db.query(StockCapex).filter(
        StockCapex.stock_code == code,
        StockCapex.market == market,
    ).first()
    if not rec or rec.updated_at is None:
        return True
    # Records with NULL capex are always re-fetched (previous fetch may have failed)
    if rec.capex is None:
        return True
    return (datetime.utcnow() - rec.updated_at) > timedelta(hours=CAPEX_STALE_HOURS)


# ── Batch refresh ──

async def refresh_all_capex(watchlist_items, db) -> None:
    """Refresh Capex for every stale A-share stock in the watchlist."""
    stock_items = [i for i in watchlist_items
                   if (i.item_type or "stock") != "sector" and i.market == "A"
                   and _is_stale(i.stock_code, i.market, db)]

    if not stock_items:
        return

    sem = asyncio.Semaphore(3)

    async def _fetch_and_store(item):
        async with sem:
            data = await fetch_capex(item.stock_code, item.market)
        if data:
            _upsert_capex(item.stock_code, item.market,
                          data.get("capex"), data.get("report_year", ""), db)
        else:
            _upsert_capex(item.stock_code, item.market, None, "", db)

    await asyncio.gather(*[_fetch_and_store(i) for i in stock_items])
    logger.info(f"Capex refreshed for {len(stock_items)} stocks")

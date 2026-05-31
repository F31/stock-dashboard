"""Quantitative analysis score endpoints."""
import asyncio
import datetime as _dt
import json
import logging
import os
import re
import sqlite3
import subprocess
import time
from typing import Optional

import requests
from fastapi import APIRouter, Depends, Query

from database import DB_PATH, DB_DIR
from routes.auth import get_current_user
from models import User

logger = logging.getLogger(__name__)
router = APIRouter(tags=["quan"])

# Load stock_quan base config for pipeline paths (graceful fallback if missing)
try:
    import sys as _sys
    _sys.path.insert(0, "/root/projects/stock_quan")
    from core.config import load_base_cfg as _load_base_cfg
    _BASE: dict = _load_base_cfg()
except Exception:
    _BASE = {}

# ── Per-code live price cache ──────────────────────────────────────────────
# Keyed by stock_code → {"price": float, "change_pct": float, "ts": float}
# Each code has its own timestamp so a partial update never evicts valid data.
import threading as _threading
_price_cache: dict[str, dict] = {}
_price_fetch_lock = _threading.Lock()   # prevents thundering herd on cold cache
_PRICE_TTL_TRADING = 120   # seconds — during market hours (9:00–15:30 weekdays)
_BATCH_SIZE  = 100
_TQ_HEADERS  = {"Referer": "https://gu.qq.com", "User-Agent": "Mozilla/5.0"}

# Per-code detail cache for _fetch_tencent_detail (price/PE/PB/mktcap)
_detail_cache: dict[str, dict] = {}


def _is_trading_time() -> bool:
    """A股交易时段：周一至周五 09:00–15:30"""
    now = _dt.datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.time()
    return _dt.time(9, 0) <= t <= _dt.time(15, 30)


def _is_stale(ts: float, trading_ttl: int) -> bool:
    """Return True only if the entry needs refreshing.

    During trading hours: expire after trading_ttl seconds.
    Outside trading hours: never expire — prices are frozen at close.
    """
    if not _is_trading_time():
        return False
    return time.time() - ts > trading_ttl


# ── Endpoint-level response cache ─────────────────────────────────────────
# Avoids re-running SQL + Tencent on rapid tab-switches / re-renders.
# Keyed by a string cache key → {"data": any, "ts": float}
_resp_cache: dict[str, dict] = {}
_RESP_TTL_TRADING = 60   # 1 min during market hours; off-hours entries never expire


def _resp_get(key: str):
    entry = _resp_cache.get(key)
    if not entry:
        return None
    if _is_stale(entry["ts"], _RESP_TTL_TRADING):
        return None
    return entry["data"]


def _resp_set(key: str, data) -> None:
    _resp_cache[key] = {"data": data, "ts": time.time()}


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

    Thread-safe: only one thread fires Tencent requests at a time; others wait
    and hit the freshly-populated cache after the lock is released.
    """
    stale = [c for c in codes
             if c not in _price_cache or _is_stale(_price_cache[c]["ts"], _PRICE_TTL_TRADING)]

    if stale:
        with _price_fetch_lock:
            # Re-check under lock — another thread may have just fetched
            stale = [c for c in codes
                     if c not in _price_cache or _is_stale(_price_cache[c]["ts"], _PRICE_TTL_TRADING)]
            if stale:
                fresh = _fetch_tencent(stale)
                ts = time.time()
                for code, data in fresh.items():
                    _price_cache[code] = {**data, "ts": ts}
                for code in stale:
                    if code not in _price_cache:
                        _price_cache[code] = {"price": None, "change_pct": None, "ts": ts}
                logger.info(
                    "Price cache: requested=%d  stale=%d  fetched=%d  total_cached=%d",
                    len(codes), len(stale), len(fresh), len(_price_cache),
                )

    return {c: _price_cache[c] for c in codes if c in _price_cache}


# ── Technical levels cache ────────────────────────────────────────────────
_levels_cache: dict[str, dict] = {}   # code → {"data": dict, "ts": float}
_LEVELS_TTL  = 3600                    # 1 h — levels change slowly
_QLIB_PYTHON = os.environ.get("QLIB_PYTHON", "/root/qlib/qvenv/bin/python")
_FEATURE_STORE_PATH = os.environ.get(
    "FEATURE_STORE_PATH",
    os.path.join(DB_DIR, "feature_store.db"),
)

# Self-contained qlib script; INSTRUMENT_CODE is replaced before execution.
_QLIB_SCRIPT_TPL = r"""
import sys, json, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, '/root/qlib/qvenv/lib/python3.10/site-packages')
import qlib, pandas as pd, numpy as np

try:
    qlib.init(provider_uri='/root/.qlib/qlib_data/cn_data', region='cn')
    instrument = 'INSTRUMENT_CODE'
    df = qlib.data.D.features(
        [instrument], ['$close', '$high', '$low'],
        start_time='2024-01-01', end_time=None, freq='day',
    )
    df = df.droplevel('instrument')
    # 停牌日 OHLC 为 NaN，前向填充（沿用前收价），避免 rolling 窗口中断
    df = df.ffill()
    close, high, low = df['$close'], df['$high'], df['$low']

    prev = close.shift(1)
    tr = pd.concat([high-low, (high-prev).abs(), (low-prev).abs()], axis=1).max(axis=1)
    atr14 = float(tr.rolling(14).mean().iloc[-1])

    d = close.diff()
    gain = d.clip(lower=0).rolling(14).mean()
    loss = (-d.clip(upper=0)).rolling(14).mean()
    rsi14 = float((100 - 100/(1 + gain/(loss+1e-9))).iloc[-1])

    result = {
        'ok': True,
        'ma5':   float(close.rolling(5).mean().iloc[-1]),
        'ma20':  float(close.rolling(20).mean().iloc[-1]),
        'ma60':  float(close.rolling(60).mean().iloc[-1]),
        'ma120': float(close.rolling(120).mean().iloc[-1]),
        'atr14': atr14, 'rsi14': rsi14,
        'h52w':  float(high.rolling(252).max().iloc[-1]),
        'l52w':  float(low.rolling(252).min().iloc[-1]),
        'last_adj': float(close.iloc[-1]),
    }
    print(json.dumps(result))
except Exception as e:
    print(json.dumps({'ok': False, 'error': str(e)}))
"""


def _load_precomputed_levels(code: str) -> dict | None:
    """Read pre-computed technical indicators from quan_tech_levels (no qlib needed).

    Populated nightly by run_daily.py on the machine that has qlib installed.
    Returns None if no data has been precomputed for this stock yet.
    """
    try:
        with _get_conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """SELECT * FROM quan_tech_levels
                   WHERE stock_code=?
                   ORDER BY trade_date DESC LIMIT 1""",
                (code,),
            ).fetchone()
        if not row:
            return None
        r = dict(row)
        if r.get("last_adj") is None:
            return None
        return {
            "ok":       True,
            "last_adj": r["last_adj"],
            "ma5":      r["ma5"],
            "ma20":     r["ma20"],
            "ma60":     r["ma60"],
            "ma120":    r["ma120"],
            "atr14":    r["atr14"],
            "rsi14":    r["rsi14"],
            "h52w":     r["h52w"],
            "l52w":     r["l52w"],
            "trade_date": r["trade_date"],
        }
    except Exception as e:
        logger.warning("_load_precomputed_levels failed for %s: %s", code, e)
        return None


_EM_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
_EM_KLINE_HEADERS = {
    "Referer":    "https://finance.eastmoney.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


def _fetch_em_klines(code: str) -> "pd.DataFrame | None":
    """Fetch 3 years of front-adjusted daily OHLCV from EastMoney directly.

    Uses the same datacenter API as AKShare internally — no AKShare dependency.
    Kline fields: date, open, close, high, low, volume, amount, amp, chg_pct, chg, turnover
    """
    import pandas as pd

    secid = ("1." if code.startswith("6") else "0.") + code
    params = {
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56",
        "ut":      "7eea3edcaed734bea9cbfc24409ed989",
        "klt":     "101",   # daily
        "fqt":     "1",     # front-adjusted (前复权)
        "secid":   secid,
        "beg":     "20230101",
        "end":     "20500101",
    }
    try:
        r = requests.get(_EM_KLINE_URL, params=params,
                         headers=_EM_KLINE_HEADERS, timeout=15)
        j = r.json()
    except Exception as e:
        logger.warning("EM kline fetch failed for %s: %s", code, e)
        return None

    klines = (j.get("data") or {}).get("klines")
    if not klines:
        logger.warning("EM kline: empty result for %s (secid=%s)", code, secid)
        return None

    rows = []
    for line in klines:
        parts = line.split(",")
        if len(parts) < 6:
            continue
        try:
            rows.append({
                "date":  parts[0],
                "open":  float(parts[1]),
                "close": float(parts[2]),
                "high":  float(parts[3]),
                "low":   float(parts[4]),
            })
        except (ValueError, IndexError):
            continue

    if not rows:
        return None

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def _compute_levels_from_ohlc(
    code: str,
    close: "pd.Series",
    high:  "pd.Series",
    low:   "pd.Series",
    trade_date: str,
) -> "dict | None":
    """Compute MA/ATR/RSI/52w from price series; cache in quan_tech_levels."""
    import math as _math
    import pandas as pd

    close = close.ffill()
    high  = high.ffill()
    low   = low.ffill()

    if len(close) < 5 or _math.isnan(float(close.iloc[-1])):
        return None

    # ATR14
    prev = close.shift(1)
    tr   = pd.concat(
        [high - low, (high - prev).abs(), (low - prev).abs()], axis=1
    ).max(axis=1)
    atr14_v = tr.rolling(14).mean().iloc[-1]

    # RSI14
    d     = close.diff()
    gain  = d.clip(lower=0).rolling(14).mean()
    loss  = (-d.clip(upper=0)).rolling(14).mean()
    rsi14_v = (100 - 100 / (1 + gain / (loss + 1e-9))).iloc[-1]

    def _safe(v):
        f = float(v)
        return None if (_math.isnan(f) or _math.isinf(f)) else round(f, 6)

    def _ma(n):
        return _safe(close.rolling(n).mean().iloc[-1]) if len(close) >= n else None

    def _rmax(n):
        return _safe(high.rolling(n).max().iloc[-1]) if len(close) >= n else None

    def _rmin(n):
        return _safe(low.rolling(n).min().iloc[-1]) if len(close) >= n else None

    result = {
        "ok":         True,
        "last_adj":   _safe(close.iloc[-1]),
        "ma5":        _ma(5),
        "ma20":       _ma(20),
        "ma60":       _ma(60),
        "ma120":      _ma(120),
        "atr14":      _safe(atr14_v),
        "rsi14":      _safe(rsi14_v),
        "h52w":       _rmax(252),
        "l52w":       _rmin(252),
        "trade_date": trade_date,
    }

    if result["last_adj"] is None:
        return None

    _save_tech_levels(code, trade_date, result)
    logger.info("EM kline tech levels computed and cached for %s (%s)", code, trade_date)
    return result


def _compute_levels_em(code: str) -> "dict | None":
    """Compute technical indicators via EastMoney K-line API (no qlib/akshare needed).

    Works on cloud deployments. Fetches 3 years of front-adjusted daily OHLCV
    via direct HTTP, computes indicators, caches in quan_tech_levels.
    """
    df = _fetch_em_klines(code)
    if df is None:
        return None
    trade_date = df["date"].iloc[-1].strftime("%Y-%m-%d")
    return _compute_levels_from_ohlc(
        code, df["close"], df["high"], df["low"], trade_date
    )


def _save_tech_levels(code: str, trade_date: str, data: dict) -> None:
    """Persist AKShare-computed tech levels into quan_tech_levels for caching."""
    try:
        with _get_conn() as conn:
            conn.execute(
                """INSERT INTO quan_tech_levels
                       (stock_code, trade_date, last_adj, ma5, ma20, ma60, ma120, atr14, rsi14, h52w, l52w)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(stock_code, trade_date) DO UPDATE SET
                       last_adj=excluded.last_adj, ma5=excluded.ma5, ma20=excluded.ma20,
                       ma60=excluded.ma60, ma120=excluded.ma120, atr14=excluded.atr14,
                       rsi14=excluded.rsi14, h52w=excluded.h52w, l52w=excluded.l52w,
                       updated_at=datetime('now')""",
                (code, trade_date,
                 data.get("last_adj"), data.get("ma5"), data.get("ma20"),
                 data.get("ma60"), data.get("ma120"), data.get("atr14"),
                 data.get("rsi14"), data.get("h52w"), data.get("l52w")),
            )
    except Exception as e:
        logger.warning("_save_tech_levels failed for %s: %s", code, e)


def _run_qlib_levels(code: str) -> dict | None:
    """Blocking: call qlib subprocess to compute technical indicators.

    Local-only fallback — only succeeds if _QLIB_PYTHON and qlib data exist.
    On cloud deployments this always returns None; use precomputed DB or AKShare instead.
    """
    import os
    if not os.path.exists(_QLIB_PYTHON):
        return None
    prefix = "SH" if code.startswith("6") else "SZ"
    script = _QLIB_SCRIPT_TPL.replace("INSTRUMENT_CODE", prefix + code)
    try:
        r = subprocess.run(
            [_QLIB_PYTHON, "-c", script],
            capture_output=True, text=True, timeout=75,
        )
        for line in reversed(r.stdout.strip().split("\n")):
            if line.strip().startswith("{"):
                data = json.loads(line.strip())
                if data.get("ok"):
                    return data
                logger.warning("qlib levels error for %s: %s", code, data.get("error"))
                return None
        logger.warning("qlib levels: no JSON for %s | stderr=%s", code, r.stderr[:300])
        return None
    except Exception as e:
        logger.error("qlib levels subprocess failed for %s: %s", code, e)
        return None


def _fetch_em_spot_price(code: str) -> dict:
    """EastMoney real-time spot price fallback for stocks not covered by Tencent (e.g. BSE 920xxx)."""
    secid = ("1." if code.startswith("6") else "0.") + code
    try:
        r = requests.get(
            "https://push2.eastmoney.com/api/qt/stock/get",
            params={"secid": secid, "fields": "f43,f170,f116,f9,f23"},
            headers=_EM_KLINE_HEADERS,
            timeout=8,
        )
        d = (r.json().get("data") or {})
        price  = d.get("f43")
        chg    = d.get("f170")
        mktcap = d.get("f116")
        pe     = d.get("f9")
        pb     = d.get("f23")
        # EM returns integers ×100 for price/chg, ×100 for pe/pb, mktcap in 亿元 ×10000
        price  = round(price / 100, 2)   if price  and price  != "-"  else None
        chg    = round(chg   / 100, 2)   if chg    and chg    != "-"  else None
        pe     = round(pe    / 100, 2)   if pe     and pe     != "-"  else None
        pb     = round(pb    / 100, 2)   if pb     and pb     != "-"  else None
        mktcap = round(mktcap / 10000, 2) if mktcap and mktcap != "-" else None
        return {"price": price, "change_pct": chg, "pe": pe, "pb": pb, "mktcap": mktcap}
    except Exception as e:
        logger.warning("EM spot fallback error for %s: %s", code, e)
        return {}


def _fetch_tencent_detail(code: str) -> dict:
    """Fetch extended real-time quote: price, PE, PB, market cap.

    Result is cached; off-hours entries never expire (prices frozen at close).
    Falls back to EastMoney for BSE stocks (920xxx) not covered by Tencent.
    """
    cached = _detail_cache.get(code)
    if cached and not _is_stale(cached["ts"], _PRICE_TTL_TRADING):
        return cached["data"]

    # BSE stocks (920xxx, 830xxx, etc.) are not covered by Tencent's gtimg API
    if code.startswith("92") or code.startswith("83") or code.startswith("87"):
        data = _fetch_em_spot_price(code)
        if data.get("price"):
            _detail_cache[code] = {"data": data, "ts": time.time()}
        return data

    prefix = "sh" if code.startswith("6") else "sz"
    try:
        r = requests.get(
            f"https://qt.gtimg.cn/q={prefix}{code}",
            headers=_TQ_HEADERS, timeout=8,
        )
        r.encoding = "gbk"
        parts = r.text.strip().split("~")
        if len(parts) < 50:
            return cached["data"] if cached else {}
        price      = float(parts[3])  if parts[3]  else None
        prev_close = float(parts[4])  if parts[4]  else None
        pe         = float(parts[39]) if parts[39] else None
        pb         = float(parts[46]) if parts[46] else None
        mktcap     = float(parts[45]) if parts[45] else None   # 亿元
        chg = round((price - prev_close) / prev_close * 100, 2) if price and prev_close else None
        data = {"price": price, "change_pct": chg, "pe": pe, "pb": pb, "mktcap": mktcap}
        _detail_cache[code] = {"data": data, "ts": time.time()}
        return data
    except Exception as e:
        logger.warning("Tencent detail error for %s: %s", code, e)
        return cached["data"] if cached else {}


def _get_sector_valuation(stock_code: str, pe: float | None, pb: float | None) -> dict:
    """Return industry peer PE comparison using stored daily_pe and quan_stock_info.

    Lightweight: one JOIN on ~10-50 rows; cached inside _levels_cache (1h TTL).
    Returns {} if industry data is unavailable (non-fatal).
    """
    try:
        import statistics as _stats
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT industry FROM quan_stock_info WHERE stock_code=?", (stock_code,)
            ).fetchone()
            if not row or not row["industry"]:
                return {}
            industry = row["industry"]

            peer_codes = [
                r[0] for r in conn.execute(
                    "SELECT stock_code FROM quan_stock_info "
                    "WHERE industry=? AND stock_code!=?",
                    (industry, stock_code),
                ).fetchall()
            ]
            if not peer_codes:
                return {"industry": industry}

            ph = ",".join("?" * len(peer_codes))
            pe_rows = conn.execute(
                f"""SELECT stock_code, pe FROM daily_pe
                    WHERE stock_code IN ({ph})
                    GROUP BY stock_code HAVING trade_date = MAX(trade_date)""",
                peer_codes,
            ).fetchall()

        peer_pes = [r[1] for r in pe_rows if r[1] and r[1] > 0 and r[1] < 500]
        if len(peer_pes) < 3:
            return {"industry": industry}

        sector_median_pe = round(_stats.median(peer_pes), 1)
        sector_mean_pe   = round(sum(peer_pes) / len(peer_pes), 1)

        result: dict = {
            "industry":        industry,
            "peer_count":      len(peer_pes),
            "sector_median_pe": sector_median_pe,
            "sector_mean_pe":   sector_mean_pe,
        }

        if pe and pe > 0:
            relative_pe = round(pe / sector_median_pe, 2)
            pe_premium  = round((pe - sector_median_pe) / sector_median_pe * 100, 1)
            if relative_pe <= 0.80:
                verdict, verdict_level = "行业内低估", "cheap"
            elif relative_pe <= 1.20:
                verdict, verdict_level = "行业内合理", "fair"
            elif relative_pe <= 1.60:
                verdict, verdict_level = "行业内偏高", "pricey"
            else:
                verdict, verdict_level = "行业内高估", "expensive"
            result.update({
                "stock_pe":      round(pe, 1),
                "relative_pe":   relative_pe,
                "pe_premium_pct": pe_premium,
                "verdict":       verdict,
                "verdict_level": verdict_level,
            })

        return result
    except Exception as e:
        logger.warning("Sector valuation failed for %s: %s", stock_code, e)
        return {}


def _get_fundamentals(code: str) -> dict:
    """Return latest quarterly fundamentals from feature_store.db."""
    try:
        conn = sqlite3.connect(_FEATURE_STORE_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """SELECT report_date, profit_yoy, revenue_yoy,
                      roe, gross_margin, cash_profit_ratio
               FROM fin_quarterly WHERE stock_code=?
               ORDER BY report_date DESC LIMIT 1""",
            (code,),
        ).fetchone()
        conn.close()
        return dict(row) if row else {}
    except Exception:
        return {}


def _derive_levels(
    price: float,
    ma5: float | None, ma20: float | None, ma60: float | None, ma120: float | None,
    atr14: float | None, rsi14: float,
    h52w: float | None, l52w: float | None,
    pe: float | None, profit_yoy: float | None,
    label: str,
) -> dict:
    """Derive buy zones, targets, stop-loss and sentiment from technical data.
    ma60/ma120/h52w/l52w may be None for recently-listed stocks."""
    if rsi14 >= 80:   rsi_tag = "强烈超买"
    elif rsi14 >= 70: rsi_tag = "超买"
    elif rsi14 >= 60: rsi_tag = "偏强"
    elif rsi14 >= 40: rsi_tag = "中性"
    elif rsi14 >= 30: rsi_tag = "偏弱"
    else:             rsi_tag = "超卖"

    ma20_pct = round((price - ma20) / ma20 * 100, 1) if ma20 else None
    ma60_pct = round((price - ma60) / ma60 * 100, 1) if ma60 else None

    if rsi14 > 70 or (ma20_pct is not None and ma20_pct > 15):
        sentiment, sentiment_level = "不建议追高", "warn"
    elif label in ("强烈推荐", "推荐") and rsi14 < 60:
        sentiment, sentiment_level = "可建仓", "buy"
    elif label in ("强烈推荐", "推荐"):
        sentiment, sentiment_level = "可关注", "neutral"
    else:
        sentiment, sentiment_level = "等待回调", "neutral"

    # Buy zones anchored to MA levels (skip tiers whose MA is unavailable)
    buy_zones = []
    if ma5:
        buy_zones.append({"tier": 1, "label": "观察买点",
            "low": round(ma5 * 0.97, 2), "high": round(ma5 * 1.01, 2),
            "basis": "MA5支撑 / 约1×ATR回调", "note": "轻仓试探，需放量企稳"})
    if ma20:
        buy_zones.append({"tier": 2, "label": "中线买点",
            "low": round(ma20 * 0.97, 2), "high": round(ma20 * 1.03, 2),
            "basis": "MA20均线支撑，情绪降温后主要买点", "note": "可建半仓"})
    if ma60:
        buy_zones.append({"tier": 3, "label": "最优买点",
            "low": round(ma60 * 0.97, 2), "high": round(ma60 * 1.03, 2),
            "basis": "MA60强支撑，性价比最高", "note": "可重仓，需确认基本面"})

    targets = []
    if h52w:
        targets.append({"tier": 1, "label": "第一目标", "price": round(h52w * 1.05, 2),
                        "basis": "52周高点上方5%，逢高减仓1/3"})

    if pe and profit_yoy and profit_yoy > 0:
        ttm_eps  = price / pe
        next_eps = ttm_eps * (1 + profit_yoy / 100)
        fair_pe  = min(80, max(25, profit_yoy * 2))
        t2 = round(next_eps * fair_pe, 2)
        if t2 > price:
            targets.append({"tier": 2, "label": "扩展目标", "price": t2,
                             "basis": f"预期EPS×{fair_pe:.0f}x（PEG≈2）"})

    stop_loss = []
    if ma20:
        stop_loss.append({"label": "MA20止损", "price": round(ma20 * 0.95, 2),
                          "basis": "收盘跌破MA20 -5%时减仓"})
    if ma60:
        stop_loss.append({"label": "MA60止损", "price": round(ma60 * 0.97, 2),
                          "basis": "深度回调跌破MA60 -3%时清仓"})

    return {
        "sentiment":       sentiment,
        "sentiment_level": sentiment_level,
        "rsi_tag":         rsi_tag,
        "rsi14":           round(rsi14, 1),
        "atr14":           round(atr14, 2) if atr14 else None,
        "ma20_pct":        ma20_pct,
        "ma60_pct":        ma60_pct,
        "ma": {
            "ma5":   ma5,
            "ma20":  ma20,
            "ma60":  ma60,
            "ma120": ma120,
        },
        "h52w":      h52w,
        "l52w":      l52w,
        "buy_zones": buy_zones,
        "targets":   targets,
        "stop_loss": stop_loss,
    }


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


# ── 子板块元数据：从 DB 读取，兜底从共享 JSON 加载 ──────────────────
# 数据来源：
#   1. system_settings.subsector_config（由 pipeline Step 0 写入）
#   2. 兜底: config/subsector_defaults.json（与 stock_quan 共享，无代码重复）
# 仅含显示名+分类，不含权重/patterns 等配置（权重从 training_history.db 加载）


def _load_subsector_defaults() -> dict[str, dict]:
    """从共享 JSON 加载兜底子板块列表（仅显示名+分类+链映射）。"""
    import json as _json
    from pathlib import Path as _Path
    default_path = _Path(__file__).resolve().parent.parent / "config" / "subsector_defaults.json"
    try:
        if default_path.exists():
            with open(default_path) as f:
                data = _json.load(f)
        else:
            raise FileNotFoundError(str(default_path))
    except Exception:
        # 极简兜底：JSON 不存在时的最后防线
        return {}

    _chain_map: dict[str, str] = {
        "科技产业链": "tech", "航天军工": "space", "生物医药": "bio",
    }
    _chain_label: dict[str, str] = {
        "tech": "科技链", "space": "航天军工", "bio": "生物医药",
    }
    result: dict[str, dict] = {}
    for chain_cn, subs in data.items():
        ck = _chain_map.get(chain_cn, "tech")
        cl = _chain_label.get(ck, chain_cn)
        for ss_key, ss_data in subs.items():
            result[ss_key] = {
                "name": ss_data.get("name", ss_key),
                "chain": cl,
                "chain_key": ck,
            }
    return result


def _load_subsector_meta() -> dict[str, dict]:
    """读取子板块元数据，优先从 DB system_settings 表。

    DB 中有配置时使用 DB 的（含训练权重等完整配置）；
    DB 无配置时使用内置 fallback（仅中英文名+分类，不含权重）。
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT value FROM system_settings WHERE key='subsector_config'"
            ).fetchone()
        if row and row[0]:
            import json as _json
            data = _json.loads(row[0])
            # 从完整配置中提取显示名+分类
            result: dict[str, dict] = {}
            _chain_map: dict[str, str] = {
                "科技产业链": "tech",
                "航天军工": "space",
                "生物医药": "bio",
            }
            _chain_label: dict[str, str] = {
                "tech": "科技链", "space": "航天军工", "bio": "生物医药",
            }
            for chain_cn, subs in data.items():
                ck = _chain_map.get(chain_cn, "tech")
                cl = _chain_label.get(ck, chain_cn)
                for ss_key, ss_data in subs.items():
                    entry: dict = {
                        "name": ss_data.get("name", ss_key),
                        "chain": cl,
                        "chain_key": ck,
                    }
                    # 透传 valuation_peers（仅 DB 配置中有，JSON 兜底无）
                    if "valuation_peers" in ss_data:
                        entry["valuation_peers"] = ss_data["valuation_peers"]
                    result[ss_key] = entry
            return result
    except Exception as e:
        logging.getLogger(__name__).warning(
            "Failed to load subsector config from DB: %s (falling back to JSON)", e
        )
    return _load_subsector_defaults()


_SUBSECTOR_META: dict[str, dict] = _load_subsector_meta()
_SUBSECTOR_META_TS: float = 0.0   # last load timestamp


def _get_subsector_meta() -> dict[str, dict]:
    """Return subsector meta, reloading from DB if config changed (TTL=60s)."""
    import time as _time
    global _SUBSECTOR_META, _SUBSECTOR_META_TS
    if _time.monotonic() - _SUBSECTOR_META_TS > 60:
        _SUBSECTOR_META = _load_subsector_meta()
        _SUBSECTOR_META_TS = _time.monotonic()
    return _SUBSECTOR_META

_THEME_HISTORY_DB = "/root/projects/stock_quan/data/training_results/training_history.db"


def _load_theme_weights() -> dict[str, dict]:
    """Load latest per-subsector IC-calibrated weights from training_history.db."""
    try:
        with sqlite3.connect(_THEME_HISTORY_DB) as conn:
            rows = conn.execute("""
                SELECT subsector_key, weight_growth, weight_quality, weight_valuation,
                       weight_momentum, weight_sentiment
                FROM training_runs
                WHERE run_id = (SELECT MAX(run_id) FROM training_runs)
            """).fetchall()
        return {
            r[0]: {"growth": r[1], "quality": r[2], "valuation": r[3],
                   "momentum": r[4], "sentiment": r[5]}
            for r in rows if r[1] is not None
        }
    except Exception:
        return {}


def _resolve_date(conn, trade_date, model):
    if trade_date is not None:
        return trade_date
    # Prefer the date with the most stocks (handles partial runs that miss CSI300 data).
    # Secondary sort by date so ties always pick the most recent full run.
    row = conn.execute(
        """SELECT trade_date FROM quan_daily_scores WHERE model_name=?
           GROUP BY trade_date ORDER BY COUNT(*) DESC, trade_date DESC LIMIT 1""",
        (model,)
    ).fetchone()
    return row[0] if row and row[0] else None


def _enrich(scores: list[dict], price_map: dict) -> list[dict]:
    # Add price data
    for s in scores:
        px = price_map.get(s["stock_code"], {})
        s["price"]      = px.get("price")       # None if suspended / no data
        s["change_pct"] = px.get("change_pct")

    # Compute industry rank: within each industry, rank by percentile_score desc
    from collections import defaultdict
    ind_scores = defaultdict(list)
    for s in scores:
        ind = s.get("industry", "")
        if ind:
            ind_scores[ind].append(s["percentile_score"])

    # For each industry, precompute percentile thresholds for rank mapping
    ind_rank_map: dict[str, dict[int, int]] = {}
    for ind, vals in ind_scores.items():
        sorted_vals = sorted(vals, reverse=True)
        ind_rank_map[ind] = {v: i + 1 for i, v in enumerate(sorted_vals)}

    for s in scores:
        ind = s.get("industry", "")
        if ind and ind in ind_rank_map:
            s["industry_rank"] = ind_rank_map[ind].get(s["percentile_score"], 0)
            s["industry_total"] = len(ind_scores[ind])
        else:
            s["industry_rank"] = 0
            s["industry_total"] = 0

    return scores


def _fetch_scores(conn, trade_date, model, min_percentile, top_n, codes_filter) -> list[dict]:
    """Fetch scores with latest PE (up to trade_date) and latest earnings data."""
    sql = """
        SELECT q.stock_code, q.trade_date, q.model_name,
               q.raw_score, q.percentile_score, q.label, q.rank,
               COALESCE(q.growth_score, 0)              AS growth_score,
               COALESCE(q.quality_score, 0)             AS quality_score,
               COALESCE(q.valuation_score, 0)           AS valuation_score,
               COALESCE(q.momentum_score, 0)            AS momentum_score,
               COALESCE(q.sentiment_score, 50)          AS sentiment_score,
               COALESCE(q.surprise_score, 50)           AS surprise_score,
               COALESCE(q.opportunity_tag, '')          AS opportunity_tag,
               COALESCE(q.sector_warning, '')           AS sector_warning,
               COALESCE(q.subsector, '')                AS subsector,
               COALESCE(NULLIF(i.stock_name,''), w.stock_name, '') AS stock_name,
               COALESCE(NULLIF(i.industry,''), '')               AS industry,
               p.pe                                          AS pe,
               (CASE WHEN p.pe > 0 AND e.profit_yoy IS NOT NULL AND e.profit_yoy > 0
                     THEN ROUND(p.pe / e.profit_yoy, 2)
                     ELSE NULL END)                     AS peg
        FROM quan_daily_scores q
        LEFT JOIN (
            SELECT stock_code,
                   NULLIF(MAX(stock_name),'') AS stock_name,
                   NULLIF(MAX(industry),'')   AS industry
            FROM quan_stock_info GROUP BY stock_code
        ) i ON i.stock_code = q.stock_code
        LEFT JOIN (
            SELECT stock_code, MAX(stock_name) AS stock_name
            FROM watchlist WHERE stock_name IS NOT NULL AND stock_name != ''
            GROUP BY stock_code
        ) w ON w.stock_code = q.stock_code
        -- PE: latest non-null value up to score date (NOT exact date match)
        LEFT JOIN (
            SELECT p1.stock_code, p1.pe
            FROM daily_pe p1
            INNER JOIN (
                SELECT stock_code, MAX(trade_date) AS max_date
                FROM daily_pe
                WHERE pe IS NOT NULL AND trade_date <= ?
                GROUP BY stock_code
            ) p2 ON p1.stock_code = p2.stock_code AND p1.trade_date = p2.max_date
        ) p ON p.stock_code = q.stock_code
        -- Earnings: latest quarter with non-null profit_yoy
        LEFT JOIN (
            SELECT e1.stock_code, e1.profit_yoy
            FROM earnings_quarterly e1
            INNER JOIN (
                SELECT stock_code, MAX(report_date) AS max_date
                FROM earnings_quarterly
                WHERE profit_yoy IS NOT NULL AND profit_yoy > 0
                GROUP BY stock_code
            ) e2 ON e1.stock_code = e2.stock_code AND e1.report_date = e2.max_date
        ) e ON e.stock_code = q.stock_code
        WHERE q.trade_date=? AND q.model_name=? AND q.percentile_score>=?
    """
    params: list = [trade_date, trade_date, model, min_percentile]

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

    cache_key = f"scores:{model}:{trade_date}:{min_percentile}:{top_n}:{stock_codes}"
    if cached := _resp_get(cache_key):
        return cached

    with _get_conn() as conn:
        td = _resolve_date(conn, trade_date, model)
        if td is None:
            return {"trade_date": None, "model": model, "scores": [], "message": "No data"}

        codes_filter = [c.strip() for c in stock_codes.split(",") if c.strip()] if stock_codes else []
        scores = _fetch_scores(conn, td, model, min_percentile, top_n, codes_filter)

    if scores:
        all_codes = [s["stock_code"] for s in scores]
        prices = await asyncio.to_thread(_batch_prices, all_codes)
        scores = _enrich(scores, prices)

    result = {"trade_date": td, "model": model, "total": len(scores), "scores": scores}
    _resp_set(cache_key, result)
    return result


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

    scores = _enrich(rows, await asyncio.to_thread(_batch_prices, [stock_code]))
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
        prices = await asyncio.to_thread(_batch_prices, all_found)
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


@router.get("/quan/theme-scores")
async def get_theme_scores(
    trade_date: Optional[str] = Query(None),
    subsector: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    """Return theme_3chain scores with subsector grouping and IC-calibrated weights.

    Returns all stocks (or filtered by subsector) plus a per-subsector summary
    including trained factor weights from training_history.db.
    """
    if not _table_exists():
        return {"trade_date": None, "total": 0, "subsectors": [], "scores": []}

    cache_key = f"theme:{trade_date}:{subsector}"
    if cached := _resp_get(cache_key):
        return cached

    with _get_conn() as conn:
        td = _resolve_date(conn, trade_date, "theme_3chain")
        if td is None:
            return {"trade_date": None, "total": 0, "subsectors": [], "scores": []}

        sql = """
            SELECT q.stock_code, q.trade_date, q.model_name,
                   q.raw_score, q.percentile_score, q.label, q.rank,
                   COALESCE(q.growth_score, 0)     AS growth_score,
                   COALESCE(q.quality_score, 0)    AS quality_score,
                   COALESCE(q.valuation_score, 0)  AS valuation_score,
                   COALESCE(q.momentum_score, 0)   AS momentum_score,
                   COALESCE(q.sentiment_score, 50) AS sentiment_score,
                   COALESCE(q.subsector, '')        AS subsector,
                   COALESCE(NULLIF(i.stock_name,''), w.stock_name, '') AS stock_name,
                   COALESCE(NULLIF(i.industry,''), '')               AS industry,
                   p.pe                                  AS pe,
                   (CASE WHEN p.pe > 0 AND e.profit_yoy IS NOT NULL AND e.profit_yoy > 0
                         THEN ROUND(p.pe / e.profit_yoy, 2)
                         ELSE NULL END)             AS peg
            FROM quan_daily_scores q
            LEFT JOIN (
                SELECT stock_code,
                       NULLIF(MAX(stock_name),'') AS stock_name,
                       NULLIF(MAX(industry),'')   AS industry
                FROM quan_stock_info GROUP BY stock_code
            ) i ON i.stock_code = q.stock_code
            LEFT JOIN (
                SELECT stock_code, MAX(stock_name) AS stock_name
                FROM watchlist WHERE stock_name IS NOT NULL AND stock_name != ''
                GROUP BY stock_code
            ) w ON w.stock_code = q.stock_code
            LEFT JOIN (
                SELECT p1.stock_code, p1.pe
                FROM daily_pe p1
                INNER JOIN (
                    SELECT stock_code, MAX(trade_date) AS max_date
                    FROM daily_pe
                    WHERE pe IS NOT NULL AND trade_date <= ?
                    GROUP BY stock_code
                ) p2 ON p1.stock_code = p2.stock_code AND p1.trade_date = p2.max_date
            ) p ON p.stock_code = q.stock_code
            LEFT JOIN (
                SELECT e1.stock_code, e1.profit_yoy
                FROM earnings_quarterly e1
                INNER JOIN (
                    SELECT stock_code, MAX(report_date) AS max_date
                    FROM earnings_quarterly
                    WHERE profit_yoy IS NOT NULL AND profit_yoy > 0
                    GROUP BY stock_code
                ) e2 ON e1.stock_code = e2.stock_code AND e1.report_date = e2.max_date
            ) e ON e.stock_code = q.stock_code
            WHERE q.trade_date=? AND q.model_name='theme_3chain'
        """
        params: list = [td, td]
        if subsector:
            sql += " AND q.subsector=?"
            params.append(subsector)
        sql += " ORDER BY q.subsector, q.percentile_score DESC"

        scores = [dict(r) for r in conn.execute(sql, params).fetchall()]

        # 从 ai_pool_cache 加载多板块归属（悬浮浮窗用）
        try:
            _pool_db = "/root/projects/stock_quan/data/feature_store.db"
            with sqlite3.connect(_pool_db) as _pc:
                _ph = ",".join("?" * min(len(scores), 500))
                if scores and _ph:
                    _codes = list({s["stock_code"] for s in scores})
                    _ph_all = ",".join("?" * len(_codes))
                    _pool_rows = _pc.execute(
                        f"SELECT stock_code, subsector FROM ai_pool_cache "
                        f"WHERE stock_code IN ({_ph_all}) AND subsector LIKE '%,%'",
                        _codes,
                    ).fetchall()
                    _multi_map = {r[0]: r[1] for r in _pool_rows}
                    for s in scores:
                        subs = _multi_map.get(s["stock_code"])
                        if subs:
                            s["subsectors_all"] = [x.strip() for x in subs.split(",")]
        except Exception:
            pass

    # Per-subsector stock counts
    ss_counts: dict[str, int] = {}
    for s in scores:
        ss_counts[s["subsector"]] = ss_counts.get(s["subsector"], 0) + 1

    # Load IC-calibrated weights from training_history.db
    weights_map = _load_theme_weights()

    # Build ordered subsector summary (tech → space → bio)
    # Show ALL configured subsectors (n_stocks=0 for empty ones) so dropdown is always complete.
    ss_meta = _get_subsector_meta()
    chain_order = ["tech", "space", "bio"]
    seen: set[str] = set()
    subsectors_out = []
    for chain_key in chain_order:
        for key, meta in ss_meta.items():
            if meta["chain_key"] == chain_key and key not in seen:
                seen.add(key)
                subsectors_out.append({
                    "key":       key,
                    "name":      meta["name"],
                    "chain":     meta["chain"],
                    "chain_key": meta["chain_key"],
                    "n_stocks":  ss_counts.get(key, 0),
                    "weights":   weights_map.get(key, {}),
                    "valuation_peers": meta.get("valuation_peers"),
                })
    # Any unknown subsectors (in data but not in config) last
    for key, cnt in ss_counts.items():
        if key not in seen:
            subsectors_out.append({
                "key":       key,
                "name":      key,
                "chain":     "其他",
                "chain_key": "other",
                "n_stocks":  cnt,
                "weights":   weights_map.get(key, {}),
            })

    if scores:
        prices = await asyncio.to_thread(_batch_prices, [s["stock_code"] for s in scores])
        scores = _enrich(scores, prices)

    result = {
        "trade_date": td,
        "total":      len(scores),
        "subsectors": subsectors_out,
        "scores":     scores,
    }
    _resp_set(cache_key, result)
    return result


@router.get("/quan/scores/{stock_code}/levels")
async def get_stock_levels(
    stock_code: str,
    current_user: User = Depends(get_current_user),
):
    """Return buy/sell levels, technical indicators, and valuation for one stock.

    Calls qlib subprocess (result cached 1 h) + Tencent API for live price/PE.
    Tencent detail is cached; off-hours it never expires (prices frozen at close).
    """
    now = time.time()
    cached = _levels_cache.get(stock_code)

    detail = await asyncio.to_thread(_fetch_tencent_detail, stock_code)
    actual_price = detail.get("price")

    if cached and now - cached["ts"] < _LEVELS_TTL and actual_price:
        return {**cached["data"], "price": actual_price,
                "change_pct": detail.get("change_pct")}

    if not actual_price:
        return {"error": "无法获取实时价格", "stock_code": stock_code}

    # Three-tier fallback for technical indicator computation:
    #   Tier 1: Precomputed DB (quan_tech_levels) — instant, works on cloud
    #   Tier 2: AKShare real-time price history    — ~3-5s, works on cloud, caches result
    #   Tier 3: qlib subprocess                   — local dev only
    tech = _load_precomputed_levels(stock_code)
    if not tech:
        logger.info("Tech levels not in DB for %s — computing via EastMoney API", stock_code)
        tech = await asyncio.to_thread(_compute_levels_em, stock_code)
    if not tech:
        tech = await asyncio.to_thread(_run_qlib_levels, stock_code)

    if not tech:
        return {"error": "技术指标计算失败，请稍候重试",
                "stock_code": stock_code}

    # Scale qlib backward-adjusted prices → actual market prices
    # NaN values arise for recently-listed stocks (insufficient history for long windows)
    import math as _math

    def _scale(v: float) -> float | None:
        return None if (v is None or _math.isnan(v)) else round(v * scale, 2)

    scale = actual_price / tech["last_adj"]
    ma5   = _scale(tech["ma5"])
    ma20  = _scale(tech["ma20"])
    ma60  = _scale(tech["ma60"])
    ma120 = _scale(tech["ma120"])
    atr14 = _scale(tech["atr14"])
    rsi14 = tech["rsi14"] if tech["rsi14"] is not None else 50.0
    h52w  = _scale(tech["h52w"])
    l52w  = _scale(tech["l52w"])

    fund = _get_fundamentals(stock_code)
    sector_val = _get_sector_valuation(stock_code, detail.get("pe"), detail.get("pb"))

    # Get quant score from DB (try both universes)
    score_data: dict = {}
    with _get_conn() as conn:
        for model in ("factor", "factor_star50"):
            td = _resolve_date(conn, None, model)
            if not td:
                continue
            rows = _fetch_scores(conn, td, model, 0.0, 1, [stock_code])
            if rows:
                score_data = rows[0]
                break

    levels = _derive_levels(
        price=actual_price,
        ma5=ma5, ma20=ma20, ma60=ma60, ma120=ma120,
        atr14=atr14, rsi14=rsi14, h52w=h52w, l52w=l52w,
        pe=detail.get("pe"),
        profit_yoy=fund.get("profit_yoy"),
        label=score_data.get("label", ""),
    )

    data = {
        "stock_code": stock_code,
        "price":      actual_price,
        "change_pct": detail.get("change_pct"),
        "pe":         detail.get("pe"),
        "pb":         detail.get("pb"),
        "mktcap":     detail.get("mktcap"),
        "score": {
            "percentile_score": score_data.get("percentile_score"),
            "label":            score_data.get("label", "—"),
            "sector_warning":   score_data.get("sector_warning", ""),
            "trade_date":       score_data.get("trade_date"),
        },
        "fundamentals": {
            k: (round(v, 2) if isinstance(v, float) else v)
            for k, v in fund.items()
        },
        "sector_valuation": sector_val,
        **levels,
    }

    # Sanitize any stray NaN/Inf values that would break JSON serialization
    import math as _math

    def _clean(obj):
        if isinstance(obj, float):
            return None if (_math.isnan(obj) or _math.isinf(obj)) else obj
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_clean(v) for v in obj]
        return obj

    data = _clean(data)
    _levels_cache[stock_code] = {"data": data, "ts": now}
    return data


# ═══════════════════════════════════════════════════════════════════════════════
# Pipeline trigger & status endpoints
# ═══════════════════════════════════════════════════════════════════════════════

import threading as _threading
from datetime import datetime as _datetime
from fastapi import Body

_PIPELINE_ROOT  = "/root/projects/stock_quan"
_PIPELINE_SCRIPT = f"{_PIPELINE_ROOT}/run_pipeline.sh"
_PIPELINE_LOG   = f"{_PIPELINE_ROOT}/logs/pipeline_latest.log"
_PIPELINE_PYTHON = "/root/qlib/qvenv/bin/python"

# In-process state for the running pipeline (reset on process restart)
_pipeline_state: dict = {
    "status": "idle",       # idle | running | success | error
    "pid":     None,
    "started": None,
    "ended":   None,
    "date":    None,
    "tail":    "",
}
_pipeline_lock = _threading.Lock()


def _run_pipeline_bg(trade_date: str) -> None:
    """Background thread that executes run_pipeline.sh."""
    import shlex
    cmd = ["bash", _PIPELINE_SCRIPT, trade_date]
    log_path = f"{_PIPELINE_ROOT}/logs/pipeline_{trade_date.replace('-','')}.log"
    try:
        with open(log_path, "w") as lf, _pipeline_lock:
            _pipeline_state["status"]  = "running"
            _pipeline_state["started"] = _datetime.now().isoformat()
            _pipeline_state["ended"]   = None
            _pipeline_state["tail"]    = ""

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=_PIPELINE_ROOT, text=True, bufsize=1,
        )
        with _pipeline_lock:
            _pipeline_state["pid"] = proc.pid

        lines: list[str] = []
        with open(log_path, "a") as lf:
            for line in proc.stdout:
                lf.write(line)
                lines.append(line.rstrip())
                if len(lines) > 50:
                    lines.pop(0)

        proc.wait()
        with _pipeline_lock:
            _pipeline_state["status"] = "success" if proc.returncode == 0 else "error"
            _pipeline_state["ended"]  = _datetime.now().isoformat()
            _pipeline_state["tail"]   = "\n".join(lines[-20:])
            _pipeline_state["pid"]    = None
    except Exception as exc:
        with _pipeline_lock:
            _pipeline_state["status"] = "error"
            _pipeline_state["ended"]  = _datetime.now().isoformat()
            _pipeline_state["tail"]   = str(exc)
            _pipeline_state["pid"]    = None


@router.post("/pipeline/trigger")
async def trigger_pipeline(
    trade_date: Optional[str] = Body(None, embed=True),
    current_user: User = Depends(get_current_user),
):
    """Trigger the AI industry chain quantitative training pipeline.

    Runs run_pipeline.sh in a background thread. Returns immediately with
    the current state. Poll /pipeline/status to track progress.
    """
    with _pipeline_lock:
        if _pipeline_state["status"] == "running":
            return {
                "ok": False,
                "message": "Pipeline already running",
                "state": dict(_pipeline_state),
            }

    td = trade_date or _datetime.now().strftime("%Y-%m-%d")
    with _pipeline_lock:
        _pipeline_state["date"]    = td
        _pipeline_state["status"]  = "pending"
        _pipeline_state["started"] = _datetime.now().isoformat()

    t = _threading.Thread(target=_run_pipeline_bg, args=(td,), daemon=True)
    t.start()
    logger.info("Pipeline triggered by %s for date=%s", current_user.username, td)
    return {"ok": True, "message": f"Pipeline started for {td}", "state": dict(_pipeline_state)}


@router.get("/pipeline/status")
async def pipeline_status(current_user: User = Depends(get_current_user)):
    """Return the current pipeline execution state."""
    with _pipeline_lock:
        return dict(_pipeline_state)


@router.get("/pipeline/log")
async def pipeline_log(
    lines: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
):
    """Return the last N lines of the most recent pipeline log file."""
    import glob
    pattern = f"{_PIPELINE_ROOT}/logs/pipeline_*.log"
    logs = sorted(glob.glob(pattern), reverse=True)
    if not logs:
        return {"log": "", "file": None}
    log_file = logs[0]
    try:
        with open(log_file) as f:
            content = f.readlines()
        tail = "".join(content[-lines:])
    except Exception as e:
        tail = str(e)
    return {"log": tail, "file": log_file}


@router.get("/pipeline/pool-stats")
async def pool_stats(current_user: User = Depends(get_current_user)):
    """Return AI industry pool statistics from ai_pool_cache."""
    feature_db = _BASE.get("db", {}).get(
        "feature_store_path",
        "/root/projects/stock_quan/data/feature_store.db",
    )
    try:
        with sqlite3.connect(feature_db) as conn:
            total = conn.execute("SELECT COUNT(*) FROM ai_pool_cache").fetchone()[0]
            by_chain = conn.execute(
                "SELECT chain, COUNT(*) as n FROM ai_pool_cache GROUP BY chain ORDER BY n DESC"
            ).fetchall()
            by_source = conn.execute(
                "SELECT source, COUNT(*) as n FROM ai_pool_cache GROUP BY source ORDER BY n DESC"
            ).fetchall()
        return {
            "total": total,
            "by_chain":  [{"chain": r[0], "n": r[1]} for r in by_chain],
            "by_source": [{"source": r[0], "n": r[1]} for r in by_source],
        }
    except Exception as e:
        return {"total": 0, "by_chain": [], "by_source": [], "error": str(e)}


_precompute_state: dict = {
    "status": "idle",   # idle | running | done | error
    "started": None,
    "ended":   None,
    "total":   0,
    "done":    0,
    "failed":  0,
    "date":    None,
}
_precompute_lock = _threading.Lock()


def _run_precompute_tech_bg(trade_date: str) -> None:
    """Background thread: batch-precompute tech levels for all pool stocks via EM kline."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    try:
        with _get_conn() as conn:
            codes = [r[0] for r in conn.execute(
                "SELECT stock_code FROM quan_stock_info"
            ).fetchall()]
            existing = {r[0] for r in conn.execute(
                "SELECT stock_code FROM quan_tech_levels WHERE trade_date=?", (trade_date,)
            ).fetchall()}
    except Exception as e:
        with _precompute_lock:
            _precompute_state.update({"status": "error", "ended": _datetime.now().isoformat()})
        logger.error("precompute-tech: DB read failed: %s", e)
        return

    pending = [c for c in codes if c not in existing]
    total = len(pending)
    logger.info("precompute-tech: %d stocks pending for %s", total, trade_date)

    with _precompute_lock:
        _precompute_state.update({"total": total, "done": 0, "failed": 0})

    done = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(_compute_levels_em, c): c for c in pending}
        for future in as_completed(futures):
            try:
                result = future.result()
                if result:
                    done += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
            with _precompute_lock:
                _precompute_state["done"]   = done
                _precompute_state["failed"] = failed

    with _precompute_lock:
        _precompute_state.update({
            "status": "done",
            "ended":  _datetime.now().isoformat(),
        })
    logger.info("precompute-tech: done=%d failed=%d for %s", done, failed, trade_date)


@router.post("/pipeline/precompute-tech")
async def trigger_precompute_tech(
    trade_date: Optional[str] = Body(None, embed=True),
    current_user: User = Depends(get_current_user),
):
    """Batch-precompute technical indicators for all pool stocks via EastMoney K-line.

    Runs in a background thread with 10 parallel workers (~3 min for 3000 stocks).
    Returns immediately; poll GET /pipeline/precompute-tech for progress.
    """
    with _precompute_lock:
        if _precompute_state["status"] == "running":
            return {"ok": False, "message": "Already running", "state": dict(_precompute_state)}

    td = trade_date or _datetime.now().strftime("%Y-%m-%d")
    with _precompute_lock:
        _precompute_state.update({
            "status": "running",
            "started": _datetime.now().isoformat(),
            "ended":   None,
            "date":    td,
        })

    t = _threading.Thread(target=_run_precompute_tech_bg, args=(td,), daemon=True)
    t.start()
    logger.info("precompute-tech triggered by %s for %s", current_user.username, td)
    return {"ok": True, "message": f"Precompute started for {td}", "state": dict(_precompute_state)}


@router.get("/pipeline/precompute-tech")
async def precompute_tech_status(current_user: User = Depends(get_current_user)):
    """Return the current batch-precompute progress."""
    with _precompute_lock:
        return dict(_precompute_state)


_EM_ULIST_URL   = "https://push2.eastmoney.com/api/qt/ulist.np/get"
_EM_ULIST_BATCH = 80    # ~720-char secids param — safe for most proxies
_H10_SEM        = 10    # max concurrent H10 requests in fallback


async def _ulist_probe(codes: list[str]) -> dict[str, dict]:
    """Try EM push2 ulist.np for name+industry. Returns {} if the endpoint is down."""
    import httpx
    result: dict[str, dict] = {}
    headers = {"Referer": "https://quote.eastmoney.com/", "User-Agent": "Mozilla/5.0"}
    total_hits = 0

    for i in range(0, len(codes), _EM_ULIST_BATCH):
        batch = codes[i: i + _EM_ULIST_BATCH]
        secids = ",".join(("1" if c.startswith("6") else "0") + "." + c for c in batch)
        items: list[dict] = []
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=12) as cl:
                    resp = await cl.get(
                        _EM_ULIST_URL,
                        params={"fltt": "2", "fields": "f12,f14,f100", "secids": secids},
                        headers=headers,
                    )
                    resp.raise_for_status()
                    items = (resp.json().get("data") or {}).get("diff") or []
                break
            except Exception as e:
                if attempt == 0:
                    await asyncio.sleep(0.8)
                else:
                    logger.debug("ulist batch %d failed: %s", i, e)

        for item in items:
            code = str(item.get("f12", "")).strip()
            if code:
                result[code] = {
                    "name":     str(item.get("f14", "") or "").strip(),
                    "industry": str(item.get("f100", "") or "").strip(),
                }
        total_hits += len(items)
        logger.info("ulist batch %d-%d: %d/%d", i, i + len(batch), len(items), len(batch))

        # If first two batches both return 0, the endpoint is down — bail early
        if i >= _EM_ULIST_BATCH and total_hits == 0:
            logger.warning("ulist endpoint appears down, switching to fallback")
            return {}

        if i + _EM_ULIST_BATCH < len(codes):
            await asyncio.sleep(0.15)

    return result


async def _fallback_sina_names(codes: list[str]) -> dict[str, str]:
    """Batch-fetch stock names from Sina hq API (proven reliable). Returns {code: name}."""
    import httpx, re as _re
    result: dict[str, str] = {}
    headers = {"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"}
    for i in range(0, len(codes), 100):
        batch = codes[i: i + 100]
        syms = ",".join(("sh" if c.startswith("6") else "sz") + c for c in batch)
        try:
            async with httpx.AsyncClient(timeout=10) as cl:
                resp = await cl.get(f"http://hq.sinajs.cn/list={syms}", headers=headers)
                resp.raise_for_status()
            for line in resp.text.strip().split("\n"):
                m = _re.match(r'var hq_str_s[hz](\d+)="([^"]*)"', line)
                if not m:
                    continue
                parts = m.group(2).split(",")
                if parts and parts[0]:
                    result[m.group(1)] = parts[0]
        except Exception as e:
            logger.warning("Sina name fallback error (offset %d): %s", i, e)
    return result


async def _fallback_h10_industry(codes: list[str]) -> dict[str, str]:
    """Per-stock H10 CompanySurvey industry fetch, concurrency-limited to _H10_SEM.

    Only called for stocks not resolved by other means. Caps total requests.
    """
    import httpx
    sem = asyncio.Semaphore(_H10_SEM)
    fields = ["INDUSTRYCSRC1", "INDUSTRYNAME", "EM2016_INDUSTRY_NAME"]

    async def _one(code: str) -> tuple[str, str]:
        prefix = "SH" if code.startswith("6") else "SZ"
        url = (f"https://emweb.securities.eastmoney.com"
               f"/PC_HSF10/CompanySurvey/PageAjax?code={prefix}{code}")
        async with sem:
            try:
                async with httpx.AsyncClient(timeout=8) as cl:
                    resp = await cl.get(url, headers={
                        "Referer": "https://emweb.securities.eastmoney.com",
                        "User-Agent": "Mozilla/5.0",
                    })
                    data = resp.json()
                jbzl = data.get("jbzl") or []
                if jbzl:
                    row = jbzl[0]
                    for f in fields:
                        if row.get(f):
                            return code, row[f]
            except Exception as e:
                logger.debug("H10 industry fetch failed for %s: %s", code, e)
        return code, ""

    results = await asyncio.gather(*[_one(c) for c in codes])
    return {code: ind for code, ind in results if ind}


@router.post("/quan/refresh-stock-info")
async def refresh_stock_info(current_user: User = Depends(get_current_user)):
    """Fill missing stock names + industry.

    Strategy (in order):
    1. EM push2 ulist.np  — one batch call, returns both name + industry.
    2. If ulist is down: Sina batch for names + H10 for industry (theme_3chain only,
       capped at _H10_SEM concurrent requests).
    """
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS quan_stock_info (
                stock_code  TEXT PRIMARY KEY,
                stock_name  TEXT,
                industry    TEXT,
                updated_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        rows = conn.execute("""
            SELECT DISTINCT q.stock_code,
                   q.model_name,
                   COALESCE(NULLIF(i.stock_name,''), w.stock_name, '') AS stock_name,
                   COALESCE(NULLIF(i.industry,''), '')                 AS industry
            FROM quan_daily_scores q
            LEFT JOIN quan_stock_info i ON i.stock_code = q.stock_code
            LEFT JOIN (
                SELECT stock_code, MAX(stock_name) AS stock_name
                FROM watchlist WHERE stock_name IS NOT NULL AND stock_name != ''
                GROUP BY stock_code
            ) w ON w.stock_code = q.stock_code
            WHERE COALESCE(NULLIF(i.stock_name,''), w.stock_name, '') = ''
               OR COALESCE(NULLIF(i.industry,''), '') = ''
        """).fetchall()

    if not rows:
        return {"status": "ok", "updated": 0, "message": "No missing data"}

    codes_to_fetch  = list({r[0] for r in rows})
    theme_codes_set = {r[0] for r in rows if r[1] == "theme_3chain"}
    logger.info("refresh-stock-info: %d stocks with missing data (%d theme_3chain)",
                len(codes_to_fetch), len(theme_codes_set))

    # ── Step 1: try EM push2 ulist (bulk, minimal requests) ──────────────────
    bulk = await _ulist_probe(codes_to_fetch)
    ulist_ok = bool(bulk)

    # ── Step 2: fallback when push2 is down ──────────────────────────────────
    fallback_names:    dict[str, str] = {}
    fallback_industry: dict[str, str] = {}
    if not ulist_ok:
        logger.info("ulist down — using Sina names + H10 industry fallback")
        need_name     = [r[0] for r in rows if not r[2]]
        # For industry: limit to theme_3chain to cap H10 requests
        need_industry = [c for c in codes_to_fetch
                         if not next((r[3] for r in rows if r[0] == c), "")
                         and c in theme_codes_set]
        if need_name:
            fallback_names = await _fallback_sina_names(need_name)
        if need_industry:
            fallback_industry = await _fallback_h10_industry(need_industry)

    # ── Build records ─────────────────────────────────────────────────────────
    local_names = {r[0]: r[2] for r in rows if r[2]}   # already-known local names
    records = []
    for r in rows:
        code = r[0]
        local_name, local_industry = r[2], r[3]
        em = bulk.get(code, {})

        name     = local_name     or em.get("name", "")     or fallback_names.get(code, "")
        industry = local_industry or em.get("industry", "") or fallback_industry.get(code, "")

        if name or industry:
            records.append({"stock_code": code, "stock_name": name, "industry": industry})

    if records:
        with _get_conn() as conn:
            conn.executemany("""
                INSERT INTO quan_stock_info (stock_code, stock_name, industry, updated_at)
                VALUES (:stock_code, :stock_name, :industry, datetime('now'))
                ON CONFLICT(stock_code) DO UPDATE SET
                    stock_name = CASE WHEN excluded.stock_name != '' THEN excluded.stock_name
                                      ELSE quan_stock_info.stock_name END,
                    industry   = CASE WHEN excluded.industry != '' THEN excluded.industry
                                      ELSE quan_stock_info.industry END,
                    updated_at = datetime('now')
            """, records)

    n_names = sum(1 for r in records if r["stock_name"])
    n_inds  = sum(1 for r in records if r["industry"])
    mode = "ulist" if ulist_ok else "fallback(sina+h10)"
    logger.info("refresh-stock-info done: %d updated, %d names, %d industries [%s]",
                len(records), n_names, n_inds, mode)
    return {
        "status": "ok",
        "candidates": len(codes_to_fetch),
        "updated": len(records),
        "names_resolved": n_names,
        "industries_resolved": n_inds,
        "mode": mode,
    }


@router.post("/quan/pe-backfill")
async def trigger_pe_backfill(
    trade_date: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    """Trigger PE backfill from Tencent API for missing values."""
    try:
        from services.valuation_backfill import backfill_pe
        result = backfill_pe(trade_date)
        return result
    except Exception as e:
        return {"status": "error", "error": str(e)}

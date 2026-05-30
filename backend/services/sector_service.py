"""Sector (板块) data service — fetches board data from EastMoney public APIs.

Data sources (all accessible via current network):
  1. sidemenu_new.json — static JSON with all 1014 BK codes + names
  2. push2ex getAllBKChanges — realtime change% and fund-flow for all boards
  3. push2his kline API — full OHLCV (rate-limited; used when available)
"""
import re
import os
import json
import time
import asyncio
import logging
from typing import Optional, Dict, Any, List

import httpx

logger = logging.getLogger(__name__)

from services.stock_service import _akshare_sem

# ── Cache ──
_cache: Dict[str, tuple] = {}
CACHE_TTL = 30           # realtime quote cache (seconds)
CACHE_TTL_NAMES = 86400  # board name list (24 h — sidemenu is semi-static)
CACHE_TTL_CHANGES = 30   # getAllBKChanges (one batch covers all sectors)


def _get_cached(key: str):
    if key in _cache:
        val, ts, ttl = _cache[key]
        if time.time() - ts < ttl:
            return val
        del _cache[key]
    return None


def _set_cache(key: str, val, ttl: int = None):
    if ttl is None:
        ttl = CACHE_TTL
    _cache[key] = (val, time.time(), ttl)
    if len(_cache) > 500:
        oldest = min(_cache.keys(), key=lambda k: _cache[k][1])
        del _cache[oldest]


# ── Persistent user-overridden names ──
_NAMES_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'bk_names.json')
_custom_names: Dict[str, str] = {}


def _load_custom_names() -> None:
    global _custom_names
    try:
        if os.path.exists(_NAMES_FILE):
            with open(_NAMES_FILE, 'r', encoding='utf-8') as f:
                _custom_names = json.load(f)
    except Exception as e:
        logger.warning(f'Failed to load bk_names.json: {e}')
        _custom_names = {}


def _save_custom_names() -> None:
    try:
        os.makedirs(os.path.dirname(_NAMES_FILE), exist_ok=True)
        with open(_NAMES_FILE, 'w', encoding='utf-8') as f:
            json.dump(_custom_names, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f'Failed to save bk_names.json: {e}')


def save_board_name(code: str, name: str) -> None:
    """Persist a user-provided BK board name."""
    code = code.upper()
    if not name or name == code or name == f'板块{code}':
        return
    _custom_names[code] = name
    _save_custom_names()
    _cache.pop(f'sector:{code}', None)


_load_custom_names()

# 防止并发请求竞态：多个 asyncio task 同时 cache miss 时只发一次 HTTP 请求
_board_map_lock = asyncio.Lock()
_bk_changes_lock = asyncio.Lock()


# ── Board code patterns ──
RE_BOARD_CODE = re.compile(r'^BK\d{4}$', re.IGNORECASE)
RE_SINA_BOARD = re.compile(r'^(sh|sz)880\d{3}$', re.IGNORECASE)


def is_board_code(code: str) -> bool:
    return bool(RE_BOARD_CODE.match(code) or RE_SINA_BOARD.match(code))


def is_industry_board_code(code: str) -> bool:
    return bool(RE_BOARD_CODE.match(code))


# ── HTTP helpers ──

_HEADERS_EM = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/",
}

def _make_client(timeout: float = 8) -> httpx.AsyncClient:
    """Create an httpx client.  EastMoney domains bypass the local proxy."""
    return httpx.AsyncClient(
        timeout=timeout,
        mounts={
            "https://push2.eastmoney.com": None,
            "https://push2delay.eastmoney.com": None,
            "https://push2his.eastmoney.com": None,
            "https://push2ex.eastmoney.com": None,
            "https://quote.eastmoney.com": None,
        },
    )


# ── Source 1: sidemenu_new.json (all BK names) ──

async def _load_board_map() -> Dict[str, Dict]:
    """Fetch all board names from EastMoney's sidemenu JSON.

    Returns {BK_CODE: {"name": ..., "type": "industry"|"concept"|"region"}}
    Cached 24 h. Very fast (static JSON, ~50 KB).
    """
    cache_key = "board_map:sidemenu"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    async with _board_map_lock:
        cached = _get_cached(cache_key)
        if cached is not None:
            return cached

        result: Dict[str, Dict] = {}
        try:
            async with _make_client(timeout=6) as client:
                resp = await client.get(
                    "https://quote.eastmoney.com/center/api/sidemenu_new.json",
                    headers=_HEADERS_EM,
                )
                resp.raise_for_status()
                data = resp.json()

            type_map = {1: "region", 2: "industry", 3: "concept"}
            for entry in data.get("bklist", []):
                code = entry.get("code", "").upper()
                name = entry.get("name", "")
                btype = type_map.get(entry.get("type", 3), "concept")
                if code and name:
                    result[code] = {"name": name, "type": btype}

            logger.info(f"board_map: loaded {len(result)} boards from sidemenu_new.json")
        except Exception as e:
            logger.warning(f"sidemenu_new.json fetch failed: {e}")

        ttl = CACHE_TTL_NAMES if result else 60
        _set_cache(cache_key, result, ttl)
        return result


# ── Source 2: push2ex getAllBKChanges (realtime change% + fund flow) ──

async def _fetch_all_bk_changes() -> Dict[str, Dict]:
    """Fetch realtime change% and fund-flow for ALL boards from push2ex.

    Returns {BK_CODE: {"change_pct": float, "fund_flow": float, "name": str}}
    Cached 30 s. One API call covers all boards.
    """
    cache_key = "bk_changes:all"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    async with _bk_changes_lock:
        cached = _get_cached(cache_key)
        if cached is not None:
            return cached

        result: Dict[str, Dict] = {}
        try:
            async with _make_client(timeout=8) as client:
                resp = await client.get(
                    "https://push2ex.eastmoney.com/getAllBKChanges",
                    params={
                        "ut": "7eea3edcaed734bea9cbfc24409ed989",
                        "dpt": "wzchanges",
                        "pageindex": "0",
                        "pagesize": "5000",
                    },
                    headers=_HEADERS_EM,
                )
                resp.raise_for_status()
                data = resp.json()

            for entry in data.get("data", {}).get("allbk", []):
                code = entry.get("c", "").upper()
                if code:
                    raw_flow = _float(entry.get("zjl"))
                    result[code] = {
                        "name": entry.get("n", ""),
                        "change_pct": _float(entry.get("u")),
                        "fund_flow": raw_flow * 10000 if raw_flow is not None else None,  # zjl is 万元, convert to 元
                    }
            logger.info(f"bk_changes: loaded {len(result)} boards from push2ex")
        except Exception as e:
            logger.warning(f"getAllBKChanges fetch failed: {e}")

        ttl = CACHE_TTL_CHANGES if result else 10
        _set_cache(cache_key, result, ttl)
        return result


# ── Source 3: push2his kline (OHLCV — rate-limited) ──

async def _fetch_board_via_push2his(code: str) -> Optional[Dict[str, Any]]:
    """Fetch board daily OHLCV from push2his kline API.

    Kline fields: date,open,close,high,low,volume,amount,amplitude,change_pct,change,turnover_rate
    Returns None if blocked or rate-limited (server drops connection silently).
    Uses a short timeout so the fallback path (getAllBKChanges) is not delayed.
    """
    # Skip if known-unavailable (cached failure)
    if _get_cached(f"push2his_fail:{code}"):
        return None
    try:
        async with _make_client(timeout=3) as client:
            resp = await client.get(
                "https://push2his.eastmoney.com/api/qt/stock/kline/get",
                params={
                    "secid": f"90.{code.upper()}",
                    "klt": "101",
                    "fqt": "0",
                    "lmt": "1",
                    "end": "20500101",
                    "iscca": "1",
                    "fields1": "f1,f2,f3,f4,f5,f6",
                    "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                },
                headers=_HEADERS_EM,
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("rc") != 0 or not data.get("data"):
            return None

        board = data["data"]
        klines = board.get("klines", [])
        out: Dict[str, Any] = {"name": board.get("name", "")}

        if klines:
            parts = klines[-1].split(",")
            if len(parts) >= 11:
                out["open"]         = _float(parts[1])
                out["price"]        = _float(parts[2])
                out["high"]         = _float(parts[3])
                out["low"]          = _float(parts[4])
                out["volume"]       = _float(parts[5])
                out["amount"]       = _float(parts[6])
                out["amplitude"]    = _float(parts[7])
                out["change_pct"]   = _float(parts[8])
                out["change"]       = _float(parts[9])
                out["turnover_rate"]= _float(parts[10])
                out["prev_close"]   = _float(board.get("preKPrice"))

        return out

    except Exception as e:
        logger.debug(f"push2his fetch error for {code}: {e}")
        # Cache failure for 5 min so we don't keep retrying a blocked endpoint
        _set_cache(f"push2his_fail:{code}", True, 300)
        return None


# ── Main fetch entry point ──

async def fetch_sector_realtime(code: str) -> dict:
    """Fetch realtime data for a single BK board.

    Strategy:
      1. push2his kline  → full OHLCV (best, but rate-limited)
      2. sidemenu + getAllBKChanges → name + change% + fund flow (always works)
    """
    cache_key = f"sector:{code}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    code_up = code.upper()
    saved_name = _custom_names.get(code_up, "")

    base: Dict[str, Any] = {
        "code": code,
        "market": "SECTOR",
        "stock_name": saved_name or code_up,
        "item_type": "sector",
        "board_type": "concept",
        "pe": None,
        "market_cap": None,
        "float_market_cap": None,
        "up_count": None,
        "down_count": None,
    }

    # Run push2his and getAllBKChanges concurrently
    push2his_task = asyncio.create_task(_fetch_board_via_push2his(code_up))
    changes_task  = asyncio.create_task(_fetch_all_bk_changes())

    push2his_data, changes_map = await asyncio.gather(
        push2his_task, changes_task, return_exceptions=True
    )
    if isinstance(push2his_data, Exception):
        push2his_data = None
    if isinstance(changes_map, Exception):
        changes_map = {}

    # ── Determine board name ──
    # Priority: user override > push2his name > getAllBKChanges name > sidemenu name
    api_name = ""
    if isinstance(push2his_data, dict):
        api_name = push2his_data.get("name", "")
    if not api_name and isinstance(changes_map, dict):
        api_name = changes_map.get(code_up, {}).get("name", "")

    if not api_name:
        board_map = await _load_board_map()
        api_name = board_map.get(code_up, {}).get("name", "")

    display_name = saved_name or api_name or code_up
    base["stock_name"] = display_name

    # Persist the API name for future lookups (don't overwrite user overrides)
    if api_name and not saved_name and _custom_names.get(code_up) != api_name:
        _custom_names[code_up] = api_name
        _save_custom_names()

    # ── Market data: prefer push2his (full OHLCV) ──
    if isinstance(push2his_data, dict) and push2his_data.get("price") is not None:
        base.update({
            "price":        push2his_data.get("price"),
            "change":       push2his_data.get("change"),
            "change_pct":   push2his_data.get("change_pct"),
            "open":         push2his_data.get("open"),
            "high":         push2his_data.get("high"),
            "low":          push2his_data.get("low"),
            "volume":       push2his_data.get("volume"),
            "amount":       push2his_data.get("amount"),
            "turnover_rate":push2his_data.get("turnover_rate"),
            "amplitude":    push2his_data.get("amplitude"),
            "prev_close":   push2his_data.get("prev_close"),
        })
        _set_cache(cache_key, base, CACHE_TTL)
        return base

    # ── Fallback: getAllBKChanges (change% only) ──
    if isinstance(changes_map, dict):
        entry = changes_map.get(code_up, {})
        if entry.get("change_pct") is not None:
            base["change_pct"] = entry["change_pct"]

    _set_cache(cache_key, base, CACHE_TTL_CHANGES)
    return base


# ── Board search & name lookup ──

async def search_board(keyword: str) -> list:
    """Search boards by keyword (code or partial name). Returns [{code, name, ...}]."""
    if not keyword or not keyword.strip():
        return []
    kw_raw = keyword.strip()
    kw_upper = kw_raw.upper()

    board_map = await _load_board_map()
    results = []
    for code, info in board_map.items():
        name = info["name"]
        # Match by code (case-insensitive) or by Chinese name substring
        if kw_upper in code or kw_raw in name or kw_upper in name.upper():
            results.append({
                "code": code,
                "market": "SECTOR",
                "name": name,
                "type": info["type"],
                "item_type": "sector",
            })
    return results[:20]


async def lookup_board_name(code: str) -> str:
    """Return the display name for a BK code, empty string if unknown."""
    code = code.upper()
    if code in _custom_names:
        return _custom_names[code]

    board_map = await _load_board_map()
    name = board_map.get(code, {}).get("name", "")
    if name:
        _custom_names[code] = name
        _save_custom_names()
    return name


async def get_sector_congestion_data() -> list:
    """Return real-time metrics for all sectors in bk_names.json.

    Uses getAllBKChanges (fast batch) as primary source, supplements with
    any cached push2his data already in memory from prior refresh calls.
    """
    changes = await _fetch_all_bk_changes()

    result = []
    for code, name in _custom_names.items():
        code_up = code.upper()
        ce = changes.get(code_up, {})

        # Pull richer data from push2his cache if it's already there
        cached = _get_cached(f"sector:{code_up}") or {}

        result.append({
            "code": code_up,
            "name": name,
            "change_pct": ce.get("change_pct"),
            "fund_flow": ce.get("fund_flow"),
            "turnover_rate": cached.get("turnover_rate"),
            "amplitude": cached.get("amplitude"),
            "price": cached.get("price"),
        })

    # Sort: sectors with data first, descending change_pct
    result.sort(key=lambda x: (x["change_pct"] is None, -(x["change_pct"] or 0)))
    return result


async def fetch_sector_top5(code: str) -> list:
    """Return top-5 constituents of a sector by total market cap.

    Calls EastMoney clist API (fltt=2, sorted by f20 desc), then fetches
    financial snapshots for PEG / profit_growth_rate.
    Cached 60 s.
    """
    code_up = code.upper()
    cache_key = f"sector_top5:{code_up}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    url = "https://push2delay.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1", "pz": "10", "po": "1", "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2", "invt": "2", "fid": "f20",
        "fs": f"b:{code_up}",
        "fields": "f2,f3,f9,f12,f13,f14,f20",
    }

    try:
        async with _make_client(timeout=8) as client:
            resp = await client.get(url, params=params, headers=_HEADERS_EM)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning(f"sector_top5 fetch error {code}: {e}")
        return []

    diff = (data.get("data") or {}).get("diff") or []
    result = []
    for rank, item in enumerate(diff, 1):
        raw_code = str(item.get("f12", "")).zfill(6)
        price = _float(item.get("f2"))
        change_pct = _float(item.get("f3"))
        # Skip stocks with no price or no change — suspended / delisted / no data
        if price is None or change_pct is None:
            continue
        pe = _float(item.get("f9"))
        if pe is not None and pe < 0:
            pe = None  # loss-making — suppress display
        result.append({
            "rank": rank,
            "code": raw_code,
            "market": "A",
            "name": item.get("f14", ""),
            "price": price,
            "change_pct": change_pct,
            "pe": pe,
            "market_cap": _float(item.get("f20")),  # yuan
            "peg": None,
            "profit_growth_rate": None,
        })

    if result:
        from services.stock_service import fetch_financial_snapshot, compute_peg
        snap_tasks = [fetch_financial_snapshot(r["code"], "A") for r in result]
        try:
            snaps = await asyncio.wait_for(
                asyncio.gather(*snap_tasks, return_exceptions=True), timeout=10
            )
            for r, snap in zip(result, snaps):
                if isinstance(snap, dict):
                    growth = snap.get("profit_growth_rate")
                    r["profit_growth_rate"] = growth
                    r["peg"] = compute_peg(r["pe"], growth)
        except asyncio.TimeoutError:
            pass

    _set_cache(cache_key, result, 60)
    return result


async def fetch_sector_top5_by_change(code: str) -> list:
    """Return top-5 constituents of a sector by change% (涨幅).

    Calls EastMoney clist API (fltt=2, sorted by f3 desc).
    Simpler variant — no PEG computation.
    Cached 60 s.
    """
    code_up = code.upper()
    cache_key = f"sector_top5_change:{code_up}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    url = "https://push2delay.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1", "pz": "10", "po": "1", "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2", "invt": "2", "fid": "f3",
        "fs": f"b:{code_up}",
        "fields": "f2,f3,f12,f13,f14,f20",
    }

    try:
        async with _make_client(timeout=8) as client:
            resp = await client.get(url, params=params, headers=_HEADERS_EM)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning(f"sector_top5_by_change fetch error {code}: {e}")
        return []

    diff = (data.get("data") or {}).get("diff") or []
    result = []
    for rank, item in enumerate(diff, 1):
        raw_code = str(item.get("f12", "")).zfill(6)
        price = _float(item.get("f2"))
        change_pct = _float(item.get("f3"))
        # Skip stocks with no price or no change — they are suspended / delisted / no data
        if price is None or change_pct is None:
            continue
        result.append({
            "rank": rank,
            "code": raw_code,
            "market": item.get("f13", "A"),
            "name": item.get("f14", ""),
            "price": price,
            "change_pct": change_pct,
            "market_cap": _float(item.get("f20")),
        })

    _set_cache(cache_key, result, 60)
    return result


# ── Helpers ──

def _float(v):
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


# ── Top-N queries backed by getAllBKChanges ──


async def fetch_sector_fund_flow_top10() -> list:
    """Return top-10 boards sorted by fund_flow (主力净流入) descending.

    Uses the batched getAllBKChanges endpoint (fast, single API call).
    Only BK-format industry boards are included.
    """
    changes = await _fetch_all_bk_changes()
    entries = []
    for code, info in changes.items():
        if is_industry_board_code(code) and info.get("fund_flow") is not None:
            entries.append({
                "code": code,
                "name": info.get("name", ""),
                "change_pct": info.get("change_pct"),
                "fund_flow": info.get("fund_flow"),
            })
    entries.sort(key=lambda x: x["fund_flow"], reverse=True)
    return entries[:10]


async def fetch_heatmap_data() -> list:
    """Return top-100 boards with change_pct and fund_flow for heatmap rendering.

    Uses the batched getAllBKChanges endpoint.  Sorted by descending
    absolute fund_flow so the most active boards appear first.
    Only BK-format industry boards are included.
    """
    changes = await _fetch_all_bk_changes()
    entries = []
    for code, info in changes.items():
        if is_industry_board_code(code):
            entries.append({
                "code": code,
                "name": info.get("name", ""),
                "change_pct": info.get("change_pct"),
                "fund_flow": info.get("fund_flow"),
            })
    # Sort by |fund_flow| descending — most active boards first
    entries.sort(key=lambda x: abs(x["fund_flow"]) if x["fund_flow"] is not None else 0, reverse=True)
    return entries[:100]

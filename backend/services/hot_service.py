"""Hot stocks service — Xueqiu hot list + EastMoney popularity ranking.

Xueqiu   (stock.xueqiu.com): GET with auto-refreshed anonymous xq_a_token.
EastMoney (emappdata.eastmoney.com): POST to get rank list, then GET prices
          via push2delay.eastmoney.com (proxy-safe).
Both results are cached 5 minutes in-process.
"""
from __future__ import annotations

import asyncio
import logging
import time

import httpx

logger = logging.getLogger(__name__)

# ── In-process cache ──────────────────────────────────────────────────────────
_cache: dict[str, tuple] = {}
_CACHE_TTL = 300  # 5 minutes


def _get_cached(key: str):
    if key in _cache:
        val, ts = _cache[key]
        if time.time() - ts < _CACHE_TTL:
            return val
        del _cache[key]
    return None


def _set_cached(key: str, val) -> None:
    _cache[key] = (val, time.time())


_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


# ── Xueqiu ────────────────────────────────────────────────────────────────────
# Confirmed endpoint: stock.xueqiu.com/v5/stock/hot_stock/list.json
# Response: {data: {items: [{symbol, name, value, percent, rank_change, ...}]}}
# symbol format: "SZ002975" / "SH600519" / "09926" (HK bare)
# value  = hot score (higher = hotter)
# percent = price change % (e.g. 7.46 means +7.46%)

_xq_token: str | None = None
_xq_lock = asyncio.Lock()

_XQ_HEADERS = {"User-Agent": _UA, "Referer": "https://xueqiu.com/"}


async def _refresh_xq_token() -> str:
    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as c:
        r = await c.get("https://xueqiu.com/", headers=_XQ_HEADERS)
    token = r.cookies.get("xq_a_token")
    if not token:
        raise RuntimeError("xq_a_token not in Xueqiu response")
    logger.info("Xueqiu token refreshed")
    return token


async def _get_xq_token() -> str:
    global _xq_token
    async with _xq_lock:
        if not _xq_token:
            _xq_token = await _refresh_xq_token()
        return _xq_token


def _strip_prefix(symbol: str) -> tuple[str, str]:
    """Return (code, market).  SZ002975 → ('002975','A')  09926 → ('09926','HK')"""
    for pfx in ("SH", "SZ", "BJ"):
        if symbol.upper().startswith(pfx):
            return symbol[2:], "A"
    # HK stocks have no prefix; typically 5-digit
    return symbol, "HK"


async def fetch_xueqiu_hot(type_: int = 10) -> list[dict]:
    """Xueqiu hot stocks.  type_: 10=近1小时  11=近24小时  12=近5天"""
    cache_key = f"xq:{type_}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    global _xq_token
    for attempt in range(2):
        try:
            token = await _get_xq_token()
            async with httpx.AsyncClient(timeout=12, follow_redirects=True) as c:
                r = await c.get(
                    "https://stock.xueqiu.com/v5/stock/hot_stock/list.json",
                    params={"size": 20, "type": type_, "_type": type_},
                    headers={**_XQ_HEADERS, "Cookie": f"xq_a_token={token}"},
                )
            if r.status_code in (400, 401, 403):
                logger.warning("Xueqiu HTTP %d — refreshing token", r.status_code)
                async with _xq_lock:
                    _xq_token = await _refresh_xq_token()
                continue

            items: list = (r.json().get("data") or {}).get("items") or []
            result = []
            for i, it in enumerate(items[:20]):
                sym: str = str(it.get("symbol") or "")
                code, market = _strip_prefix(sym)
                pct = it.get("percent")
                hot = it.get("value")
                result.append({
                    "rank":         i + 1,
                    "code":         code,
                    "market":       market,
                    "name":         str(it.get("name") or ""),
                    "percent":      round(float(pct), 2) if pct is not None else None,
                    "hot":          int(hot) if hot is not None else None,
                    "rank_change":  int(it.get("rank_change") or 0),
                })
            if result:
                _set_cached(cache_key, result)
            return result

        except Exception as exc:
            logger.warning("Xueqiu attempt %d: %s", attempt + 1, exc)
            async with _xq_lock:
                _xq_token = None

    return []


# ── EastMoney ─────────────────────────────────────────────────────────────────
# Step 1: POST emappdata.eastmoney.com/stockrank/getAllCurrentList
#   → [{sc: "SH600011", rk: 1, rc: 0, hisRc: 0}, ...]
#   sc = stock code with SH/SZ prefix
#   rk = current rank   rc = rank change (0/+/-N)
#
# Step 2: GET push2delay.eastmoney.com/api/qt/ulist.np/get
#   fields: f2=price  f3=change_pct  f12=code  f14=name

_EM_HEADERS = {"User-Agent": _UA, "Referer": "https://guba.eastmoney.com/rank/"}
# Disable proxy so push2delay is always reachable (local dev has proxy on push2)
_EM_TRANSPORT = httpx.AsyncHTTPTransport(proxy=None)

_EM_RANK_URL   = "https://emappdata.eastmoney.com/stockrank/getAllCurrentList"
_EM_PRICE_URL  = "https://push2delay.eastmoney.com/api/qt/ulist.np/get"
_EM_RANK_BODY  = {
    "appId": "appId01",
    "globalId": "786e4c21-70dc-435a-93bb-38",
    "marketType": "",
    "pageNo": 1,
    "pageSize": 20,
}


def _sc_to_secid(sc: str) -> str:
    """SH600011 → 1.600011,  SZ002975 → 0.002975"""
    if sc.upper().startswith("SH"):
        return "1." + sc[2:]
    return "0." + sc[2:]


def _rank_delta_icon(rc) -> str:
    try:
        v = int(rc)
    except (TypeError, ValueError):
        return "—"
    return "↑" if v > 0 else ("↓" if v < 0 else "—")


async def fetch_em_hot() -> list[dict]:
    """EastMoney popularity ranking top 20."""
    cache_key = "em:hot"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        async with httpx.AsyncClient(
            timeout=12, follow_redirects=True, transport=_EM_TRANSPORT
        ) as c:
            # Step 1 — rank list
            r1 = await c.post(_EM_RANK_URL, json=_EM_RANK_BODY, headers=_EM_HEADERS)
            rank_items: list = r1.json().get("data") or []
            if not rank_items:
                return []

            # Build secid list for price fetch
            secids = [_sc_to_secid(it["sc"]) for it in rank_items if it.get("sc")]
            rank_map = {it["sc"][2:]: it for it in rank_items}  # code → rank row

            # Step 2 — real-time prices
            r2 = await c.get(
                _EM_PRICE_URL,
                params={
                    "ut": "f057cbcbce2a86e2866ab8877db1d059",
                    "fltt": "2",
                    "invt": "2",
                    "fields": "f14,f3,f12,f2",
                    "secids": ",".join(secids),
                },
                headers=_EM_HEADERS,
            )
            price_rows: list = (r2.json().get("data") or {}).get("diff") or []
            price_map = {str(row.get("f12")): row for row in price_rows}

        result = []
        for rank_row in rank_items:
            sc: str = rank_row.get("sc") or ""
            code = sc[2:] if sc[2:].isdigit() or len(sc) > 2 else sc
            rk = int(rank_row.get("rk") or 0)
            rc = rank_row.get("rc", 0)
            pr = price_map.get(code, {})
            pct = pr.get("f3")
            result.append({
                "rank":        rk,
                "code":        code,
                "market":      "A",
                "name":        str(pr.get("f14") or ""),
                "percent":     round(float(pct), 2) if pct is not None else None,
                "rank_delta":  _rank_delta_icon(rc),
            })
        result.sort(key=lambda x: x["rank"])

        if result:
            _set_cached(cache_key, result)
        return result

    except Exception as exc:
        logger.warning("EastMoney hot fetch failed: %s", exc)
        return []

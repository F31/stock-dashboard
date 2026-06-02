"""Hot stocks service — Xueqiu hot list + EastMoney popularity ranking.

Resilience strategy:
  - Two-layer cache: fresh (5 min TTL) + stale (persists forever, updated on success).
  - On fresh-fetch failure, return stale data so users always see something.
  - Exponential back-off per source (5 → 15 → 30 → 60 min) to avoid hammering
    rate-limited / blocked endpoints.
  - Xueqiu token is NOT discarded on network errors — only on explicit auth errors
    (HTTP 400/401/403) so a single timeout doesn't force an extra homepage hit.
"""
from __future__ import annotations

import asyncio
import logging
import time

import httpx

logger = logging.getLogger(__name__)

# ── Cache ─────────────────────────────────────────────────────────────────────
_CACHE_TTL = 300          # fresh cache: 5 minutes
_fresh: dict[str, tuple]  = {}   # key → (val, ts)
_stale: dict[str, list]   = {}   # key → val  (no expiry, replaced on success)


def _get_fresh(key: str):
    if key in _fresh:
        val, ts = _fresh[key]
        if time.time() - ts < _CACHE_TTL:
            return val
        del _fresh[key]
    return None


def _set_fresh(key: str, val: list) -> None:
    _fresh[key] = (val, time.time())


def _get_stale(key: str) -> list | None:
    return _stale.get(key)


def _set_stale(key: str, val: list) -> None:
    _stale[key] = val


def _on_success(key: str, val: list) -> None:
    """Call after a successful fetch — updates both caches, resets backoff."""
    _set_fresh(key, val)
    _set_stale(key, val)
    _failures.pop(key, None)
    _last_fail.pop(key, None)


# ── Exponential back-off ──────────────────────────────────────────────────────
# Backoff schedule in seconds: 5 min → 15 min → 30 min → 60 min
_BACKOFF = [300, 900, 1800, 3600]
_failures: dict[str, int]   = {}   # key → consecutive failure count
_last_fail: dict[str, float] = {}  # key → timestamp of last failure


def _backoff_secs(key: str) -> int:
    n = min(_failures.get(key, 0), len(_BACKOFF) - 1)
    return _BACKOFF[n]


def _is_backed_off(key: str) -> bool:
    if key not in _last_fail:
        return False
    return time.time() - _last_fail[key] < _backoff_secs(key)


def _on_failure(key: str) -> None:
    _failures[key] = _failures.get(key, 0) + 1
    _last_fail[key] = time.time()
    logger.warning(
        "hot_service: %s failed (consecutive=%d), back-off=%ds",
        key, _failures[key], _backoff_secs(key),
    )


# ── Common ────────────────────────────────────────────────────────────────────
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _result(items: list, stale: bool = False) -> dict:
    """Wrap a list into the standard response shape."""
    return {"items": items, "stale": stale}


# ── Xueqiu ────────────────────────────────────────────────────────────────────
_xq_token: str | None = None
_xq_token_ts: float = 0.0
_XQ_TOKEN_MAX_AGE = 21600          # proactive refresh after 6 h
_xq_lock = asyncio.Lock()

# Xueqiu has Alibaba Cloud WAF (acw_tc challenge).
# Single GET to homepage only returns acw_tc; a second GET to /hq
# resolves the JS challenge and yields xq_a_token.
_XQ_BROWSER_HEADERS = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}
_XQ_API_HEADERS = {"User-Agent": _UA, "Referer": "https://xueqiu.com/"}


async def _refresh_xq_token() -> str:
    """Two-request flow to bypass Xueqiu's WAF cookie challenge.

    1st GET  → xueqiu.com/    → sets acw_tc (WAF probe cookie)
    2nd GET  → xueqiu.com/hq  → resolves challenge → sets xq_a_token
    """
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
        await c.get("https://xueqiu.com/", headers=_XQ_BROWSER_HEADERS)
        await c.get("https://xueqiu.com/hq",  headers=_XQ_BROWSER_HEADERS)
        token = c.cookies.get("xq_a_token")
    if not token:
        raise RuntimeError("xq_a_token not found after two-request WAF bypass")
    logger.info("Xueqiu token refreshed (two-request WAF bypass)")
    return token


async def _get_xq_token() -> str:
    global _xq_token, _xq_token_ts
    async with _xq_lock:
        if not _xq_token or time.time() - _xq_token_ts > _XQ_TOKEN_MAX_AGE:
            _xq_token = await _refresh_xq_token()
            _xq_token_ts = time.time()
        return _xq_token


async def _invalidate_xq_token() -> None:
    global _xq_token, _xq_token_ts
    async with _xq_lock:
        _xq_token = None
        _xq_token_ts = 0.0


def _strip_prefix(symbol: str) -> tuple[str, str]:
    for pfx in ("SH", "SZ", "BJ"):
        if symbol.upper().startswith(pfx):
            return symbol[2:], "A"
    return symbol, "HK"


async def fetch_xueqiu_hot(type_: int = 10) -> dict:
    """Return {'items': [...], 'stale': bool}.

    Fresh data preferred; stale data returned on failure; empty only on first-ever failure.
    """
    cache_key = f"xq:{type_}"

    fresh = _get_fresh(cache_key)
    if fresh is not None:
        return _result(fresh)

    # Back-off: don't hammer a blocked endpoint
    if _is_backed_off(cache_key):
        stale = _get_stale(cache_key)
        logger.debug("xq:%d backed off (%.0fs remaining), returning stale=%s",
                     type_, _backoff_secs(cache_key) - (time.time() - _last_fail[cache_key]),
                     stale is not None)
        return _result(stale or [], stale=stale is not None)

    global _xq_token
    for attempt in range(2):
        try:
            token = await _get_xq_token()
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
                c.cookies.set("xq_a_token", token, domain="xueqiu.com")
                r = await c.get(
                    "https://stock.xueqiu.com/v5/stock/hot_stock/list.json",
                    params={"size": 20, "type": type_, "_type": type_},
                    headers=_XQ_API_HEADERS,
                )

            # Auth error → invalidate token and retry once
            if r.status_code in (400, 401, 403):
                logger.warning("Xueqiu HTTP %d on attempt %d — invalidating token",
                               r.status_code, attempt + 1)
                await _invalidate_xq_token()
                if attempt == 0:
                    continue
                # Second auth failure → treat as blocked
                _on_failure(cache_key)
                break

            if r.status_code != 200:
                logger.warning("Xueqiu HTTP %d — treating as failure", r.status_code)
                _on_failure(cache_key)
                break

            items: list = (r.json().get("data") or {}).get("items") or []
            result = []
            for i, it in enumerate(items[:20]):
                sym: str = str(it.get("symbol") or "")
                code, market = _strip_prefix(sym)
                pct = it.get("percent")
                hot = it.get("value")
                result.append({
                    "rank":        i + 1,
                    "code":        code,
                    "market":      market,
                    "name":        str(it.get("name") or ""),
                    "percent":     round(float(pct), 2) if pct is not None else None,
                    "hot":         int(hot) if hot is not None else None,
                    "rank_change": int(it.get("rank_change") or 0),
                })

            if result:
                _on_success(cache_key, result)
                return _result(result)

            # Empty list — could be off-market hours, treat as soft failure
            _on_failure(cache_key)
            break

        except Exception as exc:
            logger.warning("Xueqiu attempt %d failed: %s", attempt + 1, exc)
            # Don't invalidate token on network errors (timeout, connect refused)
            if attempt == 1:
                _on_failure(cache_key)

    # All attempts failed — return stale data if available
    stale = _get_stale(cache_key)
    return _result(stale or [], stale=stale is not None)


# ── EastMoney ─────────────────────────────────────────────────────────────────
_EM_HEADERS = {"User-Agent": _UA, "Referer": "https://guba.eastmoney.com/rank/"}
_EM_TRANSPORT = httpx.AsyncHTTPTransport(proxy=None)   # bypass local dev proxy

_EM_RANK_URL  = "https://emappdata.eastmoney.com/stockrank/getAllCurrentList"
_EM_PRICE_URL = "https://push2delay.eastmoney.com/api/qt/ulist.np/get"
_EM_RANK_BODY = {
    "appId": "appId01",
    "globalId": "786e4c21-70dc-435a-93bb-38",
    "marketType": "",
    "pageNo": 1,
    "pageSize": 20,
}


def _sc_to_secid(sc: str) -> str:
    if sc.upper().startswith("SH"):
        return "1." + sc[2:]
    return "0." + sc[2:]


def _rank_delta_icon(rc) -> str:
    try:
        v = int(rc)
    except (TypeError, ValueError):
        return "—"
    return "↑" if v > 0 else ("↓" if v < 0 else "—")


async def fetch_em_hot() -> dict:
    """Return {'items': [...], 'stale': bool}."""
    cache_key = "em:hot"

    fresh = _get_fresh(cache_key)
    if fresh is not None:
        return _result(fresh)

    if _is_backed_off(cache_key):
        stale = _get_stale(cache_key)
        logger.debug("em:hot backed off, returning stale=%s", stale is not None)
        return _result(stale or [], stale=stale is not None)

    try:
        async with httpx.AsyncClient(
            timeout=15, follow_redirects=True, transport=_EM_TRANSPORT
        ) as c:
            r1 = await c.post(_EM_RANK_URL, json=_EM_RANK_BODY, headers=_EM_HEADERS)

            if r1.status_code != 200:
                logger.warning("EM rank list HTTP %d", r1.status_code)
                _on_failure(cache_key)
                return _result(_get_stale(cache_key) or [], stale=True)

            rank_items: list = r1.json().get("data") or []
            if not rank_items:
                logger.warning("EM rank list returned empty data")
                _on_failure(cache_key)
                return _result(_get_stale(cache_key) or [], stale=True)

            secids = [_sc_to_secid(it["sc"]) for it in rank_items if it.get("sc")]

            r2 = await c.get(
                _EM_PRICE_URL,
                params={
                    "ut": "f057cbcbce2a86e2866ab8877db1d059",
                    "fltt": "2", "invt": "2",
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
            code = sc[2:] if len(sc) > 2 else sc
            pr = price_map.get(code, {})
            pct = pr.get("f3")
            result.append({
                "rank":       int(rank_row.get("rk") or 0),
                "code":       code,
                "market":     "A",
                "name":       str(pr.get("f14") or ""),
                "percent":    round(float(pct), 2) if pct is not None else None,
                "rank_delta": _rank_delta_icon(rank_row.get("rc", 0)),
            })
        result.sort(key=lambda x: x["rank"])

        if result:
            _on_success(cache_key, result)
            return _result(result)

        _on_failure(cache_key)
        return _result(_get_stale(cache_key) or [], stale=True)

    except Exception as exc:
        logger.warning("EastMoney hot fetch failed: %s", exc)
        _on_failure(cache_key)
        stale = _get_stale(cache_key)
        return _result(stale or [], stale=stale is not None)

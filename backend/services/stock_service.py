"""Stock data service — direct Sina individual stock API (fast, no akshare bottleneck).
   Also uses akshare for search and chart data.
"""
import re
import time
import asyncio
import logging
from typing import Optional, List, Dict, Any
from collections import defaultdict

import httpx

logger = logging.getLogger(__name__)

# ── Cache ──
_cache: Dict[str, tuple] = {}
CACHE_TTL = 35           # seconds — realtime quotes (>30s interval so next auto-refresh hits cache)
CACHE_TTL_CHART = 3600   # 1 hour — K-line data (changes once per trading day)
CACHE_TTL_NEWS = 900     # 15 min — news headlines (refresh more often so articles stay current)
CACHE_TTL_FINANCE = 3600 # 1 hour — PE, market cap, turnover rate

# ── Thread pool throttle ──
# akshare uses blocking I/O via asyncio.to_thread. Limit concurrency
# to prevent thread pool exhaustion when many stocks are being refreshed.
_akshare_sem = asyncio.Semaphore(3)


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


# ── Sina symbol helpers ──

def _sina_symbol(code: str, market: str) -> str:
    if market == "A":
        prefix = "sh" if code.startswith(("6", "5", "9")) else "sz"
        return f"{prefix}{code}"
    elif market == "HK":
        return f"hk{code}"
    elif market == "US":
        return f"gb_{code.lower()}"
    return code


def _sina_to_tencent_symbol(sina_sym: str) -> str:
    """Convert Sina quote symbol to Tencent Finance format.

    gb_aapl → usAAPL, sh000001 → sh000001, hk06809 → hk06809
    """
    if sina_sym.startswith("gb_"):
        return "us" + sina_sym[3:].upper()
    return sina_sym


# Full browser-like headers — cloud server IPs need these to avoid 403 from Sina
_SINA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.sina.com.cn/",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
}

# Tencent Finance headers — used when Sina is blocked
_TENCENT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://gu.qq.com/",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


async def _fetch_sina_quotes(symbols: List[str]) -> Dict[str, str]:
    """Fetch raw Sina quote strings for a batch of symbols.

    Returns dict mapping symbol -> raw CSV line.
    """
    if not symbols:
        return {}

    url = f"http://hq.sinajs.cn/list={','.join(symbols)}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=_SINA_HEADERS)
            resp.raise_for_status()
    except Exception as e:
        logger.warning(f"Sina quote HTTP error: {e}")
        return {}

    result = {}
    for line in resp.text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        m = re.match(r'var hq_str_(\w+)="(.*)";?', line)
        if m:
            csv = m.group(2)
            if csv and not csv.startswith("FAILED"):
                result[m.group(1)] = csv
    return result


async def _fetch_tencent_quotes(symbols: List[str]) -> Dict[str, dict]:
    """Fetch quotes from Tencent Finance (qt.gtimg.cn) — fallback when Sina is blocked.

    symbols: Sina-format strings (sh000001, sz399001, hk06809, gb_aapl …)
    Returns dict keyed by original Sina symbol, values match _parse_*_quote output format.

    Tencent field layout (~ separated):
      [1]=name, [3]=price, [4]=prev_close, [5]=open, [6]=volume(手),
      [31]=change, [32]=change_pct, [33]=high, [34]=low,
      [37]=amount(万元), [38]=turnover_rate(%),
      [39]=PE(动态), [44]=market_cap(亿元), [45]=float_market_cap(亿元)
    """
    if not symbols:
        return {}

    # Build sina→tencent conversion and reverse lookup
    sym_map: Dict[str, str] = {}  # tencent_sym → original sina_sym
    tencent_syms: List[str] = []
    for sina_sym in symbols:
        t_sym = _sina_to_tencent_symbol(sina_sym)
        sym_map[t_sym] = sina_sym
        tencent_syms.append(t_sym)

    url = f"https://qt.gtimg.cn/q={','.join(tencent_syms)}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=_TENCENT_HEADERS)
            resp.raise_for_status()
    except Exception as e:
        logger.warning(f"Tencent quote HTTP error: {e}")
        return {}

    result: Dict[str, dict] = {}
    for line in resp.text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        m = re.match(r'v_(\w+)="(.+)"', line)
        if not m:
            continue
        tencent_sym = m.group(1)
        original_sym = sym_map.get(tencent_sym, tencent_sym)
        parts = m.group(2).split("~")
        if len(parts) < 6:
            continue

        def fp(i: int) -> Optional[float]:
            try:
                v = parts[i].strip()
                return float(v) if v else None
            except (IndexError, ValueError):
                return None

        try:
            name = parts[1] if len(parts) > 1 else ""
            price = fp(3)
            prev_close = fp(4)
            open_ = fp(5)
            volume = fp(6)   # 手 (lots)
            high = fp(33)
            low = fp(34)

            # amount: Tencent field [37] is in 万元 → convert to 元
            amt_raw = fp(37)
            amount = amt_raw * 1e4 if amt_raw is not None else None

            turnover_rate = fp(38)
            pe = fp(52)      # PE-TTM (trailing twelve months) — 主显示值，与主流终端一致
            pe_ttm = fp(39)  # 动态PE (annualised from latest quarter) — 保留备用

            # market_cap / float_market_cap: Tencent fields [44]/[45] in 亿元 → 元
            mc_raw = fp(44)
            market_cap = mc_raw * 1e8 if mc_raw is not None else None
            fmc_raw = fp(45)
            float_market_cap = fmc_raw * 1e8 if fmc_raw is not None else None

            change, change_pct = None, None
            if price is not None and prev_close is not None and prev_close != 0:
                change = round(price - prev_close, 4)
                change_pct = round(change / prev_close * 100, 2)

            amplitude = None
            if high is not None and low is not None and prev_close is not None and prev_close != 0:
                amplitude = round((high - low) / prev_close * 100, 2)

            result[original_sym] = {
                "stock_name": name,
                "price": price,
                "change": change,
                "change_pct": change_pct,
                "prev_close": prev_close,
                "open": open_,
                "high": high,
                "low": low,
                "volume": volume,
                "amount": amount,
                "turnover_rate": turnover_rate,
                "pe": pe,
                "pe_ttm": pe_ttm,
                "market_cap": market_cap,
                "float_market_cap": float_market_cap,
                "amplitude": amplitude,
            }
        except Exception:
            continue
    return result


# ── Parsers ──

def _parse_a_quote(csv: str) -> dict:
    """Parse A-share Sina CSV.

    Fields: name(0), open(1), prev_close(2), price(3), high(4), low(5),
            bid(6), ask(7), volume_手(8), amount_万(9), ..., date(30), time(31)
    """
    parts = csv.split(",")

    def f(i):
        try:
            v = parts[i].strip()
            return float(v) if v else None
        except (IndexError, ValueError):
            return None

    name = parts[0] if len(parts) > 0 else ""
    price = f(3)
    prev_close = f(2)
    if price is None and prev_close is not None:
        price = prev_close

    change = None
    change_pct = None
    if price is not None and prev_close is not None and prev_close != 0:
        change = round(price - prev_close, 2)
        change_pct = round((change / prev_close) * 100, 2)
    
    return {
        "stock_name": name,
        "price": price,
        "change": change,
        "change_pct": change_pct,
        "prev_close": prev_close,
        "open": f(1),
        "high": f(4),
        "low": f(5),
        "volume": f(8),       # 股（Sina直接返回股数）
        "amount": f(9),       # 元（Sina直接返回元）
        "turnover_rate": None,
        "pe": None,
        "market_cap": None,
        "float_market_cap": None,
        "amplitude": None,
    }


def _parse_hk_quote(csv: str) -> dict:
    """Parse HK Sina CSV (18 fields).

    Actual format: name_en(0), name_cn(1), open(2), prev_close(3), high(4), low(5),
                   current_price(6), change(7), change_pct(8), bid(9), ask(10),
                   turnover_amount(11), volume_shares(12), pe(13), dividend_yield(14),
                   52w_high(15), 52w_low(16), date(17), time(18)
    """
    parts = csv.split(",")

    def f(i):
        try:
            v = parts[i].strip()
            return float(v) if v else None
        except (IndexError, ValueError):
            return None

    name = parts[1] if len(parts) > 1 else (parts[0] if parts else "")  # 中文名
    price = f(6)
    prev_close = f(3)
    change = f(7)
    change_pct = f(8)

    # Fallback: calculate change from price if API didn't provide it
    if change is None and price is not None and prev_close is not None and prev_close != 0:
        change = round(price - prev_close, 2)
        change_pct = round((change / prev_close) * 100, 2)

    return {
        "stock_name": name,
        "price": price,
        "change": change,
        "change_pct": change_pct,
        "prev_close": prev_close,
        "open": f(2),
        "high": f(4),
        "low": f(5),
        "volume": f(12),     # 成交量（股数）
        "amount": f(11),     # 成交额（元）
        "turnover_rate": None,
        "pe": f(13),         # 市盈率（Sina直接提供）
        "market_cap": None,
        "float_market_cap": None,
        "amplitude": None,
    }


def _parse_us_quote(csv: str) -> dict:
    """Parse US Sina CSV (36 fields).

    Actual format (verified live):
      [0]  name (Chinese, e.g. '苹果')
      [1]  price
      [2]  change_pct (%)
      [3]  datetime
      [4]  change (absolute)
      [5]  open
      [6]  high
      [7]  low
      [8-9]  other
      [10] volume (shares)
      [11] another volume
      [12] turnover (yuan/cents)
      [13] PE ratio
      ...
      [26] prev_close
    """
    parts = csv.split(",")

    def f(i):
        try:
            v = parts[i].strip()
            return float(v) if v else None
        except (IndexError, ValueError):
            return None

    price = f(1)
    prev_close = f(26)
    change = f(4)
    change_pct = f(2)

    # Self-check: if change != price - prev_close, recalculate
    if price is not None and prev_close is not None and prev_close != 0:
        calc_change = round(price - prev_close, 2)
        calc_pct = round((calc_change / prev_close) * 100, 2)
        if change is None or abs(change - calc_change) > 0.01:
            change = calc_change
            change_pct = calc_pct
        elif change_pct is None:
            change_pct = calc_pct

    return {
        "stock_name": parts[0] if len(parts) > 0 else "",
        "price": price,
        "change": change,
        "change_pct": change_pct,
        "prev_close": prev_close,
        "open": f(5),
        "high": f(6),
        "low": f(7),
        "volume": f(10),
        "amount": None,
        "turnover_rate": None,
        "pe": f(13),
        "market_cap": f(12),       # field [12] = total market cap
        "float_market_cap": None,
        "amplitude": None,
    }


_PARSERS = {"A": _parse_a_quote, "HK": _parse_hk_quote, "US": _parse_us_quote}


# ── Supplementary financial data (PE, market cap, turnover rate) ──

SINA_FINANCE_URL = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/StockQuotes.getStockFinance"


async def _fetch_sina_finance(symbols: List[str]) -> Dict[str, dict]:
    """Fetch supplementary financial data (PE, market cap, total shares) from Sina.
    Now fetches ALL symbols in PARALLEL using asyncio.gather.

    Returns dict mapping symbol -> {pe, market_cap, total_shares}.
    Returns empty dict for non-A shares or on failure.
    """
    # Only A-shares have this API
    a_symbols = [s for s in symbols if s.startswith(("sh", "sz"))]
    if not a_symbols:
        return {}

    result = {}
    try:
        async with httpx.AsyncClient(timeout=15) as client:

            async def _fetch_one(sym: str):
                try:
                    resp = await client.get(
                        SINA_FINANCE_URL,
                        params={"symbol": sym},
                        headers=_SINA_HEADERS,
                    )
                    resp.raise_for_status()
                    text = resp.text.strip()
                    m = re.search(r'\{.*\}', text)
                    if m:
                        import json
                        data = json.loads(m.group())
                        finance = {}
                        mc_str = data.get("market_cap", data.get("总市值", ""))
                        finance["market_cap"] = _parse_chinese_number(mc_str)
                        pe_str = data.get("pe", data.get("市盈率", ""))
                        try:
                            finance["pe"] = float(pe_str) if pe_str else None
                        except (ValueError, TypeError):
                            finance["pe"] = None
                        ts_str = data.get("total_shares", data.get("总股本", ""))
                        finance["total_shares"] = _parse_chinese_number(ts_str)
                        if any(v is not None for v in finance.values()):
                            return sym, finance
                except Exception as e:
                    logger.debug(f"Sina finance error for {sym}: {e}")
                return sym, None

            tasks = [_fetch_one(sym) for sym in a_symbols]
            outcomes = await asyncio.gather(*tasks)
            for sym, data in outcomes:
                if data:
                    result[sym] = data
    except Exception as e:
        logger.warning(f"Sina finance API error: {e}")

    return result


def _parse_chinese_number(s: str) -> Optional[float]:
    """Parse Chinese number strings like '2.5万亿', '128.6亿', '35000万' into float."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip().replace(",", "").replace("，", "")
    if not s:
        return None
    try:
        if "万亿" in s:
            return float(s.replace("万亿", "")) * 1e12
        if "亿" in s:
            return float(s.replace("亿", "")) * 1e8
        if "万" in s:
            return float(s.replace("万", "")) * 1e4
        return float(s)
    except (ValueError, TypeError):
        return None


async def _fetch_market_center_data(symbol: str, market: str) -> dict:
    """Fetch financial data (PE, market cap, turnover rate) from Sina Market_Center API.
    Works for A, HK, US stocks. Returns {pe, market_cap, turnover_rate} or empty dict.
    """
    cache_key = f"finance:mc:{market}:{symbol}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    node_map = {"A": "hs_a", "HK": "hk", "US": "us"}
    node = node_map.get(market)
    if not node:
        return {}

    # Map to Market_Center symbol format
    if market == "A":
        mc_symbol = _sina_symbol(symbol, "A")
    elif market == "HK":
        mc_symbol = f"hk{symbol}"
    elif market == "US":
        mc_symbol = symbol.lower()
    else:
        return {}

    url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
    params = {
        "page": 1, "num": 1, "sort": "symbol",
        "asc": 1, "node": node,
        "symbol": mc_symbol, "_s_r_a": "page",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params, headers=_SINA_HEADERS)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                item = data[0]
                result = {}
                # PE
                pe = item.get("per") or item.get("pe")
                if pe is not None:
                    try:
                        result["pe"] = float(pe)
                    except (ValueError, TypeError):
                        pass
                # Market cap
                mc = item.get("mktcap") or item.get("marketcapital")
                if mc is not None:
                    try:
                        result["market_cap"] = float(mc)
                    except (ValueError, TypeError):
                        pass
                # Turnover rate
                tr = item.get("turnoverratio")
                if tr is not None:
                    try:
                        if isinstance(tr, str) and "%" in tr:
                            result["turnover_rate"] = float(tr.replace("%", ""))
                        else:
                            result["turnover_rate"] = float(tr)
                    except (ValueError, TypeError):
                        pass
                # Amount (成交额)
                amt = item.get("amount")
                if amt is not None:
                    try:
                        result["amount"] = float(amt)
                    except (ValueError, TypeError):
                        pass
                # Float market cap (流通市值)
                nmc = item.get("nmc")
                if nmc is not None:
                    try:
                        result["float_market_cap"] = float(nmc)
                    except (ValueError, TypeError):
                        pass

                if result:
                    _set_cache(cache_key, result, CACHE_TTL_FINANCE)
                    return result
    except Exception as e:
        logger.debug(f"Market_Center error for {mc_symbol}: {e}")

    return {}


# ── Market_Center API helpers ──

MARKET_CENTER_URL = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
MC_HEADERS = _SINA_HEADERS


def _extract_code_from_symbol(sym: str, market: str) -> str:
    """Extract stock code from Market_Center response symbol field.
    Handles: sh688008, SH688008, 688008, hk00700, HK00700.
    """
    if not sym:
        return ""
    sym = sym.strip().lower()
    for prefix in ("sh", "sz"):
        if sym.startswith(prefix):
            return sym[len(prefix):]
    if sym.startswith("hk"):
        return sym[2:]
    return sym


def _parse_market_center_item(item: dict) -> dict:
    """Parse a single Market_Center response item into financial data dict."""
    fin = {}
    pe = item.get("per") or item.get("pe")
    if pe is not None:
        try:
            fin["pe"] = float(pe)
        except (ValueError, TypeError):
            pass
    mc = item.get("mktcap") or item.get("marketcapital")
    if mc is not None:
        try:
            fin["market_cap"] = float(mc)
        except (ValueError, TypeError):
            pass
    tr = item.get("turnoverratio")
    if tr is not None:
        try:
            if isinstance(tr, str) and "%" in tr:
                fin["turnover_rate"] = float(tr.replace("%", ""))
            else:
                fin["turnover_rate"] = float(tr)
        except (ValueError, TypeError):
            pass
    amt = item.get("amount")
    if amt is not None:
        try:
            fin["amount"] = float(amt)
        except (ValueError, TypeError):
            pass
    nmc = item.get("nmc")
    if nmc is not None:
        try:
            fin["float_market_cap"] = float(nmc)
        except (ValueError, TypeError):
            pass
    return fin


async def _fetch_all_stocks_finance(codes_by_market: Dict[str, List[str]]) -> Dict[str, dict]:
    """Fetch financial data for ALL needed stocks in ONE call per market.
    Queries Market_Center sorted by amount descending, fetches enough to cover all codes,
    then filters locally. Returns dict keyed by (market, code).

    For each market with stocks, makes exactly 1 HTTP call.
    """
    node_map = {"A": "hs_a", "HK": "hk", "US": "us"}
    result: Dict[str, dict] = {}

    for market, codes in codes_by_market.items():
        if not codes:
            continue
        node = node_map.get(market)
        if not node:
            continue

        cache_key = f"finance:mc:all:{market}"
        cached = _get_cached(cache_key)
        if cached:
            # Filter cached data to only needed codes
            for code in codes:
                if code in cached:
                    result[(market, code)] = cached[code]
            continue

        # Fetch top stocks by amount — covers most actively traded stocks
        params = {"page": 1, "num": 200, "sort": "amount", "asc": 0, "node": node, "_s_r_a": "page"}

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(MARKET_CENTER_URL, params=params, headers=MC_HEADERS)
                resp.raise_for_status()
                data = resp.json()

                all_finance = {}
                if isinstance(data, list):
                    for item in data:
                        sym = item.get("symbol", "")
                        code = _extract_code_from_symbol(sym, market)
                        if not code:
                            continue
                        fin = _parse_market_center_item(item)
                        if fin:
                            all_finance[code] = fin
                            if code in codes:
                                result[(market, code)] = fin

                # Cache the full batch
                if all_finance:
                    _set_cache(cache_key, all_finance, CACHE_TTL_FINANCE)

        except Exception as e:
            logger.debug(f"Market_Center batch error for {market}: {e}")

    return result


def _float_market_cap_fallback(entries: List[dict]):
    """Fallback: if float_market_cap is still None, use market_cap instead.
    HK stocks are fully floated (all shares tradable), so 流通市值 ≈ 总市值.
    """
    for e in entries:
        if e.get("float_market_cap") is None and e.get("market_cap") is not None:
            e["float_market_cap"] = e["market_cap"]


async def _enrich_with_finance(entries: List[dict]):
    """Enrich entries with PE, market cap, turnover rate, float_market_cap.
    Phase 0 (A-shares): Tencent batch — provides 动态PE + market cap for ALL A-shares.
    Phase 1: ONE Market_Center call per market (up to 200 stocks sorted by amount).
    Falls back to parallel per-stock calls for any stocks not found in the batch.
    Modifies entries in-place.

    HK stocks: fully floated, so float_market_cap falls back to market_cap if not available.
    """
    valid_entries = [e for e in entries if e.get("stock_name") and (e.get("pe") is None or e.get("market_cap") is None)]
    if not valid_entries:
        return

    # Group by market
    from collections import defaultdict
    by_market: Dict[str, List[dict]] = defaultdict(list)
    for e in valid_entries:
        by_market[e["market"]].append(e)

    # Phase 0: Tencent batch for A-shares — field [39]=动态PE, [41]=总市值, [42]=流通市值
    a_entries = [e for e in valid_entries if e.get("market") == "A"]
    if a_entries:
        a_symbols = [_sina_symbol(e["code"], "A") for e in a_entries]
        tq = await _fetch_tencent_quotes(a_symbols)
        for e, sym in zip(a_entries, a_symbols):
            td = tq.get(sym)
            if not td:
                continue
            for field in ("pe", "pe_ttm", "market_cap", "float_market_cap",
                          "turnover_rate", "amplitude"):
                if e.get(field) is None and td.get(field) is not None:
                    e[field] = td[field]

    # Re-check which still need data
    valid_entries = [e for e in entries if e.get("stock_name") and (e.get("pe") is None or e.get("market_cap") is None)]
    if not valid_entries:
        _float_market_cap_fallback(entries)
        return

    by_market = defaultdict(list)
    for e in valid_entries:
        by_market[e["market"]].append(e)

    # Phase 1: ONE Market_Center call per market
    codes_by_market = {m: [e["code"] for e in es] for m, es in by_market.items()}
    all_finance = await _fetch_all_stocks_finance(codes_by_market)

    # Apply batch results
    still_missing: List[dict] = []
    for e in valid_entries:
        fin = all_finance.get((e["market"], e["code"]))
        if fin:
            if e.get("pe") is None:
                e["pe"] = fin.get("pe")
            if e.get("market_cap") is None:
                e["market_cap"] = fin.get("market_cap")
            if e.get("turnover_rate") is None:
                e["turnover_rate"] = fin.get("turnover_rate")
            if e.get("amount") is None:
                e["amount"] = fin.get("amount")
            if e.get("float_market_cap") is None:
                e["float_market_cap"] = fin.get("float_market_cap")
        else:
            still_missing.append(e)

    if not still_missing:
        _float_market_cap_fallback(entries)
        return

    # Phase 2: Fallback per-stock
    missing_a = [e for e in still_missing if e.get("market") == "A"]
    if missing_a:
        symbols = [_sina_symbol(e["code"], "A") for e in missing_a]
        finance_map = await _fetch_sina_finance(symbols)
        for entry, sym in zip(missing_a, symbols):
            fin = finance_map.get(sym)
            if not fin:
                continue
            if entry.get("pe") is None:
                entry["pe"] = fin.get("pe")
            if entry.get("market_cap") is None:
                entry["market_cap"] = fin.get("market_cap")
            vol = entry.get("volume")
            total_shares = fin.get("total_shares")
            if entry.get("turnover_rate") is None and vol is not None and total_shares and total_shares > 0:
                entry["turnover_rate"] = round(vol / total_shares * 100, 2)
            if entry.get("float_market_cap") is None and entry.get("market_cap") is not None:
                entry["float_market_cap"] = entry["market_cap"]

    missing_others = [e for e in still_missing if e.get("market") != "A"]
    if missing_others:
        tasks = [_fetch_market_center_data(e["code"], e["market"]) for e in missing_others]
        mc_fallback = await asyncio.gather(*tasks)
        for entry, fin in zip(missing_others, mc_fallback):
            if fin:
                if entry.get("pe") is None:
                    entry["pe"] = fin.get("pe")
                if entry.get("market_cap") is None:
                    entry["market_cap"] = fin.get("market_cap")
                if entry.get("turnover_rate") is None:
                    entry["turnover_rate"] = fin.get("turnover_rate")
                if entry.get("amount") is None:
                    entry["amount"] = fin.get("amount")
                if entry.get("float_market_cap") is None:
                    entry["float_market_cap"] = fin.get("float_market_cap")

    # Phase 3: Final fallback
    _float_market_cap_fallback(entries)


EASTMONEY_FINANCIAL_URL = "https://datacenter.eastmoney.com/api/data/get"
CACHE_TTL_GROWTH = 86400   # 24 h — earnings data changes quarterly

_EM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://data.eastmoney.com/",
}


async def _batch_fetch_em_fundamentals(codes: List[str]) -> Dict[str, dict]:
    """Single EM API call for multiple codes using IN filter.

    Returns {code: {"profit_growth_rate": float, "roe": float}}.
    Uses ps=len(codes)*4 so even if codes share the same report date we still
    get the latest row for every code after deduplication.
    """
    if not codes:
        return {}
    try:
        if len(codes) == 1:
            filter_expr = f'(SECURITY_CODE="{codes[0]}")'
        else:
            # EM API requires IN syntax for multiple codes; OR syntax returns 9501 error
            in_list = ",".join(f'"{c}"' for c in codes)
            filter_expr = f'(SECURITY_CODE in ({in_list}))'
        ps = min(len(codes) * 4, 400)
        params = {
            "type": "RPT_LICO_FN_CPD",
            "sty": "SECURITY_CODE,REPORTDATE,SJLTZ,WEIGHTAVG_ROE",
            "filter": filter_expr,
            "sr": "-1", "st": "REPORTDATE",
            "p": "1", "ps": str(ps),
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(EASTMONEY_FINANCIAL_URL, params=params, headers=_EM_HEADERS)
            resp.raise_for_status()
            data = resp.json()
            rows = (data.get("result") or {}).get("data") or []
        seen: set = set()
        result: Dict[str, dict] = {}
        for row in rows:
            code = row.get("SECURITY_CODE", "")
            if not code or code in seen:
                continue
            seen.add(code)
            r: dict = {}
            if row.get("SJLTZ") is not None:
                r["profit_growth_rate"] = round(float(row["SJLTZ"]), 2)
            if row.get("WEIGHTAVG_ROE") is not None:
                r["roe"] = round(float(row["WEIGHTAVG_ROE"]), 2)
            result[code] = r
        logger.debug(f"EM batch fundamentals: {len(codes)} requested, {len(result)} returned")
        return result
    except Exception as e:
        logger.debug(f"EM batch fundamentals error: {e}")
    return {}


async def _fetch_em_fundamentals(code: str) -> dict:
    """Fetch profit growth rate (SJLTZ) + ROE (WEIGHTAVG_ROE) from East Money (single stock)."""
    result = await _batch_fetch_em_fundamentals([code])
    return result.get(code, {})


def _fetch_akshare_fundamentals(code: str) -> dict:
    """Fetch debt ratio + cash-flow quality from akshare via THS financial abstract.

    Uses stock_financial_abstract_ths (按报告期) which returns Chinese-formatted
    strings. Extracts:
      - 资产负债率: "40.79%" → debt_ratio=40.8
      - cash_profit_ratio = 每股经营现金流 / 基本每股收益 × 100  (= op CF / net profit %)
    """
    try:
        import akshare as ak
        import math

        df = ak.stock_financial_abstract_ths(symbol=code, indicator='按报告期')
        if df is None or df.empty:
            return {}

        # Rows are ascending by date; last row = most recent period
        row = df.iloc[-1]
        result = {}

        def _parse_float(v) -> Optional[float]:
            if v is None or v is False:
                return None
            s = str(v).strip().rstrip('%')
            if not s or s in ('nan', 'None', 'False', '-'):
                return None
            try:
                f = float(s)
                return None if math.isnan(f) else f
            except (ValueError, TypeError):
                return None

        debt = _parse_float(row.get('资产负债率'))   # already a percentage, e.g. 40.79
        if debt is not None:
            result['debt_ratio'] = round(debt, 1)

        # cash quality = operating CF / net profit (both on per-share basis)
        cps = _parse_float(row.get('每股经营现金流'))   # yuan per share
        eps = _parse_float(row.get('基本每股收益'))     # yuan per share
        if cps is not None and eps is not None and eps != 0:
            result['cash_profit_ratio'] = round(cps / eps * 100, 1)

        return result
    except Exception as e:
        logger.debug(f"akshare fundamentals error for {code}: {e}")
    return {}


async def fetch_financial_snapshot(code: str, market: str) -> dict:
    """Fetch key financial indicators for one A-share stock. Cached 24 h.
    Returns dict with keys: profit_growth_rate, roe, debt_ratio, cash_profit_ratio.
    """
    if market != "A":
        return {}
    cache_key = f"finsnapshot:{code}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    loop = asyncio.get_event_loop()
    em_task = _fetch_em_fundamentals(code)
    ak_task = loop.run_in_executor(None, _fetch_akshare_fundamentals, code)
    em_data, ak_data = await asyncio.gather(em_task, ak_task)

    snapshot = {**em_data, **ak_data}
    ttl = CACHE_TTL_GROWTH if snapshot else 3600
    _set_cache(cache_key, snapshot, ttl)
    return snapshot


async def batch_fetch_financial_snapshots(
    stock_pairs: List[tuple],  # List of (stock_code, market)
) -> List[dict]:
    """Batch-fetch financial snapshots for multiple stocks (EM only, no THS).

    Returns profit_growth_rate and roe via a single EM batch call.
    debt_ratio and cash_profit_ratio are fetched lazily by the detail modal
    via /stocks/financials/{code} → fetch_financial_snapshot (which caches
    the full snapshot; subsequent batch calls will serve it from cache).
    """
    a_share_indices = [(i, code) for i, (code, mkt) in enumerate(stock_pairs) if mkt == "A"]

    uncached: List[tuple] = []
    result_map: Dict[int, dict] = {}

    for i, code in a_share_indices:
        # Use full cached snapshot if available (populated when detail modal was opened)
        cached = _get_cached(f"finsnapshot:{code}")
        if cached is not None:
            result_map[i] = cached
        else:
            uncached.append((i, code))

    if uncached:
        uncached_codes = [code for _, code in uncached]
        em_batch = await _batch_fetch_em_fundamentals(uncached_codes)
        for i, code in uncached:
            result_map[i] = em_batch.get(code, {})

    return [result_map.get(i, {}) for i in range(len(stock_pairs))]


async def fetch_profit_growth_rate(code: str, market: str) -> Optional[float]:
    """Backward-compatible wrapper — returns only the growth rate from fetch_financial_snapshot."""
    snapshot = await fetch_financial_snapshot(code, market)
    return snapshot.get("profit_growth_rate")


def compute_peg(pe: Optional[float], growth_rate: Optional[float]) -> Optional[float]:
    """PEG = PE / annualised growth rate (%). Only valid when both are positive."""
    if pe is None or growth_rate is None:
        return None
    if pe <= 0 or growth_rate <= 0:
        return None
    return round(pe / growth_rate, 2)


def compute_signal(
    pe: Optional[float],
    peg: Optional[float],
    growth_rate: Optional[float],
    market: str,
) -> str:
    """
    Rule-based trading signal: 买入 | 关注 | 持有 | 减仓
    Priority: PEG rules > growth rules > PE-only rules.
    """
    # Loss-making (negative PE)
    if pe is not None and pe < 0:
        return "关注" if (growth_rate is not None and growth_rate > 50) else "减仓"

    # Extreme overvaluation
    if pe is not None and pe > 80:
        return "减仓"

    # PEG-based (most reliable when data available)
    if peg is not None:
        if peg < 0.8 and growth_rate is not None and growth_rate > 15:
            return "买入"
        if peg < 1.2 and growth_rate is not None and growth_rate > 10:
            return "关注"
        if peg > 3.0:
            return "减仓"

    # Growth-based
    if growth_rate is not None:
        if growth_rate < -20:
            return "减仓"
        if growth_rate > 30 and (pe is None or pe < 60):
            return "关注"

    # PE-only (HK/US or when growth not available)
    if pe is not None:
        if pe < 15:
            return "关注"
        if pe > 60:
            return "减仓"

    return "持有"


async def fetch_stock_realtime(stock_code: str, market: str) -> dict:
    """Fetch realtime data for a single stock. Primary: Sina. Fallback: Tencent."""
    cache_key = f"realtime:{market}:{stock_code}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    symbol = _sina_symbol(stock_code, market)
    quotes = await _fetch_sina_quotes([symbol])
    csv = quotes.get(symbol)

    if not csv:
        # Sina blocked or empty — try Tencent Finance
        logger.info(f"Sina empty for {stock_code} ({market}), trying Tencent fallback")
        tencent_quotes = await _fetch_tencent_quotes([symbol])
        tencent_data = tencent_quotes.get(symbol)
        if tencent_data and tencent_data.get("stock_name"):
            result = dict(tencent_data)
            result["code"] = stock_code
            result["market"] = market
            await _enrich_with_finance([result])
            _set_cache(cache_key, result)
            logger.info(f"Tencent OK: {stock_code} ({market}) = {result.get('price')}")
            return result
        raise ValueError(f"Stock {stock_code} ({market}) not found in Sina or Tencent")

    parser = _PARSERS.get(market, _parse_a_quote)
    result = parser(csv)
    result["code"] = stock_code
    result["market"] = market

    if not result.get("stock_name"):
        raise ValueError(f"Stock {stock_code} ({market}) returned empty name")

    # Enrich with financial data
    await _enrich_with_finance([result])

    _set_cache(cache_key, result)
    logger.info(f"Sina OK: {stock_code} ({market}) = {result.get('price')}")
    return result


async def fetch_stocks_batch(stocks: List[Dict[str, str]]) -> List[dict]:
    """Fetch multiple stocks in ONE Sina HTTP call."""
    results: List[dict] = []
    uncached: Dict[str, List[str]] = defaultdict(list)

    for s in stocks:
        code = s.get("code", "")
        market = s.get("market", "A")
        cached = _get_cached(f"realtime:{market}:{code}")
        if cached:
            results.append(cached)
        else:
            uncached[market].append(code)

    if not uncached:
        return results

    new_entries: List[dict] = []
    for market, codes in uncached.items():
        symbols = [_sina_symbol(c, market) for c in codes]
        quotes = await _fetch_sina_quotes(symbols)

        # Tencent fallback: if Sina returned nothing (403 or network error), try Tencent
        tencent_quotes: Dict[str, dict] = {}
        if not quotes and symbols:
            logger.info(f"Sina empty for {market} ({len(codes)} stocks), trying Tencent fallback")
            tencent_quotes = await _fetch_tencent_quotes(symbols)

        parser = _PARSERS.get(market, _parse_a_quote)

        for code in codes:
            sym = _sina_symbol(code, market)
            csv = quotes.get(sym)
            if csv:
                entry = parser(csv)
                entry["code"] = code
                entry["market"] = market
                if entry.get("stock_name"):
                    new_entries.append(entry)
                    continue
            # Try Tencent fallback data
            tq = tencent_quotes.get(sym)
            if tq and tq.get("stock_name"):
                entry = dict(tq)
                entry["code"] = code
                entry["market"] = market
                new_entries.append(entry)
                continue
            results.append({
                "code": code, "market": market,
                "error": "not found",
            })

    # Enrich all new entries with PE, market cap, turnover rate (batch)
    await _enrich_with_finance(new_entries)

    # Cache and collect
    for entry in new_entries:
        _set_cache(f"realtime:{entry['market']}:{entry['code']}", entry)
        results.append(entry)

    logger.info(f"batch: {len(stocks)} req, {len(results)} result")
    return results


_EM_NEWS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.eastmoney.com/",
}

async def fetch_stock_news(stock_code: str, market: str) -> list:
    """Fetch news directly from EastMoney's news list API. Only works for A-shares."""
    if market != "A":
        return []

    cache_key = f"news:{market}:{stock_code}"
    cached = _get_cached(cache_key)
    if cached is not None and len(cached) > 0:
        return cached

    # EastMoney market prefix: 1 = SH (6xxxxx), 0 = SZ (0/3xxxxx)
    em_prefix = "1" if stock_code.startswith("6") else "0"
    mtype = f"{em_prefix}.{stock_code}"

    news_list = []
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            r = await client.get(
                "https://np-listapi.eastmoney.com/comm/web/getListInfo",
                params={
                    "client": "web",
                    "type": "1",
                    "mTypeAndCode": mtype,
                    "pageSize": "20",
                    "startTime": "",
                    "endTime": "",
                    "callback": "jQuery",
                    "_": str(int(time.time() * 1000)),
                },
                headers=_EM_NEWS_HEADERS,
            )
        # Response is JSONP: jQuery({...})
        text = r.text.strip()
        if text.startswith("jQuery(") and text.endswith(")"):
            import json
            data = json.loads(text[7:-1])
            items = (data.get("data") or {}).get("list") or []
            for item in items[:20]:
                title = str(item.get("Art_Title") or "").strip()
                if not title:
                    continue
                news_list.append({
                    "title":  title,
                    "source": "东方财富",
                    "url":    str(item.get("Art_OriginUrl") or item.get("Art_Url") or ""),
                    "time":   str(item.get("Art_ShowTime") or ""),
                })
    except Exception as e:
        logger.warning(f"EM news fetch failed for {stock_code}: {e}")

    # Only cache non-empty results; empty will be retried on next request
    if news_list:
        _set_cache(cache_key, news_list, CACHE_TTL_NEWS)
    return news_list



SINA_KLINE_URL = "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"


async def fetch_chart_data(stock_code: str, market: str) -> list:
    """Fetch K-line chart data via Sina K-line API."""
    cache_key = f"chart:{market}:{stock_code}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    symbol = _sina_symbol(stock_code, market)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                SINA_KLINE_URL,
                params={"symbol": symbol, "scale": 240, "ma": 5, "datalen": 30},
                headers=_SINA_HEADERS,
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and len(data) >= 2:
                chart = [float(item["close"]) for item in data]
                _set_cache(cache_key, chart, CACHE_TTL_CHART)
                return chart
    except Exception as e:
        logger.debug(f"chart data error for {stock_code} ({market}): {e}")
    return []


async def compute_ytd_change(stock_code: str, market: str) -> Optional[float]:
    """Compute YTD percentage change using Sina K-line.
    Cached for CACHE_TTL_CHART (1 hour).
    """
    cache_key = f"ytd:{market}:{stock_code}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    if market == "US":
        return None  # Sina K-line may not support US stocks

    symbol = _sina_symbol(stock_code, market)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                SINA_KLINE_URL,
                params={"symbol": symbol, "scale": 240, "ma": 5, "datalen": 200},
                headers=_SINA_HEADERS,
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and len(data) >= 10:
                closes = [float(item["close"]) for item in data]
                first = closes[0]
                last = closes[-1]
                if first > 0:
                    pct = (last - first) / first * 100
                    _set_cache(cache_key, pct, CACHE_TTL_CHART)
                    return round(pct, 2)
    except Exception as e:
        logger.debug(f"ytd error for {stock_code}: {e}")
    return None


def fmt_market_cap(value: Optional[float]) -> str:
    """Format market cap to Chinese units."""
    if value is None:
        return ""
    if value >= 1e12:
        return f"${value / 1e12:.2f}万亿"
    if value >= 1e8:
        return f"${value / 1e8:.0f}亿"
    return f"${value / 1e4:.0f}万"


TECH_GIANTS_CAPEX = {
    "total_2025e": 7250e8,
    "total_2024": 4100e8,
    "yoy_pct": 77.0,
    "label": "$7,250亿",
    "subtitle": "2025年合计$4,100亿 · +77% 同比",
    "source": "微软/亚马逊/谷歌/Meta FY2025资本开支指引",
}

GOOGLE_CLOUD_BACKLOG = {
    "backlog": 4600e8,
    "qoq_pct": 95.0,
    "label": "$4,600亿",
    "subtitle": "季度环比+95%",
    "source": "Alphabet FY2025 Q1财报",
}


async def get_aindex_intel() -> list:
    """Fetch Shanghai / Shenzhen / ChiNext index real-time data.

    Primary: Sina hq.sinajs.cn
    Fallback: Tencent qt.gtimg.cn  (used when Sina returns 403 from cloud IPs)
    """
    index_map = [
        ("sh000001", "上证指数"),
        ("sz399001", "深证成指"),
        ("sz399006", "创业板指"),
        ("sh000688", "科创50"),
    ]
    symbols = [s for s, _ in index_map]

    # Try Sina first
    sina_quotes = await _fetch_sina_quotes(symbols)
    use_tencent = not sina_quotes
    tencent_quotes: Dict[str, dict] = {}
    if use_tencent:
        logger.info("Sina index blocked, falling back to Tencent Finance")
        tencent_quotes = await _fetch_tencent_quotes(symbols)

    items = []
    for symbol, name in index_map:
        if use_tencent:
            d = tencent_quotes.get(symbol, {})
            price = d.get("price")
            change_pct = d.get("change_pct")
        else:
            csv = sina_quotes.get(symbol)
            if not csv:
                continue
            d = _parse_a_quote(csv)
            price = d.get("price")
            change_pct = d.get("change_pct")

        if price is None:
            continue
        sign = "+" if (change_pct or 0) >= 0 else ""
        pct_str = f"{sign}{change_pct:.2f}%" if change_pct is not None else "--"
        items.append({
            "id": symbol,
            "title": name,
            "value": f"{price:.2f}",
            "subtitle": pct_str,
            "direction": "up" if (change_pct or 0) >= 0 else "down",
        })
    return items


async def get_tech_giants_intel() -> list:
    """Return market intelligence items for US tech giants."""
    items = []

    items.append({
        "id": "hyperscaler_capex",
        "title": "北美四大Hyperscaler 合计资本开支指引",
        "value": TECH_GIANTS_CAPEX["label"],
        "subtitle": TECH_GIANTS_CAPEX["subtitle"],
        "direction": "up",
    })

    items.append({
        "id": "google_cloud_backlog",
        "title": "谷歌云合同积压订单",
        "value": GOOGLE_CLOUD_BACKLOG["label"],
        "subtitle": GOOGLE_CLOUD_BACKLOG["subtitle"],
        "direction": "up",
    })

    # Total market cap from Market_Center
    codes = ["msft", "amzn", "googl", "meta"]
    fin_map = await _fetch_all_stocks_finance({"US": codes})

    total_cap = 0
    for code in codes:
        fin = fin_map.get(("US", code))
        if fin and fin.get("market_cap"):
            total_cap += fin["market_cap"]

    if total_cap > 0:
        items.append({
            "id": "tech_giants_mcap",
            "title": "四大科技股合计市值",
            "value": fmt_market_cap(total_cap),
            "subtitle": "微软 · 亚马逊 · 谷歌 · Meta",
            "direction": "",
        })

    return items


async def get_stock_performance_intel() -> list:
    """Return YTD performance for tracked stocks."""
    items = []
    tracked = [
        ("300502", "A", "新易盛"),
        ("300308", "A", "中际旭创"),
    ]

    for code, market, name in tracked:
        try:
            ytd = await compute_ytd_change(code, market)
            if ytd is not None:
                sign = "+" if ytd >= 0 else ""
                items.append({
                    "id": f"perf_{code}",
                    "title": f"{name} 年度累计涨幅",
                    "value": f"{sign}{ytd:.2f}%",
                    "subtitle": f"代码 {code}",
                    "direction": "up" if ytd >= 0 else "down",
                })
        except Exception as e:
            logger.debug(f"perf error for {name}: {e}")

    return items


async def search_stock(keyword: str) -> list:
    """Search stocks by keyword.
    Strategy:
      - A-shares: use akshare local name DB (fast, no network needed)
      - HK/US: use Sina real-time API directly (reliable, single-call verification)
    """
    if not keyword or not keyword.strip():
        return []
    keyword = keyword.strip()
    kw_upper = keyword.upper()
    results = []

    # ── A-shares: search local akshare name DB ──
    try:
        import akshare as ak
        try:
            async with _akshare_sem:
                df = await asyncio.wait_for(
                    asyncio.to_thread(ak.stock_info_a_code_name), timeout=8
                )
            if df is not None and not df.empty:
                df["code_str"] = df["code"].astype(str)
                mask = df["code_str"].str.contains(keyword, case=False) | df["name"].str.contains(keyword, case=False)
                for _, r in df[mask].head(10).iterrows():
                    results.append({
                        "code": str(r["code"]), "market": "A",
                        "name": str(r["name"]).strip(),
                    })
        except Exception as e:
            logger.debug(f"A-share search error: {e}")
    except ImportError:
        logger.warning("akshare not installed")

    # ── Fallback: verify unknown codes via Sina real-time API ──
    # A-share numeric code not found → try Sina
    if not any(r["market"] == "A" for r in results) and keyword.isdigit():
        try:
            symbol = _sina_symbol(keyword, "A")
            quotes = await asyncio.wait_for(_fetch_sina_quotes([symbol]), timeout=5)
            csv = quotes.get(symbol)
            if csv:
                parser = _PARSERS.get("A", lambda c: {"stock_name": c.split(",")[0] if c else keyword})
                entry = parser(csv)
                name = entry.get("stock_name", "") or keyword
                results.insert(0, {"code": keyword, "market": "A", "name": name})
        except Exception as e:
            logger.debug(f"Sina A-share fallback error: {e}")

    # US ticker (1-5 alpha chars) → verify via Sina
    if not any(r["market"] == "US" for r in results) and keyword.isalpha() and 1 <= len(keyword) <= 5:
        try:
            symbol = _sina_symbol(keyword, "US")
            quotes = await asyncio.wait_for(_fetch_sina_quotes([symbol]), timeout=5)
            csv = quotes.get(symbol)
            if csv:
                parser = _PARSERS.get("US", lambda c: {"stock_name": c.split(",")[0] if c else keyword})
                entry = parser(csv)
                name = entry.get("stock_name", "") or keyword
                if name:
                    results.insert(0, {"code": kw_upper, "market": "US", "name": name})
        except Exception as e:
            logger.debug(f"Sina US fallback error: {e}")

    # HK code (5 digits, may start with 0) → try Sina
    if not any(r["market"] == "HK" for r in results) and keyword.isdigit() and len(keyword) == 5:
        try:
            symbol = _sina_symbol(keyword, "HK")
            quotes = await asyncio.wait_for(_fetch_sina_quotes([symbol]), timeout=5)
            csv = quotes.get(symbol)
            if csv:
                entry = _parse_hk_quote(csv)
                name = entry.get("stock_name", "") or keyword
                if name:
                    results.insert(0, {"code": keyword, "market": "HK", "name": name})
        except Exception as e:
            logger.debug(f"Sina HK fallback error: {e}")

    return results


def get_cached_realtime(market: str, code: str) -> dict | None:
    """Return cached realtime price data for a stock, None if not cached / expired."""
    return _get_cached(f"realtime:{market}:{code}")

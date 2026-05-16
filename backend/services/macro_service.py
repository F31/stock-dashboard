"""Macro economic data service: US/CN Treasury yields, CPI, PPI, PMI.

Primary sources (EastMoney datacenter — near real-time):
  RPT_ECONOMY_CPI  → NATIONAL_SAME (yoy%), NATIONAL_SEQUENTIAL (mom%)
  RPT_ECONOMY_PPI  → BASE (price index, yoy% = BASE-100), BASE_ACCUMULATE
  RPT_ECONOMY_PMI  → MAKE_INDEX (mfg PMI), NMAKE_INDEX (non-mfg PMI)

Fallback sources (akshare, monthly refresh, data may lag 1-2 months):
  bond_zh_us_rate          → US + CN Treasury yields (always used for yields)
  macro_china_cpi_yearly   → China CPI YoY%
  macro_china_ppi_yearly   → China PPI YoY%
  macro_china_pmi_yearly   → Official NBS manufacturing PMI
  index_pmi_man_cx         → Caixin manufacturing PMI
  macro_china_non_man_pmi  → Official NBS non-manufacturing PMI
"""
import time
import asyncio
import logging
from datetime import datetime, timedelta, date
from typing import Dict, Any, Optional, List

import httpx

logger = logging.getLogger(__name__)

_cache: Dict[str, tuple] = {}
CACHE_TTL_BONDS = 3600    # 1 hour
CACHE_TTL_MACRO = 43200   # 12 hours (monthly data)

_ak_sem = asyncio.Semaphore(2)

_EM_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_EM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://data.eastmoney.com/",
}


def _get_cached(key: str):
    if key in _cache:
        val, ts, ttl = _cache[key]
        if time.time() - ts < ttl:
            return val
        del _cache[key]
    return None


def _set_cache(key: str, val, ttl: int):
    _cache[key] = (val, time.time(), ttl)


async def _run_ak(fn_name: str, *args, **kwargs):
    import akshare as ak
    fn = getattr(ak, fn_name, None)
    if fn is None:
        raise AttributeError(f"akshare.{fn_name} not found")
    async with _ak_sem:
        return await asyncio.wait_for(
            asyncio.to_thread(fn, *args, **kwargs),
            timeout=25,
        )


async def _fetch_eastmoney(report_name: str, columns: str, page_size: int = 2) -> list:
    """Fetch records from EastMoney datacenter API, sorted by date descending."""
    params = {
        "reportName": report_name,
        "columns": columns,
        "pageSize": page_size,
        "sortColumns": "REPORT_DATE",
        "sortTypes": -1,
        "source": "WEB",
    }
    async with httpx.AsyncClient(timeout=15, headers=_EM_HEADERS) as client:
        resp = await client.get(_EM_URL, params=params)
        resp.raise_for_status()
        body = resp.json()
    if not body.get("success"):
        raise ValueError(f"EastMoney API error: {body.get('message')}")
    return body["result"]["data"] or []


def _fmt_date(d) -> str:
    """Convert datetime.date, datetime string, or string to YYYY-MM-DD."""
    if isinstance(d, date):
        return d.strftime("%Y-%m-%d")
    s = str(d)
    return s[:10]


def _ym(date_str: str) -> str:
    """Trim to YYYY-MM (for period labels)."""
    return str(date_str)[:7]


def _latest_valid(df, value_col: str = "今值"):
    """Return the latest row where value_col is not NaN/None (akshare DataFrames)."""
    import math
    for _, row in df.iloc[::-1].iterrows():
        v = row.get(value_col)
        try:
            if v is not None and not math.isnan(float(v)):
                return row
        except (TypeError, ValueError):
            pass
    return None


# ── Bond Yields (US + CN, akshare — data is up-to-date) ────────────────────

async def fetch_all_yields() -> Dict[str, Any]:
    """
    Fetch US and China Treasury benchmark yields via akshare bond_zh_us_rate.
    Returns:
      {
        "date": "2026-05-15",
        "us": [{"term": "2Y", "value": 4.09}, ...],
        "cn": [{"term": "2Y", "value": 1.27}, ...],
        "spread_10y": -2.82   # CN 10Y minus US 10Y
      }
    """
    cache_key = "macro:yields"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        start = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
        df = await _run_ak("bond_zh_us_rate", start_date=start)
        if df is None or df.empty:
            raise ValueError("empty DataFrame")

        latest = df.iloc[-1]
        date_str = _fmt_date(latest["日期"])

        def _get(col) -> Optional[float]:
            v = latest.get(col)
            try:
                f = float(v)
                return round(f, 4) if f == f else None
            except (TypeError, ValueError):
                return None

        us_yields, cn_yields = [], []
        for term, cn_col, us_col in [
            ("2Y",  "中国国债收益率2年",  "美国国债收益率2年"),
            ("5Y",  "中国国债收益率5年",  "美国国债收益率5年"),
            ("10Y", "中国国债收益率10年", "美国国债收益率10年"),
            ("30Y", "中国国债收益率30年", "美国国债收益率30年"),
        ]:
            cn_v = _get(cn_col)
            us_v = _get(us_col)
            if cn_v is not None:
                cn_yields.append({"term": term, "value": cn_v})
            if us_v is not None:
                us_yields.append({"term": term, "value": us_v})

        cn10 = next((y["value"] for y in cn_yields if y["term"] == "10Y"), None)
        us10 = next((y["value"] for y in us_yields if y["term"] == "10Y"), None)
        spread = round(cn10 - us10, 4) if (cn10 is not None and us10 is not None) else None

        result = {
            "date": date_str,
            "us": us_yields,
            "cn": cn_yields,
            "spread_10y": spread,
        }
        _set_cache(cache_key, result, CACHE_TTL_BONDS)
        logger.info(f"Yields loaded: date={date_str}, US10Y={us10}%, CN10Y={cn10}%")
        return result

    except Exception as e:
        logger.warning(f"fetch_all_yields error: {e}")
        return {}


# ── China CPI (EastMoney primary, akshare fallback) ─────────────────────────

async def fetch_cn_cpi() -> Dict[str, Any]:
    """
    China CPI YoY% and MoM%.
    Returns: {"period": "2026-04", "yoy": 1.2, "mom": 0.3, "prev": 1.0}
    """
    cache_key = "macro:cn_cpi"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        rows = await _fetch_eastmoney(
            "RPT_ECONOMY_CPI",
            "REPORT_DATE,NATIONAL_SAME,NATIONAL_SEQUENTIAL",
            page_size=2,
        )
        if not rows:
            raise ValueError("empty")
        row = rows[0]
        prev_row = rows[1] if len(rows) >= 2 else None
        result = {
            "period": _ym(row["REPORT_DATE"]),
            "yoy": round(float(row["NATIONAL_SAME"]), 2),
            "mom": round(float(row["NATIONAL_SEQUENTIAL"]), 2) if row.get("NATIONAL_SEQUENTIAL") is not None else None,
            "prev": round(float(prev_row["NATIONAL_SAME"]), 2) if prev_row else None,
        }
        _set_cache(cache_key, result, CACHE_TTL_MACRO)
        logger.info(f"CPI (EastMoney): {result}")
        return result
    except Exception as e:
        logger.warning(f"fetch_cn_cpi EastMoney error: {e}, falling back to akshare")
        return await _fetch_cn_cpi_akshare()


async def _fetch_cn_cpi_akshare() -> Dict[str, Any]:
    try:
        df = await _run_ak("macro_china_cpi_yearly")
        if df is None or df.empty:
            raise ValueError("empty")
        row = _latest_valid(df, "今值")
        if row is None:
            raise ValueError("no valid row")
        result = {
            "period": _fmt_date(row["日期"])[:7],
            "yoy": round(float(row["今值"]), 2),
            "mom": None,
            "prev": round(float(row["前值"]), 2) if row.get("前值") == row.get("前值") else None,
        }
        logger.info(f"CPI (akshare fallback): {result}")
        return result
    except Exception as e:
        logger.warning(f"fetch_cn_cpi akshare error: {e}")
        return {}


# ── China PPI (EastMoney primary, akshare fallback) ─────────────────────────

async def fetch_cn_ppi() -> Dict[str, Any]:
    """
    China PPI YoY% (BASE field is price index; yoy% = BASE - 100).
    Returns: {"period": "2026-04", "yoy": 2.8, "prev": 0.5}
    """
    cache_key = "macro:cn_ppi"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        rows = await _fetch_eastmoney(
            "RPT_ECONOMY_PPI",
            "REPORT_DATE,BASE,BASE_ACCUMULATE",
            page_size=2,
        )
        if not rows:
            raise ValueError("empty")
        row = rows[0]
        prev_row = rows[1] if len(rows) >= 2 else None
        yoy = round(float(row["BASE"]) - 100, 2)
        prev = round(float(prev_row["BASE"]) - 100, 2) if prev_row else None
        result = {
            "period": _ym(row["REPORT_DATE"]),
            "yoy": yoy,
            "prev": prev,
        }
        _set_cache(cache_key, result, CACHE_TTL_MACRO)
        logger.info(f"PPI (EastMoney): {result}")
        return result
    except Exception as e:
        logger.warning(f"fetch_cn_ppi EastMoney error: {e}, falling back to akshare")
        return await _fetch_cn_ppi_akshare()


async def _fetch_cn_ppi_akshare() -> Dict[str, Any]:
    try:
        df = await _run_ak("macro_china_ppi_yearly")
        if df is None or df.empty:
            raise ValueError("empty")
        row = _latest_valid(df, "今值")
        if row is None:
            raise ValueError("no valid row")
        result = {
            "period": _fmt_date(row["日期"])[:7],
            "yoy": round(float(row["今值"]), 2),
            "prev": round(float(row["前值"]), 2) if row.get("前值") == row.get("前值") else None,
        }
        logger.info(f"PPI (akshare fallback): {result}")
        return result
    except Exception as e:
        logger.warning(f"fetch_cn_ppi akshare error: {e}")
        return {}


# ── China PMI (EastMoney primary, akshare fallback) ─────────────────────────

async def fetch_cn_pmi() -> Dict[str, Any]:
    """
    China manufacturing + non-manufacturing PMI via EastMoney.
    MAKE_INDEX = manufacturing PMI (制造业)
    NMAKE_INDEX = non-manufacturing PMI (非制造业)

    Returns:
      {
        "mfg_period": "2026-04",
        "mfg_value": 50.3,
        "mfg_prev": 50.4,
        "mfg_source": "官方NBS",
        "svc_period": "2026-04",
        "svc_value": 49.4,
        "svc_prev": 50.1,
      }
    """
    cache_key = "macro:cn_pmi"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        rows = await _fetch_eastmoney(
            "RPT_ECONOMY_PMI",
            "REPORT_DATE,MAKE_INDEX,NMAKE_INDEX",
            page_size=2,
        )
        if not rows:
            raise ValueError("empty")
        row = rows[0]
        prev_row = rows[1] if len(rows) >= 2 else None
        period = _ym(row["REPORT_DATE"])
        result: Dict[str, Any] = {
            "mfg_period": period,
            "mfg_value":  float(row["MAKE_INDEX"]) if row.get("MAKE_INDEX") is not None else None,
            "mfg_prev":   float(prev_row["MAKE_INDEX"]) if prev_row and prev_row.get("MAKE_INDEX") is not None else None,
            "mfg_source": "官方NBS",
            "svc_period": period,
            "svc_value":  float(row["NMAKE_INDEX"]) if row.get("NMAKE_INDEX") is not None else None,
            "svc_prev":   float(prev_row["NMAKE_INDEX"]) if prev_row and prev_row.get("NMAKE_INDEX") is not None else None,
        }
        _set_cache(cache_key, result, CACHE_TTL_MACRO)
        logger.info(f"PMI (EastMoney): mfg={result['mfg_value']}, svc={result['svc_value']}")
        return result
    except Exception as e:
        logger.warning(f"fetch_cn_pmi EastMoney error: {e}, falling back to akshare")
        return await _fetch_cn_pmi_akshare()


async def _fetch_cn_pmi_akshare() -> Dict[str, Any]:
    mfg_official_task = _fetch_pmi_official_mfg()
    svc_task = _fetch_pmi_svc()
    caixin_task = _fetch_pmi_caixin()

    mfg_official, svc, caixin = await asyncio.gather(
        mfg_official_task, svc_task, caixin_task,
        return_exceptions=True,
    )

    mfg_official = mfg_official if not isinstance(mfg_official, Exception) else {}
    svc          = svc          if not isinstance(svc,          Exception) else {}
    caixin       = caixin       if not isinstance(caixin,        Exception) else {}

    if mfg_official.get("value") is not None:
        mfg = mfg_official
        mfg["source"] = "官方NBS"
    elif caixin.get("value") is not None:
        mfg = caixin
        mfg["source"] = "财新"
    else:
        mfg = {}

    result: Dict[str, Any] = {
        "mfg_period": mfg.get("period", ""),
        "mfg_value":  mfg.get("value"),
        "mfg_prev":   mfg.get("prev"),
        "mfg_source": mfg.get("source", ""),
        "svc_period": svc.get("period", ""),
        "svc_value":  svc.get("value"),
        "svc_prev":   svc.get("prev"),
    }
    return result


async def _fetch_pmi_official_mfg() -> Dict[str, Any]:
    try:
        df = await _run_ak("macro_china_pmi_yearly")
        if df is None or df.empty:
            return {}
        row = _latest_valid(df, "今值")
        if row is None:
            return {}
        return {
            "period": _fmt_date(row["日期"])[:7],
            "value":  round(float(row["今值"]), 1),
            "prev":   round(float(row["前值"]), 1) if row.get("前值") == row.get("前值") else None,
        }
    except Exception as e:
        logger.debug(f"Official mfg PMI error: {e}")
        return {}


async def _fetch_pmi_caixin() -> Dict[str, Any]:
    try:
        df = await _run_ak("index_pmi_man_cx")
        if df is None or df.empty:
            return {}
        import math
        valid_rows = df[df["制造业PMI"].apply(
            lambda v: v is not None and not math.isnan(float(v))
        )]
        if valid_rows.empty:
            return {}
        row = valid_rows.iloc[-1]
        prev_row = valid_rows.iloc[-2] if len(valid_rows) >= 2 else None
        return {
            "period": _fmt_date(row["日期"])[:7],
            "value":  round(float(row["制造业PMI"]), 1),
            "prev":   round(float(prev_row["制造业PMI"]), 1) if prev_row is not None else None,
        }
    except Exception as e:
        logger.debug(f"Caixin PMI error: {e}")
        return {}


async def _fetch_pmi_svc() -> Dict[str, Any]:
    try:
        df = await _run_ak("macro_china_non_man_pmi")
        if df is None or df.empty:
            return {}
        row = _latest_valid(df, "今值")
        if row is None:
            return {}
        return {
            "period": _fmt_date(row["日期"])[:7],
            "value":  round(float(row["今值"]), 1),
            "prev":   round(float(row["前值"]), 1) if row.get("前值") == row.get("前值") else None,
        }
    except Exception as e:
        logger.debug(f"Services PMI error: {e}")
        return {}


# ── Aggregate ───────────────────────────────────────────────────────────────

async def get_macro_data() -> Dict[str, Any]:
    """Fetch all macro indicators concurrently."""
    yields, cpi, ppi, pmi = await asyncio.gather(
        fetch_all_yields(),
        fetch_cn_cpi(),
        fetch_cn_ppi(),
        fetch_cn_pmi(),
        return_exceptions=True,
    )

    def _safe(v):
        return {} if isinstance(v, Exception) else (v or {})

    return {
        "yields": _safe(yields),
        "cn_cpi": _safe(cpi),
        "cn_ppi": _safe(ppi),
        "cn_pmi": _safe(pmi),
    }

"""Macro economic data service: US/CN Treasury yields, CPI, PPI, PMI.

Data sources (all via akshare, confirmed working):
  bond_zh_us_rate      → US + CN Treasury yields (single call, daily)
  macro_china_cpi_yearly   → China CPI YoY%
  macro_china_ppi_yearly   → China PPI YoY%
  macro_china_pmi_yearly   → Official NBS manufacturing PMI
  index_pmi_man_cx         → Caixin manufacturing PMI (more recent)
  macro_china_non_man_pmi  → Official NBS non-manufacturing PMI

Response column format for cpi/ppi/pmi_yearly/non_man_pmi:
  ['商品', '日期', '今值', '预测值', '前值']
  - 今值  = actual released value  (filter out NaN rows)
  - 前值  = previous period value
  - 日期  = datetime.date of the release announcement
"""
import time
import asyncio
import logging
from datetime import datetime, timedelta, date
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

_cache: Dict[str, tuple] = {}
CACHE_TTL_BONDS = 3600    # 1 hour
CACHE_TTL_MACRO = 43200   # 12 hours (monthly data)

_ak_sem = asyncio.Semaphore(2)


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


def _fmt_date(d) -> str:
    """Convert datetime.date or string to YYYY-MM-DD string."""
    if isinstance(d, date):
        return d.strftime("%Y-%m-%d")
    return str(d)[:10]


def _latest_valid(df, value_col: str = "今值"):
    """Return the latest row where value_col is not NaN/None."""
    import math
    for _, row in df.iloc[::-1].iterrows():
        v = row.get(value_col)
        try:
            if v is not None and not math.isnan(float(v)):
                return row
        except (TypeError, ValueError):
            pass
    return None


# ── Bond Yields (US + CN, single akshare call) ─────────────────────────────

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
                return round(f, 4) if f == f else None  # NaN check
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


# ── China CPI ───────────────────────────────────────────────────────────────

async def fetch_cn_cpi() -> Dict[str, Any]:
    """
    China CPI YoY% via macro_china_cpi_yearly.
    Returns: {"period": "2025-08-09", "yoy": 0.0, "prev": 0.1}
    """
    cache_key = "macro:cn_cpi"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        df = await _run_ak("macro_china_cpi_yearly")
        if df is None or df.empty:
            raise ValueError("empty")

        row = _latest_valid(df, "今值")
        if row is None:
            raise ValueError("no valid row")

        result = {
            "period": _fmt_date(row["日期"]),
            "yoy": round(float(row["今值"]), 2),
            "prev": round(float(row["前值"]), 2) if row.get("前值") == row.get("前值") else None,
        }
        _set_cache(cache_key, result, CACHE_TTL_MACRO)
        logger.info(f"CPI: {result}")
        return result

    except Exception as e:
        logger.warning(f"fetch_cn_cpi error: {e}")
        return {}


# ── China PPI ───────────────────────────────────────────────────────────────

async def fetch_cn_ppi() -> Dict[str, Any]:
    """
    China PPI YoY% via macro_china_ppi_yearly.
    Returns: {"period": "2025-08-09", "yoy": -3.6, "prev": -3.6}
    """
    cache_key = "macro:cn_ppi"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        df = await _run_ak("macro_china_ppi_yearly")
        if df is None or df.empty:
            raise ValueError("empty")

        row = _latest_valid(df, "今值")
        if row is None:
            raise ValueError("no valid row")

        result = {
            "period": _fmt_date(row["日期"]),
            "yoy": round(float(row["今值"]), 2),
            "prev": round(float(row["前值"]), 2) if row.get("前值") == row.get("前值") else None,
        }
        _set_cache(cache_key, result, CACHE_TTL_MACRO)
        logger.info(f"PPI: {result}")
        return result

    except Exception as e:
        logger.warning(f"fetch_cn_ppi error: {e}")
        return {}


# ── China PMI ───────────────────────────────────────────────────────────────

async def fetch_cn_pmi() -> Dict[str, Any]:
    """
    China manufacturing + non-manufacturing PMI.
    Primary for manufacturing: official NBS (macro_china_pmi_yearly)
    Fallback:                  Caixin (index_pmi_man_cx) — usually more recent
    Non-manufacturing:         macro_china_non_man_pmi

    Returns:
      {
        "mfg_period": "2025-08-31",
        "mfg_value": 49.4,
        "mfg_prev": 49.3,
        "mfg_source": "官方NBS" | "财新",
        "svc_period": "2025-08-31",
        "svc_value": 50.3,
        "svc_prev": 50.1,
      }
    """
    cache_key = "macro:cn_pmi"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    # Run manufacturing and services PMI in parallel
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

    # Choose manufacturing source: official if it has data, else Caixin
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

    if result["mfg_value"] is not None or result["svc_value"] is not None:
        _set_cache(cache_key, result, CACHE_TTL_MACRO)
        logger.info(f"PMI: mfg={result['mfg_value']} ({result['mfg_source']}), svc={result['svc_value']}")

    return result


async def _fetch_pmi_official_mfg() -> Dict[str, Any]:
    """Official NBS manufacturing PMI via macro_china_pmi_yearly."""
    try:
        df = await _run_ak("macro_china_pmi_yearly")
        if df is None or df.empty:
            return {}
        row = _latest_valid(df, "今值")
        if row is None:
            return {}
        return {
            "period": _fmt_date(row["日期"]),
            "value":  round(float(row["今值"]), 1),
            "prev":   round(float(row["前值"]), 1) if row.get("前值") == row.get("前值") else None,
        }
    except Exception as e:
        logger.debug(f"Official mfg PMI error: {e}")
        return {}


async def _fetch_pmi_caixin() -> Dict[str, Any]:
    """Caixin manufacturing PMI via index_pmi_man_cx (more recent data)."""
    try:
        df = await _run_ak("index_pmi_man_cx")
        if df is None or df.empty:
            return {}
        # columns: ['日期', '制造业PMI', '变化值']
        # Filter rows where 制造业PMI is valid
        import math
        valid_rows = df[df["制造业PMI"].apply(
            lambda v: v is not None and not math.isnan(float(v))
        )]
        if valid_rows.empty:
            return {}
        row = valid_rows.iloc[-1]
        prev_row = valid_rows.iloc[-2] if len(valid_rows) >= 2 else None
        return {
            "period": _fmt_date(row["日期"]),
            "value":  round(float(row["制造业PMI"]), 1),
            "prev":   round(float(prev_row["制造业PMI"]), 1) if prev_row is not None else None,
        }
    except Exception as e:
        logger.debug(f"Caixin PMI error: {e}")
        return {}


async def _fetch_pmi_svc() -> Dict[str, Any]:
    """Official NBS non-manufacturing PMI via macro_china_non_man_pmi."""
    try:
        df = await _run_ak("macro_china_non_man_pmi")
        if df is None or df.empty:
            return {}
        row = _latest_valid(df, "今值")
        if row is None:
            return {}
        return {
            "period": _fmt_date(row["日期"]),
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

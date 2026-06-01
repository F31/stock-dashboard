"""风险预警数据服务 — 所有数据来自 AKShare 免费接口"""
import asyncio, time, logging, math, threading
from datetime import date, timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _clean(obj):
    """递归将 nan / inf 转为 None，确保 JSON 序列化安全"""
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return obj


# ── 异步缓存（供 FastAPI handler 调用）─────────────────────────
_cache: Dict[str, Any] = {}
_locks: Dict[str, asyncio.Lock] = {}


def _lock(key: str) -> asyncio.Lock:
    if key not in _locks:
        _locks[key] = asyncio.Lock()
    return _locks[key]


def _is_trading_time() -> bool:
    """A股交易时段：周一至周五 09:00–15:30（不处理法定节假日，节假日本身不开盘数据不变）"""
    import datetime as _dt
    now = _dt.datetime.now()
    if now.weekday() >= 5:          # 周六=5, 周日=6
        return False
    t = now.time()
    return _dt.time(9, 0) <= t <= _dt.time(15, 30)


def _get(key: str, ttl: int):
    e = _cache.get(key)
    if not e:
        return None
    # 非交易时段：缓存永不过期，所有终端共享同一份数据
    if not _is_trading_time():
        return e["data"]
    effective_ttl = e.get("ttl") or ttl
    if (time.time() - e["ts"]) < effective_ttl:
        return e["data"]
    return None


def _set(key: str, data: Any, ttl: Optional[int] = None):
    _cache[key] = {"data": data, "ts": time.time(), "ttl": ttl}


async def _cached(key: str, ttl: int, fn):
    hit = _get(key, ttl)
    if hit is not None:
        return hit
    async with _lock(key):
        hit = _get(key, ttl)
        if hit is not None:
            return hit
        result = await asyncio.to_thread(fn)
        _set(key, result, ttl)
        return result


# ── 同步缓存（供 ThreadPoolExecutor 内的 worker 调用）──────────
_sync_cache: Dict[str, Any] = {}
_sync_lock_meta = threading.Lock()
_sync_locks: Dict[str, threading.Lock] = {}
FETCH_TIMEOUT = 25  # seconds — per raw data fetch


def _run_with_timeout(fn, timeout_s: int = FETCH_TIMEOUT):
    """Run fn() in a daemon thread. Raise TimeoutError if it doesn't finish in time."""
    _result = [None]
    _exc:   list = [None]

    def _target():
        try:
            _result[0] = fn()
        except Exception as e:
            _exc[0] = e

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        raise TimeoutError(f"raw data fetch timed out after {timeout_s}s")
    if _exc[0] is not None:
        raise _exc[0]
    return _result[0]


def _sync_cached(key: str, ttl: int, fn):
    def _fresh(e) -> bool:
        if not _is_trading_time():
            return True
        return (time.time() - e["ts"]) < ttl

    e = _sync_cache.get(key)
    if e and _fresh(e):
        return e["data"]

    with _sync_lock_meta:
        if key not in _sync_locks:
            _sync_locks[key] = threading.Lock()

    lock_timeout = FETCH_TIMEOUT + 3
    acquired = _sync_locks[key].acquire(timeout=lock_timeout)
    if not acquired:
        e = _sync_cache.get(key)
        if e:
            logger.warning("_sync_cached: lock timeout for %s — returning stale data", key)
            return e["data"]
        raise TimeoutError(f"_sync_cached: could not acquire lock for {key} in {lock_timeout}s")

    try:
        e = _sync_cache.get(key)
        if e and _fresh(e):
            return e["data"]
        data = _run_with_timeout(fn)
        _sync_cache[key] = {"data": data, "ts": time.time()}
        return data
    finally:
        _sync_locks[key].release()


# ── 原始数据层：所有重量级 AKShare 调用集中于此 ─────────────────

def _raw_gold():
    """黄金价格 — Sina 新浪 沪金期货主力 AU0 日线 — TTL 1h"""
    def _fetch():
        import akshare as ak
        import pandas as pd
        df = ak.futures_zh_daily_sina(symbol="AU0")
        if df is None or df.empty:
            raise ValueError("AU0 data empty")
        df = df[["date", "close"]].copy()
        df["date"]  = df["date"].astype(str)
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        return df.dropna()
    return _sync_cached("raw:gold", 3600, _fetch)


def _raw_us10y():
    """美国10Y国债收益率 — Sina 新浪数据 — TTL 1h"""
    def _fetch():
        import akshare as ak
        import pandas as pd
        df = ak.bond_gb_us_sina()
        if df is None or df.empty:
            raise ValueError("US bond data empty")
        df = df[["date", "close"]].copy()
        df["date"]  = df["date"].astype(str)
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        return df.dropna()
    return _sync_cached("raw:us10y", 3600, _fetch)


def _raw_cn_yields():
    """中国国债收益率曲线 — CCDC 中债登 1Y/10Y — TTL 4h"""
    def _fetch():
        import akshare as ak
        import pandas as pd
        start = (date.today() - timedelta(days=365)).strftime("%Y%m%d")
        end   = date.today().strftime("%Y%m%d")
        df = ak.bond_china_yield(start_date=start, end_date=end)
        gov = df[df["曲线名称"] == "中债国债收益率曲线"][["日期", "1年", "10年"]].copy()
        gov = gov.rename(columns={"日期": "date", "1年": "y1", "10年": "y10"})
        gov["y1"]  = pd.to_numeric(gov["y1"],  errors="coerce")
        gov["y10"] = pd.to_numeric(gov["y10"], errors="coerce")
        return gov.dropna().reset_index(drop=True)
    return _sync_cached("raw:cn_yields", 14400, _fetch)


def _raw_margin():
    """沪深两市合计融资余额 3 年历史（按日期升序）— TTL 1h"""
    def _fetch():
        import akshare as ak
        import pandas as pd
        start = (date.today() - timedelta(days=3 * 365)).strftime("%Y%m%d")
        end   = date.today().strftime("%Y%m%d")

        sse_df = ak.stock_margin_sse(start_date=start, end_date=end).sort_values("信用交易日期")
        sse_df = sse_df[["信用交易日期", "融资余额"]].copy()
        sse_df["融资余额"] = pd.to_numeric(sse_df["融资余额"], errors="coerce")

        try:
            szse_raw = ak.stock_margin_szse()
            date_col = next((c for c in szse_raw.columns if "日期" in c), None)
            szse_col = next((c for c in szse_raw.columns if "融资余额" in c), None)
            if date_col and szse_col:
                szse_df = szse_raw[[date_col, szse_col]].rename(
                    columns={date_col: "信用交易日期", szse_col: "融资余额"}
                ).sort_values("信用交易日期")
                szse_df["融资余额"] = pd.to_numeric(szse_df["融资余额"], errors="coerce")
                szse_df = szse_df[szse_df["信用交易日期"].astype(str) >= start]
                merged = pd.merge(sse_df, szse_df, on="信用交易日期", suffixes=("_sse", "_szse"), how="inner")
                merged["融资余额"] = merged["融资余额_sse"] + merged["融资余额_szse"]
                return merged[["信用交易日期", "融资余额"]].dropna()
        except Exception as e:
            logger.warning("SZSE margin fetch failed, using SSE only: %s", e)

        return sse_df.dropna()

    return _sync_cached("raw:margin", 3600, _fetch)


def _raw_csi300():
    """沪深300全量日线（Sina）— TTL 1h"""
    import akshare as ak
    return _sync_cached("raw:csi300", 3600,
        lambda: ak.stock_zh_index_daily(symbol="sh000300"))


def _raw_qvix():
    """50ETF期权 QVIX 日线历史 — TTL 30min"""
    import akshare as ak
    return _sync_cached("raw:qvix", 1800, ak.index_option_50etf_qvix)


# ── 1. 市场情绪：涨停 / 跌停 ─────────────────────────────────

def _parse_pct(s) -> Optional[float]:
    """'20.02%' / '-1.40' / None → float or None"""
    try:
        return float(str(s).replace("%", "").replace("+", "").strip())
    except (ValueError, TypeError):
        return None


_EM_HEADERS_SENT = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://data.eastmoney.com/",
}
_EM_SENT_URL = (
    "https://push2delay.eastmoney.com/api/qt/clist/get"
    "?pz=100&np=1&fltt=2&invt=2"
    "&ut=b2884a393a59ad64002292a3e90d46a5"
    "&fields=f3"
    "&fs=m:0+t:6+f:!2,m:0+t:13+f:!2,m:0+t:80+f:!2,m:1+t:2+f:!2,m:1+t:23+f:!2,m:0+t:7+f:!2,m:1+t:3+f:!2"
)


def _sentiment_em_fast() -> Optional[tuple]:
    """Primary-A: 东财 push2delay 分页拉取全市场涨跌（~53页 × 200ms ≈ 10s）。
    返回 (up, dn, flat, zt, dt) 或 None（不足 500 只视为失败）。
    """
    import requests
    session = requests.Session()
    all_pcts = []
    total_pages = None

    try:
        for pn in range(1, 70):  # 5288只 / 100 = ~53页，留余量
            url = f"{_EM_SENT_URL}&pn={pn}"
            r = session.get(url, headers=_EM_HEADERS_SENT, timeout=6)
            d = r.json()
            diff = d.get("data", {}).get("diff", [])
            if not diff:
                break
            if total_pages is None:
                total = d.get("data", {}).get("total", 0)
                total_pages = max(1, (total + 99) // 100)
            for x in diff:
                v = x.get("f3")
                if v not in (None, "-"):
                    try:
                        all_pcts.append(float(v))
                    except (ValueError, TypeError):
                        pass
            if total_pages and pn >= total_pages:
                break
    except Exception as e:
        logger.warning("sentiment EM fast pagination error: %s", e)
    finally:
        session.close()

    if len(all_pcts) < 500:
        return None

    up   = sum(1 for p in all_pcts if p > 0.05)
    dn   = sum(1 for p in all_pcts if p < -0.05)
    flat = len(all_pcts) - up - dn
    zt   = sum(1 for p in all_pcts if p >= 9.9)
    dt   = sum(1 for p in all_pcts if p <= -9.9)
    logger.info("sentiment EM fast: %d stocks, up=%d dn=%d zt=%d dt=%d", len(all_pcts), up, dn, zt, dt)
    return up, dn, flat, zt, dt


def _sentiment_sync():
    """
    主指标A（快速）：东财 push2delay 分页（~10s，稳定）
    主指标B：新浪全量快照 stock_zh_a_spot（~35s，可能被封）
    主指标C（备用）：stock_fund_flow_individual 即时资金流
    副指标：东财涨停/跌停/炸板池
    """
    import akshare as ak
    import os
    today = date.today().strftime("%Y%m%d")

    up_count = dn_count = flat_count = 0
    zt_limit = dt_limit = 0
    live_valid = False

    # ── 主指标A：东财 push2delay 分页（最快最稳，约10s）────────────────
    try:
        result = _run_with_timeout(_sentiment_em_fast, timeout_s=20)
        if result is not None:
            up_count, dn_count, flat_count, zt_limit, dt_limit = result
            live_valid = True
            logger.info("sentiment: EM push2delay up=%d dn=%d", up_count, dn_count)
    except Exception as e:
        logger.warning("sentiment EM fast error: %s", e)

    # ── 主指标B：新浪全量快照（被封时降级）────────────────────────────
    if not live_valid:
        try:
            env_bak = {k: os.environ.pop(k, None) for k in
                       ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"]}
            try:
                df_spot = _run_with_timeout(ak.stock_zh_a_spot, timeout_s=30)
            finally:
                for k, v in env_bak.items():
                    if v: os.environ[k] = v
            chg = df_spot["涨跌幅"]
            up_c = int((chg > 0).sum()); dn_c = int((chg < 0).sum())
            if up_c + dn_c >= 500:
                up_count, dn_count, flat_count = up_c, dn_c, int((chg == 0).sum())
                zt_limit = int((chg >= 9.9).sum()); dt_limit = int((chg <= -9.9).sum())
                live_valid = True
                logger.info("sentiment: sina spot up=%d dn=%d", up_count, dn_count)
        except Exception as e:
            logger.warning("stock_zh_a_spot error: %s", e)

    # ── 主指标C：资金流向全量（二次备用）────────────────────────────────
    if not live_valid:
        try:
            env_bak = {k: os.environ.pop(k, None) for k in
                       ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"]}
            try:
                df_ff = _run_with_timeout(
                    lambda: ak.stock_fund_flow_individual(symbol="即时"), timeout_s=25
                )
            finally:
                for k, v in env_bak.items():
                    if v: os.environ[k] = v

            chg_col = next((c for c in df_ff.columns if "涨跌幅" in c), None)
            if chg_col and len(df_ff) > 500:
                pcts = df_ff[chg_col].apply(_parse_pct).dropna()
                up_c = int((pcts > 0).sum()); dn_c = int((pcts < 0).sum())
                if up_c + dn_c >= 500:
                    up_count, dn_count, flat_count = up_c, dn_c, int((pcts == 0).sum())
                    zt_limit = int((pcts >= 9.9).sum()); dt_limit = int((pcts <= -9.9).sum())
                    live_valid = True
                    logger.info("sentiment: fund_flow fallback up=%d dn=%d", up_count, dn_count)
        except Exception as e:
            logger.warning("stock_fund_flow_individual sentiment error: %s", e)

    # ── 副指标：东财涨停/跌停/炸板池 ──────────────────────────────────
    zt_sealed = zt_broken = dt_pool = 0
    try:
        zt_sealed = len(ak.stock_zt_pool_em(date=today))
    except Exception as e:
        logger.warning("zt pool error: %s", e)
    try:
        zt_broken = len(ak.stock_zt_pool_zbgc_em(date=today))
    except Exception as e:
        logger.warning("zbgc pool error: %s", e)
    try:
        dt_pool = len(ak.stock_zt_pool_dtgc_em(date=today))
    except Exception as e:
        logger.warning("dt pool error: %s", e)

    # ── 情绪判断 ────────────────────────────────────────────────────────
    zt_total = zt_sealed + zt_broken
    broken_ratio = round(zt_broken / zt_total * 100, 1) if zt_total > 0 else 0.0

    if live_valid:
        data_source = "full_market"
        nonflat = up_count + dn_count
        ratio = round(up_count / nonflat * 100, 1) if nonflat > 0 else 50.0

        if ratio >= 75:
            label, level = "极度乐观", "danger"
        elif ratio >= 58:
            label, level = "偏乐观", "warning"
        elif ratio >= 42:
            label, level = "中性", "normal"
        elif ratio >= 25:
            label, level = "偏谨慎", "warning"
        else:
            label, level = "极度恐慌", "danger"

    elif zt_sealed + dt_pool > 0:
        data_source = "pool_only"
        ratio = None
        pool_total = zt_sealed + dt_pool
        pool_ratio = zt_sealed / pool_total * 100
        if pool_ratio >= 75:
            label, level = "偏乐观（池数据）", "warning"
        elif pool_ratio >= 40:
            label, level = "中性（池数据）", "normal"
        else:
            label, level = "偏谨慎（池数据）", "warning"

    else:
        data_source = "unavailable"
        ratio = None
        label, level = "数据暂不可用", "neutral"

    data_valid = live_valid or (zt_sealed + dt_pool > 0)
    return {
        "up_count":     up_count,
        "dn_count":     dn_count,
        "flat_count":   flat_count,
        "total":        up_count + dn_count + flat_count,
        "up_ratio":     ratio,
        "zt_limit":     zt_limit,
        "dt_limit":     dt_limit,
        "zt_sealed":    zt_sealed,
        "zt_broken":    zt_broken,
        "dt_pool":      dt_pool,
        "zt_count":     zt_sealed + zt_broken,
        "dt_count":     dt_pool,
        "zt_ratio":     ratio,
        "broken_ratio": broken_ratio,
        "label":        label,
        "level":        level,
        "data_source":  data_source,
        "live_valid":   live_valid,
        "data_valid":   data_valid,
        "date":         date.today().strftime("%Y-%m-%d"),
    }


async def fetch_sentiment():
    hit = _get("risk:sentiment", 1800)
    if hit is not None:
        return hit
    async with _lock("risk:sentiment"):
        hit = _get("risk:sentiment", 1800)
        if hit is not None:
            return hit
        result = await asyncio.to_thread(_sentiment_sync)
        if result.get("live_valid"):
            ttl = 1800
        elif result.get("data_valid"):
            ttl = 900
        else:
            ttl = 300
        _set("risk:sentiment", result, ttl)
        return result


# ── 2. 北向资金 ───────────────────────────────────────────────
# 注：净流向数据已于2024年9月停止公开发布

def _north_fund_sync():
    import akshare as ak
    try:
        df = ak.stock_hsgt_fund_flow_summary_em()
        north = df[df["资金方向"] == "北向"]
        up_total, down_total = 0, 0
        boards = []
        for _, r in north.iterrows():
            up = int(r.get("上涨数", 0) or 0)
            down = int(r.get("下跌数", 0) or 0)
            up_total += up
            down_total += down
            boards.append({"board": str(r.get("板块", "")), "up": up, "down": down})
        total = up_total + down_total
        up_ratio = round(up_total / total * 100, 1) if total > 0 else 0.0
    except Exception as e:
        logger.warning("north fund breadth error: %s", e)
        boards, up_total, down_total, up_ratio = [], 0, 0, 0.0

    return {
        "data_unavailable": True,
        "total_net": 0,
        "signal": "数据已停止发布",
        "level": "neutral",
        "up": up_total,
        "down": down_total,
        "up_ratio": up_ratio,
        "boards": boards,
        "date": str(date.today()),
    }


async def fetch_north_fund():
    return await _cached("risk:north_fund", 300, _north_fund_sync)


# ── 3. 融资余额（上交所，T+1）────────────────────────────────

def _margin_sync():
    df = _raw_margin().tail(10)

    latest_yi = float(df["融资余额"].iloc[-1]) / 1e8
    prev_yi   = float(df["融资余额"].iloc[-2]) / 1e8 if len(df) >= 2 else latest_yi
    chg = round(latest_yi - prev_yi, 1)

    trend = [
        {"date": str(r["信用交易日期"]), "balance": round(float(r["融资余额"]) / 1e8, 1)}
        for _, r in df.iterrows()
    ]
    level = "negative" if chg < -50 else ("positive" if chg > 50 else "neutral")

    data_date = df["信用交易日期"].iloc[-1]
    if hasattr(data_date, "date"):
        data_date = data_date.date()
    days_lag = (date.today() - data_date).days if hasattr(data_date, "year") else 0

    return {
        "latest":   round(latest_yi, 1),
        "chg":      chg,
        "level":    level,
        "trend":    trend,
        "date":     str(df["信用交易日期"].iloc[-1]),
        "days_lag": days_lag,
        "is_stale": days_lag > 7,
    }


async def fetch_margin():
    return await _cached("risk:margin", 3600, _margin_sync)


# ── 4. 大宗交易折价（T+1）────────────────────────────────────

def _block_trade_sync():
    """主：ak.stock_dzjy_mrtj（EM 汇总，含折溢率）
    备：ak.stock_dzjy_mrmx（EM 明细，无折溢率但更基础）
    """
    import akshare as ak
    today     = date.today().strftime("%Y%m%d")
    yesterday = (date.today() - timedelta(days=3)).strftime("%Y%m%d")

    df = None
    # 主方案
    try:
        df = _run_with_timeout(
            lambda: ak.stock_dzjy_mrtj(start_date=yesterday, end_date=today),
            timeout_s=20
        )
    except Exception as e:
        logger.warning("block trade primary (dzjy_mrtj) failed: %s — trying fallback", e)

    # 备用方案：股票级别明细，折溢率需自行计算
    if df is None or len(df) == 0:
        try:
            df_raw = _run_with_timeout(
                lambda: ak.stock_dzjy_mrmx(start_date=yesterday, end_date=today),
                timeout_s=20
            )
            if df_raw is not None and len(df_raw) > 0:
                # 标准化字段名以便下方解析复用
                df_raw = df_raw.rename(columns={
                    "证券代码": "证券代码", "证券简称": "证券简称",
                    "成交价": "成交价", "成交总量": "成交总量", "成交总额": "成交总额",
                })
                df = df_raw
                logger.info("block trade: using fallback source (dzjy_mrmx)")
        except Exception as e2:
            logger.warning("block trade fallback also failed: %s", e2)

    if df is None or len(df) == 0:
        return {"items": [], "date": today}

    items = []
    for _, r in df.iterrows():
        discount = 0.0
        for col in ("折溢率", "折溢价率", "折价率", "溢价率"):
            if col in r.index and r[col] is not None:
                try:
                    discount = float(r[col]) * 100
                    break
                except (ValueError, TypeError):
                    pass
        amount = round(float(r.get("成交总额", r.get("成交额", 0)) or 0), 1)
        items.append({
            "date":       str(r.get("交易日期", "")),
            "code":       str(r.get("证券代码", "")),
            "name":       str(r.get("证券简称", "")),
            "change_pct": float(r.get("涨跌幅", 0) or 0),
            "amount":     amount,
            "discount":   round(discount, 2),
        })

    items.sort(key=lambda x: x["discount"])
    return {"items": items[:20], "date": today}


async def fetch_block_trades():
    return await _cached("risk:block_trades", 1800, _block_trade_sync)


# ── 5. 龙虎榜（T+1）─────────────────────────────────────────

def _lhb_sync():
    """主：ak.stock_lhb_detail_em（东财详情）
    备：ak.stock_lhb_stock_detail_em 按个股汇总
    lookback=7天确保覆盖周末/节假日，始终能拿到最近交易日数据。
    """
    import akshare as ak
    today = date.today().strftime("%Y%m%d")
    start = (date.today() - timedelta(days=7)).strftime("%Y%m%d")

    df = None
    try:
        df = _run_with_timeout(
            lambda: ak.stock_lhb_detail_em(start_date=start, end_date=today),
            timeout_s=20
        )
    except Exception as e:
        logger.warning("lhb primary (lhb_detail_em) failed: %s — trying fallback", e)

    # 备用：stock_lhb_stock_detail_em 按个股汇总
    if df is None or len(df) == 0:
        try:
            df = _run_with_timeout(
                lambda: ak.stock_lhb_stock_detail_em(start_date=start, end_date=today),
                timeout_s=20
            )
            logger.info("lhb: using fallback source (lhb_stock_detail_em)")
        except Exception as e2:
            logger.warning("lhb fallback also failed: %s", e2)

    if df is None or len(df) == 0:
        return {"items": [], "date": today}

    seen: set = set()
    items = []
    for _, r in df.iterrows():
        code = str(r.get("代码", r.get("股票代码", "")))
        if code in seen:
            continue
        seen.add(code)
        chg = 0.0
        for col in ("涨跌幅", "涨跌", "区间涨跌幅"):
            if col in r.index:
                try:
                    chg = float(r[col] or 0)
                    break
                except (ValueError, TypeError):
                    pass
        items.append({
            "date":       str(r.get("上榜日", r.get("日期", ""))),
            "code":       code,
            "name":       str(r.get("名称", r.get("股票名称", ""))),
            "reason":     str(r.get("解读", r.get("上榜原因", ""))),
            "change_pct": chg,
        })

    return {"items": items[:20], "date": today}


async def fetch_lhb():
    return await _cached("risk:lhb", 1800, _lhb_sync)


# ── 6. 宏观风险：黄金 / 国债 / 汇率 ────────────────────────

def _macro_risk_sync():
    import akshare as ak
    result: Dict[str, Any] = {}

    try:
        gdf    = _raw_gold().tail(6)
        latest = float(gdf["close"].iloc[-1])
        base   = float(gdf["close"].iloc[0])
        chg5   = round((latest - base) / base * 100, 2)
        result["gold"] = {
            "price": latest,
            "chg5":  chg5,
            "date":  str(gdf["date"].iloc[-1]),
            "level": "warning" if abs(chg5) > 2 else "neutral",
        }
    except Exception as e:
        logger.warning("Gold fetch error: %s", e)
        result["gold"] = None

    us10 = us10_chg = us_date = None
    try:
        us_df    = _raw_us10y().tail(6)
        us10     = float(us_df["close"].iloc[-1])
        us10_chg = round(us10 - float(us_df["close"].iloc[0]), 4)
        us_date  = str(us_df["date"].iloc[-1])
    except Exception as e:
        logger.warning("US10Y fetch error: %s", e)

    cn10 = cn10_chg = cn_date = None
    try:
        cn_df    = _raw_cn_yields().tail(6)
        cn10     = float(cn_df["y10"].iloc[-1])
        cn10_chg = round(cn10 - float(cn_df["y10"].iloc[0]), 4)
        cn_date  = str(cn_df["date"].iloc[-1])
    except Exception as e:
        logger.warning("CN bond fetch error: %s", e)

    if us10 is not None or cn10 is not None:
        result["bonds"] = {
            "cn10":      round(cn10, 4) if cn10 is not None else None,
            "us10":      round(us10, 4) if us10 is not None else None,
            "cn10_chg5": cn10_chg,
            "us10_chg5": us10_chg,
            "date":      us_date or cn_date,
            "us10_level": "negative" if (us10 or 0) > 4.5 else ("warning" if (us10 or 0) > 4.0 else "neutral"),
        }
    else:
        result["bonds"] = None

    try:
        fdf = ak.fx_spot_quote()
        usd_rows = fdf[fdf["货币对"].str.contains("USD", case=False, na=False)]
        cny_rate = None
        for _, r in usd_rows.iterrows():
            mid = (float(r["买报价"]) + float(r["卖报价"])) / 2
            if 6.0 <= mid <= 8.5:
                cny_rate = {"pair": r["货币对"], "rate": round(mid, 4)}
                break
        result["cny"] = cny_rate
    except Exception as e:
        logger.warning("FX fetch error: %s", e)
        result["cny"] = None

    return _clean(result)


async def fetch_macro_risk():
    return await _cached("risk:macro", 3600, _macro_risk_sync)


# ── 7. 近期限售股解禁压力（未来 21 天 + 7 天明细）────────────
# 历史数据拆分为独立缓存，避免3次串行AKShare调用超时前端30s限制

def _restricted_main_sync():
    """未来解禁：汇总(21天) + 明细(7天)，2次AKShare调用，通常 < 10s"""
    import akshare as ak
    today = date.today()
    start = today.strftime("%Y%m%d")
    end21 = (today + timedelta(days=21)).strftime("%Y%m%d")
    end7  = (today + timedelta(days=7)).strftime("%Y%m%d")

    summary = []
    try:
        df = _run_with_timeout(
            lambda: ak.stock_restricted_release_summary_em(start_date=start, end_date=end21),
            timeout_s=20
        )
        for _, r in df.iterrows():
            mv = float(r.get("实际解禁市值", 0) or 0) / 1e8
            summary.append({
                "date":         str(r.get("解禁时间", "")),
                "count":        int(r.get("当日解禁股票家数", 0) or 0),
                "market_value": round(mv, 1),
            })
    except Exception as e:
        logger.warning("restricted summary error: %s", e)

    detail = []
    try:
        df2 = _run_with_timeout(
            lambda: ak.stock_restricted_release_detail_em(start_date=start, end_date=end7),
            timeout_s=20
        )
        for _, r in df2.iterrows():
            mv    = float(r.get("实际解禁市值", 0) or 0) / 1e8
            ratio = float(r.get("占解禁前流通市值比例", 0) or 0) * 100
            detail.append({
                "date":         str(r.get("解禁时间", "")),
                "code":         str(r.get("股票代码", "")),
                "name":         str(r.get("股票简称", "")),
                "type":         str(r.get("限售股类型", "")),
                "market_value": round(mv, 2),
                "ratio":        round(ratio, 2),
            })
        detail.sort(key=lambda x: (x["date"], -x["market_value"]))
    except Exception as e:
        logger.warning("restricted detail error: %s", e)

    return {
        "summary": summary,
        "detail":  detail[:30],
        "date":    today.strftime("%Y-%m-%d"),
    }


def _restricted_history_sync():
    """历史解禁：近 31 天已解禁个股（含前后20日涨跌幅）— 独立缓存，TTL 4h"""
    import akshare as ak
    today = date.today()
    hist_start = (today - timedelta(days=31)).strftime("%Y%m%d")
    hist_end   = (today - timedelta(days=1)).strftime("%Y%m%d")

    history = []
    try:
        df3 = _run_with_timeout(
            lambda: ak.stock_restricted_release_detail_em(start_date=hist_start, end_date=hist_end),
            timeout_s=25
        )
        for _, r in df3.iterrows():
            mv    = float(r.get("实际解禁市值", 0) or 0) / 1e8
            ratio = float(r.get("占解禁前流通市值比例", 0) or 0) * 100
            def _pct(col):
                v = r.get(col)
                try:
                    return round(float(v), 2) if v is not None and str(v) not in ("", "nan") else None
                except (ValueError, TypeError):
                    return None
            history.append({
                "date":         str(r.get("解禁时间", "")),
                "code":         str(r.get("股票代码", "")),
                "name":         str(r.get("股票简称", "")),
                "type":         str(r.get("限售股类型", "")),
                "market_value": round(mv, 2),
                "ratio":        round(ratio, 2),
                "pre20_chg":    _pct("解禁前20日涨跌幅"),
                "post20_chg":   _pct("解禁后20日涨跌幅"),
            })
        history.sort(key=lambda x: (x["date"], -x["market_value"]), reverse=True)
    except Exception as e:
        logger.warning("restricted history error: %s", e)

    return {"history": history[:60], "date": date.today().strftime("%Y-%m-%d")}


async def fetch_restricted():
    return await _cached("risk:restricted", 3600, _restricted_main_sync)


async def fetch_restricted_history():
    return await _cached("risk:restricted_history", 14400, _restricted_history_sync)


# ── 启动预热：T+1 数据（不随交易时间变化，一天只需拉一次）─────
async def prefetch_risk_t1():
    """服务启动后台预热：将大宗交易、龙虎榜、解禁压力缓存提前填充。
    这些数据 T+1 更新，一天内不变，避免第一个用户请求等待 10-20s。
    """
    await asyncio.sleep(15)   # 等服务器完全就绪
    logger.info("Risk T+1 prefetch started")
    tasks = [
        ("block_trades", fetch_block_trades),
        ("lhb",          fetch_lhb),
        ("restricted",   fetch_restricted),
    ]
    for name, fn in tasks:
        try:
            await fn()
            logger.info("Risk T+1 prefetch OK: %s", name)
        except Exception as e:
            logger.warning("Risk T+1 prefetch failed [%s]: %s", name, e)

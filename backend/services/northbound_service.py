"""北向资金数据服务 — 多源自动回退 + UA轮换 + 随机延迟。

数据源（依次尝试）：
  1. Tushare moneyflow_hsgt（24h缓存，免费版1次/分钟，但对我们足够了）
  2. EM push2his KAMT kline（沪股通+深股通额度余额走势）
  3. AKShare stock_hsgt_hist_em（历史数据，最新到2024-08）

每日净买入 = 累计值的差分。返回最近48个交易日的数据。
"""
import asyncio
import logging
import sys
from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd

_STOCK_QUAN = "/root/projects/stock_quan"
if _STOCK_QUAN not in sys.path:
    sys.path.insert(0, _STOCK_QUAN)

logger = logging.getLogger(__name__)

_cache: Dict[str, tuple] = {}
CACHE_TTL = 86400  # 24小时
_fetch_lock = asyncio.Lock()


async def get_northbound_flow() -> Dict[str, Any]:
    cache_key = "northbound_flow"
    now = datetime.now()

    if cache_key in _cache:
        data, ts = _cache[cache_key]
        if (now - ts).total_seconds() < CACHE_TTL:
            return data

    async with _fetch_lock:
        if cache_key in _cache:
            data, ts = _cache[cache_key]
            if (now - ts).total_seconds() < CACHE_TTL:
                return data

        try:
            data = await _fetch_multi_source()
            _cache[cache_key] = (data, now)
            n = len(data.get("dates", []))
            logger.info("北向资金刷新: %d天, 最后更新=%s", n, data.get("last_update"))
            return data
        except Exception as e:
            logger.error("北向资金获取失败: %s", e)
            if cache_key in _cache:
                return _cache[cache_key][0]
            return _empty()


async def _fetch_multi_source() -> Dict[str, Any]:
    """多源依次尝试。"""
    # 1. Tushare
    result = await _try_source("Tushare", _fetch_tushare())
    if result and result.get("dates"):
        return result
    # 2. EM push2his
    result = await _try_source("EM push2his", _fetch_em_push2his())
    if result and result.get("dates"):
        return result
    # 3. AKShare
    result = await _try_source("AKShare", _fetch_akshare())
    if result and result.get("dates"):
        return result
    raise RuntimeError("所有北向数据源均失败")


async def _try_source(name: str, coro) -> Optional[Dict]:
    try:
        return await coro
    except Exception as e:
        logger.warning("北向数据源 %s 失败: %s", name, e)
        return None


# ── 数据源 1: Tushare ───────────────────────────────────────────────────────────

async def _fetch_tushare() -> Optional[Dict[str, Any]]:
    from core.data_sources import tushare_call

    def _do():
        return tushare_call("moneyflow_hsgt", start_date="20260101",
                            end_date=datetime.now().strftime("%Y%m%d"))

    loop = asyncio.get_event_loop()
    df = await loop.run_in_executor(None, _do)
    if df is None or len(df) < 5:
        return None

    df = df.sort_values("trade_date").reset_index(drop=True)
    df["sh_net"] = df["hgt"].diff()
    df["sz_net"] = df["sgt"].diff()
    df["total_net"] = df["north_money"].diff()
    df = df.dropna(subset=["total_net"]).tail(48)

    dates = df["trade_date"].tolist()
    return {
        "dates": dates,
        "sh_net_buy": [round(float(v), 2) for v in df["sh_net"]],
        "sz_net_buy": [round(float(v), 2) for v in df["sz_net"]],
        "total_net_buy": [round(float(v), 2) for v in df["total_net"]],
        "sh_cumulative": [round(float(v), 2) for v in df["hgt"]],
        "sz_cumulative": [round(float(v), 2) for v in df["sgt"]],
        "total_cumulative": [round(float(v), 2) for v in df["north_money"]],
        "last_update": dates[-1],
    }


# ── 数据源 2: EM push2his KAMT API（含UA轮换+随机延迟） ──────────────────────────

async def _fetch_em_push2his() -> Optional[Dict[str, Any]]:
    from core.crawler import crawler
    import random, time as _time, json as _json

    async def _get(secid: int, key: str, retries: int = 2) -> list:
        url = "https://push2his.eastmoney.com/api/qt/kamt.kline.get"
        params = {"fields1": "f1,f2,f3,f4", "fields2": "f51,f52,f53,f54,f55",
                   "klt": "101", "lmt": "60", "secid": str(secid)}
        for attempt in range(retries):
            try:
                loop = asyncio.get_event_loop()
                data = await loop.run_in_executor(
                    None, lambda: crawler.get_json(url, params=params))
                return data.get("data", {}).get(key, [])
            except Exception as e:
                logger.debug("EM push2his 第%d次尝试 secid=%d 失败: %s",
                             attempt + 1, secid, e)
                if attempt < retries - 1:
                    await asyncio.sleep(random.uniform(1.0, 2.5))
        return []

    raw_sh, raw_sz = await asyncio.gather(_get(1, "hk2sh"), _get(2, "hk2sz"))
    if not raw_sh or not raw_sz:
        logger.warning("EM push2his: sh=%d klines, sz=%d klines", len(raw_sh), len(raw_sz))
        return None

    # 解析 kline 格式: date, net_buy, quota_balance, cum_buy
    # 非交易时段 net_buy=0, 取累计值的差分作为日净买入
    def _parse(klines):
        dates, cum = [], []
        for k in reversed(klines):
            parts = k.split(",")
            if len(parts) >= 4:
                try:
                    d, cm = parts[0], float(parts[3])
                    dates.append(d)
                    cum.append(cm)
                except (ValueError, IndexError):
                    continue
        # 计算每日净买入 = 累计差分
        net = [0.0]
        for i in range(1, len(cum)):
            net.append(round(cum[i] - cum[i - 1], 2))
        return dates, net, cum

    sh_dates, sh_net, sh_cum = _parse(raw_sh)
    sz_dates, sz_net, sz_cum = _parse(raw_sz)

    # 合并日期
    sh_map = dict(zip(sh_dates, zip(sh_net, sh_cum)))
    sz_map = dict(zip(sz_dates, zip(sz_net, sz_cum)))
    all_dates = sorted(set(sh_dates) & set(sz_dates))
    if len(all_dates) < 10:
        return None

    all_dates = all_dates[-48:]
    sh_nb = [sh_map[d][0] for d in all_dates]
    sz_nb = [sz_map[d][0] for d in all_dates]
    sh_c_list = [sh_map[d][1] for d in all_dates]
    sz_c_list = [sz_map[d][1] for d in all_dates]

    return {
        "dates": all_dates,
        "sh_net_buy": sh_nb,
        "sz_net_buy": sz_nb,
        "total_net_buy": [round(s + z, 2) for s, z in zip(sh_nb, sz_nb)],
        "sh_cumulative": sh_c_list,
        "sz_cumulative": sz_c_list,
        "total_cumulative": [round(s + z, 2) for s, z in zip(sh_c_list, sz_c_list)],
        "last_update": all_dates[-1],
    }


# ── 数据源 3: AKShare（历史数据到2024-08，之后可能NaN） ──────────────────────────

async def _fetch_akshare() -> Optional[Dict[str, Any]]:
    import akshare as ak

    async def _get(symbol):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, ak.stock_hsgt_hist_em, symbol)

    try:
        df_sh, df_sz = await asyncio.gather(_get("沪股通"), _get("深股通"))
    except Exception as e:
        logger.warning("AKShare 北向获取失败: %s", e)
        return None

    if df_sh is None or df_sz is None:
        return None

    df_sh = df_sh[["日期", "当日成交净买额", "历史累计净买额"]].copy()
    df_sh.columns = ["date", "sh_net", "sh_cum"]
    df_sz = df_sz[["日期", "当日成交净买额", "历史累计净买额"]].copy()
    df_sz.columns = ["date", "sz_net", "sz_cum"]

    merged = pd.merge(df_sh, df_sz, on="date", how="outer").sort_values("date")
    merged = merged.dropna(subset=["sh_cum", "sz_cum"], how="all")
    if len(merged) < 10:
        return None

    merged = merged.tail(48)
    merged["total_net"] = merged["sh_net"].fillna(0) + merged["sz_net"].fillna(0)
    merged["total_cum"] = merged["sh_cum"].fillna(0) + merged["sz_cum"].fillna(0)

    # Date is string type from AKShare
    dates = merged["date"].tolist()

    def _cln(col):
        return [round(float(v), 2) if pd.notna(v) else 0 for v in col]

    return {
        "dates": dates,
        "sh_net_buy": _cln(merged["sh_net"]),
        "sz_net_buy": _cln(merged["sz_net"]),
        "total_net_buy": _cln(merged["total_net"]),
        "sh_cumulative": _cln(merged["sh_cum"]),
        "sz_cumulative": _cln(merged["sz_cum"]),
        "total_cumulative": _cln(merged["total_cum"]),
        "last_update": dates[-1],
    }


def _empty() -> Dict[str, Any]:
    return {"dates": [], "sh_net_buy": [], "sz_net_buy": [],
            "total_net_buy": [], "sh_cumulative": [], "sz_cumulative": [],
            "total_cumulative": [], "last_update": None}


def clear_northbound_cache() -> None:
    _cache.pop("northbound_flow", None)
    logger.info("北向资金缓存已清除")

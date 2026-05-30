"""风险雷达图服务 — 6维度风险评分（0=低风险，100=高风险）

维度：
  1. 情绪温度   — 全市场上涨比（反向情绪；炸板率高则压低分值）
                  主A：新浪 stock_zh_a_spot；主B（备用）：stock_fund_flow_individual 涨跌幅列
  2. 杠杆水位   — 沪深两市合计融资余额3年历史分位 × 70% + 5日变化动量 × 30%
  3. 宏观金融   — 美债10Y固定阈值 × 60% + 黄金5日涨幅 × 40%
  4. 技术超买   — 沪深300偏离MA250分位 × 60% + RSI14 × 40%
  5. 曲线斜率   — CN10Y-CN1Y利差历史分位（倒置：陡峭=低风险，平坦/倒挂=高风险）
                  注：CCDC无2Y数据，用1Y替代（利差方向一致）
  6. 期权波动率  — QVIX历史分位（含实时分钟数据修正）

所有原始数据通过 risk_service 的共享原始数据层获取，同一进程内的多个并行
worker 共用一份 _sync_cached 数据，消除重复 HTTP 请求。
"""
import asyncio, time, logging
from datetime import date
from typing import Any, Dict, Optional
from services.risk_service import _is_trading_time

logger = logging.getLogger(__name__)

_cache: Dict[str, Any] = {}
_locks: Dict[str, asyncio.Lock] = {}


def _lock(key: str) -> asyncio.Lock:
    if key not in _locks:
        _locks[key] = asyncio.Lock()
    return _locks[key]


def _get(key: str, ttl: Optional[int] = None):
    e = _cache.get(key)
    if not e:
        return None
    if not _is_trading_time():
        return e["data"]
    effective_ttl = ttl if ttl is not None else e.get("ttl", 1800)
    if (time.time() - e["ts"]) < effective_ttl:
        return e["data"]
    return None


def _set(key: str, data: Any, ttl: int = 1800):
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


def _percentile(series, value: float) -> float:
    """historical percentile of value in series (0–100)"""
    if not series:
        return 50.0
    below = sum(1 for v in series if v <= value)
    return round(below / len(series) * 100, 1)


# ── 1. 情绪温度 ──────────────────────────────────────────────

def _score_sentiment(up_ratio: Optional[float], zt_sealed: int, dt_pool: int,
                     broken_ratio: float = 0.0) -> float:
    """
    情绪评分（0=低风险, 100=高风险）采用反向情绪逻辑：
    - 全市场上涨比越高 → 乐观泡沫风险越大 → 分值越高
    - 炸板率越高 → 情绪崩溃信号 → 压低分值（市场已在泄压）
    """
    if up_ratio is not None:
        if up_ratio >= 75:   base = 95.0
        elif up_ratio >= 58: base = 65.0
        elif up_ratio >= 42: base = 40.0
        elif up_ratio >= 25: base = 20.0
        else:                base = 5.0

        # 炸板率修正：炸板率 ≥ 50% 说明情绪快速降温，下调最多 15 分
        broken_adj = min(15.0, broken_ratio * 0.3)
        return round(max(0.0, base - broken_adj), 1)

    # 降级：仅有涨停/跌停池数据
    total = zt_sealed + dt_pool
    if total == 0:
        return 50.0
    ratio = zt_sealed / total * 100
    if ratio >= 75: return 90.0
    if ratio >= 58: return 60.0
    if ratio >= 42: return 40.0
    return 20.0


# ── 2. 杠杆水位 ──────────────────────────────────────────────

def _score_leverage_sync() -> Dict:
    from services.risk_service import _raw_margin
    df = _raw_margin()  # 已排序的3年融资余额，与 _margin_sync 共享同一次请求

    series = df["融资余额"].astype(float).tolist()
    latest = series[-1]
    prev5  = series[-6] if len(series) >= 6 else series[0]

    pct = _percentile(series[:-1], latest)

    import statistics
    diffs = [series[i] - series[i-1] for i in range(1, len(series))]
    std = statistics.stdev(diffs) if len(diffs) > 1 else 1
    momentum_pct = min(100, max(0, ((latest - prev5) / (std * 5) + 1) / 2 * 100))

    score = round(pct * 0.7 + momentum_pct * 0.3, 1)
    return {"score": score, "pct": pct, "latest_yi": round(latest / 1e8, 1)}


# ── 3. 宏观金融压力 ──────────────────────────────────────────

def _score_macro_sync() -> Dict:
    from services.risk_service import _raw_us10y, _raw_gold

    us10_score = 50.0
    gold_score = 50.0
    us10_val   = None   # 实际利率值
    gold_chg5  = None   # 黄金5日涨跌幅%

    try:
        us10 = float(_raw_us10y().tail(6)["close"].iloc[-1])
        us10_val = round(us10, 2)
        if us10 >= 5.0:   us10_score = 90.0
        elif us10 >= 4.5: us10_score = 70.0
        elif us10 >= 4.0: us10_score = 50.0
        elif us10 >= 3.5: us10_score = 30.0
        else:             us10_score = 15.0
    except Exception as e:
        logger.warning("radar macro US10Y error: %s", e)

    try:
        gdf   = _raw_gold().tail(6)
        chg5  = (float(gdf["close"].iloc[-1]) - float(gdf["close"].iloc[0])) / float(gdf["close"].iloc[0]) * 100
        gold_chg5 = round(chg5, 2)
        if chg5 >= 5:    gold_score = 90.0
        elif chg5 >= 3:  gold_score = 70.0
        elif chg5 >= 1:  gold_score = 55.0
        elif chg5 >= -1: gold_score = 40.0
        else:            gold_score = 20.0
    except Exception as e:
        logger.warning("radar macro gold error: %s", e)

    return {
        "score":      round(us10_score * 0.6 + gold_score * 0.4, 1),
        "us10_score": us10_score,
        "gold_score": gold_score,
        "us10_val":   us10_val,
        "gold_chg5":  gold_chg5,
    }


# ── 4. 技术超买 ──────────────────────────────────────────────

def _score_technical_sync() -> Dict:
    from services.risk_service import _raw_csi300

    ma250_score = rsi_score = 50.0
    rsi_val    = None   # RSI14 实际值
    ma250_dev  = None   # 较MA250偏离%

    try:
        closes = _raw_csi300()["close"].astype(float).tolist()
        if len(closes) < 250:
            raise ValueError("insufficient data")

        latest = closes[-1]
        ma250  = sum(closes[-250:]) / 250
        ma250_dev = round((latest - ma250) / ma250 * 100, 2)

        deviations = []
        for i in range(250, len(closes)):
            ma = sum(closes[i-250:i]) / 250
            deviations.append((closes[i] - ma) / ma * 100)

        ma250_score = _percentile(deviations[:-1], ma250_dev)

        # RSI14
        gains  = [max(0, closes[i] - closes[i-1]) for i in range(len(closes) - 14, len(closes))]
        losses = [max(0, closes[i-1] - closes[i]) for i in range(len(closes) - 14, len(closes))]
        avg_loss = sum(losses) / 14
        rsi = 100.0 if avg_loss == 0 else 100 - 100 / (1 + sum(gains) / 14 / avg_loss)
        rsi_val = round(rsi, 1)

        if rsi >= 80:   rsi_score = 90.0
        elif rsi >= 70: rsi_score = 72.0
        elif rsi >= 60: rsi_score = 55.0
        elif rsi >= 40: rsi_score = 38.0
        elif rsi >= 30: rsi_score = 22.0
        else:           rsi_score = 10.0

    except Exception as e:
        logger.warning("radar technical error: %s", e)

    return {
        "score":      round(ma250_score * 0.6 + rsi_score * 0.4, 1),
        "ma250_score": ma250_score,
        "rsi_score":   rsi_score,
        "rsi":         rsi_val,
        "ma250_dev":   ma250_dev,
    }


# ── 5. 收益率曲线斜率 ─────────────────────────────────────────

def _score_yield_curve_sync() -> Dict:
    from services.risk_service import _raw_cn_yields

    try:
        df = _raw_cn_yields()
        slopes = (df["y10"].astype(float) - df["y1"].astype(float)).tolist()
        if len(slopes) < 10:
            return {"score": 50.0, "slope": None, "pct": None}

        current_slope = slopes[-1]
        pct   = _percentile(slopes[:-1], current_slope)
        score = round((1 - pct / 100) * 100, 1)  # 倒置：陡峭=低风险，倒挂=高风险
        return {"score": score, "slope": round(current_slope, 4), "pct": pct}
    except Exception as e:
        logger.warning("radar yield curve error: %s", e)
        return {"score": 50.0, "slope": None, "pct": None}


# ── 6. 期权隐含波动率（QVIX）────────────────────────────────

def _score_qvix_sync() -> Dict:
    import akshare as ak
    from services.risk_service import _raw_qvix

    try:
        hist_values = _raw_qvix()["close"].astype(float).tolist()

        try:
            mdf   = ak.index_option_50etf_min_qvix()
            valid = mdf["qvix"].dropna()
            current = float(valid.iloc[-1]) if len(valid) > 0 else hist_values[-1]
        except Exception:
            current = hist_values[-1]

        pct   = _percentile(hist_values, current)
        return {"score": round(pct, 1), "qvix": round(current, 2), "pct": pct}
    except Exception as e:
        logger.warning("radar qvix error: %s", e)
        return {"score": 50.0, "qvix": None, "pct": None}


# ── 汇总雷达数据 ─────────────────────────────────────────────

def _radar_sync() -> Dict:
    import concurrent.futures
    from services.risk_service import _get as risk_get, _clean

    # 情绪：优先读缓存（30min内有效）。
    # 缓存为空时只做快速池数据查询（<2s），不触发 stock_zh_a_spot（~20s）。
    # 完整情绪数据由情绪面板的独立请求负责填充，避免双重 Sina 请求。
    cached_sent = risk_get("risk:sentiment", 1800)
    if not cached_sent:
        import akshare as ak
        from datetime import date as _date
        today = _date.today().strftime("%Y%m%d")
        zt_sealed = zt_broken = dt_pool = 0
        try: zt_sealed = len(ak.stock_zt_pool_em(date=today))
        except Exception: pass
        try: zt_broken = len(ak.stock_zt_pool_zbgc_em(date=today))
        except Exception: pass
        try: dt_pool = len(ak.stock_zt_pool_dtgc_em(date=today))
        except Exception: pass
        zt_total = zt_sealed + zt_broken
        cached_sent = {
            "up_ratio":     None,
            "zt_sealed":    zt_sealed,
            "dt_pool":      dt_pool,
            "broken_ratio": round(zt_broken / zt_total * 100, 1) if zt_total > 0 else 0.0,
        }
        logger.info("radar: sentiment cache miss — pool fallback zt=%d dt=%d", zt_sealed, dt_pool)

    up_ratio     = cached_sent.get("up_ratio")
    zt_sealed    = cached_sent.get("zt_sealed", 0)
    dt_pool      = cached_sent.get("dt_pool", 0)
    broken_ratio = cached_sent.get("broken_ratio", 0.0)

    sentiment_score = _score_sentiment(up_ratio, zt_sealed, dt_pool, broken_ratio)

    # 5个维度并行计算；原始数据层的 _sync_cached 保证同一批并发请求中
    # 每个数据源只发一次 HTTP 请求，其余线程等锁后命中缓存直接返回。
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        futures = {
            "lev": ex.submit(_score_leverage_sync),
            "mac": ex.submit(_score_macro_sync),
            "tec": ex.submit(_score_technical_sync),
            "yld": ex.submit(_score_yield_curve_sync),
            "qvx": ex.submit(_score_qvix_sync),
        }

        results = {}
        failed_dims = []
        for name, fut in futures.items():
            try:
                results[name] = fut.result(timeout=60)
            except Exception as e:
                logger.warning("radar dim [%s] error: %s", name, e, exc_info=True)
                results[name] = {"score": 50.0}
                failed_dims.append(name)

    lev, mac, tec, yld, qvx = (results[k] for k in ("lev", "mac", "tec", "yld", "qvx"))

    scores = {
        "情绪温度":   round(sentiment_score, 1),
        "杠杆水位":   lev["score"],
        "宏观金融":   mac["score"],
        "技术超买":   tec["score"],
        "曲线斜率":   yld["score"],
        "期权波动率": qvx["score"],
    }

    composite = round(sum(scores.values()) / len(scores), 1)

    if composite >= 75:   risk_level, risk_label = "danger",  "高风险"
    elif composite >= 55: risk_level, risk_label = "warning", "中高风险"
    elif composite >= 35: risk_level, risk_label = "normal",  "中性"
    else:                 risk_level, risk_label = "safe",    "低风险"

    result = _clean({
        "scores":      scores,
        "composite":   composite,
        "risk_level":  risk_level,
        "risk_label":  risk_label,
        "failed_dims": failed_dims,
        "detail": {
            "sentiment":   {"up_ratio": up_ratio, "zt_sealed": zt_sealed, "dt_pool": dt_pool, "broken_ratio": broken_ratio},
            "leverage":    lev,
            "macro":       mac,
            "technical":   tec,
            "yield_curve": yld,
            "qvix":        qvx,
        },
        "date": date.today().strftime("%Y-%m-%d"),
    })
    # Cache shorter if some dims failed — retry sooner
    _set("risk:radar", result, ttl=300 if failed_dims else 1800)
    return result


async def fetch_risk_radar():
    hit = _get("risk:radar")
    if hit is not None:
        return hit
    async with _lock("risk:radar"):
        hit = _get("risk:radar")
        if hit is not None:
            return hit
        return await asyncio.to_thread(_radar_sync)

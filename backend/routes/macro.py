"""Macro economic data endpoints."""
import logging
from fastapi import APIRouter, Depends
from routes.auth import get_current_user
from models import User
from services.macro_service import (
    get_macro_data, fetch_industrial_profit,
    fetch_nbs_industrial_charts, fetch_industrial_profit_history,
    clear_macro_cache,
)
from services.calendar_service import get_trade_calendar
logger = logging.getLogger(__name__)

router = APIRouter(tags=["macro"])


@router.get("/macro")
async def get_macro(current_user: User = Depends(get_current_user)):
    return await get_macro_data()


@router.get("/macro/profit")
async def get_profit(current_user: User = Depends(get_current_user)):
    return await fetch_industrial_profit()


@router.get("/macro/industrial-charts")
async def get_industrial_charts(current_user: User = Depends(get_current_user)):
    return await fetch_nbs_industrial_charts()


@router.get("/macro/profit-history")
async def get_profit_history(current_user: User = Depends(get_current_user)):
    return await fetch_industrial_profit_history()


@router.post("/macro/refresh")
async def refresh_macro(current_user: User = Depends(get_current_user)):
    """Force-clear all macro caches and re-fetch."""
    clear_macro_cache()
    logger.info(f"All macro caches cleared by {current_user.username}")
    return await get_macro_data()


@router.post("/macro/profit/refresh")
async def refresh_profit(current_user: User = Depends(get_current_user)):
    clear_macro_cache(["macro:industrial_profit"])
    logger.info(f"Profit cache cleared by {current_user.username}")
    return await fetch_industrial_profit()


@router.post("/macro/industrial-charts/refresh")
async def refresh_industrial_charts(current_user: User = Depends(get_current_user)):
    clear_macro_cache(["macro:nbs_industrial_charts"])
    logger.info(f"Industrial charts cache cleared by {current_user.username}")
    return await fetch_nbs_industrial_charts()


@router.post("/macro/profit-history/refresh")
async def refresh_profit_history(current_user: User = Depends(get_current_user)):
    clear_macro_cache(["macro:industrial_profit_history"])
    logger.info(f"Profit history cache cleared by {current_user.username}")
    return await fetch_industrial_profit_history()


# ── A股交易日历（动态，非硬编码）─────────────────────────────────────────────

@router.get("/macro/trade-calendar")
async def trade_calendar():
    """动态获取 A 股交易日历（通过 AKShare / Sina 财经）。

    前端 marketTime.js 用此数据替代硬编码的节假日列表。
    缓存: 每次调用重新获取（AKShare 内部有 HTTP 缓存，无需额外缓存层）。
    """
    return await get_trade_calendar()


# ── 主力净流入 TOP 20 ─────────────────────────────────────────────────────
# 从东方财富 push2 API 获取，绕过系统代理（代理会拦截 East Money 请求）

_FUND_FLOW_CACHE: dict[str, any] = {"data": None, "ts": 0}
_FUND_FLOW_TTL = 60  # seconds


@router.get("/macro/fund-flow/top20")
async def fund_flow_top20(current_user: User = Depends(get_current_user)):
    import time, json, urllib.request

    now = time.time()
    if _FUND_FLOW_CACHE["data"] and (now - _FUND_FLOW_CACHE["ts"]) < _FUND_FLOW_TTL:
        return _FUND_FLOW_CACHE["data"]

    url = (
        "https://push2.eastmoney.com/api/qt/clist/get"
        "?fid=f62&po=1&pz=20&pn=1&np=1&fltt=2&invt=2"
        "&ut=b2884a393a59ad64002292a3e90d46a5"
        "&fs=m:0+t:6+f:!2,m:0+t:13+f:!2,m:0+t:80+f:!2,m:1+t:2+f:!2,m:1+t:23+f:!2,m:0+t:7+f:!2,m:1+t:3+f:!2"
        "&fields=f12,f14,f2,f3,f62,f184"
    )
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://data.eastmoney.com/",
    })
    # Bypass system proxy — East Money blocks proxy IPs
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        resp = opener.open(req, timeout=15)
        raw = json.loads(resp.read().decode("utf-8"))
        diff = raw.get("data", {}).get("diff", [])
        items = []
        for r in diff:
            code = str(r.get("f12", "")).zfill(6)
            name = r.get("f14", "")
            price = r.get("f2")  # 现价
            pct = r.get("f3")   # 涨跌幅(%)
            net = r.get("f62")  # 主力净流入(元)
            ratio = r.get("f184")  # 主力净流入占比(%)
            items.append({
                "stock_code": code,
                "stock_name": name,
                "price": price,
                "change_pct": pct,
                "net_inflow": round(net / 1e8, 2) if net else 0,  # 元→亿
                "net_ratio": round(ratio, 2) if ratio else 0,
            })
        result = {"items": items, "update_time": now}
        _FUND_FLOW_CACHE["data"] = result
        _FUND_FLOW_CACHE["ts"] = now
        return result
    except Exception as e:
        logger.warning("Fund flow fetch failed: %s", e)
        return {"items": _FUND_FLOW_CACHE["data"]["items"] if _FUND_FLOW_CACHE["data"] else [], "update_time": _FUND_FLOW_CACHE["ts"], "error": str(e)}

"""Macro economic data endpoints."""
import asyncio
import logging
import httpx
from fastapi import APIRouter, Depends
from routes.auth import get_current_user
from models import User
from services.macro_service import (
    get_macro_data, fetch_industrial_profit,
    fetch_nbs_industrial_charts, fetch_industrial_profit_history,
    clear_macro_cache,
)
from services.calendar_service import get_trade_calendar
from services.risk_service import _is_trading_time
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
# 从东方财富 push2 API 获取，trust_env=False 绕过系统代理

_FUND_FLOW_CACHE: dict = {"data": None, "ts": 0.0}
_FUND_FLOW_TTL  = 300  # 5 min — reduce EM hammering
_fund_flow_lock = asyncio.Lock()

_EM_HEADERS_FF = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://data.eastmoney.com/",
}
_FUND_FLOW_URL = (
    "https://push2delay.eastmoney.com/api/qt/clist/get"
    "?fid=f62&po=1&pz=20&pn=1&np=1&fltt=2&invt=2"
    "&ut=b2884a393a59ad64002292a3e90d46a5"
    "&fs=m:0+t:6+f:!2,m:0+t:13+f:!2,m:0+t:80+f:!2,m:1+t:2+f:!2,m:1+t:23+f:!2,m:0+t:7+f:!2,m:1+t:3+f:!2"
    "&fields=f12,f14,f2,f3,f62,f184"
)


def _parse_cn_yuan(s) -> float:
    """解析中文金额字符串 → 元，如 '1.39亿' → 1.39e8，'1150.70万' → 1.157e7"""
    s = str(s or "").strip().replace(",", "").replace("+", "")
    if not s or s in ("-", "—"):
        return 0.0
    try:
        if "亿" in s:
            return float(s.replace("亿", "")) * 1e8
        if "万" in s:
            return float(s.replace("万", "")) * 1e4
        return float(s)
    except ValueError:
        return 0.0


def _gen_ths_token() -> str:
    """生成一个 THS hexin-v 鉴权 token（~0.02s）。"""
    import py_mini_racer
    from akshare.datasets import get_ths_js
    js_path = get_ths_js("ths.js")
    with open(js_path, encoding="utf-8") as f:
        js_content = f.read()
    jsc = py_mini_racer.MiniRacer()
    jsc.eval(js_content)
    return jsc.call("v")


def _ths_headers(token: str) -> dict:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/90.0.4430.85 Safari/537.36",
        "Accept": "text/html, */*; q=0.01",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "hexin-v": token,
        "Host": "data.10jqka.com.cn",
        "Referer": "http://data.10jqka.com.cn/funds/ggzjl/",
        "X-Requested-With": "XMLHttpRequest",
    }


_THS_BASE = "http://data.10jqka.com.cn/funds/ggzjl/field/zdf/order/desc/page/{page}/ajax/1/free/1/"
_TOKEN_PAGE_LIMIT = 4   # THS 每个 token 约允许 5 次连续请求，保守取 4


def _fetch_ths_pages_batch(pages: list[int]) -> list[list]:
    """同步抓取一批页面，每 _TOKEN_PAGE_LIMIT 页刷新一次 token。
    各批次由 ThreadPoolExecutor 并行调用。
    """
    import requests as _req
    from bs4 import BeautifulSoup

    rows_all = []
    token = _gen_ths_token()
    session = _req.Session()

    for i, page in enumerate(pages):
        if i > 0 and i % _TOKEN_PAGE_LIMIT == 0:
            token = _gen_ths_token()           # 刷新 token

        url = _THS_BASE.format(page=page)
        try:
            r = session.get(url, headers=_ths_headers(token), timeout=10)
            soup = BeautifulSoup(r.text, "lxml")
            for row in soup.select("tbody tr"):
                cols = [td.text.strip() for td in row.select("td")]
                if len(cols) >= 9:
                    rows_all.append(cols)
        except Exception:
            pass   # 单页失败不中断整批

    session.close()
    return rows_all


def _fetch_fund_flow_ths_fast() -> list:
    """快速 THS 即时资金流向抓取：多线程并行，速度 ~3s（原串行 ~20s）。

    策略：
    - 获取总页数（1 次请求）
    - 将所有页均分给 N_WORKERS 个线程，各线程独立维护 token（每 4 页轮换）
    - 收集全部行后按净额排序取 TOP 20
    """
    import requests as _req
    import concurrent.futures
    from bs4 import BeautifulSoup

    N_WORKERS = 12   # 并发线程数，平衡速度与服务器友好度

    # ① 获取总页数
    token0 = _gen_ths_token()
    r0 = _req.get(_THS_BASE.format(page=1), headers=_ths_headers(token0), timeout=12)
    soup0 = BeautifulSoup(r0.text, "lxml")
    page_span = soup0.find("span", class_="page_info")
    if not page_span:
        return []
    try:
        total_pages = int(page_span.text.split("/")[1])
    except (IndexError, ValueError):
        return []

    # ② 将所有页切分给各线程
    all_pages = list(range(1, total_pages + 1))
    chunk_size = max(1, (total_pages + N_WORKERS - 1) // N_WORKERS)
    chunks = [all_pages[i: i + chunk_size] for i in range(0, total_pages, chunk_size)]

    # ③ 并行抓取
    all_rows: list[list] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=N_WORKERS) as exe:
        futures = [exe.submit(_fetch_ths_pages_batch, chunk) for chunk in chunks]
        for fut in concurrent.futures.as_completed(futures):
            try:
                all_rows.extend(fut.result())
            except Exception:
                pass

    if not all_rows:
        return []

    # ④ 解析行 & 排序（索引：0=序号 1=代码 2=简称 3=最新价 4=涨跌幅 5=换手率 6=流入 7=流出 8=净额 9=成交额）
    parsed = []
    for cols in all_rows:
        try:
            net_yuan = _parse_cn_yuan(cols[8])
            vol_yuan = _parse_cn_yuan(cols[9])
            chg = float(cols[4].replace("%", "").replace("+", "")) if cols[4] not in ("—", "") else 0.0
            parsed.append({
                "stock_code": cols[1].zfill(6),
                "stock_name": cols[2],
                "price":      float(cols[3].replace(",", "")) if cols[3] not in ("—", "") else 0.0,
                "change_pct": round(chg, 2),
                "net_inflow": round(net_yuan / 1e8, 2),
                "net_ratio":  round(net_yuan / vol_yuan * 100, 2) if vol_yuan > 0 else 0.0,
                "_net_yuan":  net_yuan,
            })
        except Exception:
            pass

    parsed.sort(key=lambda x: x["_net_yuan"], reverse=True)
    top20 = parsed[:20]
    for item in top20:
        del item["_net_yuan"]
    return top20


async def _do_fund_flow_refresh() -> dict | None:
    """实际执行资金流向抓取并更新缓存，返回结果 dict 或 None（两路均失败时）。
    无鉴权依赖，可在启动预热任务中直接调用。
    """
    import time
    now = time.time()

    async with _fund_flow_lock:
        # Double-checked: 可能另一个协程已刷新好
        if _FUND_FLOW_CACHE["data"] and (
            not _is_trading_time()
            or (now - _FUND_FLOW_CACHE["ts"]) < _FUND_FLOW_TTL
        ):
            return _FUND_FLOW_CACHE["data"]

        items = []
        trading = _is_trading_time()

        # Primary: push2 direct API
        try:
            async with httpx.AsyncClient(timeout=12, trust_env=False) as client:
                resp = await client.get(_FUND_FLOW_URL, headers=_EM_HEADERS_FF)
                resp.raise_for_status()
                raw = resp.json()
            diff = raw.get("data", {}).get("diff", [])
            for r in diff:
                code = str(r.get("f12", "")).zfill(6)
                net   = r.get("f62")
                ratio = r.get("f184")
                items.append({
                    "stock_code": code,
                    "stock_name": r.get("f14", ""),
                    "price":       r.get("f2"),
                    "change_pct":  r.get("f3"),
                    "net_inflow":  round(net / 1e8, 2) if net else 0,
                    "net_ratio":   round(ratio, 2) if ratio else 0,
                })
        except Exception as e:
            (logger.warning if trading else logger.debug)(
                "Fund flow push2 failed: %s — trying AKShare fallback", e)

        # Fallback: THS 即时资金流向，多线程并行抓取（~3s，原串行约 20s）
        # 非交易时段跳过：即时资金流向在非交易日无数据
        if not items and trading:
            try:
                items = await asyncio.wait_for(
                    asyncio.to_thread(_fetch_fund_flow_ths_fast), timeout=30
                )
            except Exception as e:
                logger.warning("Fund flow THS fast fetch failed: %s", e)

        if items:
            result = {"items": items, "update_time": now}
            _FUND_FLOW_CACHE["data"] = result
            _FUND_FLOW_CACHE["ts"]   = now
            return result

        return None


async def _prefetch_fund_flow():
    """服务启动后台预热：交易时段提前拉取资金流向，首次用户请求直接命中缓存。"""
    await asyncio.sleep(8)   # 等服务器完全就绪
    if not _is_trading_time():
        return
    logger.info("Fund flow prefetch started (background)")
    result = await _do_fund_flow_refresh()
    if result:
        logger.info("Fund flow prefetch done: %d items cached", len(result.get("items", [])))
    else:
        logger.debug("Fund flow prefetch: no data (non-trading or both sources failed)")


@router.get("/macro/fund-flow/top20")
async def fund_flow_top20(current_user: User = Depends(get_current_user)):
    import time
    now = time.time()

    def _ff_fresh():
        if not _FUND_FLOW_CACHE["data"]:
            return False
        if not _is_trading_time():
            return True  # 非交易时段永不过期
        return (now - _FUND_FLOW_CACHE["ts"]) < _FUND_FLOW_TTL

    if _ff_fresh():
        return _FUND_FLOW_CACHE["data"]

    result = await _do_fund_flow_refresh()
    if result:
        return result

    # Both sources failed — return stale cache or empty
    cached_items = _FUND_FLOW_CACHE["data"]["items"] if _FUND_FLOW_CACHE["data"] else []
    return {"items": cached_items, "update_time": _FUND_FLOW_CACHE["ts"], "stale": True}

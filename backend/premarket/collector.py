"""采集层：RSS / API / 网页抓取 + 美股行情。单源失败跳过并标注，不中断整体流程。"""
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

PROXIES = None  # 若需代理可设 {"http":"...","https":"..."}
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}
TIMEOUT = 15


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(val) -> str:
    """将各种时间格式统一成 ISO-8601 字符串，无法解析则返回当前时间。"""
    if not val:
        return _utc_now().isoformat()
    if isinstance(val, (int, float)):
        try:
            return datetime.fromtimestamp(val, tz=timezone.utc).isoformat()
        except Exception:
            pass
    if hasattr(val, "tm_year"):  # time.struct_time from feedparser
        try:
            return datetime(*val[:6], tzinfo=timezone.utc).isoformat()
        except Exception:
            pass
    if isinstance(val, str):
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%a, %d %b %Y %H:%M:%S %z",
                    "%a, %d %b %Y %H:%M:%S GMT", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(val[:25], fmt[:len(val[:25])])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.isoformat()
            except Exception:
                pass
    return _utc_now().isoformat()


def _is_within_24h(ts_str: str) -> bool:
    try:
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt) <= timedelta(hours=24)
    except Exception:
        return True  # 解析失败时保留


# ── RSS 采集 ──────────────────────────────────────────────────────────────────

_RSS_HEADERS = {
    **HEADERS,
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Encoding": "identity",   # 禁止 gzip，防止 IncompleteRead
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}


def fetch_rss(source: dict) -> list[dict]:
    try:
        import feedparser
        # 先用 requests 抓取原始内容，再交给 feedparser 解析。
        # 直接让 feedparser 用 urllib 拉取时 CNBC/MarketWatch 会返回截断响应。
        try:
            r = requests.get(
                source["url"], headers=_RSS_HEADERS,
                timeout=TIMEOUT, proxies=PROXIES,
            )
            r.raise_for_status()
            feed = feedparser.parse(r.content)
        except Exception:
            # 降级：让 feedparser 自己取
            feed = feedparser.parse(source["url"], request_headers=HEADERS)

        items = []
        for entry in feed.entries:
            pub = _parse_time(
                getattr(entry, "published_parsed", None)
                or getattr(entry, "updated_parsed", None)
            )
            if not _is_within_24h(pub):
                continue
            items.append({
                "source": source["name"],
                "category": source.get("category", ""),
                "title": getattr(entry, "title", ""),
                "url": getattr(entry, "link", ""),
                "summary": getattr(entry, "summary", "")[:500],
                "published_at": pub,
            })
        logger.info(f"[RSS] {source['name']}: {len(items)} items")
        return items
    except Exception as e:
        logger.warning(f"[RSS] {source['name']} failed: {e}")
        return [{"_error": str(e), "source": source["name"]}]


# ── 新浪滚动新闻 API ───────────────────────────────────────────────────────────

def _fetch_sina_rolling(source: dict) -> list[dict]:
    try:
        r = requests.get(
            "https://feed.mix.sina.com.cn/api/roll/get",
            params={"pageid": "153", "lid": "2509", "num": "50", "page": "1"},
            headers=HEADERS, timeout=TIMEOUT, proxies=PROXIES,
        )
        r.raise_for_status()
        data = r.json()
        items = []
        for art in data.get("result", {}).get("data", []):
            pub = _parse_time(art.get("ctime", ""))
            if not _is_within_24h(pub):
                continue
            items.append({
                "source": source["name"],
                "category": source.get("category", ""),
                "title": art.get("title", ""),
                "url": art.get("url", ""),
                "summary": art.get("intro", "")[:500],
                "published_at": pub,
            })
        logger.info(f"[SinaAPI] {source['name']}: {len(items)} items")
        return items
    except Exception as e:
        logger.warning(f"[SinaAPI] {source['name']} failed: {e}")
        return [{"_error": str(e), "source": source["name"]}]


# ── 财联社电报（akshare） ──────────────────────────────────────────────────────

def _fetch_cls(source: dict) -> list[dict]:
    """用 akshare.stock_info_global_cls() 获取财联社实时电报，原 API 已 404。"""
    try:
        import akshare as ak
        df = ak.stock_info_global_cls()
        # 列名：标题, 内容, 发布日期, 发布时间
        items = []
        for _, row in df.iterrows():
            date_str = str(row.get("发布日期", ""))
            time_str = str(row.get("发布时间", ""))
            pub = _parse_time(f"{date_str} {time_str}".strip())
            if not _is_within_24h(pub):
                continue
            title = str(row.get("标题", "") or row.get("内容", ""))[:200]
            summary = str(row.get("内容", ""))[:500]
            items.append({
                "source": source["name"],
                "category": source.get("category", ""),
                "title": title,
                "url": "",
                "summary": summary,
                "published_at": pub,
            })
        logger.info(f"[CLS] {source['name']}: {len(items)} items")
        return items
    except Exception as e:
        logger.warning(f"[CLS] {source['name']} failed: {e}")
        return [{"_error": str(e), "source": source["name"]}]


# ── 通用网页抓取 ───────────────────────────────────────────────────────────────

def fetch_webpage(source: dict) -> list[dict]:
    try:
        r = requests.get(
            source["url"], headers=HEADERS, timeout=TIMEOUT, proxies=PROXIES,
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        texts = []
        for tag in soup.find_all(["h1", "h2", "h3", "p"])[:40]:
            t = tag.get_text(strip=True)
            if len(t) > 20:
                texts.append(t)
        summary = " | ".join(texts[:10])
        return [{
            "source": source["name"],
            "category": source.get("category", ""),
            "title": soup.title.string if soup.title else source["name"],
            "url": source["url"],
            "summary": summary[:500],
            "published_at": _utc_now().isoformat(),
        }]
    except Exception as e:
        logger.warning(f"[Web] {source['name']} failed: {e}")
        return [{"_error": str(e), "source": source["name"]}]


# ── API 路由分发 ───────────────────────────────────────────────────────────────

def fetch_api(source: dict) -> list[dict]:
    name_lower = source["name"].lower()
    url_lower = source["url"].lower()
    if "sina" in name_lower or "新浪" in name_lower:
        return _fetch_sina_rolling(source)
    if "cls" in name_lower or "财联社" in name_lower:
        return _fetch_cls(source)
    # 通用 JSON API
    try:
        r = requests.get(
            source["url"], headers=HEADERS, timeout=TIMEOUT, proxies=PROXIES,
        )
        r.raise_for_status()
        return [{
            "source": source["name"],
            "category": source.get("category", ""),
            "title": f"{source['name']} API response",
            "url": source["url"],
            "summary": r.text[:500],
            "published_at": _utc_now().isoformat(),
        }]
    except Exception as e:
        logger.warning(f"[API] {source['name']} failed: {e}")
        return [{"_error": str(e), "source": source["name"]}]


# ── 美股行情（yfinance） ────────────────────────────────────────────────────────

def _vix_level(vix: float) -> str:
    """将 VIX 数值映射为市场情绪语义标签。"""
    if vix < 15:   return "极度平静"
    if vix < 20:   return "低波动"
    if vix < 25:   return "正常"
    if vix < 30:   return "偏高/谨慎"
    if vix < 40:   return "高恐慌"
    return "极度恐慌"


def fetch_us_market() -> dict:
    result = {"indices": {}, "futures": {}, "commodities": {}, "errors": []}
    try:
        import yfinance as yf

        symbols = {
            "indices":     {"SPY": "标普500 ETF", "QQQ": "纳斯达克100 ETF",
                            "DIA": "道琼斯 ETF",  "^VIX": "VIX恐慌指数"},
            "futures":     {"ES=F": "标普500期货", "NQ=F": "纳指期货",
                            "YM=F": "道指期货"},
            "commodities": {"GC=F": "黄金", "SI=F": "白银", "HG=F": "铜"},
        }

        for group, syms in symbols.items():
            for sym, label in syms.items():
                last, prev = None, None
                tk = yf.Ticker(sym)
                try:
                    info = tk.fast_info
                    last = getattr(info, "last_price", None)
                    prev = getattr(info, "previous_close", None)
                except Exception:
                    pass
                # fast_info 对 ^VIX / HG=F 等可能抛 KeyError，降级用 history 补充
                # period="2d" 对 ^VIX 返回空，必须用 "5d" 再取最后两行
                if last is None:
                    for _p in ("5d", "1mo"):
                        try:
                            hist = tk.history(period=_p)
                            if not hist.empty:
                                last = float(hist["Close"].iloc[-1])
                                if len(hist) > 1:
                                    prev = float(hist["Close"].iloc[-2])
                                break
                        except Exception:
                            pass
                if last is None:
                    result["errors"].append(f"{sym}: no price data")
                    continue
                chg_pct = (
                    round((last - prev) / prev * 100, 2)
                    if last and prev and prev != 0 else None
                )
                entry = {
                    "label": label,
                    "price": round(last, 4) if last else None,
                    "change_pct": chg_pct,
                }
                # VIX 附加语义标签，方便前端和 LLM 解读
                if sym == "^VIX":
                    entry["vix_level"] = _vix_level(last)
                result[group][sym] = entry
    except ImportError:
        result["errors"].append("yfinance not installed")
    except Exception as e:
        result["errors"].append(f"US market fetch error: {e}")
    logger.info(f"US market fetched. errors={result['errors']}")
    return result


# ── 主入口 ─────────────────────────────────────────────────────────────────────

def collect_all(sources: list[dict]) -> dict:
    """
    采集所有数据源 + 美股行情。
    返回: {"news": [...], "us_market": {...}, "fetch_errors": [...]}
    """
    news_items: list[dict] = []
    fetch_errors: list[str] = []

    for src in sources:
        if not src.get("enabled", True):
            continue
        stype = src.get("source_type", "rss")
        if stype == "rss":
            items = fetch_rss(src)
        elif stype == "api":
            items = fetch_api(src)
        else:
            items = fetch_webpage(src)

        for item in items:
            if "_error" in item:
                fetch_errors.append(f"{item['source']}: {item['_error']}")
            else:
                news_items.append(item)

    us_market = fetch_us_market()
    fetch_errors.extend(us_market.pop("errors", []))

    return {
        "news": news_items,
        "us_market": us_market,
        "fetch_errors": fetch_errors,
    }

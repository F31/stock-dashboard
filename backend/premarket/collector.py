"""采集层：RSS / API / 网页抓取 + 美股行情。单源失败跳过并标注，不中断整体流程。"""
import json as _json
import logging
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests
from bs4 import BeautifulSoup

# 从 .env 文件加载环境变量（优先 os.environ，其次 .env 文件）
def _load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())

_load_env()

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
                    "%a, %d %b %Y %H:%M:%S GMT", "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d"):
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


# ── 财新资讯（akshare） ───────────────────────────────────────────────────────

def _fetch_caixin(source: dict) -> list[dict]:
    """用 akshare.stock_news_main_cx() 采集财新快讯（约100条，实时更新）。"""
    try:
        import akshare as ak
        df = ak.stock_news_main_cx()
        items = []
        for _, row in df.iterrows():
            summary = str(row.get("summary", "")).strip()
            if len(summary) < 10:
                continue
            tag = str(row.get("tag", ""))
            title = f"[{tag}] {summary[:120]}" if tag else summary[:120]
            items.append({
                "source": source["name"],
                "category": source.get("category", "国内"),
                "title": title,
                "url": str(row.get("url", "")),
                "summary": summary[:500],
                "published_at": _utc_now().isoformat(),
            })
        logger.info(f"[Caixin] {source['name']}: {len(items)} items")
        return items
    except Exception as e:
        logger.warning(f"[Caixin] {source['name']} failed: {e}")
        return [{"_error": str(e), "source": source["name"]}]


# ── 财联社电报（东方财富快讯接口） ─────────────────────────────────────────────
# 原 akshare.stock_info_global_cls() → cls.cn/nodeapi/telegraphList 已 404
# 改用东方财富快讯列表接口，内容与财联社电报高度重叠，稳定可用。

_EM_FLASH_URL = (
    "https://np-listapi.eastmoney.com/comm/web/getFastNewsList"
    "?client=web&biz=web_news_flash&fastColumn=102&sortEnd=0"
    "&page=1&pageSize=50&req=2&req_trace={trace}"
)
_EM_FLASH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://kuaixun.eastmoney.com/",
    "Accept": "application/json",
}


def _fetch_cls(source: dict) -> list[dict]:
    """东方财富快讯接口（替代已失效的 cls.cn nodeapi）。
    字段：showTime=发布时间, title=标题, summary=正文摘要。
    """
    import uuid
    trace = uuid.uuid4().hex
    url = _EM_FLASH_URL.format(trace=trace)
    try:
        r = requests.get(url, headers=_EM_FLASH_HEADERS, timeout=12)
        r.raise_for_status()
        data = r.json()
        flash_list = (data.get("data") or {}).get("fastNewsList")
        if not isinstance(flash_list, list):
            raise ValueError(f"fastNewsList missing: code={data.get('code')} msg={data.get('message')}")
        items = []
        for it in flash_list:
            pub = _parse_time(it.get("showTime", ""))
            if not _is_within_24h(pub):
                continue
            title   = str(it.get("title", ""))[:200]
            summary = str(it.get("summary", ""))[:500]
            if not title and not summary:
                continue
            items.append({
                "source":      source["name"],
                "category":    source.get("category", ""),
                "title":       title,
                "url":         "",
                "summary":     summary,
                "published_at": pub,
            })
        logger.info(f"[CLS/EM] {source['name']}: {len(items)} items")
        return items
    except Exception as e:
        logger.warning(f"[CLS/EM] {source['name']} failed: {e}")
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
    if "sina" in name_lower or "新浪" in name_lower:
        return _fetch_sina_rolling(source)
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


# ── A股IPO动态（akshare，通过数据库配置驱动） ────────────────────────────────────

def _fetch_ipo_tutor(source: dict) -> list[dict]:
    """IPO辅导备案（近30天）— akshare:stock_ipo_tutor_em"""
    try:
        import akshare as ak
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        df = ak.stock_ipo_tutor_em()
        items, cnt = [], 0
        for _, row in df.iterrows():
            date_str = str(row.get("备案日期", ""))
            pub = _parse_time(date_str)
            try:
                dt = datetime.fromisoformat(pub)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt < cutoff:
                    continue
            except Exception:
                pass
            company = str(row.get("企业名称", ""))
            broker  = str(row.get("辅导机构", ""))
            bureau  = str(row.get("派出机构", ""))
            status  = str(row.get("辅导状态", ""))
            items.append({
                "source": source["name"],
                "category": source.get("category", "国内"),
                "title": f"【IPO辅导备案】{company} 启动上市辅导，辅导机构：{broker}",
                "url": "",
                "summary": (f"{company} 向{bureau}提交IPO辅导备案。"
                            f"辅导机构：{broker}，状态：{status}，备案日期：{date_str}。"),
                "published_at": pub,
            })
            cnt += 1
        logger.info(f"[IPO辅导] {source['name']}: {cnt} items in last 30d")
        return items
    except Exception as e:
        logger.warning(f"[IPO辅导] {source['name']} failed: {e}")
        return [{"_error": str(e), "source": source["name"]}]


def _fetch_ipo_declare(source: dict) -> list[dict]:
    """IPO申报受理（近7天有变更）— akshare:stock_ipo_declare_em"""
    try:
        import akshare as ak
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        df = ak.stock_ipo_declare_em()
        items, cnt = [], 0
        for _, row in df.iterrows():
            date_str = str(row.get("更新日期", ""))
            pub = _parse_time(date_str)
            try:
                dt = datetime.fromisoformat(pub)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt < cutoff:
                    continue
            except Exception:
                pass
            company  = str(row.get("企业名称", ""))
            status   = str(row.get("最新状态", ""))
            location = str(row.get("拟上市地点", ""))
            broker   = str(row.get("保荐机构", ""))
            items.append({
                "source": source["name"],
                "category": source.get("category", "国内"),
                "title": f"【IPO申报】{company} 状态：{status}，拟上市{location}",
                "url": "",
                "summary": (f"{company} IPO申报最新状态：{status}。"
                            f"拟上市地点：{location}，保荐机构：{broker}，更新日期：{date_str}。"),
                "published_at": pub,
            })
            cnt += 1
        logger.info(f"[IPO申报] {source['name']}: {cnt} items in last 7d")
        return items
    except Exception as e:
        logger.warning(f"[IPO申报] {source['name']} failed: {e}")
        return [{"_error": str(e), "source": source["name"]}]


# ── akshare 统一调度（通过 url="akshare:函数名" 路由） ──────────────────────────

_AKSHARE_DISPATCH = {
    "akshare:stock_info_global_cls":  _fetch_cls,
    "akshare:stock_news_main_cx":     _fetch_caixin,
    "akshare:stock_ipo_tutor_em":     _fetch_ipo_tutor,
    "akshare:stock_ipo_declare_em":   _fetch_ipo_declare,
}


def fetch_akshare(source: dict) -> list[dict]:
    """根据 source['url'] 中的 akshare:函数名 路由到对应采集函数。"""
    url = source.get("url", "")
    fn  = _AKSHARE_DISPATCH.get(url)
    if fn:
        return fn(source)
    logger.warning(f"[akshare] unknown url: {url!r} for source {source.get('name')!r}")
    return [{"_error": f"unknown akshare url: {url}", "source": source.get("name", "")}]


# ── 美股行情（yfinance 优先，akshare/EastMoney 备用） ──────────────────────────

def _vix_level(vix: float) -> str:
    """将 VIX 数值映射为市场情绪语义标签。"""
    if vix < 15:  return "极度平静"
    if vix < 20:  return "低波动"
    if vix < 25:  return "正常"
    if vix < 30:  return "偏高/谨慎"
    if vix < 40:  return "高恐慌"
    return "极度恐慌"


# 所有需要采集的美股标的（yfinance 符号 → (标签, 分组)）
_US_SYMBOLS: dict[str, dict[str, str]] = {
    "indices":     {"SPY":  "标普500 ETF",    "QQQ": "纳斯达克100 ETF",
                   "DIA":  "道琼斯 ETF",      "^VIX": "VIX恐慌指数"},
    "futures":     {"ES=F": "标普500期货",     "NQ=F": "纳指期货",
                   "YM=F": "道指期货"},
    "commodities": {"GC=F": "黄金",            "SI=F": "白银",
                   "HG=F": "铜"},
    "rates":       {"^TNX": "美国10年期国债收益率(%)", "DX-Y.NYB": "美元指数(DXY)"},
}


def _fill_yfinance(result: dict) -> int:
    """
    用 yfinance 填充 result。返回成功获取的标的数量。
    本地/海外服务器可用；中国云主机通常因 Yahoo Finance 被封锁而全部失败。
    """
    success = 0
    try:
        import yfinance as yf
    except ImportError:
        result["errors"].append("yfinance not installed")
        return 0

    for group, syms in _US_SYMBOLS.items():
        for sym, label in syms.items():
            last, prev = None, None
            tk = yf.Ticker(sym)
            try:
                info = tk.fast_info
                last = getattr(info, "last_price", None)
                prev = getattr(info, "previous_close", None)
            except Exception:
                pass
            # fast_info 对 ^VIX / HG=F 等可能抛 KeyError，降级用 history
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
            chg_pct = round((last - prev) / prev * 100, 2) if prev and prev != 0 else None
            entry = {"label": label, "price": round(last, 4), "change_pct": chg_pct}
            if sym == "^VIX":
                entry["vix_level"] = _vix_level(last)
            result[group][sym] = entry
            success += 1

    return success


def _fill_china_sources(result: dict):
    """
    用国内可访问的数据源补全 result 中尚缺的标的。
    中国云主机无法访问 Yahoo Finance 时的兜底方案，只填充尚未有数据的 symbol。

    数据来源：
      - US ETF (SPY/QQQ/DIA)：新浪财经 hq.sinajs.cn（gb_ 前缀）
      - VIX：CBOE 延迟行情 CDN（cdn.cboe.com，经 Cloudflare 分发，中国可达）
      - 美股指期货 + 大宗商品：东方财富 futures_global_spot_em（XX00Y 连续合约）
    """

    def _clean_err(sym: str):
        result["errors"] = [e for e in result["errors"] if not e.startswith(f"{sym}:")]

    # ── US ETF via 东方财富 ulist 实时行情（无需鉴权，国内云主机可达）──────
    # secid 格式：市场代码.标的代码，105=NASDAQ，107=NYSE Arca
    etf_secid_map = {"SPY": "107.SPY", "QQQ": "105.QQQ", "DIA": "107.DIA"}
    etf_need = [s for s in ("SPY", "QQQ", "DIA") if s not in result["indices"]]
    if etf_need:
        secids = ",".join(etf_secid_map[s] for s in etf_need)
        try:
            r = requests.get(
                "https://push2.eastmoney.com/api/qt/ulist.np/get",
                params={
                    "secids": secids,
                    "fields": "f2,f3,f4,f12,f14,f18",   # 现价,涨跌幅%,涨跌额,代码,名称,昨收
                    "ut":   "bd1d9ddb04089700cf9c27f6f7426281",
                    "invt": "2", "fltt": "2",
                },
                headers=HEADERS, timeout=TIMEOUT, proxies=PROXIES,
            )
            r.raise_for_status()
            diff = r.json().get("data", {}).get("diff", [])
            code_to_row = {item["f12"]: item for item in diff}
            for sym in etf_need:
                label = _US_SYMBOLS["indices"][sym]
                row = code_to_row.get(sym)
                if not row:
                    result["errors"].append(f"{sym}: not in EastMoney ulist response")
                    continue
                last    = float(row["f2"])
                chg_pct = float(row["f3"])
                result["indices"][sym] = {
                    "label": label,
                    "price": round(last, 4),
                    "change_pct": round(chg_pct, 2),
                }
                _clean_err(sym)
                logger.info(f"[EastMoney] {sym}: {last} ({chg_pct:+.2f}%)")
        except Exception as e:
            for sym in etf_need:
                result["errors"].append(f"{sym} (EastMoney): {e}")

    # ── VIX via CBOE CDN（Cloudflare，中国可达） ─────────────────────────
    if "^VIX" not in result["indices"]:
        try:
            r = requests.get(
                "https://cdn.cboe.com/api/global/delayed_quotes/quotes/_VIX.json",
                headers=HEADERS, timeout=TIMEOUT, proxies=PROXIES,
            )
            r.raise_for_status()
            d = r.json().get("data", {})
            last_vix = float(d["current_price"])
            chg_pct  = float(d.get("price_change_percent", 0))
            result["indices"]["^VIX"] = {
                "label":     "VIX恐慌指数",
                "price":     round(last_vix, 2),
                "change_pct": round(chg_pct, 2),
                "vix_level": _vix_level(last_vix),
            }
            _clean_err("^VIX")
            logger.info(f"[CBOE] ^VIX: {last_vix} ({chg_pct:+.2f}%)")
        except Exception as e:
            result["errors"].append(f"^VIX (CBOE): {e}")

    # ── 美股指期货 + 大宗商品 + 美元指数 via 东方财富 futures_global_spot_em ──
    # XX00Y = 东方财富当月连续合约命名规范，一次调用返回全部品种
    futures_spot_map = {
        "ES=F":      ("ES00Y", "标普500期货",  "futures"),
        "NQ=F":      ("NQ00Y", "纳指期货",     "futures"),
        "YM=F":      ("YM00Y", "道指期货",     "futures"),
        "GC=F":      ("GC00Y", "黄金",         "commodities"),
        "SI=F":      ("SI00Y", "COMEX白银",    "commodities"),
        "HG=F":      ("HG00Y", "COMEX铜",      "commodities"),
        "DX-Y.NYB":  ("DX00Y", "美元指数(DXY)","rates"),
    }
    futures_need = {
        orig: info for orig, info in futures_spot_map.items()
        if orig not in result[info[2]]
    }
    if futures_need:
        try:
            import akshare as ak
            df_spot = ak.futures_global_spot_em()
            # df 列：序号, 代码, 名称, 最新价, 涨跌额, 涨跌幅, 今开, 最高, 最低, 昨结, ...
            code_to_row = {str(row["代码"]): row for _, row in df_spot.iterrows()}
            for orig, (em_code, label, group) in futures_need.items():
                if orig in result[group]:
                    continue
                row = code_to_row.get(em_code)
                if row is None:
                    result["errors"].append(f"{orig}: symbol {em_code} not found in spot data")
                    continue
                last = row["最新价"]
                prev = row["昨结"]
                if last != last or last is None:   # NaN check
                    result["errors"].append(f"{orig}: NaN price in spot data")
                    continue
                last = float(last)
                chg_pct_raw = row.get("涨跌幅")
                if chg_pct_raw == chg_pct_raw and chg_pct_raw is not None:
                    chg_pct = round(float(chg_pct_raw), 2)
                elif prev == prev and prev and float(prev) != 0:
                    chg_pct = round((last - float(prev)) / float(prev) * 100, 2)
                else:
                    chg_pct = None
                result[group][orig] = {
                    "label": label,
                    "price": round(last, 4),
                    "change_pct": chg_pct,
                }
                _clean_err(orig)
                logger.info(f"[EastMoney] {orig} ({em_code}): {last} ({chg_pct:+.2f}%)")
        except ImportError:
            for orig in futures_need:
                result["errors"].append(f"{orig}: akshare not installed")
        except Exception as e:
            for orig in futures_need:
                result["errors"].append(f"{orig} (EastMoney spot): {e}")


def fetch_us_market() -> dict:
    result = {"indices": {}, "futures": {}, "commodities": {}, "rates": {}, "errors": []}
    total = sum(len(v) for v in _US_SYMBOLS.values())

    yf_success = _fill_yfinance(result)

    # 若超过半数标的失败（通常是云主机无法访问 Yahoo Finance），启用国内数据源兜底
    if yf_success < total // 2:
        logger.info(
            f"yfinance: {yf_success}/{total} symbols fetched, "
            "falling back to Sina/CBOE/EastMoney for missing data"
        )
        _fill_china_sources(result)

    fetched = sum(len(result[g]) for g in ("indices", "futures", "commodities", "rates"))
    logger.info(
        f"US market: {fetched}/{total} symbols OK, "
        f"indices={list(result['indices'])}, rates={list(result['rates'])}, "
        f"errors={result['errors']}"
    )
    return result


# ── 行情监控标的（可配置） ─────────────────────────────────────────────────────

def _fill_tickers_eastmoney(missing: list[dict], result: dict, errors: list):
    """用东方财富 ulist 补全缺失标的：先试 NASDAQ(105)，再试 NYSE/AMEX(107)。"""
    for market_code in ("105", "107"):
        still = [t for t in missing if t["symbol"].upper() not in result]
        if not still:
            break
        secids = ",".join(f"{market_code}.{t['symbol'].upper()}" for t in still)
        try:
            r = requests.get(
                "https://push2.eastmoney.com/api/qt/ulist.np/get",
                params={
                    "secids": secids,
                    "fields": "f2,f3,f12,f14",
                    "ut":   "bd1d9ddb04089700cf9c27f6f7426281",
                    "invt": "2", "fltt": "2",
                },
                headers=HEADERS, timeout=TIMEOUT, proxies=PROXIES,
            )
            r.raise_for_status()
            diff = r.json().get("data", {}).get("diff", []) or []
            code_to_row = {item["f12"]: item for item in diff}
            for t in still:
                sym = t["symbol"].upper()
                row = code_to_row.get(sym)
                if not row:
                    continue
                last    = float(row["f2"])
                chg_pct = float(row["f3"])
                result[sym] = {
                    "label":    t.get("name", sym),
                    "price":    round(last, 4),
                    "change_pct": round(chg_pct, 2),
                    "category": t.get("category", ""),
                }
                errors[:] = [e for e in errors if not e.startswith(f"{sym}:")]
                logger.info(f"[EastMoney {market_code}] {sym}: {last} ({chg_pct:+.2f}%)")
        except Exception as e:
            logger.warning(f"[EastMoney {market_code}] batch fetch failed: {e}")


def fetch_ai_stocks(tickers: list[dict]) -> dict:
    """
    采集可配置的行情监控标的（优先 yfinance；中国云主机降级东方财富）。
    tickers: [{"symbol": "NVDA", "name": "英伟达", "category": "AI芯片"}, ...]
    返回: {"data": {SYM: {...}}, "errors": [...]}
    """
    if not tickers:
        return {"data": {}, "errors": []}

    data: dict = {}
    errors: list = []
    yf_success = 0

    try:
        import yfinance as yf
        for t in tickers:
            sym   = t["symbol"].upper()
            label = t.get("name", sym)
            last, prev = None, None
            try:
                tk   = yf.Ticker(sym)
                info = tk.fast_info
                last = getattr(info, "last_price", None)
                prev = getattr(info, "previous_close", None)
            except Exception:
                pass
            if last is None:
                for period in ("5d", "1mo"):
                    try:
                        hist = yf.Ticker(sym).history(period=period)
                        if not hist.empty:
                            last = float(hist["Close"].iloc[-1])
                            if len(hist) > 1:
                                prev = float(hist["Close"].iloc[-2])
                            break
                    except Exception:
                        pass
            if last is not None:
                chg_pct = round((last - prev) / prev * 100, 2) if prev and prev != 0 else None
                data[sym] = {
                    "label":    label,
                    "price":    round(last, 4),
                    "change_pct": chg_pct,
                    "category": t.get("category", ""),
                }
                yf_success += 1
            else:
                errors.append(f"{sym}: no price data (yfinance)")
    except ImportError:
        errors.append("yfinance not installed")
        yf_success = -1   # 强制走备用路径

    # 超过半数失败时，用东方财富补全所有缺失标的
    if yf_success < len(tickers) // 2 + 1:
        missing = [t for t in tickers if t["symbol"].upper() not in data]
        if missing:
            logger.info(f"yfinance AI stocks partial ({yf_success}/{len(tickers)}), "
                        "falling back to EastMoney for missing")
            _fill_tickers_eastmoney(missing, data, errors)

    logger.info(f"[行情标的] {len(data)}/{len(tickers)} fetched, errors={len(errors)}")
    return {"data": data, "errors": errors}


# ── A股主要指数 ────────────────────────────────────────────────────────────────

_CN_INDEX_MAP = {
    "000001": "上证指数",
    "399001": "深证成指",
    "399006": "创业板指",
    "000300": "沪深300",
    "000016": "上证50",
    "000905": "中证500",
}


_CN_INDEX_SECID = {
    "000001": ("1.000001",  "上证指数"),
    "399001": ("0.399001",  "深证成指"),
    "399006": ("0.399006",  "创业板指"),
    "000300": ("0.000300",  "沪深300"),
    "000016": ("1.000016",  "上证50"),
    "000905": ("0.000905",  "中证500"),
}


def _float_safe(v) -> float | None:
    try:
        fv = float(v)
        return None if fv != fv else fv
    except Exception:
        return None


def fetch_cn_market() -> dict:
    """采集A股主要指数（前一交易日数据）。
    首先尝试东方财富 ulist API（直接 HTTP，与 US ETF 采集同源）；
    失败时降级使用 akshare stock_zh_index_spot_em。
    """
    result: dict = {}
    secids = ",".join(v[0] for v in _CN_INDEX_SECID.values())
    code_by_secid = {v[0]: k for k, v in _CN_INDEX_SECID.items()}

    # ── 优先：东方财富 ulist 直接 HTTP ────────────────────────────────────
    try:
        r = requests.get(
            "https://push2.eastmoney.com/api/qt/ulist.np/get",
            params={
                "secids": secids,
                "fields": "f2,f3,f12,f13,f14",   # 现价,涨跌幅%,代码,市场,名称
                "ut":   "bd1d9ddb04089700cf9c27f6f7426281",
                "invt": "2", "fltt": "2",
            },
            headers=HEADERS, timeout=TIMEOUT, proxies=PROXIES,
        )
        r.raise_for_status()
        diff = r.json().get("data", {}).get("diff", [])
        for item in diff:
            market = str(item.get("f13", ""))
            code   = str(item.get("f12", "")).zfill(6)
            secid  = f"{market}.{code}"
            if secid not in code_by_secid:
                continue
            idx_code = code_by_secid[secid]
            price   = _float_safe(item.get("f2"))
            chg_pct = _float_safe(item.get("f3"))
            result[idx_code] = {
                "label":      _CN_INDEX_MAP[idx_code],
                "price":      round(price,   2) if price   is not None else None,
                "change_pct": round(chg_pct, 2) if chg_pct is not None else None,
            }
        if result:
            logger.info(f"[A股指数] {len(result)} indices via EastMoney ulist")
            return result
    except Exception as e:
        logger.warning(f"[A股指数] EastMoney ulist failed: {e}, trying akshare fallback")

    # ── 降级：akshare stock_zh_index_spot_em ──────────────────────────────
    try:
        import akshare as ak
        df = ak.stock_zh_index_spot_em()
        for _, row in df.iterrows():
            code = str(row.get("代码", "")).lstrip("shSZ").zfill(6)
            if code not in _CN_INDEX_MAP:
                continue
            price   = _float_safe(row.get("最新价"))
            chg_pct = _float_safe(row.get("涨跌幅"))
            result[code] = {
                "label":      _CN_INDEX_MAP[code],
                "price":      round(price,   2) if price   is not None else None,
                "change_pct": round(chg_pct, 2) if chg_pct is not None else None,
            }
        logger.info(f"[A股指数] {len(result)} indices via akshare fallback")
    except Exception as e:
        logger.warning(f"[A股指数] akshare fallback also failed: {e}")
        result["_error"] = str(e)
    return result


# ── 宏观经济指标（美国：FRED API；中国：国家统计局 + akshare LPR）────────────

_FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# (series_id, key, label, units, format_fn)
# units: lin=原值 | pc1=同比% | pch=月环比% | chg=绝对变化（上期差）
_FRED_SERIES = [
    ("FEDFUNDS",  "fed_rate",       "美联储基准利率",        "lin",
     lambda v: f"{float(v):.2f}%"),
    ("CPIAUCSL",  "cpi",            "美国CPI(同比)",         "pc1",
     lambda v: f"{float(v):.2f}%"),
    ("PPIACO",    "ppi",            "美国PPI(同比)",         "pc1",
     lambda v: f"{float(v):.2f}%"),
    ("PAYEMS",    "non_farm",       "非农就业变化",          "chg",
     lambda v: f"{float(v):+.0f}千人"),
    ("UNRATE",    "unemployment",   "美国失业率",            "lin",
     lambda v: f"{float(v):.1f}%"),
    ("IC4WSA",    "initial_jobless","初申失业金(当周)",       "lin",
     lambda v: f"{float(v)/10000:.1f}万人"),
    ("RSAFS",     "retail_sales",   "零售销售(月环比)",       "pch",
     lambda v: f"{float(v):+.2f}%"),
]

# 中国宏观：国家统计局 JSON API（无需鉴权）
# endpoint 文档: https://data.stats.gov.cn/easyquery.htm
_EM_MACRO_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_EM_HEADERS   = {
    "User-Agent": HEADERS["User-Agent"],
    "Referer":    "https://data.eastmoney.com/",
}

_MACRO_CN_AKSHARE = [
    ("pmi_mfg", "中国官方制造业PMI", "macro_china_pmi_yearly"),
    ("cpi",     "中国CPI(同比%)",    "macro_china_cpi_monthly"),
    ("ppi",     "中国PPI(同比%)",    "macro_china_ppi_yearly"),
]

_DATE_COLS  = ["日期", "时间", "月份", "季度", "period"]
_VALUE_COLS = ["今值", "现值", "最新值", "当月", "当月同比", "实际值", "value"]
_PREV_COLS  = ["前值", "上期值", "前期值", "previous"]
_FCST_COLS  = ["预测值", "预期值", "一致预期", "forecast"]


def _fred_get(api_key: str, series_id: str, units: str) -> dict | None:
    """
    单次 FRED API 请求。优先 curl（规避 Python requests 的 SSL 拦截问题），
    失败时降级 requests verify=False。返回 {date, value} 或 None。
    """
    url = (
        f"{_FRED_BASE}?series_id={series_id}&api_key={api_key}"
        f"&file_type=json&limit=5&sort_order=desc&units={units}"
    )

    def _parse(text: str) -> dict | None:
        d = _json.loads(text)
        for obs in d.get("observations", []):
            if obs.get("value", ".") != ".":
                return {"date": obs.get("date", ""), "value": obs["value"]}
        return None

    # ① curl --noproxy（绕过本地 HTTPS 代理，直连 FRED）
    try:
        proc = subprocess.run(
            ["curl", "-s", "--noproxy", "*", "--max-time", "15", url],
            capture_output=True, text=True, timeout=20,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            result = _parse(proc.stdout)
            if result is not None:
                return result
    except Exception as e:
        logger.debug("[FRED-curl] %s: %s", series_id, e)

    # ② requests 直连（不走系统代理）
    try:
        r = requests.get(_FRED_BASE, params={
            "series_id": series_id, "api_key": api_key,
            "file_type": "json", "limit": "5",
            "sort_order": "desc", "units": units,
        }, headers=HEADERS, timeout=TIMEOUT, proxies={"http": None, "https": None})
        r.raise_for_status()
        return _parse(r.text)
    except Exception as e:
        raise RuntimeError(str(e)) from e


def _fetch_fred_us_macro(api_key: str) -> tuple[dict, list]:
    """通过 FRED API 获取美国最新宏观指标。返回 (data_dict, errors)。"""
    data: dict = {}
    errors: list = []
    for series_id, key, label, units, fmt in _FRED_SERIES:
        try:
            obs = _fred_get(api_key, series_id, units)
            if obs:
                data[key] = {
                    "label":  label,
                    "period": obs["date"],
                    "value":  fmt(obs["value"]),
                }
                logger.debug("[FRED] %s (%s): %s %s", series_id, obs["date"], obs["value"], units)
        except Exception as e:
            errors.append(f"FRED {series_id}: {e}")
            logger.warning("[FRED] %s failed: %s", series_id, e)
    return data, errors


def _fetch_eastmoney_cn_macro() -> tuple[dict, list]:
    """
    通过东方财富 datacenter API 获取中国 CPI/PPI/PMI（与仪表盘 macro_service 同源）。
    """
    data: dict = {}
    errors: list = []

    # CPI
    try:
        r = requests.get(_EM_MACRO_URL, headers=_EM_HEADERS, timeout=TIMEOUT, params={
            "reportName": "RPT_ECONOMY_CPI",
            "columns":    "REPORT_DATE,NATIONAL_SAME,NATIONAL_SEQUENTIAL",
            "pageSize":   "2", "sortColumns": "REPORT_DATE", "sortTypes": -1,
            "source": "WEB",
        })
        r.raise_for_status()
        rows = (r.json().get("result") or {}).get("data") or []
        if rows:
            row = rows[0]
            prev_row = rows[1] if len(rows) >= 2 else None
            period = str(row["REPORT_DATE"])[:7]
            yoy    = float(row["NATIONAL_SAME"])
            prev   = float(prev_row["NATIONAL_SAME"]) if prev_row else None
            data["cpi"] = {
                "label":    "中国CPI(同比%)",
                "period":   period,
                "value":    f"{yoy:+.1f}%",
                "previous": f"{prev:+.1f}%" if prev is not None else "",
            }
    except Exception as e:
        errors.append(f"EM CPI: {e}")

    # PPI
    try:
        r = requests.get(_EM_MACRO_URL, headers=_EM_HEADERS, timeout=TIMEOUT, params={
            "reportName": "RPT_ECONOMY_PPI",
            "columns":    "REPORT_DATE,BASE,BASE_ACCUMULATE",
            "pageSize":   "2", "sortColumns": "REPORT_DATE", "sortTypes": -1,
            "source": "WEB",
        })
        r.raise_for_status()
        rows = (r.json().get("result") or {}).get("data") or []
        if rows:
            row  = rows[0]
            prev = rows[1] if len(rows) >= 2 else None
            yoy  = round(float(row["BASE"]) - 100, 2)
            prev_yoy = round(float(prev["BASE"]) - 100, 2) if prev else None
            data["ppi"] = {
                "label":    "中国PPI(同比%)",
                "period":   str(row["REPORT_DATE"])[:7],
                "value":    f"{yoy:+.1f}%",
                "previous": f"{prev_yoy:+.1f}%" if prev_yoy is not None else "",
            }
    except Exception as e:
        errors.append(f"EM PPI: {e}")

    # PMI（制造业 + 非制造业）
    try:
        r = requests.get(_EM_MACRO_URL, headers=_EM_HEADERS, timeout=TIMEOUT, params={
            "reportName": "RPT_ECONOMY_PMI",
            "columns":    "REPORT_DATE,MAKE_INDEX,NMAKE_INDEX",
            "pageSize":   "2", "sortColumns": "REPORT_DATE", "sortTypes": -1,
            "source": "WEB",
        })
        r.raise_for_status()
        rows = (r.json().get("result") or {}).get("data") or []
        if rows:
            row  = rows[0]
            prev = rows[1] if len(rows) >= 2 else None
            mfg  = float(row["MAKE_INDEX"])  if row.get("MAKE_INDEX")  is not None else None
            svc  = float(row["NMAKE_INDEX"]) if row.get("NMAKE_INDEX") is not None else None
            pm   = float(prev["MAKE_INDEX"]) if prev and prev.get("MAKE_INDEX") is not None else None
            data["pmi_mfg"] = {
                "label":    "官方制造业PMI",
                "period":   str(row["REPORT_DATE"])[:7],
                "value":    f"{mfg:.1f}" if mfg is not None else "N/A",
                "previous": f"{pm:.1f}" if pm is not None else "",
            }
            if svc is not None:
                data["pmi_svc"] = {
                    "label":  "官方非制造业PMI",
                    "period": str(row["REPORT_DATE"])[:7],
                    "value":  f"{svc:.1f}",
                }
    except Exception as e:
        errors.append(f"EM PMI: {e}")

    return data, errors


def _extract_latest_macro(df) -> dict:
    """从 akshare 宏观 DataFrame 提取最新有效行。"""
    if df is None or df.empty:
        return {}
    row = None
    for idx in range(1, min(6, len(df) + 1)):
        candidate = df.iloc[-idx]
        for c in _VALUE_COLS:
            if c in candidate.index:
                val = candidate[c]
                if val is not None and str(val) not in ("", "nan", "None", "NaN"):
                    row = candidate
                    break
        if row is not None:
            break
    if row is None:
        row = df.iloc[-1]
    out: dict = {}
    for cols, k in [(_DATE_COLS, "period"), (_VALUE_COLS, "value"),
                    (_PREV_COLS, "previous"), (_FCST_COLS, "forecast")]:
        for c in cols:
            if c in row.index and row[c] is not None and str(row[c]) not in ("", "nan", "None", "NaN"):
                out[k] = str(row[c])
                break
    return out


def _fetch_china_lpr() -> dict:
    """采集中国LPR（TRADE_DATE / LPR1Y / LPR5Y 非标准列名）。"""
    try:
        import akshare as ak
        df = ak.macro_china_lpr()
        if df is None or df.empty:
            return {}
        row = df.iloc[-1]
        date_val = str(row.get("TRADE_DATE", ""))
        lpr1y = row.get("LPR1Y")
        lpr5y = row.get("LPR5Y")
        out: dict = {}
        if date_val:
            out["period"] = date_val
        if lpr1y == lpr1y and lpr1y is not None:
            out["value"] = str(float(lpr1y))
        if lpr5y == lpr5y and lpr5y is not None:
            out["lpr5y"] = str(float(lpr5y))
        return out
    except Exception as e:
        logger.warning("macro_china_lpr failed: %s", e)
        return {}


def fetch_macro_indicators() -> dict:
    """采集宏观经济指标。失败时记录 error，不中断整体流程。
    美国：FRED API（最新公布值）；中国：国家统计局 + akshare LPR。
    """
    result: dict = {"us": {}, "cn": {}, "errors": []}

    # ── 美国：FRED API ─────────────────────────────────────────────────────
    fred_key = os.environ.get("FRED_API_KEY", "").strip()
    if fred_key:
        us_data, us_errors = _fetch_fred_us_macro(fred_key)
        result["us"].update(us_data)
        result["errors"].extend(us_errors)
        logger.info("[宏观-US] FRED: %d 指标采集成功", len(us_data))
    else:
        result["errors"].append("FRED_API_KEY 未配置，跳过美国宏观数据")
        logger.warning("[宏观-US] FRED_API_KEY not set")

    # ── 中国：东方财富 datacenter → fallback akshare ─────────────────────
    em_data, em_errors = _fetch_eastmoney_cn_macro()
    if em_data:
        result["cn"].update(em_data)
        logger.info("[宏观-CN] EastMoney: %d 指标采集成功", len(em_data))
    if em_errors:
        result["errors"].extend(em_errors)
    # 任何缺失指标降级 akshare
    missing_cn = [k for k, _, _ in _MACRO_CN_AKSHARE if k not in result["cn"]]
    if missing_cn:
        logger.info("[宏观-CN] akshare 补齐: %s", missing_cn)
        try:
            import akshare as ak
            for key, label, fn_name in _MACRO_CN_AKSHARE:
                if key not in missing_cn:
                    continue
                try:
                    fn = getattr(ak, fn_name, None)
                    if fn is None:
                        continue
                    d = _extract_latest_macro(fn())
                    if d:
                        result["cn"][key] = {"label": label, **d}
                except Exception as e:
                    result["errors"].append(f"{label}(akshare): {e}")
        except ImportError:
            result["errors"].append("akshare not installed")

    # LPR 单独采集（列名非标准）
    lpr = _fetch_china_lpr()
    if lpr:
        result["cn"]["lpr"] = {"label": "中国LPR(1年期/5年期)", **lpr}
    else:
        result["errors"].append("中国LPR: 采集失败")

    logger.info(
        "[宏观指标] US=%s, CN=%s, errors=%d",
        list(result["us"].keys()), list(result["cn"].keys()), len(result["errors"])
    )
    return result


# ── 财报日历 ──────────────────────────────────────────────────────────────────

def fetch_earnings_calendar() -> list:
    """采集未来7天美股重要财报（东方财富数据中心）。"""
    import datetime as _dt
    today = _dt.date.today()
    end   = today + _dt.timedelta(days=7)
    try:
        r = requests.get(
            "https://datacenter-web.eastmoney.com/api/data/v1/get",
            params={
                "reportName":  "RPT_USSTOCK_RESULT_CALENDAR_NEW",
                "columns":     "SECURITY_CODE,SECURITY_NAME_ABBR,REPORT_DATE,"
                               "EPS_PREDICT,REVENUE_PREDICT,PERFORMANCE_STATUS",
                "filter":      (f"(REPORT_DATE>='{today.isoformat()}')"
                                f"(REPORT_DATE<='{end.isoformat()}')"),
                "pageSize":    "30",
                "sortTypes":   "1",
                "sortColumns": "REPORT_DATE",
                "source":      "WEB",
                "client":      "WEB",
            },
            headers=HEADERS, timeout=TIMEOUT, proxies=PROXIES,
        )
        r.raise_for_status()
        data = (r.json().get("result") or {}).get("data") or []
        items = []
        for row in data:
            rev = row.get("REVENUE_PREDICT")
            items.append({
                "company":      row.get("SECURITY_NAME_ABBR", ""),
                "code":         row.get("SECURITY_CODE", ""),
                "report_date":  str(row.get("REPORT_DATE", ""))[:10],
                "eps_est":      row.get("EPS_PREDICT"),
                "revenue_est_b": round(float(rev) / 1e9, 2) if rev else None,
                "status":       row.get("PERFORMANCE_STATUS", ""),
            })
        logger.info(f"[财报日历] {len(items)} events (next 7d)")
        return items
    except Exception as e:
        logger.warning(f"[财报日历] fetch failed: {e}")
        return [{"_error": str(e)}]


# ── 主入口 ─────────────────────────────────────────────────────────────────────

def collect_all(sources: list[dict], tickers: list[dict] = None) -> dict:
    """
    采集所有数据源 + 美股行情 + 可配置行情标的。
    tickers: 来自 WatchedTicker 数据库的标的列表，为 None 时跳过。
    """
    news_items: list[dict] = []
    fetch_errors: list[str] = []

    for src in sources:
        if not src.get("enabled", True):
            continue
        stype = src.get("source_type", "rss")
        if stype == "rss":
            items = fetch_rss(src)
        elif stype == "akshare":
            items = fetch_akshare(src)
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

    # 可配置行情标的
    if tickers:
        ai_result = fetch_ai_stocks(tickers)
        us_market["ai_stocks"] = ai_result["data"]
        fetch_errors.extend(ai_result["errors"])
    else:
        us_market["ai_stocks"] = {}

    cn_market         = fetch_cn_market()
    macro_indicators  = fetch_macro_indicators()
    fetch_errors.extend(macro_indicators.pop("errors", []))
    earnings_calendar = fetch_earnings_calendar()

    return {
        "news":             news_items,
        "us_market":        us_market,
        "cn_market":        cn_market,
        "macro_indicators": macro_indicators,
        "earnings_calendar": earnings_calendar,
        "fetch_errors":     fetch_errors,
    }

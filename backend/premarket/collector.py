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
    if "caixin" in name_lower or "财新" in name_lower:
        return _fetch_caixin(source)
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


# ── A股资本市场事件（内置，不依赖数据库配置） ───────────────────────────────────

def fetch_cn_capital_events() -> list[dict]:
    """
    采集A股资本市场监管事件：IPO辅导备案（近30天）、IPO申报受理（近7天有变更）。
    这类事件不出现在普通新闻RSS中，需要从监管数据库直接拉取。
    """
    items = []
    now = datetime.now(timezone.utc)
    cutoff_7d  = now - timedelta(days=7)
    cutoff_30d = now - timedelta(days=30)

    try:
        import akshare as ak

        # 1. IPO 辅导备案（近30天）
        try:
            df = ak.stock_ipo_tutor_em()
            cnt = 0
            for _, row in df.iterrows():
                date_str = str(row.get("备案日期", ""))
                pub = _parse_time(date_str)
                try:
                    dt = datetime.fromisoformat(pub)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if dt < cutoff_30d:
                        continue
                except Exception:
                    pass
                company  = str(row.get("企业名称", ""))
                broker   = str(row.get("辅导机构", ""))
                bureau   = str(row.get("派出机构", ""))
                status   = str(row.get("辅导状态", ""))
                items.append({
                    "source": "A股IPO动态",
                    "category": "国内",
                    "title": f"【IPO辅导备案】{company} 启动上市辅导，辅导机构：{broker}",
                    "url": "",
                    "summary": (f"{company} 向{bureau}提交IPO辅导备案。"
                                f"辅导机构：{broker}，状态：{status}，备案日期：{date_str}。"),
                    "published_at": pub,
                })
                cnt += 1
            logger.info(f"[IPO辅导] {cnt} items in last 30d")
        except Exception as e:
            logger.warning(f"[IPO辅导] {e}")

        # 2. IPO 申报受理（近7天有变更）
        try:
            df2 = ak.stock_ipo_declare_em()
            cnt = 0
            for _, row in df2.iterrows():
                date_str = str(row.get("更新日期", ""))
                pub = _parse_time(date_str)
                try:
                    dt = datetime.fromisoformat(pub)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if dt < cutoff_7d:
                        continue
                except Exception:
                    pass
                company  = str(row.get("企业名称", ""))
                status   = str(row.get("最新状态", ""))
                location = str(row.get("拟上市地点", ""))
                broker   = str(row.get("保荐机构", ""))
                items.append({
                    "source": "A股IPO动态",
                    "category": "国内",
                    "title": f"【IPO申报】{company} 状态：{status}，拟上市{location}",
                    "url": "",
                    "summary": (f"{company} IPO申报最新状态：{status}。"
                                f"拟上市地点：{location}，保荐机构：{broker}，更新日期：{date_str}。"),
                    "published_at": pub,
                })
                cnt += 1
            logger.info(f"[IPO申报] {cnt} items in last 7d")
        except Exception as e:
            logger.warning(f"[IPO申报] {e}")

    except ImportError:
        logger.warning("[CN Capital Events] akshare not installed")
    except Exception as e:
        logger.warning(f"[CN Capital Events] {e}")

    return items


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

    # ── US ETF via 新浪财经实时行情 ───────────────────────────────────────
    # 一次请求拿三个 ETF，字段：名称,现价,涨跌幅%,时间,涨跌额,...
    etf_need = [s for s in ("SPY", "QQQ", "DIA") if s not in result["indices"]]
    if etf_need:
        sina_sym_map = {"SPY": "gb_spy", "QQQ": "gb_qqq", "DIA": "gb_dia"}
        sina_query = ",".join(sina_sym_map[s] for s in etf_need)
        try:
            r = requests.get(
                f"https://hq.sinajs.cn/list={sina_query}",
                headers={**HEADERS, "Referer": "https://finance.sina.com.cn/"},
                timeout=TIMEOUT, proxies=PROXIES,
            )
            r.raise_for_status()
            import re
            for sym in etf_need:
                label = _US_SYMBOLS["indices"][sym]
                m = re.search(rf'hq_str_{sina_sym_map[sym]}="([^"]*)"', r.text)
                if not m or not m.group(1):
                    result["errors"].append(f"{sym}: empty response (Sina)")
                    continue
                parts = m.group(1).split(",")
                if len(parts) < 5:
                    result["errors"].append(f"{sym}: unexpected format (Sina)")
                    continue
                last     = float(parts[1])
                chg_pct  = float(parts[2])          # 涨跌幅，已是百分比数字
                chg_amt  = float(parts[4])          # 涨跌额
                prev     = round(last - chg_amt, 4) if chg_amt else None
                result["indices"][sym] = {
                    "label": label,
                    "price": round(last, 4),
                    "change_pct": round(chg_pct, 2),
                }
                _clean_err(sym)
                logger.info(f"[Sina] {sym}: {last} ({chg_pct:+.2f}%)")
        except Exception as e:
            for sym in etf_need:
                result["errors"].append(f"{sym} (Sina): {e}")

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

    # ── 美股指期货 + 大宗商品 via 东方财富 futures_global_spot_em ─────────
    # XX00Y = 东方财富当月连续合约命名规范，一次调用返回全部品种
    futures_spot_map = {
        "ES=F": ("ES00Y", "标普500期货",  "futures"),
        "NQ=F": ("NQ00Y", "纳指期货",     "futures"),
        "YM=F": ("YM00Y", "道指期货",     "futures"),
        "GC=F": ("GC00Y", "黄金",         "commodities"),
        "SI=F": ("SI00Y", "COMEX白银",    "commodities"),
        "HG=F": ("HG00Y", "COMEX铜",      "commodities"),
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
    result = {"indices": {}, "futures": {}, "commodities": {}, "errors": []}
    total = sum(len(v) for v in _US_SYMBOLS.values())

    yf_success = _fill_yfinance(result)

    # 若超过半数标的失败（通常是云主机无法访问 Yahoo Finance），启用国内数据源兜底
    if yf_success < total // 2:
        logger.info(
            f"yfinance: {yf_success}/{total} symbols fetched, "
            "falling back to Sina/CBOE/EastMoney for missing data"
        )
        _fill_china_sources(result)

    fetched = (len(result["indices"]) + len(result["futures"]) + len(result["commodities"]))
    logger.info(
        f"US market: {fetched}/{total} symbols OK, "
        f"indices={list(result['indices'])}, errors={result['errors']}"
    )
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

    # A股资本市场事件（IPO辅导、申报受理）— 内置，不依赖数据库配置
    cn_events = fetch_cn_capital_events()
    news_items.extend(cn_events)

    us_market = fetch_us_market()
    fetch_errors.extend(us_market.pop("errors", []))

    return {
        "news": news_items,
        "us_market": us_market,
        "fetch_errors": fetch_errors,
    }

"""清洗层：去重 → 时间戳统一（Asia/Shanghai）→ AI关键词过滤 → 矩阵打标 → 实体抽取 → 信号评分。"""
import hashlib
import logging
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

# ══════════════════════════════════════════════════════════════════════════════
# §1  时间戳工具
# ══════════════════════════════════════════════════════════════════════════════

def _to_shanghai(ts_str: str) -> str:
    """任意 ISO 时间戳 → Asia/Shanghai ISO 字符串；解析失败原样返回。"""
    if not ts_str:
        return ts_str
    try:
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(SHANGHAI_TZ).isoformat()
    except Exception:
        return ts_str


def _ts_sort_key(ts_str: str) -> float:
    try:
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=SHANGHAI_TZ)
        return dt.timestamp()
    except Exception:
        return 0.0


# ══════════════════════════════════════════════════════════════════════════════
# §2  AI 过滤关键词（兜底静态列表；运行时被框架关键词动态替换）
# ══════════════════════════════════════════════════════════════════════════════

_AI_KEYWORDS_FALLBACK = [
    "GPU", "TPU", "NPU", "ASIC", "AI芯片", "芯片", "英伟达", "NVIDIA", "AMD",
    "英特尔", "Intel", "高通", "Qualcomm", "博通", "Broadcom", "Marvell",
    "台积电", "TSMC", "SK海力士", "HBM", "高带宽内存", "先进封装", "CoWoS",
    "数据中心", "服务器", "算力", "光模块", "800G", "1.6T",
    "HBM3", "HBM3E", "DRAM", "NAND", "美光", "Micron", "长江存储", "长鑫存储",
    "大模型", "LLM", "基础模型", "多模态", "AGI",
    "GPT", "Claude", "Gemini", "Llama", "DeepSeek", "通义千问", "文心",
    "OpenAI", "Anthropic", "Google DeepMind", "Meta AI", "xAI",
    "云计算", "Azure", "AWS", "Google Cloud", "阿里云", "华为云",
    "AI应用", "AI Agent", "Copilot", "AIGC", "具身智能", "人形机器人", "自动驾驶",
    "华为", "寒武纪", "海光信息", "北方华创", "中微公司", "剑桥科技", "科大讯飞",
    "Super Micro", "Arista", "Cisco", "思科", "Salesforce", "Palantir",
    "artificial intelligence", "machine learning", "deep learning",
    "neural network", "transformer",
]

_AI_PATTERN_FALLBACK = re.compile(
    "|".join(re.escape(kw) for kw in sorted(_AI_KEYWORDS_FALLBACK, key=len, reverse=True)),
    re.IGNORECASE,
)


def _build_fw_filter_pattern(framework: dict) -> re.Pattern:
    """
    从框架 keyword_dict（各层/列关键词）+ entity_matrix（别名）
    合并兜底列表，构建动态 AI 相关性过滤正则。
    框架关键词为空时退化为静态兜底列表。
    """
    keywords: set[str] = set(_AI_KEYWORDS_FALLBACK)
    for layer in framework.get("layers", []):
        keywords.update(layer.get("keywords", []))
    for col in framework.get("columns", []):
        keywords.update(col.get("keywords", []))
    for ent in framework.get("entity_matrix", []):
        keywords.update(a for a in ent.get("aliases", []) if len(a) >= 2)
    if not keywords:
        return _AI_PATTERN_FALLBACK
    return re.compile(
        "|".join(re.escape(k) for k in sorted(keywords, key=len, reverse=True)),
        re.IGNORECASE,
    )


# ══════════════════════════════════════════════════════════════════════════════
# §3  事件类型 & 情感（与框架层无关，保持独立）
# ══════════════════════════════════════════════════════════════════════════════

_EVENT_KWDS: dict[str, list[str]] = {
    "财报业绩": [
        "财报", "业绩", "营收", "净利润", "利润", "EPS", "收入", "毛利",
        "季报", "年报", "Q1", "Q2", "Q3", "Q4", "超预期", "不及预期",
        "earnings", "revenue", "profit", "quarterly", "guidance",
    ],
    "政策监管": [
        "政策", "监管", "法规", "出口管制", "制裁", "黑名单", "实体清单",
        "补贴", "禁令", "合规", "审查", "反垄断", "数据安全",
        "regulation", "policy", "ban", "sanction", "export control", "subsidy",
    ],
    "产品技术": [
        "发布", "推出", "上线", "开源", "开放", "发表", "论文", "新品",
        "突破", "里程碑", "技术", "架构", "参数", "性能", "基准测试",
        "launch", "release", "announce", "paper", "benchmark", "open-source",
    ],
    "融资并购": [
        "融资", "收购", "并购", "投资", "估值", "IPO", "上市", "私有化",
        "战略投资", "股权", "债券",
        "merger", "acquisition", "funding", "invest", "valuation",
    ],
    "市场行情": [
        "涨停", "跌停", "创新高", "创新低", "暴涨", "暴跌", "回调", "反弹",
        "买入", "卖出", "做多", "做空", "评级", "目标价",
        "surge", "plunge", "rally", "sell-off", "upgrade", "downgrade", "target",
    ],
    "人事变动": [
        "CEO", "CFO", "CTO", "COO", "董事长", "总裁", "总经理",
        "辞职", "离职", "任命", "上任", "退休", "接任",
        "resign", "appoint", "hire", "fire", "step down", "join",
    ],
    "战略合作": [
        "合作", "签约", "战略", "协议", "联盟", "生态", "伙伴",
        "partnership", "collaboration", "deal", "agreement", "alliance",
    ],
}

_SENTIMENT_POS = [
    "涨", "上涨", "涨停", "创新高", "超预期", "利好", "突破", "强劲", "增长",
    "盈利", "beat", "surge", "rally", "record", "strong",
    "positive", "growth", "profit", "upgrade", "bullish", "upside",
]
_SENTIMENT_NEG = [
    "跌", "下跌", "跌停", "暴跌", "大跌", "减少", "亏损", "下滑", "风险",
    "制裁", "不及预期", "警告", "miss", "plunge", "crash", "loss", "weak",
    "negative", "decline", "downgrade", "bearish", "downside", "risk",
]

_EVENT_PATTERNS = {
    etype: re.compile(
        "|".join(re.escape(kw) for kw in sorted(kwds, key=len, reverse=True)),
        re.IGNORECASE,
    )
    for etype, kwds in _EVENT_KWDS.items()
}
_POS_PATTERN = re.compile(
    "|".join(re.escape(w) for w in sorted(_SENTIMENT_POS, key=len, reverse=True)),
    re.IGNORECASE,
)
_NEG_PATTERN = re.compile(
    "|".join(re.escape(w) for w in sorted(_SENTIMENT_NEG, key=len, reverse=True)),
    re.IGNORECASE,
)


def _tag_event_sentiment(text: str) -> dict:
    """事件类型 + 情感极性。"""
    events = [e for e, pat in _EVENT_PATTERNS.items() if pat.search(text)]
    pos = bool(_POS_PATTERN.search(text))
    neg = bool(_NEG_PATTERN.search(text))
    if pos and not neg:
        sentiment = "positive"
    elif neg and not pos:
        sentiment = "negative"
    elif pos and neg:
        sentiment = "mixed"
    else:
        sentiment = "neutral"
    return {"event_types": events, "sentiment": sentiment}


# ══════════════════════════════════════════════════════════════════════════════
# §4  矩阵打标（8层 × 3列，基于 framework.py 动态加载）
# ══════════════════════════════════════════════════════════════════════════════

# 数字证据正则：带单位的数值，用于信号强度评分
_NUMERIC_EVIDENCE = re.compile(
    r'\d+\.?\d*\s*(%|亿|万|trillion|billion|million|bn|mn|\$|USD|CNY|RMB)',
    re.IGNORECASE,
)


def _tag_framework(text: str, patterns: dict) -> dict:
    """
    基于框架定义对单条文本打标。
    返回: {layers: [L1, ...], columns: [cloud, ...], is_bottleneck: bool}
    """
    matched_layers = [
        lid for lid, info in patterns["layers"].items()
        if info["pattern"].search(text)
    ]
    matched_columns = [
        cid for cid, info in patterns["columns"].items()
        if info["pattern"].search(text)
    ]
    is_bottleneck = any(
        patterns["layers"][lid]["meta"].get("physical_bottleneck", False)
        for lid in matched_layers
        if lid in patterns["layers"]
    )
    return {
        "layers":       matched_layers,
        "columns":      matched_columns,
        "is_bottleneck": is_bottleneck,
    }


def _signal_strength(text: str, layers: list, entities: list, is_bottleneck: bool) -> str:
    """
    信号强度评分：high / medium / low
    积分规则：
      +1~2  数字证据（% / 亿 / billion 等带单位数值，最多计2分）
      +1~2  框架层级命中数（最多计2分）
      +1~2  实体数量（最多计2分）
      +2    命中瓶颈层（L1/L2/L3）
    总分 ≥ 5 → high；≥ 2 → medium；否则 → low
    """
    score = 0
    score += min(len(_NUMERIC_EVIDENCE.findall(text)), 2)
    score += min(len(layers), 2)
    score += min(len(entities), 2)
    if is_bottleneck:
        score += 2
    if score >= 5:
        return "high"
    elif score >= 2:
        return "medium"
    return "low"


# ══════════════════════════════════════════════════════════════════════════════
# §5  实体抽取（动态加载自框架 entity_matrix，A股代码兜底）
# ══════════════════════════════════════════════════════════════════════════════

_A_CODE_PATTERN = re.compile(r"(?<!\d)([0-9]{6})(?!\d)")


def _build_entity_patterns(entity_matrix: list[dict]) -> tuple[dict, re.Pattern]:
    """
    从 entity_matrix 构建 alias→entity 查找表和预编译正则。
    别名按长度降序排列，避免短词遮蔽长词。
    """
    alias_map: dict[str, dict] = {}
    for ent in entity_matrix:
        for alias in ent.get("aliases", []):
            alias_map[alias] = ent
    aliases_sorted = sorted(alias_map.keys(), key=len, reverse=True)
    if not aliases_sorted:
        pattern = re.compile(r"(?!x)x")
    else:
        pattern = re.compile(
            "|".join(re.escape(a) for a in aliases_sorted),
            re.IGNORECASE,
        )
    return alias_map, pattern


def _extract_entities(text: str, alias_map: dict, entity_pattern: re.Pattern) -> list[dict]:
    """从文本中抽取实体，去重后返回列表（含 layers/columns 矩阵位置）。"""
    seen_keys: set = set()
    entities: list[dict] = []

    for match in entity_pattern.finditer(text or ""):
        alias = match.group(0)
        ent = alias_map.get(alias) or alias_map.get(alias.upper())
        if not ent:
            continue
        key = ent.get("symbol") or ent["name"]
        if key in seen_keys:
            continue
        seen_keys.add(key)
        entities.append({
            "name":    ent["name"],
            "symbol":  ent.get("symbol"),
            "market":  ent.get("market"),
            "layers":  ent.get("layers", []),
            "columns": ent.get("columns", []),
        })

    # 补充文中出现的 A 股代码（实体库未命中的）
    for m in _A_CODE_PATTERN.finditer(text or ""):
        code = m.group(1)
        if code not in seen_keys:
            seen_keys.add(code)
            entities.append({"name": code, "symbol": code, "market": "A", "layers": [], "columns": []})

    return entities


# ══════════════════════════════════════════════════════════════════════════════
# §6  去重 & 唯一 ID
# ══════════════════════════════════════════════════════════════════════════════

def _fingerprint(item: dict) -> str:
    """优先用 URL；URL 为空时用标题 MD5（跨源同标题去重）。"""
    url   = (item.get("url") or "").strip()
    title = (item.get("title") or "").strip()
    key   = url if url else title
    return hashlib.md5(key.encode("utf-8", errors="ignore")).hexdigest()


def _make_item_id(published_at: str, fp: str) -> str:
    """YYYYMMDD-{8位 fingerprint}，日期取自 published_at（上海时区）。"""
    try:
        dt = datetime.fromisoformat(published_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=SHANGHAI_TZ)
        date_str = dt.astimezone(SHANGHAI_TZ).strftime("%Y%m%d")
    except Exception:
        date_str = datetime.now(SHANGHAI_TZ).strftime("%Y%m%d")
    return f"{date_str}-{fp[:8]}"


# ══════════════════════════════════════════════════════════════════════════════
# §7  按层级汇总（framework_summary）
# ══════════════════════════════════════════════════════════════════════════════

_STRENGTH_ORDER = {"high": 0, "medium": 1, "low": 2}


def _build_framework_summary(filtered: list[dict], framework: dict) -> dict:
    """
    按框架层级汇总已过滤的新闻和实体，供 {{framework_news_json}} 注入 prompt。
    返回: { layer_id: { layer_name, is_bottleneck, news_count, high_signal, entities, top_news } }
    """
    layer_meta = {layer["id"]: layer for layer in framework.get("layers", [])}
    buckets: dict[str, list[dict]] = {lid: [] for lid in layer_meta}

    for item in filtered:
        for lid in (item.get("layers") or []):
            if lid in buckets:
                buckets[lid].append(item)

    summary: dict = {}
    for lid, items in buckets.items():
        if not items:
            continue
        meta = layer_meta.get(lid, {})

        # Deduplicate entities across all items in this layer
        seen_ent: set = set()
        entities: list[dict] = []
        for item in items:
            for ent in (item.get("entities") or []):
                key = ent.get("symbol") or ent["name"]
                if key not in seen_ent:
                    seen_ent.add(key)
                    entities.append({
                        "name":   ent["name"],
                        "symbol": ent.get("symbol"),
                        "market": ent.get("market"),
                    })

        # Top-10 news sorted by signal strength (high first) then newest first
        sorted_items = sorted(
            items,
            key=lambda x: (
                _STRENGTH_ORDER.get(x.get("signal_strength", "low"), 2),
                -_ts_sort_key(x.get("published_at", "")),
            ),
        )
        top_news = [
            {
                "title":           i.get("title", ""),
                "summary":         i.get("summary", ""),
                "source":          i.get("source", ""),
                "published_at":    i.get("published_at", ""),
                "sentiment":       i.get("sentiment", ""),
                "signal_strength": i.get("signal_strength", ""),
                "event_types":     i.get("event_types", []),
            }
            for i in sorted_items[:10]
        ]

        summary[lid] = {
            "layer_name":    meta.get("name", lid),
            "is_bottleneck": meta.get("physical_bottleneck", False),
            "news_count":    len(items),
            "high_signal":   sum(1 for i in items if i.get("signal_strength") == "high"),
            "entities":      entities[:20],
            "top_news":      top_news,
        }

    return summary


# ══════════════════════════════════════════════════════════════════════════════
# §8  主入口
# ══════════════════════════════════════════════════════════════════════════════

def clean(raw_data: dict) -> dict:
    """
    输入: collect_all() 的返回值
    输出结构:
      {
        "news": [enriched items],
        "us_market", "cn_market", "macro_indicators", "earnings_calendar",
        "fetch_errors", "stats"
      }
    每条 news item 附带:
      published_at   → Asia/Shanghai ISO
      layers         → 命中的框架层 ID 列表，如 ["L3", "L4"]
      columns        → 命中的框架列 ID 列表，如 ["cloud"]
      is_bottleneck  → 是否命中 L1/L2/L3 物理瓶颈层
      event_types    → 事件类型列表
      sentiment      → positive / negative / mixed / neutral
      entities       → 实体列表（name, symbol, market, layers）
      signal_strength→ high / medium / low
      item_id        → YYYYMMDD-{hash8} 唯一标识
    """
    # 每次运行时从 DB（或 DEFAULT_FRAMEWORK 兜底）加载最新框架
    from premarket.framework import get_framework, build_patterns, DEFAULT_ENTITY_MATRIX
    framework = get_framework()
    patterns  = build_patterns(framework)
    entity_matrix = framework.get("entity_matrix") or DEFAULT_ENTITY_MATRIX
    alias_map, entity_pattern = _build_entity_patterns(entity_matrix)

    news_raw:          list[dict] = raw_data.get("news", [])
    us_market:         dict       = raw_data.get("us_market", {})
    cn_market:         dict       = raw_data.get("cn_market", {})
    macro_indicators:  dict       = raw_data.get("macro_indicators", {"us": {}, "cn": {}})
    earnings_calendar: list       = raw_data.get("earnings_calendar", [])
    fetch_errors:      list[str]  = raw_data.get("fetch_errors", [])

    # ── Step 1：去重（保留 fingerprint 供后续生成 item_id）──────────────────
    seen: set[str] = set()
    deduped: list[dict] = []
    fps: dict[int, str] = {}  # id(item) → fp
    for item in news_raw:
        fp = _fingerprint(item)
        if fp not in seen:
            seen.add(fp)
            fps[id(item)] = fp
            deduped.append(item)

    # ── Step 2：时间戳统一为 Asia/Shanghai ────────────────────────────────
    for item in deduped:
        item["published_at"] = _to_shanghai(item.get("published_at", ""))

    # ── Step 3：AI 关键词过滤（动态框架关键词 + 实体别名 + 兜底列表）────
    fw_ai_pattern = _build_fw_filter_pattern(framework)
    filtered: list[dict] = []
    for item in deduped:
        combined = (item.get("title") or "") + " " + (item.get("summary") or "")
        if fw_ai_pattern.search(combined):
            item["ai_related"] = True
            filtered.append(item)

    # ── Step 4：矩阵打标（8层 × 3列框架）────────────────────────────────
    for item in filtered:
        combined = (item.get("title") or "") + " " + (item.get("summary") or "")
        fw_tags = _tag_framework(combined, patterns)
        item["layers"]       = fw_tags["layers"]
        item["columns"]      = fw_tags["columns"]
        item["is_bottleneck"]= fw_tags["is_bottleneck"]
        ev_tags = _tag_event_sentiment(combined)
        item["event_types"]  = ev_tags["event_types"]
        item["sentiment"]    = ev_tags["sentiment"]

    # ── Step 5：实体抽取 ──────────────────────────────────────────────────
    for item in filtered:
        combined = (item.get("title") or "") + " " + (item.get("summary") or "")
        item["entities"] = _extract_entities(combined, alias_map, entity_pattern)

    # ── Step 6：信号强度评分 ──────────────────────────────────────────────
    for item in filtered:
        combined = (item.get("title") or "") + " " + (item.get("summary") or "")
        item["signal_strength"] = _signal_strength(
            combined,
            item["layers"],
            item["entities"],
            item["is_bottleneck"],
        )

    # ── Step 7：分配唯一 item_id ──────────────────────────────────────────
    for item in filtered:
        fp = fps.get(id(item), _fingerprint(item))
        item["item_id"] = _make_item_id(item.get("published_at", ""), fp)

    # ── Step 8：按发布时间降序排列 ────────────────────────────────────────
    filtered.sort(key=lambda x: _ts_sort_key(x.get("published_at", "")), reverse=True)

    # ── Step 9：按层级汇总（供 {{framework_news_json}} 注入）────────────
    framework_summary = _build_framework_summary(filtered, framework)

    stats = {
        "total_raw":    len(news_raw),
        "after_dedup":  len(deduped),
        "after_filter": len(filtered),
    }
    logger.info(
        "Clean: raw=%d dedup=%d filter=%d | "
        "layers_tagged=%d bottleneck=%d high_signal=%d",
        stats["total_raw"], stats["after_dedup"], stats["after_filter"],
        sum(1 for i in filtered if i.get("layers")),
        sum(1 for i in filtered if i.get("is_bottleneck")),
        sum(1 for i in filtered if i.get("signal_strength") == "high"),
    )

    return {
        "news":               filtered,
        "us_market":          us_market,
        "cn_market":          cn_market,
        "macro_indicators":   macro_indicators,
        "earnings_calendar":  earnings_calendar,
        "fetch_errors":       fetch_errors,
        "stats":              stats,
        "framework_summary":  framework_summary,
    }

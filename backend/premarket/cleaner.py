"""清洗层：去重、时间戳统一、AI 产业链关键词过滤，产出结构化 JSON。"""
import hashlib
import logging
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── AI 产业链关键词 ────────────────────────────────────────────────────────────

AI_KEYWORDS = [
    # 算力层
    "GPU", "TPU", "NPU", "AI芯片", "芯片", "英伟达", "NVIDIA", "AMD", "英特尔", "Intel",
    "台积电", "TSMC", "三星", "SK海力士", "HBM", "高带宽内存", "先进封装",
    "CoWoS", "数据中心", "服务器", "光模块", "800G", "1.6T", "400G",
    "液冷", "散热", "电力", "UPS", "算力", "超算", "集群",
    # 模型与平台层
    "大模型", "LLM", "GPT", "Claude", "Gemini", "Llama", "Mistral", "Deepseek",
    "DeepSeek", "通义千问", "文心", "混元", "Kimi", "OpenAI", "Anthropic",
    "Google AI", "Meta AI", "微软AI", "Azure AI", "AWS AI", "百度AI",
    "云计算", "云服务", "AGI", "多模态", "推理", "训练",
    # 应用层
    "AI应用", "AI Agent", "Agent", "Copilot", "AI软件", "AIGC",
    "AI医疗", "AI教育", "AI金融", "AI制造", "具身智能", "机器人",
    "自动驾驶", "无人驾驶", "人形机器人",
    # 配套基础设施
    "网络设备", "交换机", "路由器", "存储", "SSD", "NAND",
    "PCIe", "InfiniBand", "RoCE", "以太网",
    # 公司名
    "英伟达", "AMD", "博通", "Broadcom", "Marvell", "Arista", "思科", "Cisco",
    "美光", "Micron", "西部数据", "希捷", "超微", "Super Micro", "SMCI",
    "甲骨文", "Oracle", "Salesforce", "Palantir",
    # 中国AI公司
    "华为", "寒武纪", "海光", "龙芯", "剑桥科技", "中际旭创",
    "新易盛", "天孚通信", "光迅科技",
    # 通用
    "artificial intelligence", "machine learning", "deep learning",
    "neural network", "transformer", "foundation model",
]

AI_PATTERN = re.compile(
    "|".join(re.escape(kw) for kw in AI_KEYWORDS),
    re.IGNORECASE,
)


def _is_ai_related(text: str) -> bool:
    return bool(AI_PATTERN.search(text or ""))


def _fingerprint(item: dict) -> str:
    key = (item.get("url") or "") + (item.get("title") or "")
    return hashlib.md5(key.encode("utf-8", errors="ignore")).hexdigest()


def clean(raw_data: dict) -> dict:
    """
    输入: collect_all() 的返回值
    输出: {
        "news": [...filtered+dedup news...],
        "us_market": {...},
        "fetch_errors": [...],
        "stats": {"total_raw": N, "after_dedup": M, "after_filter": K}
    }
    """
    news_raw: list[dict] = raw_data.get("news", [])
    us_market: dict = raw_data.get("us_market", {})
    fetch_errors: list[str] = raw_data.get("fetch_errors", [])

    # 1. 去重
    seen: set[str] = set()
    deduped: list[dict] = []
    for item in news_raw:
        fp = _fingerprint(item)
        if fp not in seen:
            seen.add(fp)
            deduped.append(item)

    # 2. AI 关键词过滤
    filtered: list[dict] = []
    for item in deduped:
        combined = (item.get("title") or "") + " " + (item.get("summary") or "")
        if _is_ai_related(combined):
            item["ai_related"] = True
            filtered.append(item)

    # 3. 按发布时间降序排列
    def _sort_key(x):
        try:
            return datetime.fromisoformat(x.get("published_at", "")).timestamp()
        except Exception:
            return 0.0

    filtered.sort(key=_sort_key, reverse=True)

    stats = {
        "total_raw": len(news_raw),
        "after_dedup": len(deduped),
        "after_filter": len(filtered),
    }
    logger.info(f"Clean stats: {stats}")

    return {
        "news": filtered,
        "us_market": us_market,
        "fetch_errors": fetch_errors,
        "stats": stats,
    }

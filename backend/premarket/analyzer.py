"""分析层：调用大模型（流式），基于清洗后的结构化 JSON 生成 AI 产业链观察清单。"""
import json
import logging
import re
import threading
from typing import Optional

import requests

logger = logging.getLogger(__name__)

TIMEOUT = 120

# ── 流式输出内存缓冲区（record_id → {text, done}）──
_stream_lock = threading.Lock()
_stream_data: dict = {}


def _init_stream(record_id: int):
    with _stream_lock:
        _stream_data[record_id] = {"text": "", "done": False}


def _append_stream(record_id: int, chunk: str):
    with _stream_lock:
        if record_id in _stream_data:
            _stream_data[record_id]["text"] += chunk


def _finish_stream(record_id: int):
    with _stream_lock:
        if record_id in _stream_data:
            _stream_data[record_id]["done"] = True


def get_stream_snapshot(record_id: int) -> dict:
    with _stream_lock:
        return dict(_stream_data.get(record_id, {"text": "", "done": False}))


def clear_stream(record_id: int):
    with _stream_lock:
        _stream_data.pop(record_id, None)


# ── LLM 配置 & 模板查询 ──

def _get_default_llm(db=None) -> Optional[object]:
    """优先取 is_default=1 的配置，找不到取第一条。
    始终使用独立 session，避免管道主 session 的事务状态干扰读取。"""
    try:
        from database import SessionLocal
        from models import LLMConfig
        _db = SessionLocal()
        try:
            cfg = _db.query(LLMConfig).filter(LLMConfig.is_default == 1).first()
            if not cfg:
                cfg = _db.query(LLMConfig).first()
            if cfg:
                _db.expunge(cfg)  # 脱离 session，让调用方持有对象
            return cfg
        finally:
            _db.close()
    except Exception as e:
        logger.error(f"Failed to load LLM config: {e}", exc_info=True)
        return None


def _get_active_template(db=None, name: str = None) -> Optional[str]:
    """优先按名称匹配激活模板，找不到再用默认，再退而求其次任意激活模板。
    始终使用独立 session，避免管道主 session 的事务状态干扰读取。"""
    try:
        from database import SessionLocal
        from models import PromptTemplate
        _db = SessionLocal()
        try:
            if name:
                tpl = _db.query(PromptTemplate).filter(
                    PromptTemplate.name == name,
                    PromptTemplate.status == "active"
                ).first()
                if not tpl:
                    tpl = _db.query(PromptTemplate).filter(
                        PromptTemplate.name.contains(name),
                        PromptTemplate.status == "active"
                    ).first()
                if tpl:
                    logger.info(f"Using template by name match: {tpl.name}")
                    return tpl.content
            tpl = _db.query(PromptTemplate).filter(
                PromptTemplate.is_default == 1, PromptTemplate.status == "active"
            ).first()
            if not tpl:
                tpl = _db.query(PromptTemplate).filter(PromptTemplate.status == "active").first()
            if tpl:
                logger.info(f"Using template: {tpl.name}")
            return tpl.content if tpl else None
        finally:
            _db.close()
    except Exception as e:
        logger.error(f"Failed to load prompt template: {e}", exc_info=True)
        return None


def _build_framework_structure() -> str:
    """
    从数据库读取当前活跃的产业链框架，序列化为 JSON 字符串注入 prompt。
    格式与其他模板变量（news_json / us_market_json 等）保持一致。
    优先使用 framework_data（WYSIWYG 层级树），退而使用 entity_matrix 扁平结构。
    """
    try:
        from database import SessionLocal
        from models import AnalysisFramework
        _db = SessionLocal()
        try:
            row = _db.query(AnalysisFramework).filter(AnalysisFramework.is_active == 1).first()
            if not row:
                return "{}"

            # ── 优先：hierarchical framework_data ──────────────────────────
            fd = json.loads(row.framework_data or "null")
            if fd and fd.get("layers"):
                layers = []
                for layer in fd["layers"]:
                    sectors = []
                    for sec in layer.get("sectors", []):
                        sectors.append({
                            "name":               sec["name"],
                            "description":        sec.get("description", ""),
                            "physical_bottleneck":sec.get("physical_bottleneck", False),
                            "companies":          [co["name"] for co in sec.get("companies", [])],
                        })
                    layers.append({
                        "id":                  layer["id"],
                        "name":                layer["name"],
                        "physical_bottleneck": layer.get("physical_bottleneck", False),
                        "description":         layer.get("description", ""),
                        "sectors":             sectors,
                    })
                return json.dumps({
                    "name":        row.name or "AI产业链分析框架",
                    "description": row.description or "",
                    "layers":      layers,
                }, ensure_ascii=False, indent=2)

            # ── 退而：entity_matrix 扁平结构 ──────────────────────────────
            ld_raw = json.loads(row.layer_definition or "[]")
            em_raw = json.loads(row.entity_matrix or "[]")
            if not ld_raw:
                return "{}"

            layers_only = [d for d in ld_raw if d.get("type") == "layer"]
            layers = []
            for ld in layers_only:
                companies = [
                    e["name"] for e in em_raw
                    if ld["id"] in (e.get("layers") or [])
                ]
                layers.append({
                    "id":                  ld["id"],
                    "name":                ld["name"],
                    "physical_bottleneck": ld.get("physical_bottleneck", False),
                    "description":         ld.get("description", ""),
                    "companies":           companies,
                })
            return json.dumps({
                "name":        row.name or "AI产业链分析框架",
                "description": row.description or "",
                "layers":      layers,
            }, ensure_ascii=False, indent=2)

        finally:
            _db.close()
    except Exception as e:
        logger.warning("Failed to build framework structure: %s", e)
        return "{}"


_STRENGTH_RANK = {"high": 0, "medium": 1, "low": 2}


def _build_ticker_news(cleaned_data: dict) -> dict:
    """
    为每个行情监控标的关联相关新闻（通过 entities.symbol 匹配）。
    返回: { SYMBOL: {name, price, change_pct, category, news_count, news: [...]} }
    供 {{ticker_news_json}} 模板变量使用。
    """
    ai_stocks: dict = cleaned_data.get("us_market", {}).get("ai_stocks", {})
    news_items: list = cleaned_data.get("news", [])
    if not ai_stocks:
        return {}

    # 预先构建 symbol(upper) → [news_item] 索引
    sym_news: dict[str, list] = {}
    for item in news_items:
        for ent in (item.get("entities") or []):
            sym = (ent.get("symbol") or "").upper().strip()
            if sym:
                sym_news.setdefault(sym, []).append(item)

    result: dict = {}
    for ticker_sym, stock in ai_stocks.items():
        sym_key = ticker_sym.upper().strip()
        related = sym_news.get(sym_key, [])

        # 去重（同一篇新闻可能被多次命中）
        seen_ids: set = set()
        deduped: list = []
        for it in related:
            iid = it.get("item_id") or id(it)
            if iid not in seen_ids:
                seen_ids.add(iid)
                deduped.append(it)

        # 按信号强度（高优先）再按时间降序排列，取前 5 条
        from premarket.cleaner import _ts_sort_key
        deduped.sort(key=lambda x: (
            _STRENGTH_RANK.get(x.get("signal_strength", "low"), 2),
            -_ts_sort_key(x.get("published_at", "")),
        ))
        top = deduped[:5]

        result[ticker_sym] = {
            "name":        stock.get("label", ticker_sym),
            "price":       stock.get("price"),
            "change_pct":  stock.get("change_pct"),
            "category":    stock.get("category", ""),
            "news_count":  len(deduped),
            "news": [
                {
                    "title":           it.get("title", ""),
                    "summary":         it.get("summary", ""),
                    "source":          it.get("source", ""),
                    "published_at":    it.get("published_at", ""),
                    "sentiment":       it.get("sentiment", ""),
                    "signal_strength": it.get("signal_strength", ""),
                    "event_types":     it.get("event_types", []),
                    "layers":          it.get("layers", []),
                }
                for it in top
            ],
        }

    return result


def _build_prompt(template: str, cleaned_data: dict) -> str:
    news_items        = cleaned_data.get("news", [])
    us_market         = cleaned_data.get("us_market", {})
    cn_market         = cleaned_data.get("cn_market", {})
    macro_indicators  = cleaned_data.get("macro_indicators", {"us": {}, "cn": {}})
    earnings_calendar = cleaned_data.get("earnings_calendar", [])

    # ── 新闻：按信号强度排序，保留全量标注字段供 LLM 分层解读 ──────────────
    sorted_news = sorted(
        news_items,
        key=lambda x: (
            _STRENGTH_RANK.get(x.get("signal_strength", "low"), 2),
            # 时间降序（用负号）
        ),
    )
    news_json = json.dumps(
        [
            {
                "title":           n.get("title", ""),
                "summary":         n.get("summary", ""),
                "source":          n.get("source", ""),
                "published_at":    n.get("published_at", ""),
                "signal_strength": n.get("signal_strength", ""),
                "sentiment":       n.get("sentiment", ""),
                "event_types":     n.get("event_types", []),
                "layers":          n.get("layers", []),
                "is_bottleneck":   n.get("is_bottleneck", False),
                "entities":        [
                    {"name": e["name"], "symbol": e.get("symbol")}
                    for e in (n.get("entities") or [])[:6]
                ],
            }
            for n in sorted_news[:80]
        ],
        ensure_ascii=False, indent=2
    )

    # US market: indices + futures + commodities + rates + AI chip stocks
    us_json = json.dumps(us_market, ensure_ascii=False, indent=2)
    futures_json = json.dumps(us_market.get("futures", {}), ensure_ascii=False, indent=2)

    # A-share indices: filter out error keys
    cn_clean = {k: v for k, v in cn_market.items() if not k.startswith("_")}
    cn_json = json.dumps(cn_clean, ensure_ascii=False, indent=2)

    # Macro indicators: real data from akshare
    macro_obj: dict = {}
    if macro_indicators.get("us"):
        macro_obj["美国宏观指标"] = macro_indicators["us"]
    if macro_indicators.get("cn"):
        macro_obj["中国宏观指标"] = macro_indicators["cn"]
    if not macro_obj:
        macro_obj["note"] = "本次宏观指标采集失败，请参考美股行情和新闻判断宏观环境"
    macro_json = json.dumps(macro_obj, ensure_ascii=False, indent=2)

    # Earnings calendar
    valid_earnings = [e for e in earnings_calendar if "_error" not in e]
    if valid_earnings:
        earnings_json = json.dumps(valid_earnings, ensure_ascii=False, indent=2)
    else:
        earnings_json = json.dumps(
            {"note": "本次财报日历采集失败，请参考新闻条目中的财报相关内容"},
            ensure_ascii=False, indent=2
        )

    prompt = template
    prompt = prompt.replace("{{news_json}}", news_json)
    prompt = prompt.replace("{{earnings_events_json}}", earnings_json)
    prompt = prompt.replace("{{macro_json}}", macro_json)
    prompt = prompt.replace("{{us_market_json}}", us_json)
    prompt = prompt.replace("{{futures_json}}", futures_json)
    prompt = prompt.replace("{{cn_market_json}}", cn_json)
    if "{{framework_structure}}" in prompt:
        prompt = prompt.replace("{{framework_structure}}", _build_framework_structure())
    if "{{framework_news_json}}" in prompt:
        fw_summary = cleaned_data.get("framework_summary", {})
        prompt = prompt.replace(
            "{{framework_news_json}}",
            json.dumps(fw_summary, ensure_ascii=False, indent=2),
        )
    if "{{ticker_news_json}}" in prompt:
        prompt = prompt.replace(
            "{{ticker_news_json}}",
            json.dumps(_build_ticker_news(cleaned_data), ensure_ascii=False, indent=2),
        )

    # ── 富集数据变量（enricher 注入）─────────────────────────────────────────
    enriched: dict = cleaned_data.get("_enriched", {})

    if "{{watchlist_quan_json}}" in prompt:
        prompt = prompt.replace(
            "{{watchlist_quan_json}}",
            json.dumps(enriched.get("watchlist_quan", []), ensure_ascii=False, indent=2),
        )
    if "{{fund_flow_top20_json}}" in prompt:
        prompt = prompt.replace(
            "{{fund_flow_top20_json}}",
            json.dumps(enriched.get("fund_flow_top20", []), ensure_ascii=False, indent=2),
        )
    if "{{sector_fund_flow_json}}" in prompt:
        prompt = prompt.replace(
            "{{sector_fund_flow_json}}",
            json.dumps(enriched.get("sector_fund_flow", []), ensure_ascii=False, indent=2),
        )
    if "{{sector_heatmap_json}}" in prompt:
        prompt = prompt.replace(
            "{{sector_heatmap_json}}",
            json.dumps(enriched.get("sector_heatmap", [])[:30], ensure_ascii=False, indent=2),
        )
    if "{{risk_summary_json}}" in prompt:
        prompt = prompt.replace(
            "{{risk_summary_json}}",
            json.dumps(enriched.get("risk_summary", {}), ensure_ascii=False, indent=2),
        )
    if "{{prev_chain_signals_json}}" in prompt:
        prompt = prompt.replace(
            "{{prev_chain_signals_json}}",
            json.dumps(enriched.get("prev_chain_signals", []), ensure_ascii=False, indent=2),
        )
    if "{{bull_candidates_json}}" in prompt:
        prompt = prompt.replace(
            "{{bull_candidates_json}}",
            json.dumps(enriched.get("bull_candidates", []), ensure_ascii=False, indent=2),
        )

    return prompt


# ── LLM 调用 ──

def _make_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    return base if base.endswith("/chat/completions") else base + "/chat/completions"


def _make_headers(api_key: str) -> dict:
    return {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}


def _call_llm_streaming(cfg, prompt: str, on_chunk=None) -> str:
    """流式调用 LLM；每个 token 调用 on_chunk(text)；返回完整文本。"""
    payload = {
        "model": cfg.model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 16384,
        "stream": True,
    }
    url = _make_url(cfg.base_url)
    full_text = ""

    with requests.post(url, headers=_make_headers(cfg.api_key),
                       json=payload, timeout=TIMEOUT, stream=True) as r:
        r.raise_for_status()
        for raw_line in r.iter_lines():
            if not raw_line:
                continue
            line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
            if not line.startswith("data: "):
                continue
            data = line[6:].strip()
            if data == "[DONE]":
                break
            try:
                chunk_json = json.loads(data)
                delta = chunk_json["choices"][0]["delta"].get("content", "")
                if delta:
                    full_text += delta
                    if on_chunk:
                        on_chunk(delta)
            except Exception:
                pass

    return full_text


def _call_llm(cfg, prompt: str) -> str:
    """非流式调用（降级用）。"""
    payload = {
        "model": cfg.model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 16384,
        "stream": False,
    }
    r = requests.post(_make_url(cfg.base_url), headers=_make_headers(cfg.api_key),
                      json=payload, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _repair_json(text: str) -> str:
    """修复 LLM 常见 JSON 输出错误，使其可被标准解析器接受。"""
    # null/true/false 后面跟了多余的引号：null" → null
    text = re.sub(r'\b(null|true|false)(")', lambda m: m.group(1), text)
    # 冒号后的纯数字值跟了多余引号：: 0.0",  → : 0.0,
    # 注意：只匹配 value 位置（冒号后），避免误删字符串末尾的闭引号
    text = re.sub(r'(:\s*-?\d+(?:\.\d+)?)"\s*([,}\]])', r'\1\2', text)
    # 尾随逗号（对象/数组末尾）
    text = re.sub(r',(\s*[}\]])', r'\1', text)
    return text


def _try_parse(candidate: str) -> dict | None:
    """先直接解析，失败则修复后再试，都失败返回 None。"""
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(_repair_json(candidate))
    except json.JSONDecodeError:
        return None


def _extract_json(raw: str) -> dict:
    """
    从 LLM 输出中提取 JSON，按优先级依次尝试：
    1. markdown code fence 内的 JSON（含修复）
    2. 全文直接解析（含修复）
    3. 全文中第一个 {...} 块（含修复）
    4. 降级：将原始文本包装为 {"analysis_text": ...} 返回，避免前端报错
    """
    text = raw.strip()

    # ① markdown code fence
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if m:
        result = _try_parse(m.group(1).strip())
        if result is not None:
            return result

    # ② 全文
    result = _try_parse(text)
    if result is not None:
        return result

    # ③ 第一个 {...} 块（贪婪匹配到最后一个 }）
    m2 = re.search(r"\{[\s\S]+\}", text)
    if m2:
        result = _try_parse(m2.group(0))
        if result is not None:
            return result

    # ④ 降级：原始文本原样返回，前端可按 analysis_text 渲染
    logger.warning("LLM response is not valid JSON, returning as plain text. len=%d", len(raw))
    return {"analysis_text": raw, "_is_text_response": True}


def analyze(cleaned_data: dict, db=None, template_name: str = None, record_id: int = None) -> dict:
    """
    输入: clean() 的输出；record_id 不为 None 时启用流式输出缓冲。
    返回: LLM 分析结果 dict，或含 error 字段的 dict。
    """
    llm = _get_default_llm()
    if not llm:
        logger.error("No LLM config found in database")
        return {"error": "未找到可用的大模型配置，请在【系统→大模型配置】中添加。"}

    template = _get_active_template(name=template_name)
    if not template:
        logger.error("No active prompt template found in database")
        return {"error": "未找到激活状态的提示词模板，请在【系统→提示词模板】中配置。"}

    prompt = _build_prompt(template, cleaned_data)
    logger.info(f"Calling LLM '{llm.name}' ({llm.model_name}), prompt_len={len(prompt)}")

    try:
        if record_id is not None:
            _init_stream(record_id)
            try:
                raw_output = _call_llm_streaming(
                    llm, prompt,
                    on_chunk=lambda chunk: _append_stream(record_id, chunk),
                )
            except Exception as stream_err:
                # 流式失败 → 降级为非流式，把完整响应一次性写入缓冲
                logger.warning(f"Streaming failed ({stream_err}), falling back to non-streaming")
                raw_output = _call_llm(llm, prompt)
                _append_stream(record_id, raw_output)
            finally:
                _finish_stream(record_id)
        else:
            raw_output = _call_llm(llm, prompt)

        logger.info(f"LLM response length: {len(raw_output)}")
        result = _extract_json(raw_output)
        return result

    except requests.HTTPError as e:
        msg = f"LLM HTTP error: {e}"
        logger.error(msg)
        return {"error": msg, "raw": str(e)}
    except Exception as e:
        msg = f"LLM call failed: {e}"
        logger.error(msg)
        return {"error": msg}

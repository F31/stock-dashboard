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


def _build_prompt(template: str, cleaned_data: dict) -> str:
    news_items = cleaned_data.get("news", [])
    us_market = cleaned_data.get("us_market", {})
    fetch_errors = cleaned_data.get("fetch_errors", [])

    news_json = json.dumps(
        [{"title": n.get("title", ""), "summary": n.get("summary", ""),
          "source": n.get("source", ""), "published_at": n.get("published_at", "")}
         for n in news_items[:60]],
        ensure_ascii=False, indent=2
    )
    us_json = json.dumps(us_market, ensure_ascii=False, indent=2)
    futures_json = json.dumps(us_market.get("futures", {}), ensure_ascii=False, indent=2)
    macro_json = json.dumps(
        {"fetch_errors": fetch_errors,
         "note": "宏观数据本次从美股行情中推断，如需完整宏观数据请配置专用数据源"},
        ensure_ascii=False, indent=2
    )
    earnings_json = json.dumps(
        {"note": "财报日历数据本次未单独采集，请参考新闻条目中的财报相关内容"},
        ensure_ascii=False, indent=2
    )

    prompt = template
    prompt = prompt.replace("{{news_json}}", news_json)
    prompt = prompt.replace("{{earnings_events_json}}", earnings_json)
    prompt = prompt.replace("{{macro_json}}", macro_json)
    prompt = prompt.replace("{{us_market_json}}", us_json)
    prompt = prompt.replace("{{futures_json}}", futures_json)
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
        "max_tokens": 4096,
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
        "max_tokens": 4096,
        "stream": False,
    }
    r = requests.post(_make_url(cfg.base_url), headers=_make_headers(cfg.api_key),
                      json=payload, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _extract_json(raw: str) -> dict:
    """从 LLM 输出中提取 JSON（容忍 markdown code fences）。"""
    text = raw.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if m:
        text = m.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m2 = re.search(r"\{[\s\S]+\}", text)
        if m2:
            return json.loads(m2.group(0))
        raise


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
    except json.JSONDecodeError as e:
        msg = f"LLM response is not valid JSON: {e}"
        logger.error(msg)
        return {"error": msg}
    except Exception as e:
        msg = f"LLM call failed: {e}"
        logger.error(msg)
        return {"error": msg}

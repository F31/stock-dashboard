"""生成层：基于分析结果生成 HTML 报告文件，存放到 reports/current/。"""
import json
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

_BASE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "frontend", "reports", "current"
)


def _ensure_dir():
    os.makedirs(_BASE, exist_ok=True)


# ── Badge helpers ─────────────────────────────────────────────────────────────

def _badge(text: str, bg: str, fg: str) -> str:
    return (
        f'<span style="display:inline-block;padding:1px 7px;border-radius:10px;'
        f'font-size:11px;font-weight:600;background:{bg};color:{fg};">{text}</span>'
    )


def _strength_badge(strength: str) -> str:
    mapping = {
        "high":   ("#fef2f2", "#dc2626", "高信号"),
        "medium": ("#fffbeb", "#d97706", "中信号"),
        "low":    ("#f0fdf4", "#16a34a", "低信号"),
    }
    bg, fg, label = mapping.get(strength, ("#f3f4f6", "#6b7280", strength or "?"))
    return _badge(label, bg, fg)


def _sentiment_badge(sentiment: str) -> str:
    mapping = {
        "positive": ("#f0fdf4", "#16a34a", "利多"),
        "negative": ("#fef2f2", "#dc2626", "利空"),
        "neutral":  ("#f3f4f6", "#6b7280", "中性"),
    }
    bg, fg, label = mapping.get(sentiment, ("#f3f4f6", "#6b7280", sentiment or "?"))
    return _badge(label, bg, fg)


def _layer_badge(layer: str) -> str:
    colors = {
        "算力层":     "#2563eb",
        "模型与平台层": "#7c3aed",
        "应用层":     "#059669",
        "配套基础设施": "#d97706",
    }
    color = colors.get(layer, "#6b7280")
    return _badge(layer, f"{color}22", color)


def _tone_badge(tone: str) -> str:
    colors = {"偏乐观": "#16a34a", "中性": "#2563eb", "偏谨慎": "#dc2626"}
    color = colors.get(tone, "#2563eb")
    return (
        f'<span style="padding:4px 14px;border-radius:20px;font-weight:700;'
        f'font-size:14px;background:{color}22;color:{color};">{tone}</span>'
    )


def _market_badge(market: str) -> str:
    mapping = {"US": ("#dbeafe", "#2563eb"), "CN": ("#fce7f3", "#be185d"),
               "HK": ("#dcfce7", "#16a34a")}
    bg, fg = mapping.get(market, ("#f3f4f6", "#6b7280"))
    return _badge(market, bg, fg)


# ── Shared helpers ────────────────────────────────────────────────────────────

def _coerce_str(v) -> str:
    """Safely convert any LLM field value to a displayable string.
    LLMs occasionally nest the parent dict or a list in a field meant to be a string.
    """
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        return v.get("basis") or v.get("summary") or v.get("tone") or ""
    if isinstance(v, list):
        return "、".join(str(i) for i in v[:3])
    return str(v) if v else ""


def _ul(items):
    if not items:
        return "<p style='color:#9ca3af;font-size:13px;'>无</p>"
    return "<ul style='margin:0;padding-left:18px;'>" + "".join(
        f"<li style='margin:4px 0;font-size:13px;color:#374151;'>{i}</li>"
        for i in items
    ) + "</ul>"


def _market_table(data: dict, empty_msg: str = "数据未获取") -> str:
    clean = {k: v for k, v in data.items() if isinstance(v, dict) and not k.startswith("_")}
    if not clean:
        return f"<p style='color:#9ca3af;font-size:13px;'>{empty_msg}</p>"
    rows = ""
    for sym, info in clean.items():
        price = info.get("price")
        chg   = info.get("change_pct")
        color = "#16a34a" if (chg or 0) >= 0 else "#dc2626"
        chg_str = f"{chg:+.2f}%" if chg is not None else "N/A"
        vix_level = info.get("vix_level", "")
        label_extra = f" <span style='font-size:11px;color:#6b7280;'>({vix_level})</span>" if vix_level else ""
        rows += (
            f"<tr><td style='padding:7px 12px;color:#374151;'>"
            f"{info.get('label', sym)}{label_extra}</td>"
            f"<td style='padding:7px 12px;text-align:right;color:#374151;'>{price if price is not None else 'N/A'}</td>"
            f"<td style='padding:7px 12px;text-align:right;color:{color};font-weight:600;'>{chg_str}</td></tr>"
        )
    return (
        "<table style='width:100%;border-collapse:collapse;font-size:13px;'>"
        "<thead><tr style='background:#f9fafb;'>"
        "<th style='padding:7px 12px;text-align:left;color:#6b7280;font-weight:600;'>品种</th>"
        "<th style='padding:7px 12px;text-align:right;color:#6b7280;font-weight:600;'>价格</th>"
        "<th style='padding:7px 12px;text-align:right;color:#6b7280;font-weight:600;'>涨跌%</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
    )


# ── News Briefing ─────────────────────────────────────────────────────────────

def _news_briefing(news_items: list) -> str:
    """新闻简报：按信号强度分组，置于报告顶部。"""
    if not news_items:
        return ""

    buckets = {"high": [], "medium": [], "low": []}
    for item in news_items:
        s = item.get("signal_strength", "low")
        buckets.get(s, buckets["low"]).append(item)

    limits = {"high": 15, "medium": 10, "low": 5}
    section_labels = {"high": "🔴 高信号新闻", "medium": "🟡 中信号新闻", "low": "🟢 其他关注"}

    sections_html = ""
    for strength in ("high", "medium", "low"):
        items = buckets[strength][: limits[strength]]
        if not items:
            continue
        label = section_labels[strength]
        cards = ""
        for item in items:
            title     = item.get("title", "")
            summary   = item.get("summary", "") or ""
            source    = item.get("source", "")
            pub_at    = (item.get("published_at") or "")[:16]
            sentiment = item.get("sentiment", "")
            layers    = item.get("layers") or []
            event_types = item.get("event_types") or []
            entities  = item.get("entities") or []
            is_bn     = item.get("is_bottleneck", False)

            layer_badges = " ".join(_layer_badge(l) for l in layers[:3])
            event_tags   = " ".join(
                _badge(e, "#ede9fe", "#7c3aed") for e in event_types[:2]
            )
            entity_tags  = " ".join(
                _badge(
                    ent.get("name", "") if isinstance(ent, dict) else str(ent),
                    "#f0f9ff", "#0369a1"
                )
                for ent in entities[:4]
            )
            bn_tag = _badge("物理瓶颈", "#fef2f2", "#dc2626") if is_bn else ""

            summary_html = (
                f'<p style="font-size:12px;color:#6b7280;margin:5px 0 0;line-height:1.6;">'
                f'{summary[:160]}{"…" if len(summary) > 160 else ""}</p>'
            ) if summary else ""

            url = item.get("url", "") or ""
            if url:
                title_html = f'<a href="{url}" target="_blank" rel="noopener" class="nl">{title}</a>'
            else:
                search_url = f"https://www.baidu.com/s?wd={title[:60]}"
                title_html = (
                    f'{title} '
                    f'<a href="{search_url}" target="_blank" rel="noopener" class="nl-search" title="搜索相关新闻">🔍</a>'
                )

            cards += f"""
<div style="border-left:3px solid {'#dc2626' if strength=='high' else '#d97706' if strength=='medium' else '#9ca3af'};
     padding:10px 14px;margin-bottom:10px;background:#fafafa;border-radius:0 8px 8px 0;">
  <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:8px;">
    <div style="font-size:13px;font-weight:600;color:#111827;line-height:1.5;flex:1;">{title_html}</div>
    <div style="display:flex;gap:4px;flex-shrink:0;flex-wrap:wrap;">
      {_strength_badge(strength)}
      {_sentiment_badge(sentiment)}
      {bn_tag}
    </div>
  </div>
  {summary_html}
  <div style="margin-top:6px;display:flex;flex-wrap:wrap;gap:4px;align-items:center;">
    {layer_badges} {event_tags} {entity_tags}
    <span style="margin-left:auto;font-size:11px;color:#9ca3af;">{source} · {pub_at}</span>
  </div>
</div>"""

        sections_html += f"""
<div style="margin-bottom:16px;">
  <div style="font-size:13px;font-weight:700;color:#374151;margin-bottom:8px;">{label}
    <span style="font-size:11px;font-weight:400;color:#9ca3af;">（{len(items)} 条）</span>
  </div>
  {cards}
</div>"""

    total = len(news_items)
    return f"""
<div class="card">
  <div class="card-title">📰 AI产业链资讯简报
    <span style="margin-left:auto;font-size:12px;color:#6b7280;font-weight:400;">共 {total} 条相关资讯</span>
  </div>
  {sections_html}
</div>"""


# ── LLM Analysis Cards ────────────────────────────────────────────────────────

def _report_summary_card(analysis: dict) -> str:
    summary = _coerce_str(analysis.get("report_summary", ""))
    if not summary:
        return ""
    return f"""
<div style="background:linear-gradient(135deg,#1e40af,#3b82f6);color:#fff;
     border-radius:12px;padding:20px 24px;margin-bottom:20px;
     box-shadow:0 4px 12px rgba(37,99,235,.25);">
  <div style="font-size:12px;font-weight:700;opacity:.8;margin-bottom:8px;letter-spacing:.05em;">
    ✦ 核心研判
  </div>
  <p style="font-size:14px;line-height:1.8;opacity:.95;">{summary}</p>
</div>"""


def _macro_signals_card(analysis: dict) -> str:
    ms = analysis.get("macro_signals")
    if not ms or not isinstance(ms, dict):
        return ""

    def _row(label, value):
        if not value:
            return ""
        return (
            f"<tr><td style='padding:8px 12px;color:#6b7280;font-size:12px;"
            f"white-space:nowrap;vertical-align:top;width:130px;'>{label}</td>"
            f"<td style='padding:8px 12px;color:#374151;font-size:13px;line-height:1.6;'>{value}</td></tr>"
        )

    # Support both old field names and new field names
    fed    = _coerce_str(ms.get("fed_rate_context") or ms.get("fed_policy", ""))
    rf     = _coerce_str(ms.get("rates_and_fx") or ms.get("yield_curve", ""))
    usd    = _coerce_str(ms.get("usd_impact", ""))
    cn     = _coerce_str(ms.get("china_macro") or ms.get("china_policy", ""))
    app    = _coerce_str(ms.get("global_risk_appetite", ""))
    basis  = _coerce_str(ms.get("appetite_basis", ""))
    note   = _coerce_str(ms.get("key_risk", ""))

    rows = (
        _row("全局风险偏好", (f"{app}　{basis}" if basis else app) if app else basis)
        + _row("美联储利率", fed)
        + _row("利率与汇率", rf)
        + _row("美元影响", usd)
        + _row("中国宏观", cn)
        + _row("关键风险", note)
    )
    if not rows:
        return ""
    return (
        "<div class='card'>"
        "<div class='card-title'>🌐 宏观信号解读</div>"
        f"<table style='width:100%;border-collapse:collapse;'>{rows}</table>"
        "</div>"
    )


def _bottleneck_card(analysis: dict) -> str:
    alerts = analysis.get("bottleneck_alerts")
    if not alerts or not isinstance(alerts, list):
        return ""
    cards = ""
    for alert in alerts:
        if not isinstance(alert, dict):
            continue
        layer    = alert.get("layer", "")
        # 兼容新字段名（event）和旧字段名（signal）
        signal   = _coerce_str(alert.get("event") or alert.get("signal", ""))
        path     = alert.get("transmission_path", "")
        # 兼容新字段名（signal_strength）和旧字段名（urgency）
        strength = alert.get("signal_strength") or alert.get("urgency", "")
        affected = alert.get("affected_targets") or []
        source   = alert.get("source_ref", "")

        strength_color = {
            "high": "#dc2626", "medium": "#d97706", "low": "#16a34a",
            "高":   "#dc2626", "中":     "#d97706", "低": "#16a34a",
        }.get(strength, "#6b7280")
        strength_label = {
            "high": "高信号", "medium": "中信号", "low": "低信号",
        }.get(strength, strength or "?")

        path_html = (
            f'<p style="font-size:12px;color:#6b7280;margin-top:6px;">↳ 传导路径：{path}</p>'
        ) if path else ""
        affected_html = (
            f'<p style="font-size:12px;color:#374151;margin-top:4px;">影响标的：'
            + "、".join(str(a) for a in affected[:6]) + "</p>"
        ) if affected else ""
        source_html = (
            f'<p style="font-size:11px;color:#9ca3af;margin-top:4px;">来源：{source}</p>'
        ) if source else ""

        cards += f"""
<div style="border-left:4px solid {strength_color};background:#fef9f9;
     border-radius:0 8px 8px 0;padding:12px 16px;margin-bottom:10px;">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
    {_layer_badge(layer)}
    {_badge(strength_label, f"{strength_color}22", strength_color)}
  </div>
  <p style="font-size:13px;color:#374151;line-height:1.6;">{signal}</p>
  {path_html}
  {affected_html}
  {source_html}
</div>"""
    if not cards:
        return ""
    return (
        "<div class='card'>"
        "<div class='card-title'>⚡ 物理瓶颈预警</div>"
        f"{cards}</div>"
    )


def _layer_signals_card(analysis: dict) -> str:
    ls = analysis.get("layer_signals")
    if not ls or not isinstance(ls, list):
        return ""
    rows = ""
    for item in ls:
        if not isinstance(item, dict):
            continue
        layer   = item.get("layer", "")
        cnt     = item.get("signal_count", "")
        dom     = item.get("dominant_sentiment", "")
        key_evt = item.get("key_event", "")
        trans   = item.get("transmission_note", "")
        dom_color = {"positive": "#16a34a", "negative": "#dc2626", "neutral": "#6b7280"}.get(dom, "#6b7280")
        dom_label = {"positive": "偏多", "negative": "偏空", "neutral": "中性"}.get(dom, dom)
        rows += (
            f"<tr>"
            f"<td style='padding:8px 12px;'>{_layer_badge(layer)}</td>"
            f"<td style='padding:8px 12px;text-align:center;font-weight:600;'>{cnt}</td>"
            f"<td style='padding:8px 12px;text-align:center;color:{dom_color};font-weight:600;'>{dom_label}</td>"
            f"<td style='padding:8px 12px;font-size:12px;color:#374151;'>{key_evt}</td>"
            f"<td style='padding:8px 12px;font-size:12px;color:#6b7280;'>{trans}</td>"
            f"</tr>"
        )
    if not rows:
        return ""
    return (
        "<div class='card'>"
        "<div class='card-title'>🔗 产业链各层信号</div>"
        "<table style='width:100%;border-collapse:collapse;font-size:13px;'>"
        "<thead><tr style='background:#f9fafb;'>"
        "<th style='padding:8px 12px;text-align:left;color:#6b7280;'>层级</th>"
        "<th style='padding:8px 12px;text-align:center;color:#6b7280;'>信号数</th>"
        "<th style='padding:8px 12px;text-align:center;color:#6b7280;'>主导情绪</th>"
        "<th style='padding:8px 12px;text-align:left;color:#6b7280;'>关键事件</th>"
        "<th style='padding:8px 12px;text-align:left;color:#6b7280;'>传导备注</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
        "</div>"
    )


def _market_sentiment_card(analysis: dict) -> str:
    ms = analysis.get("market_sentiment", {})
    if not ms:
        return ""
    if isinstance(ms, str):
        try:
            ms = json.loads(ms)
        except Exception:
            return ""
    if not isinstance(ms, dict):
        return ""
    tone  = _coerce_str(ms.get("tone", "中性")) or "中性"
    basis = _coerce_str(ms.get("basis", ""))
    cloud = _coerce_str(ms.get("cloud_infrastructure", ""))
    device= _coerce_str(ms.get("edge_devices", ""))
    phys  = _coerce_str(ms.get("physical_ai", ""))

    col_items = [
        ("☁️ 云基础设施", cloud, "#dbeafe", "#1e40af"),
        ("📱 端侧设备",   device, "#ede9fe", "#6d28d9"),
        ("🤖 物理AI",    phys,   "#dcfce7", "#166534"),
    ]
    cols = ""
    for label, text, bg, fg in col_items:
        if not text:
            continue
        cols += (
            f'<div style="flex:1;min-width:180px;background:{bg};border-radius:8px;padding:12px 14px;">'
            f'<div style="font-size:11px;font-weight:700;color:{fg};margin-bottom:6px;">{label}</div>'
            f'<p style="font-size:12px;color:#374151;line-height:1.6;">{text}</p>'
            f'</div>'
        )

    cols_html = (
        f'<div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:12px;">{cols}</div>'
        if cols else ""
    )

    return f"""
<div class="card">
  <div class="card-title">📊 市场情绪基调</div>
  <div style="margin-bottom:10px;">{_tone_badge(tone)}</div>
  <p style="font-size:13px;color:#374151;line-height:1.8;">{basis}</p>
  {cols_html}
</div>"""


def _ticker_commentary_card(analysis: dict) -> str:
    tc = analysis.get("ticker_commentary")
    if not tc or not isinstance(tc, list):
        return ""
    cards = ""
    for item in tc:
        if not isinstance(item, dict):
            continue
        sym     = item.get("symbol", "")
        name    = item.get("name", "")
        mkt     = item.get("market", "")
        price   = item.get("price")
        chg     = item.get("change_pct")
        ncnt    = item.get("news_count", 0)
        comment = item.get("comment", "")
        chg_color = "#16a34a" if (chg or 0) >= 0 else "#dc2626"
        chg_str   = f"{chg:+.2f}%" if chg is not None else ""
        price_str = f"{price}" if price is not None else ""
        cards += f"""
<div style="border:1px solid #e5e7eb;border-radius:8px;padding:12px 16px;margin-bottom:8px;">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap;">
    <strong style="font-size:14px;color:#111827;">{name or sym}</strong>
    {_market_badge(mkt)}
    <span style="font-size:12px;color:#6b7280;">{sym}</span>
    {"<span style='font-size:13px;font-weight:600;color:#374151;margin-left:4px;'>" + price_str + "</span>" if price_str else ""}
    {"<span style='font-size:13px;font-weight:600;color:" + chg_color + ";'>" + chg_str + "</span>" if chg_str else ""}
    {_badge(f"相关资讯 {ncnt}", "#f3f4f6", "#6b7280") if ncnt else ""}
  </div>
  <p style="font-size:13px;color:#374151;line-height:1.7;margin:0;">{comment}</p>
</div>"""
    if not cards:
        return ""
    return (
        "<div class='card'>"
        f"<div class='card-title'>💬 个股资讯点评</div>{cards}</div>"
    )


def _premarket_outlook_card(analysis: dict) -> str:
    outlook = analysis.get("premarket_outlook", {})
    if not outlook:
        return ""
    summary    = outlook.get("summary", "")
    bull       = outlook.get("scenario_bull", "")
    bull_prob  = outlook.get("scenario_bull_prob", "")
    bear       = outlook.get("scenario_bear", "")
    bear_prob  = outlook.get("scenario_bear_prob", "")
    base_case  = outlook.get("base_case", "")
    focus      = outlook.get("matrix_focus", "")
    key_watch  = outlook.get("key_watch_points") or []
    uncertain  = outlook.get("uncertainties") or []

    scenarios_html = ""
    if bull or bear:
        if bull:
            prob_label = f" <span style='font-size:11px;background:#f0fdf4;color:#166534;border-radius:8px;padding:1px 7px;'>{bull_prob}</span>" if bull_prob else ""
            scenarios_html += (
                f'<div style="flex:1;min-width:200px;background:#f0fdf4;border-radius:8px;padding:12px 14px;border-left:4px solid #16a34a;">'
                f'<div style="font-size:11px;font-weight:700;color:#166534;margin-bottom:4px;">📈 乐观情景{prob_label}</div>'
                f'<p style="font-size:13px;color:#374151;line-height:1.6;margin:0;">{bull}</p>'
                f'</div>'
            )
        if bear:
            prob_label = f" <span style='font-size:11px;background:#fef2f2;color:#991b1b;border-radius:8px;padding:1px 7px;'>{bear_prob}</span>" if bear_prob else ""
            scenarios_html += (
                f'<div style="flex:1;min-width:200px;background:#fef2f2;border-radius:8px;padding:12px 14px;border-left:4px solid #dc2626;">'
                f'<div style="font-size:11px;font-weight:700;color:#991b1b;margin-bottom:4px;">📉 悲观情景{prob_label}</div>'
                f'<p style="font-size:13px;color:#374151;line-height:1.6;margin:0;">{bear}</p>'
                f'</div>'
            )
        scenarios_html = f'<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:14px;">{scenarios_html}</div>'

    base_html = (
        f'<div style="background:#f0f9ff;border-radius:8px;padding:10px 14px;margin-bottom:14px;">'
        f'<span style="font-size:11px;font-weight:700;color:#0369a1;">📌 基准情景：</span>'
        f'<span style="font-size:13px;color:#374151;"> {base_case}</span></div>'
    ) if base_case else ""

    focus_html = (
        f'<div style="background:#eff6ff;border-radius:8px;padding:10px 14px;margin-bottom:14px;">'
        f'<span style="font-size:11px;font-weight:700;color:#1e40af;">🔲 矩阵关注重点：</span>'
        f'<span style="font-size:13px;color:#374151;"> {focus}</span></div>'
    ) if focus else ""

    key_watch_html = (
        f'<div style="background:#fffbeb;border:1px solid #fde68a;border-radius:8px;'
        f'padding:12px 16px;margin-bottom:10px;">'
        f'<div style="font-size:12px;font-weight:700;color:#92400e;margin-bottom:6px;">🔍 重点关注</div>'
        f'{_ul(key_watch)}</div>'
    ) if key_watch else ""

    uncertain_html = (
        f'<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;'
        f'padding:12px 16px;">'
        f'<div style="font-size:12px;font-weight:700;color:#991b1b;margin-bottom:6px;">⚡ 主要不确定性</div>'
        f'{_ul(uncertain)}</div>'
    ) if uncertain else ""

    return f"""
<div class="card">
  <div class="card-title">🎯 A股开盘前情景判断</div>
  {"<p style='font-size:13px;color:#374151;line-height:1.8;margin-bottom:14px;'>" + summary + "</p>" if summary else ""}
  {scenarios_html}
  {base_html}
  {focus_html}
  {key_watch_html}
  {uncertain_html}
</div>"""


# ── Raw data cards ────────────────────────────────────────────────────────────

def _macro_card(macro_indicators: dict) -> str:
    us = macro_indicators.get("us", {})
    cn = macro_indicators.get("cn", {})
    if not us and not cn:
        return ""

    def _section(label: str, items: dict) -> str:
        if not items:
            return ""
        rows = ""
        for key, info in items.items():
            if not isinstance(info, dict):
                continue
            v      = info.get("value", "N/A")
            prev   = info.get("previous", "")
            fcst   = info.get("forecast", "")
            period = info.get("period", "")
            extra_parts = []
            if prev: extra_parts.append(f"前值: {prev}")
            if fcst: extra_parts.append(f"预期: {fcst}")
            extra = " &nbsp;|&nbsp; ".join(extra_parts)
            # Special display for LPR
            if key == "lpr":
                lpr5y = info.get("lpr5y", "")
                v = f"1Y: {v}" + (f" / 5Y: {lpr5y}" if lpr5y else "")
            rows += (
                f"<tr>"
                f"<td style='padding:7px 12px;color:#374151;'>{info.get('label', key)}</td>"
                f"<td style='padding:7px 12px;text-align:center;color:#6b7280;font-size:12px;'>{period}</td>"
                f"<td style='padding:7px 12px;text-align:right;font-weight:600;color:#111827;'>{v}</td>"
                f"<td style='padding:7px 12px;text-align:right;font-size:12px;color:#9ca3af;'>{extra}</td>"
                f"</tr>"
            )
        return (
            f"<div style='font-size:12px;font-weight:700;color:#374151;margin:12px 0 6px;'>{label}</div>"
            "<table style='width:100%;border-collapse:collapse;font-size:13px;'>"
            "<thead><tr style='background:#f9fafb;'>"
            "<th style='padding:7px 12px;text-align:left;color:#6b7280;'>指标</th>"
            "<th style='padding:7px 12px;text-align:center;color:#6b7280;'>期间</th>"
            "<th style='padding:7px 12px;text-align:right;color:#6b7280;'>最新值</th>"
            "<th style='padding:7px 12px;text-align:right;color:#6b7280;'>参考</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>"
        )

    return (
        "<div class='card'>"
        "<div class='card-title'>📉 宏观经济指标</div>"
        + _section("🇺🇸 美国", us)
        + _section("🇨🇳 中国", cn)
        + "</div>"
    )


def _earnings_card(earnings_calendar: list) -> str:
    valid = [e for e in (earnings_calendar or []) if "_error" not in e and e.get("company")]
    if not valid:
        return ""
    rows = ""
    for e in valid[:15]:
        eps = e.get("eps_est")
        rev = e.get("revenue_est_b")
        eps_str = f"{eps:+.2f}" if eps is not None else "-"
        rev_str = f"{rev:.1f}B" if rev is not None else "-"
        rows += (
            f"<tr>"
            f"<td style='padding:7px 12px;color:#374151;font-weight:500;'>{e.get('company','')}</td>"
            f"<td style='padding:7px 12px;color:#6b7280;font-size:12px;'>{e.get('code','')}</td>"
            f"<td style='padding:7px 12px;text-align:center;color:#374151;'>{e.get('report_date','')}</td>"
            f"<td style='padding:7px 12px;text-align:right;color:#374151;'>{eps_str}</td>"
            f"<td style='padding:7px 12px;text-align:right;color:#374151;'>{rev_str}</td>"
            f"</tr>"
        )
    return (
        "<div class='card'>"
        "<div class='card-title'>📅 近期美股财报日历"
        "<span style='margin-left:auto;font-size:12px;color:#6b7280;font-weight:400;'>未来7天</span></div>"
        "<table style='width:100%;border-collapse:collapse;font-size:13px;'>"
        "<thead><tr style='background:#f9fafb;'>"
        "<th style='padding:7px 12px;text-align:left;color:#6b7280;'>公司</th>"
        "<th style='padding:7px 12px;text-align:left;color:#6b7280;'>代码</th>"
        "<th style='padding:7px 12px;text-align:center;color:#6b7280;'>财报日期</th>"
        "<th style='padding:7px 12px;text-align:right;color:#6b7280;'>EPS预期</th>"
        "<th style='padding:7px 12px;text-align:right;color:#6b7280;'>营收预期</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
        "</div>"
    )


def _watchlist_card(item: dict, idx: int) -> str:
    layer   = item.get("industry_layer", "")
    symbol  = item.get("symbol", "")
    market  = item.get("market", "")
    # matrix position
    mat     = item.get("matrix_position") or {}
    layers_ = mat.get("layers") or []
    cols    = mat.get("columns") or []
    cov     = mat.get("coverage", "")
    bn_exp  = item.get("bottleneck_exposure", "")

    mat_tags = ""
    for l in layers_[:3]:
        mat_tags += _layer_badge(l)
    for c in cols[:2]:
        mat_tags += " " + _badge(c, "#f0f9ff", "#0369a1")
    if cov:
        mat_tags += " " + _badge(f"覆盖度:{cov}", "#f3f4f6", "#6b7280")

    header_extra = ""
    if symbol:
        header_extra += f'<span style="font-size:12px;color:#6b7280;">{symbol}</span>'
    if market:
        header_extra += f" {_market_badge(market)}"
    if mat_tags:
        header_extra += f' <span style="display:inline-flex;gap:4px;flex-wrap:wrap;">{mat_tags}</span>'

    bn_html = ""
    if bn_exp:
        bn_html = (
            f'<tr><td style="color:#6b7280;vertical-align:top;padding:4px 0;">瓶颈暴露</td>'
            f'<td style="color:#dc2626;padding:4px 0;">{bn_exp}</td></tr>'
        )

    open_strategy = item.get("open_strategy", "")
    open_html = (
        f'<tr><td style="color:#6b7280;vertical-align:top;padding:4px 0;">开盘策略</td>'
        f'<td style="color:#0369a1;font-weight:500;padding:4px 0;">{open_strategy}</td></tr>'
    ) if open_strategy else ""

    # quan percentile badge
    qpct = item.get("quan_percentile")
    quan_badge = ""
    if qpct is not None:
        try:
            qv = float(qpct)
            qcolor = "#16a34a" if qv >= 70 else ("#d97706" if qv >= 40 else "#dc2626")
            quan_badge = f' {_badge(f"量化{qv:.0f}%", f"{qcolor}22", qcolor)}'
        except Exception:
            pass

    return f"""
<div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;
     padding:20px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.05);">
  <div style="display:flex;align-items:flex-start;gap:12px;margin-bottom:12px;flex-wrap:wrap;">
    <span style="width:28px;height:28px;border-radius:50%;background:#1e3a8a;
          color:#fff;font-size:13px;font-weight:700;display:flex;align-items:center;
          justify-content:center;flex-shrink:0;">{idx}</span>
    <strong style="font-size:16px;color:#111827;">{item.get("name","")}</strong>
    {header_extra}{quan_badge}
  </div>
  <table style="width:100%;border-collapse:collapse;font-size:13px;line-height:1.7;">
    <tr>
      <td style="width:90px;color:#6b7280;vertical-align:top;padding:4px 0;">触发事件</td>
      <td style="color:#374151;padding:4px 0;">{item.get("trigger_event","")}</td>
    </tr>
    <tr>
      <td style="color:#6b7280;vertical-align:top;padding:4px 0;">隔夜表现</td>
      <td style="color:#374151;padding:4px 0;">{item.get("overnight_performance","")}</td>
    </tr>
    {bn_html}
    <tr>
      <td style="vertical-align:top;padding:4px 0;">
        <span style="color:#16a34a;font-weight:600;">看多</span>
      </td>
      <td style="color:#374151;padding:4px 0;">{item.get("bull_case","")}</td>
    </tr>
    <tr>
      <td style="vertical-align:top;padding:4px 0;">
        <span style="color:#dc2626;font-weight:600;">看空</span>
      </td>
      <td style="color:#374151;padding:4px 0;">{item.get("bear_case","")}</td>
    </tr>
    {open_html}
    <tr>
      <td style="color:#6b7280;vertical-align:top;padding:4px 0;">跟进问题</td>
      <td style="color:#374151;padding:4px 0;">{item.get("follow_up","")}</td>
    </tr>
  </table>
</div>"""


# ── New section cards (P1) ───────────────────────────────────────────────────

def _signal_overview_card(analysis: dict) -> str:
    so = analysis.get("signal_overview")
    if not so or not isinstance(so, dict):
        return ""
    rating    = _coerce_str(so.get("overall_rating", ""))
    basis     = _coerce_str(so.get("rating_basis", ""))
    opp       = _coerce_str(so.get("top_opportunity", ""))
    risk      = _coerce_str(so.get("top_risk", ""))
    rating_colors = {
        "强势": ("#16a34a", "#f0fdf4"),
        "偏强": ("#059669", "#ecfdf5"),
        "中性": ("#2563eb", "#eff6ff"),
        "偏弱": ("#d97706", "#fffbeb"),
        "弱势": ("#dc2626", "#fef2f2"),
    }
    fg, bg = rating_colors.get(rating, ("#6b7280", "#f3f4f6"))
    rating_html = (
        f'<span style="display:inline-block;padding:4px 16px;border-radius:20px;'
        f'font-weight:800;font-size:16px;background:{bg};color:{fg};margin-bottom:10px;">'
        f'{rating}</span>'
    ) if rating else ""

    opp_html = (
        f'<div style="margin-top:10px;display:flex;gap:10px;flex-wrap:wrap;">'
        f'<div style="flex:1;min-width:180px;background:#f0fdf4;border-radius:8px;padding:10px 14px;">'
        f'<div style="font-size:11px;font-weight:700;color:#166534;margin-bottom:4px;">💡 今日最佳机会方向</div>'
        f'<p style="font-size:13px;color:#374151;margin:0;">{opp}</p></div>'
        f'<div style="flex:1;min-width:180px;background:#fef2f2;border-radius:8px;padding:10px 14px;">'
        f'<div style="font-size:11px;font-weight:700;color:#991b1b;margin-bottom:4px;">⚠️ 今日最需警惕风险</div>'
        f'<p style="font-size:13px;color:#374151;margin:0;">{risk}</p></div>'
        f'</div>'
    ) if (opp or risk) else ""

    return f"""
<div class="card" style="border-top:3px solid {fg};">
  <div class="card-title">📊 综合信号评级</div>
  {rating_html}
  {"<p style='font-size:13px;color:#374151;line-height:1.7;'>" + basis + "</p>" if basis else ""}
  {opp_html}
</div>"""


def _risk_radar_card(analysis: dict) -> str:
    rr = analysis.get("risk_radar")
    if not rr or not isinstance(rr, dict):
        return ""
    level = _coerce_str(rr.get("overall_level", "中"))
    level_colors = {"高": ("#dc2626", "#fef2f2"), "中": ("#d97706", "#fffbeb"), "低": ("#16a34a", "#f0fdf4")}
    fg, bg = level_colors.get(level, ("#6b7280", "#f3f4f6"))
    items = [
        ("情绪风险", rr.get("sentiment_risk", "")),
        ("流动性风险", rr.get("liquidity_risk", "")),
        ("政策/监管风险", rr.get("policy_risk", "")),
        ("AI链特有风险", rr.get("chain_risk", "")),
    ]
    rows = ""
    for label, val in items:
        v = _coerce_str(val)
        if v:
            rows += (
                f"<tr><td style='padding:7px 12px;color:#6b7280;font-size:12px;white-space:nowrap;width:110px;'>{label}</td>"
                f"<td style='padding:7px 12px;color:#374151;font-size:13px;line-height:1.6;'>{v}</td></tr>"
            )
    if not rows:
        return ""
    return (
        f"<div class='card'>"
        f"<div class='card-title'>🚨 风险雷达 "
        f"<span style='margin-left:8px;padding:2px 10px;border-radius:10px;font-size:12px;"
        f"font-weight:700;background:{bg};color:{fg};'>{level}风险</span></div>"
        f"<table style='width:100%;border-collapse:collapse;'>{rows}</table>"
        f"</div>"
    )


def _fund_flow_insights_card(analysis: dict) -> str:
    ffi = analysis.get("fund_flow_insights")
    if not ffi or not isinstance(ffi, dict):
        return ""

    opp = _coerce_str(ffi.get("new_opportunities", ""))
    stocks = ffi.get("top_individual_stocks") or []
    sectors = ffi.get("top_sectors") or []

    stock_rows = ""
    for s in stocks[:5]:
        if not isinstance(s, dict):
            continue
        code = s.get("stock_code", "")
        name = s.get("stock_name", "")
        net  = s.get("net_inflow")
        chg  = s.get("change_pct")
        comment = _coerce_str(s.get("comment", ""))
        chg_color = "#16a34a" if (chg or 0) >= 0 else "#dc2626"
        chg_str   = f"{chg:+.2f}%" if chg is not None else ""
        net_str   = f"+{net:.2f}亿" if net is not None else ""
        stock_rows += (
            f"<tr>"
            f"<td style='padding:7px 12px;font-weight:500;color:#374151;'>{name}</td>"
            f"<td style='padding:7px 12px;color:#6b7280;font-size:12px;'>{code}</td>"
            f"<td style='padding:7px 12px;text-align:right;color:#16a34a;font-weight:600;'>{net_str}</td>"
            f"<td style='padding:7px 12px;text-align:right;color:{chg_color};font-weight:600;'>{chg_str}</td>"
            f"<td style='padding:7px 12px;font-size:12px;color:#6b7280;'>{comment}</td>"
            f"</tr>"
        )

    sector_rows = ""
    for s in sectors[:5]:
        if not isinstance(s, dict):
            continue
        name = s.get("name", "")
        ff   = s.get("fund_flow_yi") or s.get("fund_flow")
        chg  = s.get("change_pct")
        note = _coerce_str(s.get("opportunity_note", ""))
        chg_color = "#16a34a" if (chg or 0) >= 0 else "#dc2626"
        chg_str = f"{chg:+.2f}%" if chg is not None else ""
        ff_str  = f"{ff:+.2f}亿" if ff is not None else ""
        sector_rows += (
            f"<tr>"
            f"<td style='padding:7px 12px;font-weight:500;color:#374151;'>{name}</td>"
            f"<td style='padding:7px 12px;text-align:right;color:#16a34a;font-weight:600;'>{ff_str}</td>"
            f"<td style='padding:7px 12px;text-align:right;color:{chg_color};font-weight:600;'>{chg_str}</td>"
            f"<td style='padding:7px 12px;font-size:12px;color:#6b7280;'>{note}</td>"
            f"</tr>"
        )

    opp_html = (
        f'<div style="background:#f0fdf4;border-radius:8px;padding:10px 14px;margin-bottom:14px;">'
        f'<span style="font-size:11px;font-weight:700;color:#166534;">💡 新机会识别：</span>'
        f'<span style="font-size:13px;color:#374151;"> {opp}</span></div>'
    ) if opp else ""

    if not stock_rows and not sector_rows:
        return ""

    stocks_table = (
        "<div style='font-weight:600;font-size:12px;color:#374151;margin:10px 0 6px;'>📈 个股主力净流入TOP5</div>"
        "<table style='width:100%;border-collapse:collapse;font-size:13px;'>"
        "<thead><tr style='background:#f9fafb;'>"
        "<th style='padding:7px 12px;text-align:left;color:#6b7280;'>股票</th>"
        "<th style='padding:7px 12px;text-align:left;color:#6b7280;'>代码</th>"
        "<th style='padding:7px 12px;text-align:right;color:#6b7280;'>净流入</th>"
        "<th style='padding:7px 12px;text-align:right;color:#6b7280;'>涨跌</th>"
        "<th style='padding:7px 12px;text-align:left;color:#6b7280;'>点评</th>"
        f"</tr></thead><tbody>{stock_rows}</tbody></table>"
    ) if stock_rows else ""

    sectors_table = (
        "<div style='font-weight:600;font-size:12px;color:#374151;margin:16px 0 6px;'>🏭 板块主力净流入TOP5</div>"
        "<table style='width:100%;border-collapse:collapse;font-size:13px;'>"
        "<thead><tr style='background:#f9fafb;'>"
        "<th style='padding:7px 12px;text-align:left;color:#6b7280;'>板块</th>"
        "<th style='padding:7px 12px;text-align:right;color:#6b7280;'>净流入</th>"
        "<th style='padding:7px 12px;text-align:right;color:#6b7280;'>涨跌</th>"
        "<th style='padding:7px 12px;text-align:left;color:#6b7280;'>机会点评</th>"
        f"</tr></thead><tbody>{sector_rows}</tbody></table>"
    ) if sector_rows else ""

    return (
        "<div class='card'>"
        "<div class='card-title'>💰 资金流向新机会</div>"
        f"{opp_html}{stocks_table}{sectors_table}"
        "</div>"
    )


def _chain_tracking_card(analysis: dict) -> str:
    ct = analysis.get("chain_tracking")
    if not ct or not isinstance(ct, list):
        return ""
    cards = ""
    dir_config = {
        "strengthening": ("#16a34a", "#f0fdf4", "↑ 增强"),
        "stable":        ("#2563eb", "#eff6ff", "→ 稳定"),
        "weakening":     ("#dc2626", "#fef2f2", "↓ 减弱"),
    }
    conf_colors = {"high": "#16a34a", "medium": "#d97706", "low": "#dc2626"}
    for item in ct:
        if not isinstance(item, dict):
            continue
        theme   = item.get("theme", "")
        dirn    = item.get("direction", "stable")
        vs_yday = _coerce_str(item.get("vs_yesterday", ""))
        conf    = item.get("confidence", "medium")
        summary = _coerce_str(item.get("summary", ""))
        cats    = item.get("catalysts") or []
        risks   = item.get("risks") or []

        fg, bg, dir_label = dir_config.get(dirn, ("#6b7280", "#f3f4f6", "? 未知"))
        conf_color = conf_colors.get(conf, "#6b7280")

        cats_html = _ul(cats) if cats else ""
        risks_html = _ul(risks) if risks else ""

        cards += f"""
<div style="border:1px solid {fg}44;border-left:4px solid {fg};border-radius:8px;
     padding:14px 16px;margin-bottom:12px;background:{bg};">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap;">
    <strong style="font-size:14px;color:#111827;">{theme}</strong>
    {_badge(dir_label, bg, fg)}
    {_badge(f"信心：{conf}", f"{conf_color}22", conf_color)}
  </div>
  {"<p style='font-size:12px;color:#6b7280;margin-bottom:6px;'>对比昨日：" + vs_yday + "</p>" if vs_yday and vs_yday != "首次追踪" else ""}
  {"<p style='font-size:13px;color:#374151;line-height:1.7;margin-bottom:8px;'>" + summary + "</p>" if summary else ""}
  {"<div style='display:flex;gap:12px;flex-wrap:wrap;'>" + ("<div style='flex:1;min-width:150px;'><div style='font-size:11px;font-weight:700;color:#166534;margin-bottom:4px;'>催化因素</div>" + cats_html + "</div>" if cats else "") + ("<div style='flex:1;min-width:150px;'><div style='font-size:11px;font-weight:700;color:#991b1b;margin-bottom:4px;'>风险因素</div>" + risks_html + "</div>" if risks else "") + "</div>" if cats or risks else ""}
</div>"""

    if not cards:
        return ""
    return (
        "<div class='card'>"
        "<div class='card-title'>🔗 AI产业链方向追踪</div>"
        f"{cards}</div>"
    )


def _bull_alerts_card(analysis: dict) -> str:
    ba = analysis.get("bull_alerts")
    if not ba or not isinstance(ba, list):
        return ""
    verdict_config = {
        "confirmed": ("#16a34a", "#f0fdf4", "✓ 确认信号"),
        "possible":  ("#d97706", "#fffbeb", "? 待观察"),
        "rejected":  ("#dc2626", "#fef2f2", "✗ 暂不支持"),
    }
    cards = ""
    for item in ba:
        if not isinstance(item, dict):
            continue
        code    = item.get("stock_code", "")
        name    = item.get("stock_name", "")
        market  = item.get("market", "")
        verdict = item.get("llm_verdict", "possible")
        basis   = _coerce_str(item.get("verdict_basis", ""))
        catalyst= _coerce_str(item.get("key_catalyst", ""))
        risk_w  = _coerce_str(item.get("risk_warning", ""))
        algo    = item.get("algo_score")
        qpct    = item.get("quan_percentile")
        net_in  = item.get("net_inflow")

        fg, bg, v_label = verdict_config.get(verdict, ("#6b7280", "#f3f4f6", "?"))
        stats_badges = ""
        if algo is not None:
            stats_badges += f" {_badge(f'算法分 {algo}', '#f3f4f6', '#374151')}"
        if qpct is not None:
            try:
                qv = float(qpct)
                qc = "#16a34a" if qv >= 70 else ("#d97706" if qv >= 50 else "#6b7280")
                stats_badges += f" {_badge(f'量化{qv:.0f}%', f'{qc}22', qc)}"
            except Exception:
                pass
        if net_in is not None:
            try:
                stats_badges += f" {_badge(f'净流入+{float(net_in):.2f}亿', '#f0fdf4', '#16a34a')}"
            except Exception:
                pass

        cards += f"""
<div style="border:1px solid {fg}44;border-left:4px solid {fg};border-radius:8px;
     padding:14px 16px;margin-bottom:10px;background:{bg};">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap;">
    <strong style="font-size:14px;color:#111827;">{name}</strong>
    <span style="font-size:12px;color:#6b7280;">{code}</span>
    {_market_badge(market)}
    {_badge(v_label, bg, fg)}
    {stats_badges}
  </div>
  {"<p style='font-size:13px;color:#374151;line-height:1.7;margin-bottom:6px;'>" + basis + "</p>" if basis else ""}
  <div style="display:flex;gap:10px;flex-wrap:wrap;font-size:12px;">
    {"<div style='color:#166534;'><span style='font-weight:700;'>催化剂：</span>" + catalyst + "</div>" if catalyst else ""}
    {"<div style='color:#991b1b;'><span style='font-weight:700;'>风险：</span>" + risk_w + "</div>" if risk_w else ""}
  </div>
</div>"""

    if not cards:
        return ""
    return (
        "<div class='card'>"
        "<div class='card-title'>🚀 智能牛股预警</div>"
        f"{cards}</div>"
    )


def _open_schedule_card(analysis: dict) -> str:
    os_ = analysis.get("open_schedule")
    if not os_ or not isinstance(os_, dict):
        return ""
    f15  = _coerce_str(os_.get("first_15min", ""))
    f30  = _coerce_str(os_.get("first_30min", ""))
    mid  = _coerce_str(os_.get("mid_session", ""))
    trigs= os_.get("risk_triggers") or []

    items = [
        ("🔔 开盘前15分钟", f15, "#dbeafe", "#1e40af"),
        ("⚡ 开盘30分钟内", f30, "#fffbeb", "#92400e"),
        ("🕙 盘中关键窗口", mid, "#f0fdf4", "#166534"),
    ]
    sections = ""
    for label, text, bg, fg in items:
        if not text:
            continue
        sections += (
            f'<div style="background:{bg};border-radius:8px;padding:12px 14px;margin-bottom:8px;">'
            f'<div style="font-size:11px;font-weight:700;color:{fg};margin-bottom:4px;">{label}</div>'
            f'<p style="font-size:13px;color:#374151;line-height:1.7;margin:0;">{text}</p>'
            f'</div>'
        )

    trig_html = (
        f'<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:12px 14px;">'
        f'<div style="font-size:11px;font-weight:700;color:#991b1b;margin-bottom:6px;">🛑 风险触发条件</div>'
        f'{_ul(trigs)}</div>'
    ) if trigs else ""

    if not sections and not trig_html:
        return ""
    return (
        "<div class='card'>"
        "<div class='card-title'>📅 开盘节奏计划</div>"
        f"{sections}{trig_html}"
        "</div>"
    )


def _watchlist_quan_card(enriched: dict) -> str:
    """显示关注股票量化评分表格（直接用富集原始数据，不依赖 LLM 输出）。"""
    wq = enriched.get("watchlist_quan") or []
    if not wq:
        return ""
    rows = ""
    for s in wq:
        if not isinstance(s, dict):
            continue
        code  = s.get("stock_code", "")
        name  = s.get("stock_name", "") or code
        qpct  = s.get("quan_percentile")
        price = s.get("price")
        chg   = s.get("change_pct")
        notes = (s.get("notes") or "")[:30]

        qpct_html = ""
        if qpct is not None:
            try:
                qv = float(qpct)
                qc = "#16a34a" if qv >= 70 else ("#d97706" if qv >= 40 else "#dc2626")
                qpct_html = f'<span style="font-weight:700;color:{qc};">{qv:.0f}%</span>'
            except Exception:
                qpct_html = str(qpct)
        else:
            qpct_html = '<span style="color:#9ca3af;">-</span>'

        chg_color = "#16a34a" if (chg or 0) >= 0 else "#dc2626"
        chg_str   = f"{chg:+.2f}%" if chg is not None else "-"
        price_str = f"{price}" if price is not None else "-"

        rows += (
            f"<tr>"
            f"<td style='padding:7px 12px;font-weight:500;color:#374151;'>{name}</td>"
            f"<td style='padding:7px 12px;color:#6b7280;font-size:12px;'>{code}</td>"
            f"<td style='padding:7px 12px;text-align:right;'>{qpct_html}</td>"
            f"<td style='padding:7px 12px;text-align:right;color:#374151;'>{price_str}</td>"
            f"<td style='padding:7px 12px;text-align:right;color:{chg_color};font-weight:600;'>{chg_str}</td>"
            f"<td style='padding:7px 12px;font-size:11px;color:#9ca3af;'>{notes}</td>"
            f"</tr>"
        )

    if not rows:
        return ""
    return (
        "<div class='card'>"
        "<div class='card-title'>📐 关注股票量化评分<span style='margin-left:auto;font-size:12px;color:#6b7280;font-weight:400;'>因子百分位（越高越强）</span></div>"
        "<table style='width:100%;border-collapse:collapse;font-size:13px;'>"
        "<thead><tr style='background:#f9fafb;'>"
        "<th style='padding:7px 12px;text-align:left;color:#6b7280;'>股票</th>"
        "<th style='padding:7px 12px;text-align:left;color:#6b7280;'>代码</th>"
        "<th style='padding:7px 12px;text-align:right;color:#6b7280;'>量化百分位</th>"
        "<th style='padding:7px 12px;text-align:right;color:#6b7280;'>最新价</th>"
        "<th style='padding:7px 12px;text-align:right;color:#6b7280;'>涨跌%</th>"
        "<th style='padding:7px 12px;text-align:left;color:#6b7280;'>备注</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
        "</div>"
    )


# ── Speech text builder ───────────────────────────────────────────────────────

def _build_speech_text(analysis: dict) -> str:
    """将分析报告的关键内容组装为适合语音朗读的纯文本。"""
    parts = []

    summary = _coerce_str(analysis.get("report_summary", ""))
    if summary:
        parts.append(f"核心研判：{summary}")

    # 综合信号评级
    so = analysis.get("signal_overview", {})
    if isinstance(so, dict):
        rating = _coerce_str(so.get("overall_rating", ""))
        basis  = _coerce_str(so.get("rating_basis", ""))
        opp    = _coerce_str(so.get("top_opportunity", ""))
        risk   = _coerce_str(so.get("top_risk", ""))
        if rating:
            parts.append(f"综合信号评级：{rating}。{basis}")
        if opp:
            parts.append(f"今日最佳机会方向：{opp}。")
        if risk:
            parts.append(f"今日最需警惕风险：{risk}。")

    ms = analysis.get("market_sentiment", {})
    if isinstance(ms, dict):
        tone  = _coerce_str(ms.get("tone", ""))
        basis = _coerce_str(ms.get("basis", ""))
        if tone:
            parts.append(f"市场情绪基调：{tone}。{basis}")

    # AI链追踪
    ct = analysis.get("chain_tracking") or []
    if ct:
        parts.append(f"AI产业链方向追踪，共{len(ct)}个主题。")
        for item in ct:
            if not isinstance(item, dict):
                continue
            theme   = item.get("theme", "")
            dirn    = item.get("direction", "stable")
            summary_ct = _coerce_str(item.get("summary", ""))
            dir_map = {"strengthening": "增强", "stable": "稳定", "weakening": "减弱"}
            parts.append(f"主题{theme}，方向{dir_map.get(dirn, dirn)}。{summary_ct}")

    # 牛股预警
    ba = analysis.get("bull_alerts") or []
    confirmed = [x for x in ba if isinstance(x, dict) and x.get("llm_verdict") == "confirmed"]
    if confirmed:
        parts.append(f"牛股预警：以下{len(confirmed)}只股票出现强信号。")
        for item in confirmed:
            name    = item.get("stock_name", "")
            catalyst= _coerce_str(item.get("key_catalyst", ""))
            parts.append(f"{name}：{catalyst}。")

    watchlist = analysis.get("watchlist", [])
    if watchlist:
        parts.append(f"观察清单，共{len(watchlist)}个标的。")
        for i, item in enumerate(watchlist):
            if not isinstance(item, dict):
                continue
            name  = item.get("name", "")
            parts.append(f"第{i + 1}个标的：{name}。")
            if item.get("trigger_event"):
                parts.append(f"触发事件：{item['trigger_event']}。")
            if item.get("bull_case"):
                parts.append(f"看多：{item['bull_case']}。")
            if item.get("bear_case"):
                parts.append(f"看空：{item['bear_case']}。")
            if item.get("open_strategy"):
                parts.append(f"开盘策略：{item['open_strategy']}。")

    # 开盘节奏
    os_ = analysis.get("open_schedule", {})
    if isinstance(os_, dict):
        f15 = _coerce_str(os_.get("first_15min", ""))
        f30 = _coerce_str(os_.get("first_30min", ""))
        if f15:
            parts.append(f"开盘前15分钟：{f15}")
        if f30:
            parts.append(f"开盘30分钟内：{f30}")

    outlook = analysis.get("premarket_outlook", {})
    if isinstance(outlook, dict):
        s = _coerce_str(outlook.get("summary", ""))
        if s:
            parts.append(f"A股开盘前情景判断：{s}")
        base = _coerce_str(outlook.get("base_case", ""))
        if base:
            parts.append(f"基准情景：{base}")
        kw = outlook.get("key_watch_points") or []
        if kw:
            parts.append(f"重点关注：{'；'.join(str(p) for p in kw)}。")

    return "\n".join(parts)


# ── Main generate ─────────────────────────────────────────────────────────────

def generate(analysis: dict, cleaned_data: dict, report_date: str) -> str:
    """生成 HTML 文件，返回相对路径 current/YYYY-MM-DD-HHMMSS.html"""
    _ensure_dir()

    now = datetime.now()
    filename = f"{report_date}-{now.strftime('%H%M%S')}.html"
    filepath = os.path.join(_BASE, filename)

    speech_text      = _build_speech_text(analysis)
    speech_text_json = json.dumps(speech_text, ensure_ascii=False)

    watchlist         = analysis.get("watchlist", [])
    data_gaps         = analysis.get("data_gaps", [])
    error             = analysis.get("error", "")

    us_market         = cleaned_data.get("us_market", {})
    cn_market         = cleaned_data.get("cn_market", {})
    macro_indicators  = cleaned_data.get("macro_indicators", {"us": {}, "cn": {}})
    earnings_calendar = cleaned_data.get("earnings_calendar", [])
    news_items        = cleaned_data.get("news", [])
    futures           = us_market.get("futures", {})
    indices           = us_market.get("indices", {})
    ai_stocks         = us_market.get("ai_stocks", {})
    rates             = us_market.get("rates", {})
    stats             = cleaned_data.get("stats", {})
    fetch_errors      = cleaned_data.get("fetch_errors", [])
    enriched          = cleaned_data.get("_enriched", {})

    error_banner = ""
    if error:
        error_banner = (
            f'<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;'
            f'padding:14px 18px;margin-bottom:20px;color:#dc2626;font-size:13px;">'
            f'⚠️ 大模型分析出错：{error}</div>'
        )

    # 隔夜美股指数卡片
    index_cards = ""
    for sym, info in indices.items():
        price = info.get("price")
        chg   = info.get("change_pct")
        color = "#16a34a" if (chg or 0) >= 0 else "#dc2626"
        chg_str = f"{chg:+.2f}%" if chg is not None else "N/A"
        vix_sub = (
            f'<div style="font-size:11px;color:#6b7280;">{info.get("vix_level","")}</div>'
        ) if info.get("vix_level") else ""
        index_cards += (
            f'<div style="background:#fff;border:1px solid #e5e7eb;border-radius:8px;'
            f'padding:12px 16px;text-align:center;min-width:120px;">'
            f'<div style="font-size:11px;color:#6b7280;margin-bottom:4px;">{info.get("label",sym)}</div>'
            f'<div style="font-size:15px;font-weight:700;">{price if price is not None else "N/A"}</div>'
            f'<div style="font-size:12px;font-weight:600;color:{color};">{chg_str}</div>'
            f'{vix_sub}'
            f'</div>'
        )

    # 利率/汇率行情卡片（^TNX, DXY）
    rates_html = ""
    if rates:
        rates_cards = ""
        for sym, info in rates.items():
            price = info.get("price")
            chg   = info.get("change_pct")
            color = "#dc2626" if (chg or 0) >= 0 else "#16a34a"  # rates: up=bad for equities
            chg_str = f"{chg:+.2f}%" if chg is not None else "N/A"
            rates_cards += (
                f'<div style="background:#fff;border:1px solid #e5e7eb;border-radius:8px;'
                f'padding:12px 16px;text-align:center;min-width:120px;">'
                f'<div style="font-size:11px;color:#6b7280;margin-bottom:4px;">{info.get("label",sym)}</div>'
                f'<div style="font-size:15px;font-weight:700;">{price if price is not None else "N/A"}</div>'
                f'<div style="font-size:12px;font-weight:600;color:{color};">{chg_str}</div>'
                f'</div>'
            )
        rates_html = (
            f'<div style="font-weight:600;font-size:13px;color:#374151;margin:12px 0 8px;">'
            f'📐 利率与美元指数</div>'
            f'<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px;">'
            f'{rates_cards}</div>'
        )

    watchlist_html = "".join(
        _watchlist_card(item, i + 1) for i, item in enumerate(watchlist)
    ) or "<p style='color:#9ca3af;'>无观察标的</p>"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI产业链盘前分析 · {report_date}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0;}}
  body{{font-family:'PingFang SC','Helvetica Neue',Arial,sans-serif;
        background:#f0f2f5;color:#111827;font-size:14px;}}
  .header{{background:linear-gradient(135deg,#1e3a8a,#2563eb);color:#fff;
           padding:28px 32px;}}
  .header h1{{font-size:1.4rem;font-weight:800;margin-bottom:6px;}}
  .header .meta{{font-size:12px;opacity:.75;}}
  .container{{max-width:960px;margin:0 auto;padding:24px 20px;}}
  .card{{background:#fff;border:1px solid #e5e7eb;border-radius:12px;
         padding:20px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,.05);}}
  .card-title{{font-size:14px;font-weight:700;color:#1e3a8a;margin-bottom:14px;
               display:flex;align-items:center;gap:8px;border-bottom:1px solid #f3f4f6;
               padding-bottom:10px;}}
  footer{{text-align:center;padding:20px 20px 90px;font-size:11px;color:#9ca3af;}}
  a.nl{{color:#1d4ed8;text-decoration:none;border-bottom:1px solid #bfdbfe;}}
  a.nl:hover{{color:#1e40af;text-decoration:underline;border-bottom-color:transparent;}}
  a.nl-search{{color:#6b7280;text-decoration:none;font-size:11px;border-bottom:1px dashed #d1d5db;}}
  a.nl-search:hover{{color:#1d4ed8;border-bottom-color:#1d4ed8;}}
  /* ── TTS Panel ── */
  #tts-panel{{position:fixed;bottom:20px;right:16px;z-index:9999;display:flex;flex-direction:column;align-items:flex-end;gap:5px;}}
  #tts-error{{display:none;background:#fef3c7;border:1px solid #fde68a;border-radius:8px;
              padding:6px 12px;font-size:12px;color:#92400e;max-width:220px;text-align:center;
              box-shadow:0 2px 8px rgba(0,0,0,.12);}}
  #tts-progress{{display:none;color:#93c5fd;font-size:11px;font-weight:600;text-align:right;padding:0 4px;}}
  #tts-controls{{display:flex;align-items:center;gap:6px;
                 background:#1e3a8a;border-radius:12px;padding:8px 12px;
                 box-shadow:0 4px 16px rgba(30,58,138,.35);}}
  #tts-voice{{background:rgba(255,255,255,.15);color:#fff;border:1px solid rgba(255,255,255,.3);
              border-radius:7px;padding:5px 7px;font-size:12px;cursor:pointer;outline:none;font-family:inherit;}}
  #tts-voice option{{background:#1e3a8a;}}
  .tts-btn{{background:rgba(255,255,255,.18);color:#fff;border:1px solid rgba(255,255,255,.3);
            border-radius:8px;padding:7px 14px;font-size:13px;font-weight:600;cursor:pointer;
            font-family:inherit;transition:background .15s;white-space:nowrap;display:flex;align-items:center;gap:5px;}}
  .tts-btn:hover:not(:disabled){{background:rgba(255,255,255,.3);}}
  .tts-btn:disabled{{opacity:.55;cursor:not-allowed;}}
  #tts-stop{{padding:7px 10px;min-width:unset;display:none;}}
  .tts-spin{{width:11px;height:11px;border:2px solid rgba(255,255,255,.4);border-top-color:#fff;
             border-radius:50%;animation:tspin .7s linear infinite;}}
  @keyframes tspin{{to{{transform:rotate(360deg);}}}}
  @media(max-width:640px){{
    .header{{padding:16px;}}
    .header h1{{font-size:1.1rem;}}
    .container{{padding:12px 10px;}}
    .card{{padding:14px;margin-bottom:12px;border-radius:8px;}}
    .card-title{{font-size:13px;}}
    /* 表格横向滚动 */
    table{{display:block;overflow-x:auto;-webkit-overflow-scrolling:touch;}}
    /* 并排 flex 布局折行 */
    div[style*="display:flex"]{{flex-wrap:wrap;}}
    #tts-panel{{bottom:12px;right:10px;}}
    #tts-controls{{padding:7px 10px;gap:5px;border-radius:10px;}}
    /* 语音选择收窄 */
    #tts-voice{{max-width:80px;font-size:11px;}}
    .tts-btn{{font-size:12px;padding:6px 10px;}}
  }}
</style>
</head>
<body>

<div class="header">
  <h1>🤖 AI产业链盘前分析</h1>
  <div class="meta">报告日期：{report_date} &nbsp;|&nbsp;
    采集新闻：{stats.get("total_raw",0)}条 &nbsp;|&nbsp;
    AI相关：{stats.get("after_filter",0)}条 &nbsp;|&nbsp;
    生成时间：{now.strftime("%Y-%m-%d %H:%M:%S")}
  </div>
</div>

<div class="container">
{error_banner}

{_report_summary_card(analysis)}

{_signal_overview_card(analysis)}

{_news_briefing(news_items)}

<!-- 隔夜美股 -->
<div class="card">
  <div class="card-title">🌙 隔夜美股行情</div>
  <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px;">
    {index_cards}
  </div>
  {rates_html}
  <div style="font-weight:600;font-size:13px;color:#374151;margin:12px 0 8px;">
    📈 股指期货
  </div>
  {_market_table(futures, '期货数据未获取')}
</div>

{_macro_card(macro_indicators)}

{_earnings_card(earnings_calendar)}

{_macro_signals_card(analysis)}

{_risk_radar_card(analysis)}

{_bottleneck_card(analysis)}

{_layer_signals_card(analysis)}

{_market_sentiment_card(analysis)}

{_chain_tracking_card(analysis)}

{_bull_alerts_card(analysis)}

<!-- 观察清单 -->
<div class="card">
  <div class="card-title">👁 AI产业链观察清单
    <span style="margin-left:auto;font-size:12px;color:#6b7280;font-weight:400;">
      共 {len(watchlist)} 个标的
    </span>
  </div>
  {watchlist_html}
</div>

{_open_schedule_card(analysis)}

{_premarket_outlook_card(analysis)}

{"" if not data_gaps else f'''
<div class="card">
  <div class="card-title">⚠️ 数据缺口提示</div>
  {_ul(data_gaps)}
</div>'''}

{"" if not fetch_errors else f'''
<div class="card">
  <div class="card-title">🔧 采集异常日志</div>
  {_ul(fetch_errors[:10])}
</div>'''}

</div>

<footer>
  本报告由 AI 自动生成，仅供参考，不构成投资建议。事实数据以代码采集为准，大模型仅做判断与解读。
</footer>

<!-- ── TTS Panel ── -->
<div id="tts-panel">
  <div id="tts-error"></div>
  <div id="tts-progress"></div>
  <div id="tts-controls">
    <select id="tts-voice">
      <option value="__browser__">浏览器语音 (推荐)</option>
      <option value="zh-CN-XiaoxiaoNeural">小晓 (Azure女声)</option>
      <option value="zh-CN-YunyangNeural">云杨 (Azure男声)</option>
      <option value="zh-CN-YunxiNeural">云希 (Azure男声)</option>
    </select>
    <button class="tts-btn" id="tts-play" onclick="toggleTTS()">🔊 朗读</button>
    <button class="tts-btn" id="tts-stop" onclick="stopTTS()" title="停止朗读">⏹</button>
  </div>
</div>

<script>window._TTS_TEXT = {speech_text_json};</script>
<script>
(function(){{
  /* TTS 双引擎:
     桌面: HTMLAudioElement + AudioContext 解锁
     移动: Web Audio API (AudioContext.decodeAudioData + BufferSourceNode)
           iOS autoplay 限制下，手势解锁 AudioContext 后，后续 async decode/start 不受限。
     文本: 优先使用服务端预建的语音文本（干净、无 emoji/表格），降级才提取 DOM。  */
  var CHUNK_MAX = 700;
  var LOOKAHEAD = 2;
  var _isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);

  var _audio    = null;
  var _audioCtx = null;
  var _curSrc   = null;
  var _state    = 'idle';
  var _chunks   = [], _playIdx = 0;
  var _buffers  = {{}};
  var _fetching = {{}};
  var _session  = 0;

  // ── 浏览器语音引擎 (SpeechSynthesis) ──────────────────────────────────────
  var _utterances = [];  // SpeechSynthesisUtterance[]
  var _uIdx = 0;
  var _iosKeepalive = null;

  function _isBrowserVoice() {{
    var sel = document.getElementById('tts-voice');
    return sel && sel.value === '__browser__';
  }}

  function _getZhVoice() {{
    if (!window.speechSynthesis) return null;
    var voices = window.speechSynthesis.getVoices();
    return voices.find(function(v) {{
      return v.lang === 'zh-CN' || v.lang === 'zh_CN' || v.lang.startsWith('zh');
    }}) || null;
  }}

  function _splitUtterances(text) {{
    // Split at sentence-ending punctuation, keep chunks ≤ 150 chars for iOS compatibility
    var parts = text.split(/(?=[。！？\n])/);
    var result = [], cur = '';
    parts.forEach(function(p) {{
      if ((cur + p).length > 150 && cur) {{ result.push(cur.trim()); cur = ''; }}
      cur += p;
    }});
    if (cur.trim()) result.push(cur.trim());
    return result.filter(function(s) {{ return s.length > 0; }});
  }}

  function _startIosKeepalive() {{
    if (!_isMobile) return;
    _iosKeepalive = setInterval(function() {{
      if (window.speechSynthesis.speaking && !window.speechSynthesis.paused) {{
        window.speechSynthesis.pause();
        window.speechSynthesis.resume();
      }}
    }}, 10000);
  }}
  function _stopIosKeepalive() {{
    if (_iosKeepalive) {{ clearInterval(_iosKeepalive); _iosKeepalive = null; }}
  }}

  function _speakNext() {{
    if (_uIdx >= _utterances.length) {{ _setState('idle'); _stopIosKeepalive(); return; }}
    var mySid = _session;
    var u = _utterances[_uIdx];
    u.onstart = function() {{
      if (_session !== mySid) return;
      _setState('playing');
      var progEl = document.getElementById('tts-progress');
      if (progEl) progEl.textContent = '第 '+(_uIdx+1)+' / '+_utterances.length+' 段';
    }};
    u.onend = function() {{
      if (_session !== mySid) return;
      _uIdx++;
      _speakNext();
    }};
    u.onerror = function(e) {{
      if (_session !== mySid) return;
      // ignore 'interrupted' — happens when stop() is called
      if (e.error === 'interrupted' || e.error === 'canceled') return;
      _setState('idle'); _stopIosKeepalive();
      _showErr('浏览器语音朗读失败: ' + e.error);
    }};
    window.speechSynthesis.speak(u);
  }}

  function _startBrowserTTS(text) {{
    if (!window.speechSynthesis) {{
      _showErr('当前浏览器不支持语音朗读');
      return;
    }}
    var voice = _getZhVoice();
    if (!voice && window.speechSynthesis.getVoices().length === 0) {{
      // Voices not loaded yet — wait then retry
      window.speechSynthesis.onvoiceschanged = function() {{
        window.speechSynthesis.onvoiceschanged = null;
        _startBrowserTTS(text);
      }};
      return;
    }}
    _session++;
    window.speechSynthesis.cancel();
    _stopIosKeepalive();
    var sentences = _splitUtterances(text);
    if (!sentences.length) return;
    _utterances = sentences.map(function(s) {{
      var u = new SpeechSynthesisUtterance(s);
      u.lang = 'zh-CN';
      u.rate = 0.9;
      if (voice) u.voice = voice;
      return u;
    }});
    _uIdx = 0;
    _setState('loading');
    var progEl = document.getElementById('tts-progress');
    if (progEl) {{ progEl.style.display = sentences.length > 1 ? 'block' : 'none'; }}
    _speakNext();
    _startIosKeepalive();
  }}

  function _stopBrowserTTS() {{
    _session++;
    window.speechSynthesis.cancel();
    _stopIosKeepalive();
    _utterances = []; _uIdx = 0;
  }}

  // ── 音频解锁 ──────────────────────────────────────────────────────────────
  function _ensureAudioUnlocked() {{
    if (!_audioCtx) {{
      var AC = window.AudioContext || window.webkitAudioContext;
      if (AC) try {{ _audioCtx = new AC(); }} catch(e) {{}}
    }}
    if (_audioCtx && _audioCtx.state === 'suspended') {{
      _audioCtx.resume().catch(function() {{}});
    }}
    if (_audioCtx) {{
      try {{
        var buf = _audioCtx.createBuffer(1, 1, 22050);
        var src = _audioCtx.createBufferSource();
        src.buffer = buf; src.connect(_audioCtx.destination); src.start(0);
      }} catch(e) {{}}
    }}
  }}

  // ── 文本 ──────────────────────────────────────────────────────────────────
  function _getText() {{
    if (window._TTS_TEXT && window._TTS_TEXT.trim()) return window._TTS_TEXT;
    var el = document.querySelector('.container') || document.body;
    var clone = el.cloneNode(true);
    ['#tts-panel','script','style','noscript'].forEach(function(s) {{
      clone.querySelectorAll(s).forEach(function(n) {{ n.remove(); }});
    }});
    return (clone.innerText || clone.textContent || '').replace(/[ \\t]+/g,' ').trim();
  }}

  function _buildChunks(text) {{
    var chunks = [], t = text.trim();
    while (t.length > 0) {{
      if (t.length <= CHUNK_MAX) {{ chunks.push(t); break; }}
      var cut = CHUNK_MAX;
      for (var i = Math.min(CHUNK_MAX, t.length-1); i > CHUNK_MAX*0.5; i--) {{
        var c = t[i];
        if (c==='。'||c==='！'||c==='？'||c==='\\n') {{ cut=i+1; break; }}
        if ((c==='；'||c==='，') && i > CHUNK_MAX*0.75) {{ cut=i+1; break; }}
      }}
      chunks.push(t.slice(0,cut).trim());
      t = t.slice(cut).trim();
    }}
    return chunks.filter(function(c){{ return c.length>0; }});
  }}

  // ── 资源管理 ──────────────────────────────────────────────────────────────
  function _revokeAll() {{
    if (!_isMobile) {{
      Object.keys(_buffers).forEach(function(k) {{
        if (typeof _buffers[k]==='string') try {{ URL.revokeObjectURL(_buffers[k]); }} catch(e) {{}}
      }});
    }}
    _buffers = {{}}; _fetching = {{}};
  }}

  // ── UI ────────────────────────────────────────────────────────────────────
  function _setState(s) {{
    _state = s;
    var playBtn = document.getElementById('tts-play');
    var stopBtn = document.getElementById('tts-stop');
    var progEl  = document.getElementById('tts-progress');
    var labels  = {{idle:'🔊 朗读全文',loading:'合成中…',playing:'⏸ 暂停',paused:'▶ 继续'}};
    playBtn.innerHTML = (s==='loading'?'<span class="tts-spin"></span>':'') + (labels[s]||'🔊 朗读全文');
    playBtn.disabled  = (s === 'loading');
    stopBtn.style.display = (s !== 'idle') ? 'flex' : 'none';
    progEl.style.display  = (s !== 'idle' && _chunks.length > 1) ? 'block' : 'none';
    if (s !== 'idle' && _chunks.length > 0)
      progEl.textContent = '第 ' + (_playIdx+1) + ' / ' + _chunks.length + ' 段';
  }}

  function _showErr(msg) {{
    var el = document.getElementById('tts-error');
    el.textContent = msg; el.style.display = 'block';
    setTimeout(function(){{ el.style.display='none'; }}, 6000);
  }}

  // ── 预取 ──────────────────────────────────────────────────────────────────
  function _fetchChunk(idx) {{
    if (idx < 0 || idx >= _chunks.length) return;
    if (_buffers[idx] !== undefined || _fetching[idx]) return;
    var mySid = _session;
    var voice = document.getElementById('tts-voice').value;
    var token = '';
    var hm = window.location.hash.match(/token=([^&]+)/);
    if (hm) token = decodeURIComponent(hm[1]);
    else token = (window.localStorage && localStorage.getItem('token')) || '';
    _fetching[idx] = true;
    fetch('/api/premarket/tts', {{
      method:'POST',
      headers:{{'Content-Type':'application/json','Authorization':'Bearer '+token}},
      body:JSON.stringify({{text:_chunks[idx],voice:voice,rate:'-5%'}})
    }}).then(function(r) {{
      if (!r.ok) throw new Error('HTTP '+r.status);
      return r.blob();
    }}).then(function(blob) {{
      if (_session !== mySid) return;
      if (_isMobile && _audioCtx) {{
        return blob.arrayBuffer().then(function(ab) {{
          if (_session !== mySid) return;
          return _audioCtx.decodeAudioData(ab);
        }}).then(function(audioBuf) {{
          if (_session !== mySid) return;
          _buffers[idx] = audioBuf;
          delete _fetching[idx];
          if (_state === 'loading' && idx === _playIdx) _playChunk(idx);
        }});
      }} else {{
        _buffers[idx] = URL.createObjectURL(blob);
        delete _fetching[idx];
        if (_state === 'loading' && idx === _playIdx) _playChunk(idx);
      }}
    }}).catch(function(e) {{
      if (_session !== mySid) return;
      delete _fetching[idx];
      if (_state === 'loading' && idx === _playIdx) {{
        console.warn('Azure TTS chunk '+idx+' failed:', e, '— falling back to browser voice');
        // 自动降级：切换到浏览器语音并重新开始
        var sel = document.getElementById('tts-voice');
        if (sel) sel.value = '__browser__';
        _revokeAll(); _setState('idle');
        _showErr('Azure 语音不可用，已自动切换为浏览器语音');
        setTimeout(function() {{
          var text = _getText();
          if (text) _startBrowserTTS(text);
        }}, 800);
      }}
    }});
  }}

  function _prefetch() {{
    for (var i = 0; i < LOOKAHEAD; i++) _fetchChunk(_playIdx + i);
  }}

  // ── 播放 ──────────────────────────────────────────────────────────────────
  function _playChunk(idx) {{
    if (_buffers[idx] === undefined) return;
    if (_state !== 'loading' && _state !== 'playing') return;
    var mySid = _session;

    if (_isMobile && _audioCtx) {{
      if (_curSrc) {{ try {{ _curSrc.stop(); }} catch(e) {{}} _curSrc = null; }}
      var src = _audioCtx.createBufferSource();
      src.buffer = _buffers[idx];
      src.connect(_audioCtx.destination);
      src.onended = function() {{
        if (_session !== mySid || _state !== 'playing') return;
        delete _buffers[idx];
        _playIdx++;
        if (_playIdx >= _chunks.length) {{ _setState('idle'); return; }}
        _setState('playing'); _prefetch();
        if (_buffers[_playIdx] !== undefined) _playChunk(_playIdx);
        else _setState('loading');
      }};
      _curSrc = src; src.start(0);
      _setState('playing');
      var progEl = document.getElementById('tts-progress');
      if (progEl) progEl.textContent = '第 '+(idx+1)+' / '+_chunks.length+' 段';
      return;
    }}

    if (!_audio) return;
    _ensureAudioUnlocked();
    var prevUrl = _audio.src;
    _audio.loop = false; _audio.volume = 1.0; _audio.onended = null;
    _audio.src = _buffers[idx];
    _audio.onended = function() {{
      if (_session !== mySid || _state !== 'playing') return;
      try {{ URL.revokeObjectURL(prevUrl); }} catch(e) {{}}
      delete _buffers[idx];
      _playIdx++;
      if (_playIdx >= _chunks.length) {{ _setState('idle'); return; }}
      _setState('playing'); _prefetch();
      if (_buffers[_playIdx] !== undefined) _playChunk(_playIdx);
      else _setState('loading');
    }};
    _audio.play().then(function() {{
      _setState('playing'); _prefetch();
    }}).catch(function(e) {{
      if (_session !== mySid) return;
      _setState('idle'); _showErr('播放失败，请重试');
      console.error('audio.play() failed', e);
    }});
  }}

  function _start() {{
    // edge-tts 路径：分块 + 后端合成
    var text = _getText();
    if (!text) {{ _showErr('未找到可朗读的内容'); return; }}
    _chunks = _buildChunks(text);
    if (!_chunks.length) return;
    _session++; _playIdx = 0; _revokeAll();
    _setState('loading'); _prefetch();
  }}

  // ── 公开接口 ──────────────────────────────────────────────────────────────
  var _SILENT = 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA';

  window.toggleTTS = function() {{
    if (_state === 'loading') return;
    _ensureAudioUnlocked();  // 必须在用户手势中同步调用

    var useBrowser = _isBrowserVoice();

    if (_state === 'idle') {{
      var text = _getText();
      if (!text) {{ _showErr('未找到可朗读的内容'); return; }}
      if (useBrowser) {{
        _startBrowserTTS(text);
      }} else {{
        // edge-tts 路径（需要后端 Azure TTS）
        if (_isMobile) {{
          _start();
        }} else {{
          if (!_audio) {{ _audio = new Audio(); _audio.preload = 'auto'; }}
          _audio.src = _SILENT; _audio.loop = true; _audio.volume = 0.01;
          var p = _audio.play(); if (p) p.catch(function(){{}});
          _start();
        }}
      }}
    }} else if (_state === 'playing') {{
      if (useBrowser) {{
        window.speechSynthesis.pause();
        _stopIosKeepalive();
        _setState('paused');
      }} else if (_isMobile && _audioCtx) {{
        _audioCtx.suspend().catch(function(){{}});
        _setState('paused');
      }} else if (_audio) {{
        _audio.pause();
        _setState('paused');
      }}
    }} else if (_state === 'paused') {{
      if (useBrowser) {{
        window.speechSynthesis.resume();
        _startIosKeepalive();
        _setState('playing');
      }} else if (_isMobile && _audioCtx) {{
        _audioCtx.resume().then(function(){{ _setState('playing'); }})
          .catch(function(){{ _showErr('恢复失败，请重试'); }});
      }} else if (_audio) {{
        _audio.play().then(function(){{ _setState('playing'); }})
          .catch(function(){{ _showErr('恢复失败，请重试'); }});
      }}
    }}
  }};

  window.stopTTS = function() {{
    _stopBrowserTTS();
    if (_isMobile && _curSrc) {{
      try {{ _curSrc.stop(); }} catch(e) {{}} _curSrc = null;
    }}
    if (_audio) {{ _audio.pause(); _audio.onended = null; _audio.src = ''; }}
    _revokeAll(); _setState('idle');
  }};
}})();
</script>

</body>
</html>"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info("Report generated: %s", filepath)
    return f"current/{filename}"

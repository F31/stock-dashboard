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

            cards += f"""
<div style="border-left:3px solid {'#dc2626' if strength=='high' else '#d97706' if strength=='medium' else '#9ca3af'};
     padding:10px 14px;margin-bottom:10px;background:#fafafa;border-radius:0 8px 8px 0;">
  <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:8px;">
    <div style="font-size:13px;font-weight:600;color:#111827;line-height:1.5;flex:1;">{title}</div>
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

    fed   = _coerce_str(ms.get("fed_policy", ""))
    yield_= _coerce_str(ms.get("yield_curve", ""))
    usd   = _coerce_str(ms.get("usd_impact", ""))
    oil   = _coerce_str(ms.get("commodity_signal", ""))
    cn    = _coerce_str(ms.get("china_policy", ""))
    note  = _coerce_str(ms.get("key_risk", ""))

    rows = (
        _row("美联储政策", fed)
        + _row("收益率曲线", yield_)
        + _row("美元影响", usd)
        + _row("大宗商品", oil)
        + _row("中国政策", cn)
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
        signal   = alert.get("signal", "")
        path     = alert.get("transmission_path", "")
        urgency  = alert.get("urgency", "")
        urgency_color = {"高": "#dc2626", "中": "#d97706", "低": "#16a34a"}.get(urgency, "#6b7280")
        path_html = (
            f'<p style="font-size:12px;color:#6b7280;margin-top:6px;">↳ 传导路径：{path}</p>'
        ) if path else ""
        cards += f"""
<div style="border-left:4px solid {urgency_color};background:#fef9f9;
     border-radius:0 8px 8px 0;padding:12px 16px;margin-bottom:10px;">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
    {_layer_badge(layer)}
    {_badge(f"紧急度：{urgency}", f"{urgency_color}22", urgency_color)}
  </div>
  <p style="font-size:13px;color:#374151;line-height:1.6;">{signal}</p>
  {path_html}
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
    bear       = outlook.get("scenario_bear", "")
    focus      = outlook.get("matrix_focus", "")
    key_watch  = outlook.get("key_watch_points") or []
    uncertain  = outlook.get("uncertainties") or []

    scenarios_html = ""
    if bull:
        scenarios_html += f"""
<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:14px;">
  <div style="flex:1;min-width:200px;background:#f0fdf4;border-radius:8px;padding:12px 14px;border-left:4px solid #16a34a;">
    <div style="font-size:11px;font-weight:700;color:#166534;margin-bottom:4px;">📈 乐观情景</div>
    <p style="font-size:13px;color:#374151;line-height:1.6;margin:0;">{bull}</p>
  </div>"""
    if bear:
        scenarios_html += f"""
  <div style="flex:1;min-width:200px;background:#fef2f2;border-radius:8px;padding:12px 14px;border-left:4px solid #dc2626;">
    <div style="font-size:11px;font-weight:700;color:#991b1b;margin-bottom:4px;">📉 悲观情景</div>
    <p style="font-size:13px;color:#374151;line-height:1.6;margin:0;">{bear}</p>
  </div>"""
    if bull or bear:
        scenarios_html += "</div>"

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

    return f"""
<div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;
     padding:20px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.05);">
  <div style="display:flex;align-items:flex-start;gap:12px;margin-bottom:12px;flex-wrap:wrap;">
    <span style="width:28px;height:28px;border-radius:50%;background:#1e3a8a;
          color:#fff;font-size:13px;font-weight:700;display:flex;align-items:center;
          justify-content:center;flex-shrink:0;">{idx}</span>
    <strong style="font-size:16px;color:#111827;">{item.get("name","")}</strong>
    {header_extra}
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
    <tr>
      <td style="color:#6b7280;vertical-align:top;padding:4px 0;">跟进问题</td>
      <td style="color:#374151;padding:4px 0;">{item.get("follow_up","")}</td>
    </tr>
  </table>
</div>"""


# ── Main generate ─────────────────────────────────────────────────────────────

def generate(analysis: dict, cleaned_data: dict, report_date: str) -> str:
    """生成 HTML 文件，返回相对路径 current/YYYY-MM-DD-HHMMSS.html"""
    _ensure_dir()

    now = datetime.now()
    filename = f"{report_date}-{now.strftime('%H%M%S')}.html"
    filepath = os.path.join(_BASE, filename)

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
  footer{{text-align:center;padding:20px;font-size:11px;color:#9ca3af;}}
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

{_news_briefing(news_items)}

<!-- 隔夜美股 -->
<div class="card">
  <div class="card-title">🌙 隔夜美股行情</div>
  <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px;">
    {index_cards}
  </div>
  {rates_html}
  <div style="font-weight:600;font-size:13px;color:#374151;margin:12px 0 8px;">
    🤖 AI核心个股
  </div>
  {_market_table(ai_stocks, 'AI个股数据未获取')}
  <div style="font-weight:600;font-size:13px;color:#374151;margin:12px 0 8px;">
    📈 股指期货
  </div>
  {_market_table(futures, '期货数据未获取')}
</div>

<!-- A股主要指数 -->
<div class="card">
  <div class="card-title">🇨🇳 A股主要指数（前一交易日）</div>
  {_market_table({k: v for k, v in cn_market.items() if not k.startswith('_')}, 'A股指数数据未获取')}
</div>

{_macro_card(macro_indicators)}

{_earnings_card(earnings_calendar)}

{_macro_signals_card(analysis)}

{_bottleneck_card(analysis)}

{_layer_signals_card(analysis)}

{_market_sentiment_card(analysis)}

{_ticker_commentary_card(analysis)}

<!-- 观察清单 -->
<div class="card">
  <div class="card-title">👁 AI产业链观察清单
    <span style="margin-left:auto;font-size:12px;color:#6b7280;font-weight:400;">
      共 {len(watchlist)} 个标的
    </span>
  </div>
  {watchlist_html}
</div>

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

</body>
</html>"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info("Report generated: %s", filepath)
    return f"current/{filename}"

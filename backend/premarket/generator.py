"""生成层：基于分析结果生成 HTML 报告文件，存放到 reports/current/。"""
import json
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

# 报告目录：frontend/reports/current/
_BASE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "frontend", "reports", "current"
)


def _ensure_dir():
    os.makedirs(_BASE, exist_ok=True)


LAYER_COLORS = {
    "算力层": "#2563eb",
    "模型与平台层": "#7c3aed",
    "应用层": "#059669",
    "配套基础设施": "#d97706",
}

TONE_COLORS = {
    "偏乐观": "#16a34a",
    "中性": "#2563eb",
    "偏谨慎": "#dc2626",
}


def _layer_badge(layer: str) -> str:
    color = LAYER_COLORS.get(layer, "#6b7280")
    return (
        f'<span style="display:inline-block;padding:2px 8px;border-radius:12px;'
        f'font-size:11px;font-weight:600;background:{color}22;color:{color};">'
        f'{layer}</span>'
    )


def _tone_badge(tone: str) -> str:
    color = TONE_COLORS.get(tone, "#2563eb")
    return (
        f'<span style="padding:4px 14px;border-radius:20px;font-weight:700;'
        f'font-size:14px;background:{color}22;color:{color};">{tone}</span>'
    )


def _watchlist_card(item: dict, idx: int) -> str:
    layer = item.get("industry_layer", "")
    return f"""
<div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;
     padding:20px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.05);">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;">
    <span style="width:28px;height:28px;border-radius:50%;background:#1e3a8a;
          color:#fff;font-size:13px;font-weight:700;display:flex;align-items:center;
          justify-content:center;flex-shrink:0;">{idx}</span>
    <strong style="font-size:16px;color:#111827;">{item.get("name","")}</strong>
    {_layer_badge(layer)}
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


def _futures_table(futures: dict) -> str:
    if not futures:
        return "<p style='color:#9ca3af;font-size:13px;'>期货数据未获取</p>"
    rows = ""
    for sym, info in futures.items():
        price = info.get("price")
        chg = info.get("change_pct")
        color = "#dc2626" if (chg or 0) >= 0 else "#16a34a"
        chg_str = f"{chg:+.2f}%" if chg is not None else "N/A"
        rows += (
            f"<tr><td style='padding:8px 12px;color:#374151;'>{info.get('label',sym)}</td>"
            f"<td style='padding:8px 12px;text-align:right;'>{price or 'N/A'}</td>"
            f"<td style='padding:8px 12px;text-align:right;color:{color};font-weight:600;'>{chg_str}</td></tr>"
        )
    return (
        "<table style='width:100%;border-collapse:collapse;font-size:13px;'>"
        "<thead><tr style='background:#f9fafb;'>"
        "<th style='padding:8px 12px;text-align:left;color:#6b7280;'>品种</th>"
        "<th style='padding:8px 12px;text-align:right;color:#6b7280;'>价格</th>"
        "<th style='padding:8px 12px;text-align:right;color:#6b7280;'>涨跌%</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
    )


def generate(analysis: dict, cleaned_data: dict, report_date: str) -> str:
    """生成 HTML 文件，返回相对路径 current/YYYY-MM-DD-HHMMSS.html"""
    _ensure_dir()

    now = datetime.now()
    filename = f"{report_date}-{now.strftime('%H%M%S')}.html"
    filepath = os.path.join(_BASE, filename)

    sentiment = analysis.get("market_sentiment", {})
    tone = sentiment.get("tone", "中性")
    basis = sentiment.get("basis", "")
    watchlist = analysis.get("watchlist", [])
    outlook = analysis.get("premarket_outlook", {})
    data_gaps = analysis.get("data_gaps", [])
    error = analysis.get("error", "")

    us_market = cleaned_data.get("us_market", {})
    futures = us_market.get("futures", {})
    indices = us_market.get("indices", {})
    stats = cleaned_data.get("stats", {})
    fetch_errors = cleaned_data.get("fetch_errors", [])

    # 关注点列表
    def _ul(items):
        if not items:
            return "<p style='color:#9ca3af;font-size:13px;'>无</p>"
        return "<ul style='margin:0;padding-left:18px;'>" + "".join(
            f"<li style='margin:4px 0;font-size:13px;color:#374151;'>{i}</li>"
            for i in items
        ) + "</ul>"

    watchlist_html = "".join(
        _watchlist_card(item, i + 1) for i, item in enumerate(watchlist)
    ) or "<p style='color:#9ca3af;'>无观察标的</p>"

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
        chg = info.get("change_pct")
        color = "#dc2626" if (chg or 0) >= 0 else "#16a34a"
        chg_str = f"{chg:+.2f}%" if chg is not None else "N/A"
        index_cards += (
            f'<div style="background:#fff;border:1px solid #e5e7eb;border-radius:8px;'
            f'padding:12px 16px;text-align:center;min-width:120px;">'
            f'<div style="font-size:11px;color:#6b7280;margin-bottom:4px;">{info.get("label",sym)}</div>'
            f'<div style="font-size:15px;font-weight:700;">{price or "N/A"}</div>'
            f'<div style="font-size:12px;font-weight:600;color:{color};">{chg_str}</div>'
            f'</div>'
        )

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
  .section-tag{{display:inline-block;padding:1px 8px;border-radius:4px;
                font-size:11px;background:#dbeafe;color:#2563eb;font-weight:600;}}
  .key-watch{{background:#fffbeb;border:1px solid #fde68a;border-radius:8px;
              padding:12px 16px;margin-top:12px;}}
  .uncertainty{{background:#fef2f2;border:1px solid #fecaca;border-radius:8px;
                padding:12px 16px;margin-top:8px;}}
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

<!-- 市场情绪 -->
<div class="card">
  <div class="card-title">📊 市场情绪基调</div>
  <div style="margin-bottom:10px;">{_tone_badge(tone)}</div>
  <p style="font-size:13px;color:#374151;line-height:1.8;">{basis}</p>
</div>

<!-- 隔夜美股 -->
<div class="card">
  <div class="card-title">🌙 隔夜美股行情</div>
  <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px;">
    {index_cards}
  </div>
  <div style="font-weight:600;font-size:13px;color:#374151;margin-bottom:8px;">
    📈 股指期货
  </div>
  {_futures_table(futures)}
</div>

<!-- 观察清单 -->
<div class="card">
  <div class="card-title">👁 AI产业链观察清单
    <span style="margin-left:auto;font-size:12px;color:#6b7280;font-weight:400;">
      共 {len(watchlist)} 个标的
    </span>
  </div>
  {watchlist_html}
</div>

<!-- 开盘情景判断 -->
<div class="card">
  <div class="card-title">🎯 A股开盘前情景判断</div>
  <p style="font-size:13px;color:#374151;line-height:1.8;margin-bottom:14px;">
    {outlook.get("summary","")}
  </p>
  <div class="key-watch">
    <div style="font-size:12px;font-weight:700;color:#92400e;margin-bottom:6px;">
      🔍 重点关注
    </div>
    {_ul(outlook.get("key_watch_points",[]))}
  </div>
  <div class="uncertainty" style="margin-top:10px;">
    <div style="font-size:12px;font-weight:700;color:#991b1b;margin-bottom:6px;">
      ⚡ 主要不确定性
    </div>
    {_ul(outlook.get("uncertainties",[]))}
  </div>
</div>

<!-- 数据缺口 -->
{"" if not data_gaps else f'''
<div class="card">
  <div class="card-title">⚠️ 数据缺口提示</div>
  {_ul(data_gaps)}
</div>'''}

<!-- 采集日志 -->
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

    rel_path = f"current/{filename}"
    logger.info(f"Report generated: {filepath}")
    return rel_path

"""盘前分析富集层：收集量化评分、资金流向、板块热力、风险摘要、AI链信号等增量数据。

在 pipeline 的 clean → analyze 之间执行。所有函数均为同步调用（内部按需
使用 asyncio.run / run_coroutine 包装），不依赖 FastAPI request 上下文。
返回的字典最终以 JSON 字符串形式注入 prompt 模板变量。
"""
import asyncio
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ── 内部工具 ────────────────────────────────────────────────────────────────

def _run(coro):
    """在当前线程安全地运行异步协程（可能在非 event-loop 线程中调用）。"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(asyncio.run, coro)
                return fut.result(timeout=40)
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ── 1. 关注股票量化评分 ──────────────────────────────────────────────────────

def collect_watchlist_quan(db) -> list:
    """查询当前全体关注股票（WatchlistItem）的最新量化评分。

    返回 [{stock_code, stock_name, market, notes, quan_percentile,
            composite_score, price, change_pct, ...}, ...]
    """
    try:
        from models import WatchlistItem
        items = db.query(WatchlistItem).filter(
            WatchlistItem.hidden == 0,
            WatchlistItem.item_type == "stock",
        ).order_by(WatchlistItem.sort_order).all()

        if not items:
            return []

        codes = [it.stock_code for it in items]
        code_meta = {
            it.stock_code: {"name": it.stock_name, "market": it.market, "notes": it.notes}
            for it in items
        }

        # 直接调用 quan 模块内部函数（避免 HTTP 依赖）
        from routes.quan import _get_conn, _table_exists, _resolve_date, _fetch_scores, _batch_prices, _enrich

        if not _table_exists():
            # quan 表不存在时返回无评分的基础信息
            return [
                {"stock_code": c, "stock_name": code_meta[c]["name"],
                 "market": code_meta[c]["market"], "notes": code_meta[c]["notes"],
                 "quan_percentile": None, "composite_score": None}
                for c in codes
            ]

        result_map: dict = {}
        with _get_conn() as conn:
            for model_name in ("factor", "factor_star50"):
                remaining = [c for c in codes if c not in result_map]
                if not remaining:
                    break
                td = _resolve_date(conn, None, model_name)
                if not td:
                    continue
                rows = _fetch_scores(conn, td, model_name, 0.0, None, remaining)
                for row in rows:
                    result_map[row["stock_code"]] = dict(row)

        # 批量拉取实时价格
        found_codes = list(result_map.keys())
        if found_codes:
            prices = _batch_prices(found_codes)
            enriched = _enrich(list(result_map.values()), prices)
            for row in enriched:
                result_map[row["stock_code"]] = row

        out = []
        for code in codes:
            meta = code_meta[code]
            row = result_map.get(code, {})
            out.append({
                "stock_code": code,
                "stock_name": meta["name"],
                "market": meta["market"],
                "notes": meta["notes"],
                "quan_percentile": row.get("quan_percentile"),
                "composite_score": row.get("composite_score"),
                "momentum_score": row.get("momentum_score"),
                "value_score": row.get("value_score"),
                "quality_score": row.get("quality_score"),
                "price": row.get("price"),
                "change_pct": row.get("change_pct"),
                "trade_date": row.get("trade_date"),
            })

        return out

    except Exception as e:
        logger.warning("collect_watchlist_quan failed: %s", e)
        return []


# ── 2. 个股资金流向 TOP20 ────────────────────────────────────────────────────

def collect_fund_flow_top20() -> list:
    """调用 THS 快速抓取接口，返回主力净流入 TOP20 个股列表。"""
    try:
        from routes.macro import _fetch_fund_flow_ths_fast
        return _fetch_fund_flow_ths_fast()
    except Exception as e:
        logger.warning("collect_fund_flow_top20 failed: %s", e)
        return []


# ── 3. 板块资金流向 TOP10 ────────────────────────────────────────────────────

def collect_sector_fund_flow() -> list:
    """返回主力净流入 TOP10 行业板块（异步→同步包装）。"""
    try:
        from services.sector_service import fetch_sector_fund_flow_top10
        return _run(fetch_sector_fund_flow_top10())
    except Exception as e:
        logger.warning("collect_sector_fund_flow failed: %s", e)
        return []


# ── 4. 板块热力图 ─────────────────────────────────────────────────────────────

def collect_sector_heatmap() -> list:
    """返回 TOP100 板块的涨跌幅+主力净流入（热力图数据）。"""
    try:
        from services.sector_service import fetch_heatmap_data
        return _run(fetch_heatmap_data())
    except Exception as e:
        logger.warning("collect_sector_heatmap failed: %s", e)
        return []


# ── 5. 风险摘要 ───────────────────────────────────────────────────────────────

def collect_risk_summary() -> dict:
    """聚合情绪指标、北向动向、融资余额，返回风险摘要字典。"""
    result = {}
    try:
        from services.risk_service import fetch_sentiment, fetch_north_fund
        sentiment = _run(fetch_sentiment())
        north = _run(fetch_north_fund())
        result["sentiment"] = {
            "fear_greed_index": sentiment.get("fear_greed_index"),
            "level": sentiment.get("level"),
            "vix": sentiment.get("vix"),
            "description": sentiment.get("description", ""),
        }
        result["north_fund"] = {
            "total_net": north.get("total_net", 0),
            "signal": north.get("signal", ""),
            "level": north.get("level", "neutral"),
            "up_ratio": north.get("up_ratio", 0),
        }
    except Exception as e:
        logger.warning("collect_risk_summary (sentiment/north) failed: %s", e)

    return result


# ── 6. AI 产业链昨日信号 ──────────────────────────────────────────────────────

def collect_prev_chain_signals(db) -> list:
    """读取最近一个交易日的 PremarketChainSignal 记录，作为连续性追踪依据。"""
    try:
        from models import PremarketChainSignal
        cutoff = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        rows = (
            db.query(PremarketChainSignal)
            .filter(PremarketChainSignal.signal_date >= cutoff)
            .order_by(PremarketChainSignal.signal_date.desc(), PremarketChainSignal.id.desc())
            .limit(30)
            .all()
        )
        # 每个 theme 只保留最新一条
        seen = set()
        result = []
        for r in rows:
            if r.theme not in seen:
                seen.add(r.theme)
                try:
                    catalysts = json.loads(r.catalysts or "[]")
                except Exception:
                    catalysts = []
                try:
                    risks = json.loads(r.risks or "[]")
                except Exception:
                    risks = []
                result.append({
                    "signal_date": r.signal_date,
                    "theme": r.theme,
                    "direction": r.direction,
                    "confidence": r.confidence,
                    "summary": r.summary,
                    "catalysts": catalysts,
                    "risks": risks,
                })
        return result
    except Exception as e:
        logger.warning("collect_prev_chain_signals failed: %s", e)
        return []


# ── 7. 牛股候选预筛 ───────────────────────────────────────────────────────────

def collect_bull_candidates(watchlist_quan: list, fund_flow_top20: list) -> list:
    """
    基于量化百分位 + 资金流入双因子对关注股票进行预筛，
    返回候选牛股列表（最多 10 只）供 LLM 做最终研判。

    评分规则：
      - 量化百分位 >= 70 → +2 分
      - 量化百分位 >= 50 → +1 分
      - 出现在资金流入 TOP20 → +2 分
      - 当日涨幅 > 3% → +1 分
      - 当日涨幅 < -3% → -1 分
    """
    fund_flow_codes = {item["stock_code"] for item in fund_flow_top20}

    candidates = []
    for s in watchlist_quan:
        score = 0
        reasons = []

        pct = s.get("quan_percentile")
        if pct is not None:
            if pct >= 70:
                score += 2
                reasons.append(f"量化百分位{pct:.0f}%（高分）")
            elif pct >= 50:
                score += 1
                reasons.append(f"量化百分位{pct:.0f}%（中上）")

        code = s.get("stock_code", "")
        if code in fund_flow_codes:
            score += 2
            reasons.append("进入主力净流入TOP20")

        chg = s.get("change_pct")
        if chg is not None:
            if chg > 3:
                score += 1
                reasons.append(f"涨幅+{chg:.1f}%")
            elif chg < -3:
                score -= 1
                reasons.append(f"跌幅{chg:.1f}%（短期弱势）")

        if score >= 2:
            candidates.append({
                "stock_code": code,
                "stock_name": s.get("stock_name", ""),
                "market": s.get("market", ""),
                "score": score,
                "reasons": reasons,
                "quan_percentile": pct,
                "price": s.get("price"),
                "change_pct": chg,
            })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:10]


# ── 主入口 ────────────────────────────────────────────────────────────────────

def enrich(db) -> dict:
    """
    收集所有增量数据，返回 enriched_data 字典。
    键名与 analyzer._build_prompt() 中的模板变量对应。
    """
    logger.info("Enricher: start collecting supplemental data")

    watchlist_quan = collect_watchlist_quan(db)
    logger.info(f"Enricher: watchlist_quan={len(watchlist_quan)} stocks")

    fund_flow_top20 = collect_fund_flow_top20()
    logger.info(f"Enricher: fund_flow_top20={len(fund_flow_top20)} stocks")

    sector_fund_flow = collect_sector_fund_flow()
    logger.info(f"Enricher: sector_fund_flow={len(sector_fund_flow)} sectors")

    sector_heatmap = collect_sector_heatmap()
    logger.info(f"Enricher: sector_heatmap={len(sector_heatmap)} sectors")

    risk_summary = collect_risk_summary()
    logger.info(f"Enricher: risk_summary keys={list(risk_summary.keys())}")

    prev_chain_signals = collect_prev_chain_signals(db)
    logger.info(f"Enricher: prev_chain_signals={len(prev_chain_signals)} themes")

    bull_candidates = collect_bull_candidates(watchlist_quan, fund_flow_top20)
    logger.info(f"Enricher: bull_candidates={len(bull_candidates)}")

    return {
        "watchlist_quan": watchlist_quan,
        "fund_flow_top20": fund_flow_top20,
        "sector_fund_flow": sector_fund_flow,
        "sector_heatmap": sector_heatmap,
        "risk_summary": risk_summary,
        "prev_chain_signals": prev_chain_signals,
        "bull_candidates": bull_candidates,
    }

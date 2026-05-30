"""主流水线：采集→清洗→分析→生成，供路由和调度器调用。"""
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def _persist_chain_signals(db, report_id: int, signal_date: str, analysis: dict):
    """将 LLM 输出的 chain_tracking 字段写入 PremarketChainSignal 表。"""
    if not isinstance(analysis, dict):
        return
    chain_tracking = analysis.get("chain_tracking") or []
    if not chain_tracking:
        return

    from models import PremarketChainSignal
    for item in chain_tracking:
        if not isinstance(item, dict) or not item.get("theme"):
            continue
        row = PremarketChainSignal(
            signal_date=signal_date,
            theme=str(item.get("theme", ""))[:100],
            direction=str(item.get("direction", "stable"))[:20],
            confidence=str(item.get("confidence", "medium"))[:20],
            summary=str(item.get("summary", ""))[:500],
            catalysts=json.dumps(item.get("catalysts") or [], ensure_ascii=False),
            risks=json.dumps(item.get("risks") or [], ensure_ascii=False),
            report_id=report_id,
        )
        db.add(row)
    db.commit()
    logger.info(f"Persisted {len(chain_tracking)} chain signals for {signal_date}")


def run_pipeline(db, record_id: int = None) -> dict:
    """
    完整执行一次盘前分析流水线。
    record_id: 由路由层预先创建的记录 ID（避免重复创建）；
               调度器直接调用时为 None，pipeline 自行创建。
    """
    from models import DataSource, PremarketReport
    from premarket.collector import collect_all
    from premarket.cleaner import clean
    from premarket.analyzer import analyze, clear_stream
    from premarket.generator import generate

    today = datetime.now().strftime("%Y-%m-%d")
    now_time = datetime.now().strftime("%H:%M:%S")

    # 复用路由层已建记录，或自行创建
    if record_id:
        record = db.query(PremarketReport).filter(PremarketReport.id == record_id).first()
        if not record:
            record_id = None

    if not record_id:
        record = PremarketReport(
            report_date=today,
            report_time=now_time,
            status="running",
        )
        db.add(record)
        db.commit()
        db.refresh(record)

    try:
        # 1. 获取启用的数据源和行情标的
        from models import WatchedTicker
        from premarket.enricher import enrich
        sources = db.query(DataSource).filter(DataSource.enabled == 1).all()
        sources_list = [
            {"name": s.name, "url": s.url,
             "source_type": s.source_type, "category": s.category,
             "enabled": bool(s.enabled)}
            for s in sources
        ]
        tickers_list = [
            {"symbol": t.symbol, "name": t.name, "category": t.category or ""}
            for t in db.query(WatchedTicker).filter(WatchedTicker.enabled == 1).all()
        ]
        logger.info(f"Pipeline: {len(sources_list)} sources, {len(tickers_list)} tickers")

        # 2. 采集
        raw_data = collect_all(sources_list, tickers=tickers_list)

        # 3. 清洗
        cleaned = clean(raw_data)

        # 3.5. 富集（量化评分、资金流向、板块热力、风险摘要、链信号）
        try:
            enriched = enrich(db)
            cleaned["_enriched"] = enriched
        except Exception as _e:
            logger.warning(f"Enricher failed (non-fatal): {_e}")
            cleaned["_enriched"] = {}

        # 4. 分析（优先按名称匹配模板；record_id 用于流式输出缓冲）
        analysis = analyze(cleaned, db, template_name="AI产业链盘前分析", record_id=record.id)

        # 5. 将美股行情 + 新闻（含 URL）注入 analysis，前端直接读取
        us_market = cleaned.get("us_market")
        if isinstance(analysis, dict) and "error" not in analysis:
            if us_market:
                analysis["_us_market"] = us_market
            news_items = cleaned.get("news", [])
            if news_items:
                analysis["_news_items"] = [
                    {
                        "title":           item.get("title", ""),
                        "url":             item.get("url", ""),
                        "source":          item.get("source", ""),
                        "published_at":    (item.get("published_at") or "")[:16],
                        "signal_strength": item.get("signal_strength", "low"),
                        "sentiment":       item.get("sentiment", ""),
                    }
                    for item in news_items[:60]
                ]

        # 6. 生成 HTML
        report_path = generate(analysis, cleaned, today)

        # 6.5. 持久化 AI 链追踪信号（供下次报告连续性追踪）
        try:
            _persist_chain_signals(db, record.id, today, analysis)
        except Exception as _e:
            logger.warning(f"Persist chain signals failed (non-fatal): {_e}")

        # 7. 更新记录
        record.status = "completed"
        record.report_path = report_path
        record.analysis_json = json.dumps(analysis, ensure_ascii=False)
        record.raw_data_json = json.dumps(
            {"stats": cleaned.get("stats", {}),
             "fetch_errors": cleaned.get("fetch_errors", []),
             "news_count": len(cleaned.get("news", []))},
            ensure_ascii=False,
        )
        db.commit()
        logger.info(f"Pipeline completed: {report_path}")
        clear_stream(record.id)
        return {"status": "completed", "report_path": report_path, "id": record.id}

    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        record.status = "failed"
        record.error_msg = str(e)
        db.commit()
        clear_stream(record.id)
        return {"status": "failed", "error": str(e), "id": record.id}

"""主流水线：采集→清洗→分析→生成，供路由和调度器调用。"""
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


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

        # 4. 分析（优先按名称匹配模板；record_id 用于流式输出缓冲）
        analysis = analyze(cleaned, db, template_name="AI产业链盘前分析", record_id=record.id)

        # 5. 将美股行情注入 analysis，前端直接读取
        us_market = cleaned.get("us_market")
        if us_market and isinstance(analysis, dict) and "error" not in analysis:
            analysis["_us_market"] = us_market

        # 6. 生成 HTML
        report_path = generate(analysis, cleaned, today)

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

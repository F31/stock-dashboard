"""Stock Dashboard — FastAPI backend entry point."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from routes.auth import router as auth_router
from routes.stocks import router as stocks_router
from routes.admin import router as admin_router
from routes.llm_config import router as llm_config_router
from routes.macro import router as macro_router
from routes.reports import router as reports_router
from routes.datasources import router as datasources_router
from routes.prompt_templates import router as prompt_templates_router
from routes.scheduled_tasks import router as scheduled_tasks_router
from routes.premarket import router as premarket_router
from routes.watched_tickers import router as watched_tickers_router
from routes.analysis_framework import router as analysis_framework_router
from database import engine, Base, get_db
from models import (  # noqa: F401 — ensures tables are registered
    User, LLMConfig, StockReport,
    DataSource, PromptTemplate, PremarketReport, ScheduledTask, WatchedTicker,
    AnalysisFramework, SystemSetting, StockCapex,
)
from sqlalchemy.orm import Session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

# Create tables + migrations
Base.metadata.create_all(bind=engine)

# Migration: add role column to users table if missing
from database import _ensure_column
_ensure_column("users", "role VARCHAR(20) DEFAULT 'user'")
_ensure_column("users", "is_active INTEGER DEFAULT 1")
_ensure_column("watchlist", "item_type VARCHAR(10) DEFAULT 'stock'")
_ensure_column("watchlist", "hidden INTEGER DEFAULT 0")
_ensure_column("operation_logs", "ip_location VARCHAR(100) DEFAULT ''")
# Migration: analysis_framework table — new 3-section structure replaces old definition blob
try:
    _ensure_column("analysis_framework", "description TEXT DEFAULT ''")
    _ensure_column("analysis_framework", "layer_definition TEXT DEFAULT '[]'")
    _ensure_column("analysis_framework", "keyword_dict TEXT DEFAULT '{}'")
    _ensure_column("analysis_framework", "entity_matrix TEXT DEFAULT '[]'")
    _ensure_column("analysis_framework", "created_at DATETIME")
    _ensure_column("analysis_framework", "framework_data TEXT")
except Exception:
    pass  # table may not exist yet; create_all will handle it


def _seed_defaults():
    """首次启动时插入默认数据源、提示词模板、定时任务。"""
    from sqlalchemy.orm import Session as _S
    db: _S = next(get_db())
    try:
        # ── 默认数据源 ──
        if db.query(DataSource).count() == 0:
            defaults = [
                DataSource(name="Wired Technology", source_type="rss", category="国际",
                           url="https://www.wired.com/feed/rss",
                           notes="Wired 科技频道（替换已关闭的 Reuters RSS）"),
                DataSource(name="CNBC Tech", source_type="rss", category="国际",
                           url="https://www.cnbc.com/id/19854910/device/rss/rss.html",
                           notes="CNBC科技频道"),
                DataSource(name="MarketWatch", source_type="rss", category="国际",
                           url="https://feeds.marketwatch.com/marketwatch/topstories/",
                           notes="MarketWatch头条"),
                DataSource(name="TechCrunch", source_type="rss", category="国际",
                           url="https://techcrunch.com/feed/",
                           notes="TechCrunch科技创业"),
                DataSource(name="新浪财经科技", source_type="api", category="国内",
                           url="https://feed.mix.sina.com.cn/api/roll/get",
                           notes="新浪财经科技滚动新闻"),
                DataSource(name="东方财富", source_type="webpage", category="国内",
                           url="https://www.eastmoney.com",
                           notes="东方财富财经新闻"),
                DataSource(name="财联社", source_type="akshare", category="国内",
                           url="akshare:stock_info_global_cls",
                           notes="财联社实时电报，通过 akshare 采集（原 API 已下线）"),
                DataSource(name="36氪", source_type="rss", category="国内",
                           url="https://36kr.com/feed",
                           notes="36氪科技创业"),
                DataSource(name="财新资讯", source_type="akshare", category="国内",
                           url="akshare:stock_news_main_cx",
                           notes="财新快讯，覆盖宏观、市场、产业动态（约100条）"),
                DataSource(name="A股IPO辅导备案", source_type="akshare", category="国内",
                           url="akshare:stock_ipo_tutor_em",
                           notes="A股IPO辅导备案登记，近30天，来源：东方财富监管数据"),
                DataSource(name="A股IPO申报受理", source_type="akshare", category="国内",
                           url="akshare:stock_ipo_declare_em",
                           notes="A股IPO申报受理状态，近7天有变更，来源：东方财富监管数据"),
            ]
            db.add_all(defaults)

        # ── 默认提示词模板 ──
        if db.query(PromptTemplate).count() == 0:
            default_prompt = """# 角色
你是 AI 产业链研究助理。你的任务是基于下方提供的、经过采集和清洗的结构化数据，
做产业链关联分析，生成股票观察清单和 A股开盘前情景判断。

# 最重要的约束(违反即视为失败)
1. 你只能基于【输入数据】区块内的信息进行分析。严禁引入任何外部信息、你训练数据中的旧信息或你的猜测。
2. 所有数字、行情、事件均为既定事实，不得修改、不得编造。如果某项信息输入中没有，就明确写"数据中未提供"，不要补全。
3. 你的工作是"判断与解读"，不是"提供事实"。
4. 你输出的是"值得关注什么、为什么"，不是买卖指令。不得出现"买入""卖出""目标价"等表述。
5. 每个标的必须同时给出看多和看空两方面理由。

# 产业链分层定义(用于给标的打标签)
- 算力层：AI芯片、晶圆代工、先进封装、HBM、服务器、光模块、数据中心、电力与散热
- 模型与平台层：大模型厂商、云服务、开发框架
- 应用层：AI软件、AI Agent、垂直行业应用
- 配套基础设施：网络设备、存储

# 分析步骤
1. 通读输入数据，识别与 AI 产业链相关的关键事件。
2. 将每个事件关联到产业链层级和具体标的；若某事件可能沿产业链传导（如算力层利空传导至光模块），需指出传导路径。
3. 结合隔夜美股、股指期货表现，判断市场对科技股的情绪基调。
4. 筛选出 3-5 个本期最值得关注的标的进入观察清单。
5. 给出 A股开盘前的情景判断（注意：是情景描述，不是涨跌预测）。

# 输入数据
## 新闻(过去24小时)
{{news_json}}
## 财报与重要事件
{{earnings_events_json}}
## 宏观经济数据
{{macro_json}}
## 隔夜美股收盘(含盘后，含AI芯片个股)
{{us_market_json}}
## 股指期货
{{futures_json}}
## A股主要指数（前一交易日收盘）
{{cn_market_json}}

# 输出格式(严格输出 JSON，不要任何额外文字、不要 Markdown 代码块)
{
  "date": "YYYY-MM-DD",
  "market_sentiment": {
    "tone": "偏乐观/中性/偏谨慎",
    "basis": "基于哪些输入数据得出，逐条说明"
  },
  "watchlist": [
    {
      "name": "标的名称",
      "industry_layer": "所属产业链层级",
      "trigger_event": "今天因何进入清单",
      "source_ref": "该结论依据的输入数据条目标识",
      "overnight_performance": "隔夜相关表现，无则填'数据中未提供'",
      "bull_case": "看多理由",
      "bear_case": "看空理由",
      "follow_up": "需要用户进一步跟进的问题"
    }
  ],
  "premarket_outlook": {
    "summary": "A股开盘前情景判断",
    "key_watch_points": ["关注点1", "关注点2"],
    "uncertainties": ["主要不确定性1", "主要不确定性2"]
  },
  "data_gaps": ["本次输入中缺失或不足的数据项"]
}"""
            db.add(PromptTemplate(
                name="AI产业链盘前分析（默认）",
                content=default_prompt,
                status="active",
                is_default=1,
            ))

        # ── 默认分析框架 ──
        if db.query(AnalysisFramework).count() == 0:
            import json as _json
            from premarket.framework import (
                DEFAULT_LAYER_DEFINITION, DEFAULT_KEYWORD_DICT, DEFAULT_ENTITY_MATRIX,
            )
            db.add(AnalysisFramework(
                name             = "AI产业链",
                description      = "纵向8层（L1-L3为★物理瓶颈层）× 横向3列（云侧/端侧/物理AI）",
                is_active        = 1,
                layer_definition = _json.dumps(DEFAULT_LAYER_DEFINITION, ensure_ascii=False),
                keyword_dict     = _json.dumps(DEFAULT_KEYWORD_DICT,     ensure_ascii=False),
                entity_matrix    = _json.dumps(DEFAULT_ENTITY_MATRIX,    ensure_ascii=False),
            ))

        # ── 默认行情监控标的 ──
        if db.query(WatchedTicker).count() == 0:
            db.add_all([
                WatchedTicker(symbol="NVDA", name="英伟达",   category="AI芯片"),
                WatchedTicker(symbol="AMD",  name="AMD",      category="AI芯片"),
                WatchedTicker(symbol="AVGO", name="博通",     category="AI芯片"),
                WatchedTicker(symbol="INTC", name="英特尔",   category="AI芯片"),
            ])

        # ── 默认定时任务 ──
        if db.query(ScheduledTask).count() == 0:
            db.add(ScheduledTask(
                name="AI产业链盘前分析",
                task_type="premarket_analysis",
                schedule_time="06:00",
                enabled=1,
            ))

        db.commit()
        logging.info("Default seed data initialized")
    except Exception as e:
        logging.warning(f"Seed defaults error: {e}")
    finally:
        db.close()


_seed_defaults()


def _cleanup_stale_running():
    """启动时：把遗留 running 记录标为 failed，并删除所有 failed 记录。"""
    from sqlalchemy.orm import Session as _S
    db: _S = next(get_db())
    try:
        from models import PremarketReport
        # 1. 遗留 running → failed
        stale = db.query(PremarketReport).filter(PremarketReport.status == "running").all()
        for r in stale:
            r.status = "failed"
            r.error_msg = "服务重启，任务中断"
        if stale:
            db.commit()
            logging.info(f"Startup cleanup: marked {len(stale)} stale running record(s) as failed")
        # 2. 删除所有 failed 记录
        deleted = db.query(PremarketReport).filter(PremarketReport.status == "failed").delete()
        if deleted:
            db.commit()
            logging.info(f"Startup cleanup: deleted {deleted} failed record(s)")
    except Exception as e:
        logging.warning(f"Startup cleanup error: {e}")
    finally:
        db.close()


_cleanup_stale_running()


def _migrate_prompt_template():
    """为现有提示词模板追加 {{cn_market_json}} 占位符（仅当缺失时执行）。"""
    from sqlalchemy.orm import Session as _S
    db: _S = next(get_db())
    try:
        from models import PromptTemplate
        tpl = db.query(PromptTemplate).filter(
            PromptTemplate.is_default == 1,
            PromptTemplate.status == "active",
        ).first()
        if tpl and "{{cn_market_json}}" not in tpl.content:
            old_sec = "## 股指期货\n{{futures_json}}"
            new_sec = ("## 股指期货\n{{futures_json}}\n"
                       "## A股主要指数（前一交易日收盘）\n{{cn_market_json}}")
            if old_sec in tpl.content:
                tpl.content = tpl.content.replace(old_sec, new_sec)
                db.commit()
                logging.info("Migrated prompt template: added {{cn_market_json}} placeholder")
    except Exception as e:
        logging.warning(f"Prompt template migration error: {e}")
    finally:
        db.close()


_migrate_prompt_template()


def _migrate_analysis_framework():
    """将旧格式（definition blob）的 analysis_framework 行迁移为新三段式结构。"""
    from sqlalchemy.orm import Session as _S
    db: _S = next(get_db())
    try:
        from models import AnalysisFramework
        import json as _json
        from premarket.framework import (
            DEFAULT_LAYER_DEFINITION, DEFAULT_KEYWORD_DICT, DEFAULT_ENTITY_MATRIX,
        )
        rows = db.query(AnalysisFramework).all()
        updated = 0
        for row in rows:
            ld = _json.loads(row.layer_definition or "[]")
            if not ld:  # old row migrated from previous schema — fill with defaults
                row.layer_definition = _json.dumps(DEFAULT_LAYER_DEFINITION, ensure_ascii=False)
                row.keyword_dict     = _json.dumps(DEFAULT_KEYWORD_DICT,     ensure_ascii=False)
                row.entity_matrix    = _json.dumps(DEFAULT_ENTITY_MATRIX,    ensure_ascii=False)
                if not row.description:
                    row.description = "纵向8层（L1-L3为★物理瓶颈层）× 横向3列（云侧/端侧/物理AI）"
                if not row.name:
                    row.name = "AI产业链"
                updated += 1
        if updated:
            db.commit()
            logging.info(f"Migrated {updated} analysis_framework row(s) to new structure")
    except Exception as e:
        logging.warning(f"Analysis framework migration error: {e}")
    finally:
        db.close()


_migrate_analysis_framework()


async def _periodic_stale_cleanup():
    """每 2 分钟：删除超时 running 记录 + 删除所有 failed 记录。"""
    await asyncio.sleep(60)  # 启动 1 分钟后开始
    while True:
        try:
            import datetime as _dt
            from database import SessionLocal
            from models import PremarketReport
            db = SessionLocal()
            # 1. 超过 20 分钟仍 running → 删除
            cutoff = _dt.datetime.utcnow() - _dt.timedelta(minutes=20)
            stuck = db.query(PremarketReport).filter(
                PremarketReport.status == "running",
                PremarketReport.created_at < cutoff,
            ).delete()
            # 2. 所有 failed → 删除
            failed = db.query(PremarketReport).filter(
                PremarketReport.status == "failed",
            ).delete()
            if stuck or failed:
                db.commit()
                logging.info(f"Periodic cleanup: deleted {stuck} stuck + {failed} failed record(s)")
            db.close()
        except Exception as e:
            logging.warning(f"Periodic stale cleanup error: {e}")
        await asyncio.sleep(120)  # 每 2 分钟检查一次


async def _daily_macro_refresh():
    """Background task: pre-warm then refresh profit + industrial charts every 24h."""
    await asyncio.sleep(15)  # let app finish starting up first
    while True:
        try:
            from services.macro_service import (
                fetch_industrial_profit, fetch_nbs_industrial_charts, _cache as macro_cache,
            )
            macro_cache.pop("macro:industrial_profit", None)
            macro_cache.pop("macro:nbs_industrial_charts", None)
            await fetch_industrial_profit()
            await fetch_nbs_industrial_charts()
            logging.info("Daily macro refresh completed (profit + industrial charts)")
        except Exception as exc:
            logging.warning(f"Daily macro refresh error: {exc}")
        await asyncio.sleep(24 * 3600)


async def _daily_capex_refresh():
    """Background task: refresh Capex for all watchlist items once per day."""
    await asyncio.sleep(60)  # start after app is fully up
    while True:
        try:
            from services.capex_service import refresh_all_capex
            from models import WatchlistItem
            db = next(get_db())
            items = db.query(WatchlistItem).all()
            await refresh_all_capex(items, db)
            db.close()
            logging.info(f"Daily Capex refresh completed ({len(items)} items)")
        except Exception as exc:
            logging.warning(f"Daily Capex refresh error: {exc}")
        await asyncio.sleep(24 * 3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task_macro = asyncio.create_task(_daily_macro_refresh())
    task_capex = asyncio.create_task(_daily_capex_refresh())
    task_cleanup = asyncio.create_task(_periodic_stale_cleanup())
    # 启动盘前分析调度器
    try:
        from premarket.scheduler import start as sched_start, stop as sched_stop
        db = next(get_db())
        sched_start(db)
        db.close()
    except Exception as e:
        logging.warning(f"Scheduler start error: {e}")
    yield
    for t in (task_macro, task_capex, task_cleanup):
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass
    try:
        from premarket.scheduler import stop as sched_stop
        sched_stop()
    except Exception:
        pass


app = FastAPI(title="Stock Dashboard", lifespan=lifespan)

# CORS — 本地开发模式用（生产模式走同源无需 CORS）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
    allow_origin_regex=r".*\.trycloudflare\.com$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register routers ──

app.include_router(auth_router, prefix="/api")
app.include_router(stocks_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(llm_config_router, prefix="/api")
app.include_router(macro_router, prefix="/api")
app.include_router(reports_router, prefix="/api")
app.include_router(datasources_router, prefix="/api")
app.include_router(prompt_templates_router, prefix="/api")
app.include_router(scheduled_tasks_router, prefix="/api")
app.include_router(premarket_router, prefix="/api")
app.include_router(watched_tickers_router, prefix="/api")
app.include_router(analysis_framework_router, prefix="/api")

# ── Serve reports directory ──
reports_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "reports")
os.makedirs(reports_dir, exist_ok=True)
app.mount("/reports", StaticFiles(directory=reports_dir, html=True), name="reports")

# ── Serve built frontend (production / single-port mode) ──
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
    logging.info("Frontend mounted from %s", frontend_dist)
else:
    logging.warning("Frontend dist not found — API-only mode (dev)")

    @app.get("/")
    def root():
        return {"msg": "Stock Dashboard API", "status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)

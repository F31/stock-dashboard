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
from database import engine, Base
from models import User, LLMConfig, StockReport  # noqa: F401 — ensures table is registered
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
_ensure_column("watchlist", "item_type VARCHAR(10) DEFAULT 'stock'")
_ensure_column("watchlist", "hidden INTEGER DEFAULT 0")
_ensure_column("operation_logs", "ip_location VARCHAR(100) DEFAULT ''")


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_daily_macro_refresh())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
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

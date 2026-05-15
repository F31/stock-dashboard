"""Stock Dashboard — FastAPI backend entry point."""
import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from routes.auth import router as auth_router
from routes.stocks import router as stocks_router
from routes.admin import router as admin_router
from database import engine, Base
from models import User
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


app = FastAPI(title="Stock Dashboard")

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

"""Database setup with SQLAlchemy + SQLite. Handles schema migration for new columns."""
import os
import logging
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

logger = logging.getLogger(__name__)

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "stock_dashboard.db")

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_column(table: str, column_def: str):
    """Add a column to an existing table if it doesn't already exist."""
    inspector = inspect(engine)
    columns = [c["name"] for c in inspector.get_columns(table)]
    col_name = column_def.split()[0]
    if col_name not in columns:
        with engine.connect() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column_def}"))
            conn.commit()
            logger.info(f"Added column '{column_def}' to '{table}'")


def init_db():
    """Create all tables and run migrations for new columns."""
    Base.metadata.create_all(bind=engine)
    # Migration: add role column to users table if missing
    _ensure_column("users", "role VARCHAR(20) DEFAULT 'user'")

    # Ensure quan_tech_levels table exists (not managed by SQLAlchemy models)
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS quan_tech_levels (
                stock_code  TEXT NOT NULL,
                trade_date  TEXT NOT NULL,
                last_adj    REAL,
                ma5         REAL,
                ma20        REAL,
                ma60        REAL,
                ma120       REAL,
                atr14       REAL,
                rsi14       REAL,
                h52w        REAL,
                l52w        REAL,
                updated_at  TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (stock_code, trade_date)
            )
        """))
        conn.commit()

"""SQLAlchemy ORM models."""
import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Float
from database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    role = Column(String(20), default="user")  # "admin" | "user"
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class WatchlistItem(Base):
    __tablename__ = "watchlist"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    item_type = Column(String(10), default="stock")  # "stock" | "sector"
    stock_code = Column(String(20), nullable=False)
    market = Column(String(10), nullable=False)  # A, HK, US (or "SECTOR")
    stock_name = Column(String(100), default="")
    notes = Column(Text, default="")
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class OperationLog(Base):
    __tablename__ = "operation_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=True)
    username = Column(String(50), default="")
    action = Column(String(50), nullable=False)      # login, logout, add_stock, remove_stock, update_notes, create_user, delete_user, refresh, etc.
    target = Column(String(100), default="")          # what was acted upon (stock code, user id, etc.)
    detail = Column(Text, default="")                 # extra info
    ip_address = Column(String(50), default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)

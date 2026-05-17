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
    hidden = Column(Integer, default=0)  # 1 = hidden (has reports, soft-deleted)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class LLMConfig(Base):
    __tablename__ = "llm_configs"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)           # 展示名称，如 "DeepSeek Chat"
    provider = Column(String(50), default="custom")      # openai / anthropic / deepseek / …
    base_url = Column(String(500), nullable=False)        # API base URL
    model_name = Column(String(200), nullable=False)      # 模型标识符
    api_key = Column(String(1000), default="")            # API Key / Token
    description = Column(Text, default="")                # 备注
    is_default = Column(Integer, default=0)               # 1=默认，同时只有一个
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)


class StockReport(Base):
    __tablename__ = "stock_reports"
    id = Column(Integer, primary_key=True, index=True)
    stock_code = Column(String(20), nullable=False, index=True)
    market = Column(String(10), nullable=False)
    title = Column(String(200), nullable=False)
    report_type = Column(String(10), nullable=False)   # "file" | "link"
    file_name = Column(String(300), default="")        # saved filename (for file type)
    url = Column(String(1000), default="")             # link URL or served path
    uploader_id = Column(Integer, nullable=False)
    uploader_name = Column(String(50), default="")
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

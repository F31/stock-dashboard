"""Pydantic schemas for API request/response validation."""
from pydantic import BaseModel
from typing import Optional, List


# ── Auth ──

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


# ── Watchlist ──

class AddStockRequest(BaseModel):
    stock_code: str
    market: str  # A, HK, US
    stock_name: Optional[str] = ""


class UpdateNotesRequest(BaseModel):
    notes: str


class UpdateNameRequest(BaseModel):
    stock_name: str


class StockDataResponse(BaseModel):
    id: int
    stock_code: str
    market: str
    stock_name: str
    notes: str
    item_type: str = "stock"
    price: Optional[float] = None
    change: Optional[float] = None
    change_pct: Optional[float] = None
    prev_close: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    open: Optional[float] = None
    volume: Optional[float] = None
    amount: Optional[float] = None
    turnover_rate: Optional[float] = None
    pe: Optional[float] = None
    market_cap: Optional[float] = None
    float_market_cap: Optional[float] = None
    amplitude: Optional[float] = None
    board_type: str = ""           # "industry" | "concept" for sectors
    up_count: Optional[int] = None     # sector: stocks up
    down_count: Optional[int] = None   # sector: stocks down
    news: List[dict] = []
    chart_data: List = []


class StockListItem(BaseModel):
    id: int
    stock_code: str
    market: str
    stock_name: str
    notes: str
    sort_order: int
    item_type: str = "stock"


# ── Admin / User Management ──

class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    created_at: Optional[str] = ""

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "user"


class UserUpdate(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None


class PaginatedUsers(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[UserResponse]


# ── Admin / Operation Logs ──

class LogEntry(BaseModel):
    id: int
    user_id: Optional[int] = None
    username: str
    action: str
    target: str
    detail: str
    ip_address: str
    ip_location: str = ""
    created_at: Optional[str] = ""

    class Config:
        from_attributes = True


class PaginatedLogs(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[LogEntry]


# ── LLM Config ──

class LLMConfigCreate(BaseModel):
    name: str
    provider: str = "custom"
    base_url: str
    model_name: str
    api_key: str = ""
    description: str = ""
    is_default: bool = False


class LLMConfigUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    base_url: Optional[str] = None
    model_name: Optional[str] = None
    api_key: Optional[str] = None
    description: Optional[str] = None
    is_default: Optional[bool] = None


class LLMConfigResponse(BaseModel):
    id: int
    name: str
    provider: str
    base_url: str
    model_name: str
    api_key_masked: str      # 脱敏展示，格式：前4位 + *×8 + 后4位
    description: str
    is_default: bool
    created_at: Optional[str] = ""
    updated_at: Optional[str] = ""

    class Config:
        from_attributes = True


# ── Data Sources ──

class DataSourceCreate(BaseModel):
    name: str
    url: str
    source_type: str = "rss"
    category: str = "国际"
    notes: str = ""
    enabled: bool = True

class DataSourceUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    source_type: Optional[str] = None
    category: Optional[str] = None
    notes: Optional[str] = None
    enabled: Optional[bool] = None

class DataSourceResponse(BaseModel):
    id: int
    name: str
    url: str
    source_type: str
    category: str
    notes: str
    enabled: bool
    created_at: Optional[str] = ""
    class Config:
        from_attributes = True


# ── Prompt Templates ──

class PromptTemplateCreate(BaseModel):
    name: str
    content: str
    status: str = "active"
    is_default: bool = False

class PromptTemplateUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None
    is_default: Optional[bool] = None

class PromptTemplateResponse(BaseModel):
    id: int
    name: str
    content: str
    status: str
    is_default: bool
    created_at: Optional[str] = ""
    updated_at: Optional[str] = ""
    class Config:
        from_attributes = True


# ── Scheduled Tasks ──

class ScheduledTaskCreate(BaseModel):
    name: str
    task_type: str = "premarket_analysis"
    schedule_time: str = "06:00"
    enabled: bool = True

class ScheduledTaskUpdate(BaseModel):
    name: Optional[str] = None
    schedule_time: Optional[str] = None
    enabled: Optional[bool] = None

class ScheduledTaskResponse(BaseModel):
    id: int
    name: str
    task_type: str
    schedule_time: str
    enabled: bool
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    created_at: Optional[str] = ""
    class Config:
        from_attributes = True


# ── Premarket Reports ──

class PremarketReportResponse(BaseModel):
    id: int
    report_date: str
    report_time: str
    report_path: str
    analysis_json: str
    status: str
    error_msg: str
    created_at: Optional[str] = ""
    class Config:
        from_attributes = True

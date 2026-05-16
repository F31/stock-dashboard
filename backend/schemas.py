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
    api_key_masked: str      # 脱敏展示
    api_key: Optional[str] = None   # 仅详情接口返回明文
    description: str
    is_default: bool
    created_at: Optional[str] = ""
    updated_at: Optional[str] = ""

    class Config:
        from_attributes = True

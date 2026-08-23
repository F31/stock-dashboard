"""HMM 买卖点信号 API 路由。

数据主源：每日流水线（run_hmm_signals.py）写入的 watchlist_hmm_signal 表。
当日缺失/新增股票 → 按需兜底：腾讯K线拉 OHLCV → 调 stock_quan 的 HMM 引擎
（优先进程内，hmmlearn 缺失时用 /root/qlib/qvenv 子进程）→ 结果写回 DB 并缓存。
按需计算带 per-stock 互斥锁，防止多用户并发刷新瞬间打满外部K线接口。
"""
import asyncio
import json
import logging
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
import requests

from database import DB_PATH, DB_DIR
from routes.auth import get_current_user
from models import User

logger = logging.getLogger(__name__)
router = APIRouter(tags=["hmm"])

# ── 配置 ──────────────────────────────────────────────────────────────────────
_HMM_TTL_TRADING = 900        # 15 min during trading hours
_HMM_HISTORY_DAYS = 20        # 状态转移历史天数

# 按需兜底子进程（本机有 hmmlearn 的 env）；进程内不可用时使用
# 均支持环境变量覆盖（云端/本地路径不一致时无需改代码）
_QLIB_PYTHON = os.environ.get(
    "QLIB_PYTHON",
    os.path.expanduser("~/qlib/qvenv/bin/python"),
)
_STOCK_QUAN_ROOT = os.environ.get("STOCK_QUAN_ROOT", "/root/projects/stock_quan")

# ── 进程内 hmmlearn / HMMEngine 可用性（复用 stock_quan 引擎）────────────────
_HMM_INLINE_OK = False
_HMMEngine = None
try:
    if _STOCK_QUAN_ROOT not in sys.path:
        sys.path.insert(0, _STOCK_QUAN_ROOT)
    from core.hmm_engine import HMMEngine as _HMMEngine, hmmlearn_available as _hml_avail
    if _hml_avail():
        _HMM_INLINE_OK = True
except Exception as e:
    logger.warning("hmm inline engine unavailable: %s", e)

_HMM_MODEL_DIR = os.environ.get(
    "HMM_MODEL_DIR",
    os.path.join(_STOCK_QUAN_ROOT, "models", "hmm"),
)

# per-stock 互斥锁：防止并发按需计算打爆外部K线
_hmm_locks: dict[str, asyncio.Lock] = {}
_hmm_lock_guard = asyncio.Lock()


async def _lock_for(code: str) -> asyncio.Lock:
    async with _hmm_lock_guard:
        if code not in _hmm_locks:
            _hmm_locks[code] = asyncio.Lock()
        return _hmm_locks[code]


# ── 历史K线（多源兜底）────────────────────────────────────────────────────────
_TX_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
_TX_HEADERS = {
    "Referer":    "https://gu.qq.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}
_EM_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
_EM_HEADERS = {
    "Referer":    "https://quote.eastmoney.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}
# 使用系统代理（Yahoo 等境外源需要）；国内源显式绕过代理。
_EM_UT = "7eea3edcaed734bea9cbfc24409ed989"


def _tencent_symbol(code: str, market: str) -> str:
    """A/HK/US → 腾讯K线代码。"""
    code = code.strip().upper()
    if market == "HK":
        return f"hk{code.lower()}"
    if market == "US":
        return f"us{code}"
    return ("sh" if code.startswith(("6", "5", "9")) else "sz") + code


def _em_secid(code: str, market: str) -> str:
    """A/HK/US → 东财 secid。"""
    code = code.strip()
    if market == "HK":
        return f"116.{code}"
    if market == "US":
        return f"105.{code}"
    return ("1." if code.startswith("6") else "0.") + code


def _fetch_kline_tencent(code: str, market: str) -> "list[dict] | None":
    """腾讯 fqkline：A股(qfq)、港股(day)。"""
    sym = _tencent_symbol(code, market)
    import datetime as _dt
    start = f"{_dt.date.today().year - 3}-01-01"
    end = _dt.date.today().strftime("%Y-%m-%d")
    param = f"{sym},day,{start},{end},1500,qfq"
    try:
        r = requests.get(_TX_KLINE_URL, params={"param": param},
                         headers=_TX_HEADERS, timeout=12,
                         proxies={"http": None, "https": None})
        if r.status_code in (403, 429, 503):
            return None
        j = r.json()
    except Exception:
        return None
    stock_data = (j.get("data") or {}).get(sym) or {}
    bars = (stock_data.get("qfqday") or stock_data.get("day")
            or stock_data.get("hfqday") or [])
    if len(bars) < 60:
        return None
    return _bars_to_ohlcv(bars)


def _fetch_kline_em(code: str, market: str) -> "list[dict] | None":
    """东财 push2his kline（A/HK/US），重试 2 次。"""
    secid = _em_secid(code, market)
    params = {
        "secid": secid, "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56", "ut": _EM_UT,
        "klt": "101", "fqt": "1",
        "beg": f"{datetime.now().year - 3}0101", "end": "20500101",
    }
    for i in range(3):
        try:
            r = requests.get(_EM_KLINE_URL, params=params, headers=_EM_HEADERS,
                             timeout=12, proxies={"http": None, "https": None})
            klines = (r.json().get("data") or {}).get("klines") or []
            if len(klines) >= 60:
                bars = [k.split(",") for k in klines]
                return _bars_to_ohlcv(bars)
        except Exception:
            pass
        if i < 2:
            time.sleep(1.5)
    return None


def _fetch_kline_yahoo(code: str, market: str) -> "list[dict] | None":
    """雅虎 kline（美股可靠）。"""
    sym = code.strip()
    if market == "HK":
        sym = f"{code}.HK"
    u = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
         f"?range=3y&interval=1d")
    try:
        r = requests.get(u, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return None
        res = (r.json().get("chart", {}).get("result") or [None])[0]
        if not res:
            return None
        ts = res.get("timestamp") or []
        q = ((res.get("indicators") or {}).get("quote") or [{}])[0]
        rows = []
        for i, t in enumerate(ts):
            if i >= len(q.get("close", [])):
                break
            c = q["close"][i]
            o = q["open"][i] if i < len(q.get("open", [])) else None
            h = q["high"][i] if i < len(q.get("high", [])) else None
            l = q["low"][i] if i < len(q.get("low", [])) else None
            v = q["volume"][i] if i < len(q.get("volume", [])) else None
            if c is None or h is None or l is None:
                continue
            import datetime as _dt
            rows.append({
                "date": _dt.datetime.fromtimestamp(t).strftime("%Y-%m-%d"),
                "open": float(o) if o is not None else float(c),
                "high": float(h), "low": float(l), "close": float(c),
                "volume": float(v or 0),
            })
        if len(rows) < 60:
            return None
        return rows
    except Exception:
        return None


def _bars_to_ohlcv(bars: list) -> "list[dict] | None":
    """统一 bar 列表 → ohlcv rows。"""
    rows = []
    for bar in bars:
        if len(bar) < 5:
            continue
        # [date, open, close, high, low] → 无 volume 补 0
        if len(bar) >= 6:
            try:
                rows.append({"date": bar[0], "open": float(bar[1]),
                             "close": float(bar[2]), "high": float(bar[3]),
                             "low": float(bar[4]),
                             "volume": float(bar[5]) if bar[5] else 0.0})
            except (ValueError, TypeError, IndexError):
                continue
        else:
            rows.append({"date": bar[0], "open": float(bar[1]),
                         "close": float(bar[2]), "high": float(bar[3]),
                         "low": float(bar[4]), "volume": 0.0})
    if len(rows) < 60:
        return None
    rows.sort(key=lambda x: x["date"])
    return rows


def _fetch_kline_ohlcv(code: str, market: str) -> "list[dict] | None":
    """多源拉取 OHLCV 历史（按市场选优先后顺序）。"""
    code = code.strip().upper()
    if market == "A":
        for fn in (_fetch_kline_tencent, _fetch_kline_em, _fetch_kline_yahoo):
            rows = fn(code, market)
            if rows:
                return rows
    elif market == "HK":
        for fn in (_fetch_kline_tencent, _fetch_kline_em, _fetch_kline_yahoo):
            rows = fn(code, market)
            if rows:
                return rows
    else:  # US
        for fn in (_fetch_kline_yahoo, _fetch_kline_tencent, _fetch_kline_em):
            rows = fn(code, market)
            if rows:
                return rows
    return None


# ── 计算方式：进程内 or 子进程 ─────────────────────────────────────────────────

def _compute_inline(code: str, market: str, ohlcv: list[dict], trade_date: str) -> Optional[dict]:
    """进程内调用 stock_quan HMMEngine 计算。"""
    import pandas as pd
    df = pd.DataFrame(ohlcv)
    eng = _HMMEngine(_HMM_MODEL_DIR)
    out = eng.analyse(code, df, trade_date=trade_date, market=market, mode="auto")
    return out


def _make_worker_script() -> str:
    """子进程计算脚本（stock_quan 根目录以 JSON 首行注入，避免写死路径）。"""
    return f"""
import sys, json
_header = json.loads(sys.stdin.readline())
sys.path.insert(0, _header['stock_quan_root'])
import pandas as pd
from core.hmm_engine import HMMEngine
payload = json.load(sys.stdin)
df = pd.DataFrame(payload['ohlcv'])
eng = HMMEngine(payload['model_dir'])
out = eng.analyse(payload['code'], df, trade_date=payload['trade_date'],
                  market=payload['market'], mode='auto')
print(json.dumps(out if out else {{'error': 'no-result'}}, ensure_ascii=False))
"""


def _compute_subprocess(code: str, market: str, ohlcv: list[dict], trade_date: str) -> Optional[dict]:
    """子进程（qvenv，含 hmmlearn）计算。"""
    if not os.path.exists(_QLIB_PYTHON):
        logger.warning("hmm subprocess: %s 不存在，无法按需计算", _QLIB_PYTHON)
        return None
    payload = json.dumps({"code": code, "market": market, "trade_date": trade_date,
                          "ohlcv": ohlcv, "model_dir": _HMM_MODEL_DIR})
    worker_script = _make_worker_script()
    stdin_data = json.dumps({"stock_quan_root": _STOCK_QUAN_ROOT}) + "\n" + payload
    try:
        r = subprocess.run(
            [_QLIB_PYTHON, "-c", worker_script],
            input=stdin_data, text=True, capture_output=True, timeout=120,
        )
        for line in reversed(r.stdout.strip().split("\n")):
            if line.strip().startswith("{"):
                data = json.loads(line.strip())
                if "error" in data:
                    return None
                return data
        logger.warning("hmm subprocess no JSON for %s: %s", code, r.stderr[:300])
    except Exception as e:
        logger.error("hmm subprocess failed %s: %s", code, e)
    return None


def _compute_ondemand(code: str, market: str, trade_date: str) -> Optional[dict]:
    """兜底：拉K线 → 算 HMM → 返回信号 dict（未写库，由调用方写库）。"""
    ohlcv = _fetch_kline_ohlcv(code, market)
    if not ohlcv:
        return None
    if _HMM_INLINE_OK:
        out = _compute_inline(code, market, ohlcv, trade_date)
    else:
        out = _compute_subprocess(code, market, ohlcv, trade_date)
    return out


# ── DB 辅助 ───────────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table() -> None:
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS watchlist_hmm_signal (
                stock_code   TEXT NOT NULL,
                trade_date   TEXT NOT NULL,
                market       TEXT DEFAULT 'A',
                n_states     INTEGER,
                state_now    INTEGER,
                regime       TEXT,
                prob_bull    REAL,
                prob_neutral REAL,
                prob_bear    REAL,
                signal       TEXT,
                confidence   INTEGER,
                buy_price    REAL,
                target_price REAL,
                stop_price   REAL,
                model_json   TEXT,
                reason       TEXT,
                ticker_name  TEXT DEFAULT '',
                created_at   TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (stock_code, trade_date)
            );
            CREATE INDEX IF NOT EXISTS idx_hmm_date ON watchlist_hmm_signal(trade_date);
            CREATE INDEX IF NOT EXISTS idx_hmm_code ON watchlist_hmm_signal(stock_code);
        """)


def _lookup_watchlist(code: str) -> Optional[dict]:
    with _get_conn() as conn:
        row = conn.execute(
            """SELECT stock_code, market,
                      COALESCE(NULLIF(stock_name,''),'') AS stock_name
               FROM watchlist
               WHERE stock_code=? AND item_type='stock' AND hidden=0
               GROUP BY stock_code ORDER BY market LIMIT 1""",
            (code,),
        ).fetchone()
    return dict(row) if row else None


def _signal_to_row(sig: dict, market: str, ticker_name: str = "") -> dict:
    return {
        "stock_code": sig.get("stock_code", ""),
        "trade_date": sig.get("trade_date", ""),
        "market": sig.get("market", market),
        "n_states": sig.get("n_states"),
        "state_now": sig.get("state_now"),
        "regime": sig.get("regime", "range"),
        "prob_bull": sig.get("prob_bull"),
        "prob_neutral": sig.get("prob_neutral"),
        "prob_bear": sig.get("prob_bear"),
        "signal": sig.get("signal", "hold"),
        "confidence": sig.get("confidence"),
        "buy_price": sig.get("buy_price"),
        "target_price": sig.get("target_price"),
        "stop_price": sig.get("stop_price"),
        "model_json": sig.get("model_json"),
        "reason": sig.get("reason", ""),
        "ticker_name": sig.get("ticker_name") or ticker_name,
    }


def _upsert(row: dict) -> None:
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO watchlist_hmm_signal
                 (stock_code, trade_date, market, n_states, state_now, regime,
                  prob_bull, prob_neutral, prob_bear, signal, confidence,
                  buy_price, target_price, stop_price, model_json, reason, ticker_name)
               VALUES (:stock_code, :trade_date, :market, :n_states, :state_now, :regime,
                  :prob_bull, :prob_neutral, :prob_bear, :signal, :confidence,
                  :buy_price, :target_price, :stop_price, :model_json, :reason, :ticker_name)
               ON CONFLICT(stock_code, trade_date) DO UPDATE SET
                  market=excluded.market, n_states=excluded.n_states,
                  state_now=excluded.state_now, regime=excluded.regime,
                  prob_bull=excluded.prob_bull, prob_neutral=excluded.prob_neutral,
                  prob_bear=excluded.prob_bear, signal=excluded.signal,
                  confidence=excluded.confidence, buy_price=excluded.buy_price,
                  target_price=excluded.target_price, stop_price=excluded.stop_price,
                  model_json=excluded.model_json, reason=excluded.reason,
                  ticker_name=excluded.ticker_name, created_at=datetime('now')""",
            row,
        )
        conn.commit()


hmm_time_formatters = {}

# ── API 端点 ──────────────────────────────────────────────────────────────────


@router.get("/hmm/watchlist")
async def get_hmm_watchlist(current_user: User = Depends(get_current_user)):
    """返回全部自选股最新 HMM 信号（卡片徽章用，不触发计算）。"""
    _ensure_table()
    import datetime as _dt
    today = _dt.date.today().strftime("%Y-%m-%d")
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT h.stock_code, h.trade_date, h.market, h.regime, h.signal,
                   h.confidence, h.prob_bull, h.prob_neutral, h.prob_bear,
                   h.buy_price, h.target_price, h.stop_price, h.reason,
                   COALESCE(h.ticker_name,'') AS ticker_name
            FROM watchlist_hmm_signal h
            INNER JOIN (
                SELECT MAX(trade_date) AS d FROM watchlist_hmm_signal
            ) m ON h.trade_date = m.d
            ORDER BY h.signal DESC, h.confidence DESC
        """).fetchall()
        latest_date = rows[0]["trade_date"] if rows else None
        is_fresh = bool(latest_date) and latest_date >= today

    return {
        "latest_trade_date": latest_date,
        "fresh": is_fresh,
        "signals": [dict(r) for r in rows],
    }


@router.get("/hmm/signal/{code}")
async def get_hmm_signal(
    code: str,
    current_user: User = Depends(get_current_user),
    force: bool = Query(False),
):
    """单股 HMM 信号。DB 有则读；缺失/过期则在 per-stock 锁内按需兜底计算。"""
    _ensure_table()
    code = code.strip().upper()
    import datetime as _dt

    wl = _lookup_watchlist(code)
    market = (wl or {}).get("market") or ("A" if code.isdigit() else "US")

    today = _dt.date.today().strftime("%Y-%m-%d")
    with _get_conn() as conn:
        row = conn.execute(
            """SELECT * FROM watchlist_hmm_signal
               WHERE stock_code=? ORDER BY trade_date DESC LIMIT 1""",
            (code,),
        ).fetchone()

    usable = None
    if row and not force:
        usable = dict(row)
    if usable is None and row and today > row["trade_date"]:
        # 当日已收盘且无当日信号 → 触发当日兜底计算
        usable = None

    if usable is not None:
        data = json.loads(usable["model_json"]) if usable.get("model_json") else {}
        return {
            "stock_code": code,
            "trade_date": usable["trade_date"],
            **{k: usable[k] for k in (
                "market", "n_states", "state_now", "regime", "prob_bull",
                "prob_neutral", "prob_bear", "signal", "confidence",
                "buy_price", "target_price", "stop_price", "reason", "ticker_name")},
            "model": data.get("per_model") or {},
            "from_db": True,
        }

    # ── 按需兜底（互斥） ──────────────────────────────────────────────────
    lock = await _lock_for(code)
    async with lock:
        # 双检查：等锁期间可能已被其他请求计算完成
        with _get_conn() as conn:
            row2 = conn.execute(
                """SELECT * FROM watchlist_hmm_signal
                   WHERE stock_code=? ORDER BY trade_date DESC LIMIT 1""",
                (code,),
            ).fetchone()
        if row2 and not force:
            usable = dict(row2)

        if usable is None:
            logger.info("hmm on-demand compute: %s (%s)", code, market)
            try:
                out = await asyncio.to_thread(_compute_ondemand, code, market, today)
            except Exception as e:
                logger.exception("hmm on-demand error %s", e)
                out = None
            if not out:
                return {
                    "stock_code": code,
                    "signal": "hold",
                    "regime": "range",
                    "error": f"HMM 信号暂不可用（数据不足或模型未就绪），请运行训练流水线 {code}",
                    "from_db": False,
                }
            row_to_write = _signal_to_row(out, market, (wl or {}).get("stock_name", ""))
            _upsert(row_to_write)
            usable = row_to_write

    data = json.loads(usable["model_json"]) if usable.get("model_json") else {}
    return {
        "stock_code": code,
        "trade_date": usable["trade_date"],
        **{k: usable[k] for k in (
            "market", "n_states", "state_now", "regime", "prob_bull",
            "prob_neutral", "prob_bear", "signal", "confidence",
            "buy_price", "target_price", "stop_price", "reason", "ticker_name")},
        "model": data.get("per_model") or {},
        "from_db": bool(usable.get("model_json")),
    }


@router.get("/hmm/signal/{code}/history")
async def get_hmm_signal_history(
    code: str,
    days: int = Query(_HMM_HISTORY_DAYS, ge=1, le=120),
    current_user: User = Depends(get_current_user),
):
    """近 N 日 HMM 状态信号历史（状态转移图），附带收盘价供双轴叠加。"""
    _ensure_table()
    code = code.strip().upper()
    wl = _lookup_watchlist(code)
    market = (wl or {}).get("market") or ("A" if code.isdigit() else "US")
    with _get_conn() as conn:
        rows = conn.execute(
            """SELECT trade_date, regime, signal, confidence,
                      prob_bull, prob_neutral, prob_bear
               FROM watchlist_hmm_signal
               WHERE stock_code=?
               ORDER BY trade_date DESC LIMIT ?""",
            (code, days),
        ).fetchall()

    # 收盘价叠加（多源K线，缓存避免重复请求）
    close_map: dict[str, float] = {}
    try:
        ohlcv = await asyncio.to_thread(_fetch_kline_ohlcv, code, market)
        if ohlcv:
            close_map = {r["date"]: r["close"] for r in ohlcv}
    except Exception:
        pass

    # 对信号日期缺失收盘价的（如停牌/周末），前向填充最近一个可用收盘价
    sorted_dates = sorted(close_map.keys())
    last_close: float | None = None
    ffill: dict[str, float | None] = {}
    for d in sorted_dates:
        v = close_map[d]
        if v is not None:
            last_close = v
        ffill[d] = last_close

    history = []
    for r in reversed(rows):
        item = dict(r)
        item["close"] = ffill.get(item["trade_date"], last_close) if last_close is not None else close_map.get(item["trade_date"])
        history.append(item)
    return {
        "stock_code": code,
        "market": market,
        "history": history,
    }
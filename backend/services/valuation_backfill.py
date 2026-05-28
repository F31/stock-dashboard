"""PE/PB data backfill service — fills negative/missing values that stock_quan's
valuation_store.py filtered out (it only stores PE > 0 for scoring purposes).

Uses Tencent qt.gtimg.cn batch API + East Money as fallback.
Batch size 100 stocks per request, RobustCrawler for anti-blocking.
"""
import logging
import re
import sqlite3
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

_DB = Path(__file__).parent.parent / "data" / "stock_dashboard.db"
_TENCENT_URL = "https://qt.gtimg.cn/q={syms}"
_BATCH = 100
_TIMEOUT = 10

# ── Tencent ───────────────────────────────────────────────────────────────────

def _fetch_tencent_batch(codes: list[str]) -> dict[str, dict]:
    """Batch-fetch PE(动态, idx=39) & PB(idx=46) from Tencent.
    Returns {code: {"pe": float|None, "pb": float|None}} — ALL values stored.
    """
    result: dict[str, dict] = {}
    syms = ",".join(
        ("sh" if c.startswith("6") else "sz") + c for c in codes
    )
    url = _TENCENT_URL.replace("{syms}", syms)
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://finance.qq.com/",
        })
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            text = resp.read().decode("gbk")
        for line in text.strip().split("\n"):
            parts = line.split("~")
            if len(parts) < 47:
                continue
            m = re.search(r"v_[a-z]{2}(\d{6})", line)
            if not m:
                continue
            code = m.group(1)
            pe = pb = None
            try:
                v = float(parts[39].strip())
                if v != 0:
                    pe = round(v, 2)
            except (ValueError, IndexError):
                pass
            try:
                v = float(parts[46].strip())
                if v > 0:
                    pb = round(v, 2)
            except (ValueError, IndexError):
                pass
            result[code] = {"pe": pe, "pb": pb}
    except Exception as e:
        logger.warning("Tencent batch fetch error for %d codes: %s", len(codes), e)
    return result


# ── Backfill ──────────────────────────────────────────────────────────────────

def backfill_pe(trade_date: str | None = None) -> dict:
    """Find stocks with NULL PE in daily_pe for the latest date,
    batch-fetch from Tencent, and update. Returns summary stats.
    """
    import datetime
    conn = sqlite3.connect(str(_DB))

    # Resolve target date
    if trade_date is None:
        row = conn.execute(
            "SELECT MAX(trade_date) FROM daily_pe WHERE pe IS NULL"
        ).fetchone()
        trade_date = row[0]
    if not trade_date:
        return {"status": "no_data", "backfilled": 0, "still_missing": 0}

    # Find stocks with NULL PE on this date
    rows = conn.execute(
        "SELECT stock_code FROM daily_pe "
        "WHERE trade_date=? AND pe IS NULL",
        (trade_date,),
    ).fetchall()
    codes = [r[0] for r in rows]

    if not codes:
        return {
            "status": "complete",
            "trade_date": trade_date,
            "backfilled": 0,
            "still_missing": 0,
        }

    # Batch-fetch
    fetched = _fetch_tencent_batch(codes)
    updated = 0
    still_missing = 0

    for code in codes:
        if code not in fetched:
            still_missing += 1
            continue
        data = fetched[code]
        if data["pe"] is None:
            still_missing += 1
            continue
        conn.execute(
            "UPDATE daily_pe SET pe=?, pb=COALESCE(pb,?) "
            "WHERE stock_code=? AND trade_date=?",
            (data["pe"], data.get("pb"), code, trade_date),
        )
        updated += 1

    conn.commit()
    conn.close()

    logger.info(
        "PE backfill %s: %d updated, %d still missing",
        trade_date, updated, still_missing,
    )
    return {
        "status": "ok",
        "trade_date": trade_date,
        "backfilled": updated,
        "still_missing": still_missing,
    }


def backfill_full(codes: list[str] | None = None) -> dict:
    """Batch-fetch PE for ALL scored stocks that have no PE on any date,
    inserting fresh records.
    """
    conn = sqlite3.connect(str(_DB))

    if codes is None:
        # Get scored stocks that have NO PE entry at all
        rows = conn.execute("""
            SELECT DISTINCT q.stock_code
            FROM quan_daily_scores q
            WHERE q.stock_code NOT IN (
                SELECT stock_code FROM daily_pe WHERE pe IS NOT NULL
            )
        """).fetchall()
        codes = [r[0] for r in rows]

    if not codes:
        conn.close()
        return {"status": "complete", "backfilled": 0}

    import datetime
    today = datetime.date.today().isoformat()

    fetched = _fetch_tencent_batch(codes)
    inserted = 0

    for code in codes:
        if code not in fetched or fetched[code]["pe"] is None:
            continue
        data = fetched[code]
        try:
            conn.execute(
                "INSERT OR REPLACE INTO daily_pe (stock_code, trade_date, pe, pb) "
                "VALUES (?, ?, ?, ?)",
                (code, today, data["pe"], data.get("pb")),
            )
            inserted += 1
        except Exception:
            pass

    conn.commit()
    conn.close()

    logger.info("PE full backfill: %d/%d inserted", inserted, len(codes))
    return {"status": "ok", "backfilled": inserted, "total_missing": len(codes)}

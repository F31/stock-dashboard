"""
A-share trading calendar service.

Dynamically fetches the official trading calendar from Sina Finance
(via AKShare), which mirrors the SSE/SZSE official holiday schedule.

Cache: refreshed once per day (all trading dates for all years are cached).
Fallback: if AKShare fails, returns empty set — frontend falls back to
weekend-only check.
"""

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

_cache: list[str] | None = None       # cached list of 'MM-DD' holiday strings
_cache_date: date | None = None       # which day we last fetched


async def get_trade_calendar() -> dict:
    """Return the full trading calendar.

    Returns:
        {
            "trade_dates": ["2026-01-02", "2026-01-05", ...],  # all trading days
            "holiday_dates": ["2026-01-01", ...],               # identified holidays
            "update_time": "2026-05-28T10:30:00",
            "source": "akshare/sina"
        }
    """
    import akshare as ak
    import pandas as pd

    try:
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(None, ak.tool_trade_date_hist_sina)
        # df has a single 'trade_date' column of datetime.date objects
        all_dates: list[date] = df["trade_date"].dropna().tolist()
        date_strs = [d.isoformat() for d in all_dates]

        # Identify holidays: weekdays that are NOT trading days
        # (weekends are already excluded; this catches 春节/国庆/清明 etc.)
        trade_set = set(all_dates)
        holidays: list[str] = []
        today = date.today()
        start = date(today.year, 1, 1)
        end = date(today.year + 1, 1, 1)  # through end of current year
        d = start
        while d < end:
            if d.weekday() < 5 and d not in trade_set:
                holidays.append(d.isoformat())
            d += timedelta(days=1)

        result = {
            "trade_dates": date_strs,
            "holiday_dates": holidays,
            "update_time": datetime.now().isoformat(timespec="seconds"),
            "source": "akshare/sina",
        }
        return result
    except Exception as e:
        logger.warning("Failed to fetch trade calendar: %s", e)
        return {
            "trade_dates": [],
            "holiday_dates": [],
            "update_time": datetime.now().isoformat(timespec="seconds"),
            "source": "fallback",
            "error": str(e),
        }

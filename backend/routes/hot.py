"""Hot stocks endpoints — Xueqiu & EastMoney."""
import logging
from fastapi import APIRouter, Depends, Query
from routes.auth import get_current_user
from services.hot_service import (
    fetch_xueqiu_hot, fetch_em_hot,
    _fresh, _stale, _failures, _last_fail,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _clear_backoff(key: str) -> None:
    """Clear in-process back-off state for a cache key so the next call retries immediately."""
    _failures.pop(key, None)
    _last_fail.pop(key, None)
    _fresh.pop(key, None)


@router.get("/hot/xueqiu")
async def get_xueqiu_hot(
    type: int = Query(10, description="10=近1小时  11=近24小时  12=近5天"),
    force: bool = Query(False, description="强制清除退避状态并重新获取"),
    user=Depends(get_current_user),
):
    if force:
        _clear_backoff(f"xq:{type}")
    result = await fetch_xueqiu_hot(type)
    return {
        "data":   result["items"],
        "stale":  result["stale"],
        "source": "xueqiu",
        "type":   type,
    }


@router.get("/hot/eastmoney")
async def get_em_hot(
    force: bool = Query(False, description="强制清除退避状态并重新获取"),
    user=Depends(get_current_user),
):
    if force:
        _clear_backoff("em:hot")
    result = await fetch_em_hot()
    return {
        "data":   result["items"],
        "stale":  result["stale"],
        "source": "eastmoney",
    }

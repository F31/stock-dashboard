"""Macro economic data endpoints."""
import logging
from fastapi import APIRouter, Depends
from routes.auth import get_current_user
from models import User
from services.macro_service import get_macro_data, fetch_industrial_profit, _cache as macro_cache

logger = logging.getLogger(__name__)

router = APIRouter(tags=["macro"])


@router.get("/macro")
async def get_macro(current_user: User = Depends(get_current_user)):
    """Fetch all macro economic indicators (US/CN yields, CPI, PPI, PMI)."""
    return await get_macro_data()


@router.get("/macro/profit")
async def get_profit(current_user: User = Depends(get_current_user)):
    """Fetch last 3 monthly cumulative industrial enterprise profit releases from NBS."""
    return await fetch_industrial_profit()


@router.post("/macro/refresh")
async def refresh_macro(current_user: User = Depends(get_current_user)):
    """Force-clear macro cache (yields + CPI/PPI/PMI + profit) and re-fetch."""
    macro_cache.clear()
    logger.info(f"Macro cache cleared by {current_user.username}")
    return await get_macro_data()

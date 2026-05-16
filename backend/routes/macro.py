"""Macro economic data endpoints."""
import logging
from fastapi import APIRouter, Depends
from routes.auth import get_current_user
from models import User
from services.macro_service import get_macro_data, _cache as macro_cache

logger = logging.getLogger(__name__)

router = APIRouter(tags=["macro"])


@router.get("/macro")
async def get_macro(current_user: User = Depends(get_current_user)):
    """Fetch all macro economic indicators (US/CN yields, CPI, PPI, PMI)."""
    return await get_macro_data()


@router.post("/macro/refresh")
async def refresh_macro(current_user: User = Depends(get_current_user)):
    """Force-clear macro cache and re-fetch all indicators."""
    macro_cache.clear()
    logger.info(f"Macro cache cleared by {current_user.username}")
    return await get_macro_data()

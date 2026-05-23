"""Macro economic data endpoints."""
import logging
from fastapi import APIRouter, Depends
from routes.auth import get_current_user
from models import User
from services.macro_service import (
    get_macro_data, fetch_industrial_profit,
    fetch_nbs_industrial_charts, fetch_industrial_profit_history,
    clear_macro_cache,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["macro"])


@router.get("/macro")
async def get_macro(current_user: User = Depends(get_current_user)):
    return await get_macro_data()


@router.get("/macro/profit")
async def get_profit(current_user: User = Depends(get_current_user)):
    return await fetch_industrial_profit()


@router.get("/macro/industrial-charts")
async def get_industrial_charts(current_user: User = Depends(get_current_user)):
    return await fetch_nbs_industrial_charts()


@router.get("/macro/profit-history")
async def get_profit_history(current_user: User = Depends(get_current_user)):
    return await fetch_industrial_profit_history()


@router.post("/macro/refresh")
async def refresh_macro(current_user: User = Depends(get_current_user)):
    """Force-clear all macro caches and re-fetch."""
    clear_macro_cache()
    logger.info(f"All macro caches cleared by {current_user.username}")
    return await get_macro_data()


@router.post("/macro/profit/refresh")
async def refresh_profit(current_user: User = Depends(get_current_user)):
    clear_macro_cache(["macro:industrial_profit"])
    logger.info(f"Profit cache cleared by {current_user.username}")
    return await fetch_industrial_profit()


@router.post("/macro/industrial-charts/refresh")
async def refresh_industrial_charts(current_user: User = Depends(get_current_user)):
    clear_macro_cache(["macro:nbs_industrial_charts"])
    logger.info(f"Industrial charts cache cleared by {current_user.username}")
    return await fetch_nbs_industrial_charts()


@router.post("/macro/profit-history/refresh")
async def refresh_profit_history(current_user: User = Depends(get_current_user)):
    clear_macro_cache(["macro:industrial_profit_history"])
    logger.info(f"Profit history cache cleared by {current_user.username}")
    return await fetch_industrial_profit_history()

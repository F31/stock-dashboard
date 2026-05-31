"""Hot stocks endpoints — Xueqiu & EastMoney."""
import logging
from fastapi import APIRouter, Depends, Query
from routes.auth import get_current_user
from services.hot_service import fetch_xueqiu_hot, fetch_em_hot

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/hot/xueqiu")
async def get_xueqiu_hot(
    type: int = Query(10, description="10=近1小时  11=近24小时  12=近5天"),
    user=Depends(get_current_user),
):
    data = await fetch_xueqiu_hot(type)
    return {"data": data, "source": "xueqiu", "type": type}


@router.get("/hot/eastmoney")
async def get_em_hot(user=Depends(get_current_user)):
    data = await fetch_em_hot()
    return {"data": data, "source": "eastmoney"}

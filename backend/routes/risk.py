"""风险预警 API 路由"""
import logging
from fastapi import APIRouter, Depends
from routes.auth import get_current_user
from models import User
from services.risk_service import (
    fetch_sentiment, fetch_north_fund, fetch_margin,
    fetch_block_trades, fetch_lhb, fetch_macro_risk,
    fetch_restricted, fetch_restricted_history,
)
from services.risk_radar_service import fetch_risk_radar

logger = logging.getLogger(__name__)
router = APIRouter(tags=["risk"])


@router.get("/risk/sentiment")
async def risk_sentiment(current_user: User = Depends(get_current_user)):
    """涨停/跌停数量与市场情绪分"""
    try:
        return await fetch_sentiment()
    except Exception as e:
        logger.error("risk_sentiment error: %s", e)
        return {"zt_count": 0, "dt_count": 0, "zt_ratio": 50.0, "label": "数据异常", "level": "normal"}


@router.get("/risk/north-fund")
async def risk_north_fund(current_user: User = Depends(get_current_user)):
    """北向资金今日净流入"""
    try:
        return await fetch_north_fund()
    except Exception as e:
        logger.error("risk_north_fund error: %s", e)
        return {"total_net": 0, "signal": "数据异常", "level": "neutral", "boards": []}


@router.get("/risk/margin")
async def risk_margin(current_user: User = Depends(get_current_user)):
    """融资余额趋势（上交所 T+1）"""
    try:
        return await fetch_margin()
    except Exception as e:
        logger.error("risk_margin error: %s", e)
        return {"latest": 0, "chg": 0, "level": "neutral", "trend": []}


@router.get("/risk/block-trades")
async def risk_block_trades(current_user: User = Depends(get_current_user)):
    """大宗交易折价榜（T+1）"""
    try:
        return await fetch_block_trades()
    except Exception as e:
        logger.error("risk_block_trades error: %s", e)
        return {"items": []}


@router.get("/risk/lhb")
async def risk_lhb(current_user: User = Depends(get_current_user)):
    """龙虎榜异动（T+1）"""
    try:
        return await fetch_lhb()
    except Exception as e:
        logger.error("risk_lhb error: %s", e)
        return {"items": []}


@router.get("/risk/macro")
async def risk_macro(current_user: User = Depends(get_current_user)):
    """宏观风险：黄金 / 国债收益率 / 人民币汇率"""
    try:
        return await fetch_macro_risk()
    except Exception as e:
        logger.error("risk_macro error: %s", e)
        return {"gold": None, "bonds": None, "cny": None}



@router.get("/risk/restricted")
async def risk_restricted(current_user: User = Depends(get_current_user)):
    """近期限售股解禁压力（未来 21 天汇总 + 7 天明细）"""
    try:
        return await fetch_restricted()
    except Exception as e:
        logger.error("risk_restricted error: %s", e)
        return {"summary": [], "detail": [], "date": ""}


@router.get("/risk/restricted/history")
async def risk_restricted_history(current_user: User = Depends(get_current_user)):
    """历史解禁记录（近 31 天已解禁，含前后20日涨跌幅），独立接口按需加载"""
    try:
        return await fetch_restricted_history()
    except Exception as e:
        logger.error("risk_restricted_history error: %s", e)
        return {"history": [], "date": ""}


@router.get("/risk/radar")
async def risk_radar(current_user: User = Depends(get_current_user)):
    """6维度风险雷达图数据"""
    try:
        return await fetch_risk_radar()
    except Exception as e:
        logger.error("risk_radar error: %s", e)
        return {
            "scores": {
                "情绪温度": 50, "杠杆水位": 50, "宏观金融": 50,
                "技术超买": 50, "曲线斜率": 50, "期权波动率": 50,
            },
            "composite": 50,
            "risk_level": "normal",
            "risk_label": "中性",
            "detail": {},
            "date": "",
        }

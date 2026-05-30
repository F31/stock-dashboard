"""盘前分析主路由：手动触发、查询历史、获取最新报告。"""
import io
import json
import logging
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import PremarketReport, User
from routes.auth import get_current_user
from schemas import PremarketReportResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/premarket", tags=["premarket"])


def _to_resp(r: PremarketReport) -> PremarketReportResponse:
    return PremarketReportResponse(
        id=r.id, report_date=r.report_date, report_time=r.report_time or "",
        report_path=r.report_path or "", analysis_json=r.analysis_json or "",
        status=r.status, error_msg=r.error_msg or "",
        created_at=r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
    )


@router.post("/run")
def trigger_run(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """手动触发一次盘前分析（后台异步执行），立即返回记录 ID 供前端轮询。"""
    from datetime import datetime as _dt
    record = PremarketReport(
        report_date=_dt.now().strftime("%Y-%m-%d"),
        report_time=_dt.now().strftime("%H:%M:%S"),
        status="running",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    background_tasks.add_task(_run_in_bg, record.id)
    return {"msg": "盘前分析已在后台启动，请稍后刷新查看结果", "id": record.id}


def _run_in_bg(record_id: int):
    from database import SessionLocal
    from premarket.pipeline import run_pipeline
    db = SessionLocal()
    try:
        run_pipeline(db, record_id=record_id)
    finally:
        db.close()


@router.get("/latest")
def get_latest(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """获取最新一条 completed 报告（failed 记录会自动清理，不对外展示）。"""
    r = (
        db.query(PremarketReport)
        .filter(PremarketReport.status == "completed")
        .order_by(PremarketReport.id.desc())
        .first()
    )
    if not r:
        return {"exists": False}
    analysis = {}
    try:
        analysis = json.loads(r.analysis_json) if r.analysis_json else {}
    except Exception:
        pass
    return {
        "exists": True,
        "report": _to_resp(r),
        "analysis": analysis,
        "report_url": f"/reports/{r.report_path}" if r.report_path else None,
    }


@router.get("/reports")
def list_reports(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(PremarketReport).order_by(PremarketReport.id.desc())
    total = q.count()
    rows = q.offset(offset).limit(limit).all()
    return {"total": total, "items": [_to_resp(r) for r in rows]}


@router.get("/stream-text/{record_id}")
def get_stream_text(
    record_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """返回指定记录 ID 的 LLM 流式输出快照（text + done）。"""
    from premarket.analyzer import get_stream_snapshot
    snapshot = get_stream_snapshot(record_id)
    # 内存缓冲区在服务重启后丢失；若报告已完成，强制返回 done=True 避免前端无限轮询
    if not snapshot["done"]:
        r = db.query(PremarketReport).filter(PremarketReport.id == record_id).first()
        if r and r.status in ("completed", "failed"):
            snapshot = {"text": snapshot["text"], "done": True}
    return {"text": snapshot["text"], "done": snapshot["done"]}


class _TTSReq(BaseModel):
    text: str
    voice: str = "zh-CN-XiaoxiaoNeural"
    rate: str = "-5%"


@router.post("/tts")
async def text_to_speech(req: _TTSReq, _: User = Depends(get_current_user)):
    """使用 Microsoft Edge TTS 合成高质量中文语音，返回 MP3 音频流。"""
    try:
        import edge_tts
    except ImportError:
        raise HTTPException(500, "edge-tts 未安装，请运行 pip install edge-tts")

    text = req.text.strip()
    if not text:
        raise HTTPException(400, "text is required")
    if len(text) > 8000:
        text = text[:8000]

    last_err = None
    for attempt in range(3):
        try:
            communicate = edge_tts.Communicate(text, voice=req.voice, rate=req.rate)
            buf = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    buf.extend(chunk["data"])
            if not buf:
                raise RuntimeError("TTS 合成返回空音频")
            return Response(content=bytes(buf), media_type="audio/mpeg",
                            headers={"Cache-Control": "no-store"})
        except Exception as e:
            last_err = e
            import traceback
            logger.warning("TTS attempt %d failed: %s\n%s", attempt + 1, e, traceback.format_exc())
            if attempt < 2:
                import asyncio
                await asyncio.sleep(0.5 * (attempt + 1))
    logger.error("TTS all 3 attempts failed, last: %s", last_err)
    raise HTTPException(500, f"语音合成失败（已重试3次）：{type(last_err).__name__}: {last_err}")


@router.get("/reports/{report_id}")
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    r = db.query(PremarketReport).filter(PremarketReport.id == report_id).first()
    if not r:
        raise HTTPException(404, "Not found")
    analysis = {}
    try:
        analysis = json.loads(r.analysis_json) if r.analysis_json else {}
    except Exception:
        pass
    return {
        "report": _to_resp(r),
        "analysis": analysis,
        "report_url": f"/reports/{r.report_path}" if r.report_path else None,
    }

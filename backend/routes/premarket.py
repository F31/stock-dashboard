"""盘前分析主路由：手动触发、查询历史、获取最新报告。"""
import json
import logging
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
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


@router.get("/reports", response_model=list[PremarketReportResponse])
def list_reports(
    limit: int = 30,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = (
        db.query(PremarketReport)
        .order_by(PremarketReport.id.desc())
        .limit(limit)
        .all()
    )
    return [_to_resp(r) for r in rows]


@router.get("/stream-text/{record_id}")
def get_stream_text(
    record_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """返回指定记录 ID 的 LLM 流式输出快照（text + done）。"""
    from premarket.analyzer import get_stream_snapshot
    snapshot = get_stream_snapshot(record_id)
    return {"text": snapshot["text"], "done": snapshot["done"]}


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

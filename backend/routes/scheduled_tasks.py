"""定时任务 CRUD 路由。"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import ScheduledTask, User
from routes.auth import get_current_user
from schemas import ScheduledTaskCreate, ScheduledTaskUpdate, ScheduledTaskResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/scheduled-tasks", tags=["scheduled-tasks"])


def _to_resp(t: ScheduledTask) -> ScheduledTaskResponse:
    def _fmt(dt):
        return dt.strftime("%Y-%m-%d %H:%M") if dt else None
    return ScheduledTaskResponse(
        id=t.id, name=t.name, task_type=t.task_type,
        schedule_time=t.schedule_time, enabled=bool(t.enabled),
        last_run=_fmt(t.last_run), next_run=_fmt(t.next_run),
        created_at=t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else "",
    )


@router.get("", response_model=list[ScheduledTaskResponse])
def list_tasks(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return [_to_resp(t) for t in db.query(ScheduledTask).order_by(ScheduledTask.id).all()]


@router.post("", response_model=ScheduledTaskResponse)
def create_task(req: ScheduledTaskCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    t = ScheduledTask(name=req.name, task_type=req.task_type,
                      schedule_time=req.schedule_time, enabled=1 if req.enabled else 0)
    db.add(t); db.commit(); db.refresh(t)
    _resync(db)
    return _to_resp(t)


@router.put("/{tid}", response_model=ScheduledTaskResponse)
def update_task(tid: int, req: ScheduledTaskUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    t = db.query(ScheduledTask).filter(ScheduledTask.id == tid).first()
    if not t:
        raise HTTPException(404, "Not found")
    if req.name is not None: t.name = req.name
    if req.schedule_time is not None: t.schedule_time = req.schedule_time
    if req.enabled is not None: t.enabled = 1 if req.enabled else 0
    db.commit(); db.refresh(t)
    _resync(db)
    return _to_resp(t)


@router.delete("/{tid}")
def delete_task(tid: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    t = db.query(ScheduledTask).filter(ScheduledTask.id == tid).first()
    if not t:
        raise HTTPException(404, "Not found")
    db.delete(t); db.commit()
    _resync(db)
    return {"msg": "deleted"}


def _resync(db):
    try:
        from premarket.scheduler import sync_jobs
        sync_jobs(db)
    except Exception as e:
        logger.warning(f"Scheduler resync failed: {e}")

"""APScheduler 集成：从数据库读取定时任务，动态注册 cron job。"""
import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _run_task(task_id: int, task_type: str):
    """实际执行任务的回调（在后台线程中运行）。"""
    from database import SessionLocal
    from models import ScheduledTask

    db = SessionLocal()
    try:
        if task_type == "premarket_analysis":
            from premarket.pipeline import run_pipeline
            logger.info(f"Scheduled task {task_id} running: {task_type}")
            result = run_pipeline(db)
            logger.info(f"Scheduled task {task_id} result: {result}")

        # 更新 last_run
        task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
        if task:
            task.last_run = datetime.utcnow()
            db.commit()
    except Exception as e:
        logger.error(f"Scheduled task {task_id} error: {e}", exc_info=True)
    finally:
        db.close()


def _job_id(task_id: int) -> str:
    return f"premarket_task_{task_id}"


def sync_jobs(db):
    """将数据库中的定时任务同步到调度器（增/删/改）。"""
    global _scheduler
    if _scheduler is None:
        return

    from models import ScheduledTask

    tasks = db.query(ScheduledTask).all()
    active_job_ids = {_job_id(t.id) for t in tasks if t.enabled}

    # 移除已禁用或被删除的 jobs
    for job in _scheduler.get_jobs():
        if job.id.startswith("premarket_task_") and job.id not in active_job_ids:
            _scheduler.remove_job(job.id)
            logger.info(f"Removed job: {job.id}")

    # 添加/更新 job
    for task in tasks:
        if not task.enabled:
            continue
        jid = _job_id(task.id)
        try:
            hour, minute = task.schedule_time.split(":")
            trigger = CronTrigger(hour=int(hour), minute=int(minute))
            if _scheduler.get_job(jid):
                _scheduler.reschedule_job(jid, trigger=trigger)
            else:
                _scheduler.add_job(
                    _run_task,
                    trigger=trigger,
                    id=jid,
                    args=[task.id, task.task_type],
                    replace_existing=True,
                    misfire_grace_time=3600,
                )
            logger.info(f"Synced job {jid} at {task.schedule_time}")
        except Exception as e:
            logger.error(f"Failed to sync job {jid}: {e}")


def start(db):
    """启动调度器并同步任务。"""
    global _scheduler
    if _scheduler and _scheduler.running:
        return

    _scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    _scheduler.start()
    logger.info("APScheduler started")
    sync_jobs(db)


def stop():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped")


def get_scheduler() -> BackgroundScheduler | None:
    return _scheduler

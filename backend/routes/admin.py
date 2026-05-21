"""Admin routes: user management, operation logs, system settings."""
import logging
import bcrypt
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from database import get_db
from models import User, OperationLog, SystemSetting
from schemas import (
    UserResponse, UserCreate, UserUpdate,
    PaginatedUsers, LogEntry, PaginatedLogs,
    SystemSettingResponse, SystemSettingUpdate,
)
from routes.auth import get_current_user
from utils import get_client_ip, get_ip_location  # noqa: re-exported for stocks.py

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Helpers ──

def _user_resp(u: User) -> UserResponse:
    return UserResponse(
        id=u.id,
        username=u.username,
        role=u.role or "user",
        is_active=bool(getattr(u, "is_active", 1)),
        created_at=u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else "",
    )


def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if (current_user.role or "user") != "admin":
        raise HTTPException(403, "需要管理员权限")
    return current_user


def log_action(
    db: Session,
    user_id: int,
    username: str,
    action: str,
    target: str = "",
    detail: str = "",
    ip_address: str = "",
):
    entry = OperationLog(
        user_id=user_id,
        username=username,
        action=action,
        target=target,
        detail=detail,
        ip_address=ip_address,
        ip_location=get_ip_location(ip_address),
    )
    db.add(entry)
    db.commit()


# ── User Management (admin only) ──

@router.get("/users", response_model=PaginatedUsers)
def list_users(
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    query = db.query(User)
    total = query.count()
    users = query.order_by(User.id).offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedUsers(
        total=total,
        page=page,
        page_size=page_size,
        items=[_user_resp(u) for u in users],
    )


@router.post("/users", response_model=UserResponse)
def create_user(
    req: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    existing = db.query(User).filter(User.username == req.username).first()
    if existing:
        raise HTTPException(400, "用户名已存在")

    user = User(
        username=req.username,
        password_hash=bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode(),
        role=req.role or "user",
        is_active=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_action(db, current_user.id, current_user.username,
               "create_user", target=str(user.id),
               detail=f"username={req.username} role={req.role}",
               ip_address=get_client_ip(request))

    return _user_resp(user)


@router.put("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    req: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "用户不存在")

    if req.username is not None:
        dup = db.query(User).filter(User.username == req.username, User.id != user_id).first()
        if dup:
            raise HTTPException(400, "用户名已被占用")
        user.username = req.username

    if req.password is not None and req.password.strip():
        user.password_hash = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()

    if req.role is not None:
        if user_id == current_user.id and req.role != "admin":
            raise HTTPException(400, "不能降低自己的管理员权限")
        user.role = req.role

    if req.is_active is not None:
        if user_id == current_user.id and not req.is_active:
            raise HTTPException(400, "不能禁用自己的账号")
        user.is_active = 1 if req.is_active else 0

    db.commit()
    db.refresh(user)

    log_action(db, current_user.id, current_user.username,
               "update_user", target=str(user_id),
               detail=f"username={user.username}",
               ip_address=get_client_ip(request))

    return _user_resp(user)


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if user_id == current_user.id:
        raise HTTPException(400, "不能删除自己的账号")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "用户不存在")

    username = user.username
    db.delete(user)
    db.commit()

    log_action(db, current_user.id, current_user.username,
               "delete_user", target=str(user_id),
               detail=f"username={username}",
               ip_address=get_client_ip(request))

    return {"msg": f"用户 '{username}' 已删除"}


# ── System Settings (admin only) ──

@router.get("/settings/{key}", response_model=SystemSettingResponse)
def get_setting(
    key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    defaults = {"allow_registration": "1"}
    s = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    value = s.value if s else defaults.get(key, "")
    return SystemSettingResponse(key=key, value=value)


@router.put("/settings/{key}", response_model=SystemSettingResponse)
def update_setting(
    key: str,
    req: SystemSettingUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    allowed_keys = {"allow_registration"}
    if key not in allowed_keys:
        raise HTTPException(400, f"未知配置项: {key}")

    s = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if s:
        s.value = req.value
        s.updated_at = datetime.utcnow()
    else:
        db.add(SystemSetting(key=key, value=req.value))
    db.commit()

    log_action(db, current_user.id, current_user.username,
               "update_setting", target=key,
               detail=f"value={req.value}",
               ip_address=get_client_ip(request))

    return SystemSettingResponse(key=key, value=req.value)


# ── Operation Logs (admin only) ──

@router.get("/logs", response_model=PaginatedLogs)
def list_logs(
    page: int = 1,
    page_size: int = 20,
    action: str = "",
    username: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    query = db.query(OperationLog)

    if action:
        query = query.filter(OperationLog.action == action)
    if username:
        query = query.filter(OperationLog.username.ilike(f"%{username}%"))

    total = query.count()
    logs = (
        query.order_by(desc(OperationLog.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return PaginatedLogs(
        total=total,
        page=page,
        page_size=page_size,
        items=[LogEntry(
            id=log.id,
            user_id=log.user_id,
            username=log.username or "",
            action=log.action,
            target=log.target or "",
            detail=log.detail or "",
            ip_address=log.ip_address or "",
            ip_location=getattr(log, "ip_location", "") or "",
            created_at=log.created_at.strftime("%Y-%m-%d %H:%M:%S") if log.created_at else "",
        ) for log in logs],
    )
